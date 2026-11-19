"""Platform admission, protocol errors, local content and durable worker integration."""

from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.company_workspaces import resolve_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.engine import EngineContractError
from xti.domain.platform_engine import parse_platform_request
from xti.interfaces.entrypoint import main
from tests.test_news_integration import article, feed


class PlatformEngineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / 'platform'
        self.now = datetime.now(timezone.utc).isoformat()
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No real network')))
        self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No real network')))
        self.assertEqual(self.invoke('provision')[0], 0)
        self.context = resolve_company_workspace(self.root, 'example')
        self.storage = SQLiteAssetRepository(self.context.database)
        self.storage.add('example.com')
        self.profiles = SQLiteCollectionProfileRepository(self.context.database)
        self.profile = self.profiles.save('News', CollectionProfileDefinition('example.com',
            task_ids=(), news_sources=('cisa',)), recorded_at=self.now).profile

    @staticmethod
    def request(operation='profiles.list', parameters=None):
        return {'contract_version': 1, 'request_id': 'request:1', 'operation': operation,
                'parameters': {} if parameters is None else parameters}

    def invoke(self, action='request', *, request=None, raw=None, extra=()):
        stdout, stderr = StringIO(), StringIO()
        with patch('sys.stdin', StringIO(raw if raw is not None else json.dumps(request or self.request()))), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(['platform', action, '--root', str(self.root), '--company', 'example', *extra])
        self.assertEqual(stderr.getvalue(), '', stderr.getvalue())
        return code, json.loads(stdout.getvalue())

    def submit(self, key='collect:1'):
        return self.invoke(request=self.request('jobs.submit', {'idempotency_key': key,
            'profile_name': 'News', 'profile_revision': self.profile.revision,
            'expected_workspace_id': self.context.workspace_id}))

    def test_request_and_manifest_never_start_sources_or_workers(self):
        with patch('xti.adapters.rss_atom_news.RssAtomNewsSource.fetch', side_effect=AssertionError('Admission is local')), \
                patch('subprocess.Popen', side_effect=AssertionError('No spawned worker')):
            code, described = self.invoke(extra=('--describe',))
            self.assertEqual(code, 0)
            self.assertIn('jobs.submit', described['data']['operations'])
            self.assertTrue(described['data']['request_network_access'])
            self.assertEqual(described['data']['request_network_operations'],
                             ['reports.fetch', 'brand.discovery.run', 'brand.enrichment.run', 'brand.enrichment.refresh'])
            code, submitted = self.submit()
            self.assertEqual(code, 0, submitted)
            self.assertEqual(submitted['data']['status'], 'queued')
            self.assertNotIn('payload', submitted['data'])
            self.assertNotIn('definition', submitted['data'])
            self.assertEqual(self.submit()[1]['data'], submitted['data'])

    def test_one_worker_collects_and_repeated_admission_does_not_repeat_source(self):
        calls = []
        def fetched(source):
            calls.append(source)
            return feed((article(source),), source=source, at=datetime.now(timezone.utc).isoformat())
        _, accepted = self.submit()
        job_id = accepted['data']['job_id']
        with patch('xti.adapters.rss_atom_news.RssAtomNewsSource.fetch', side_effect=fetched):
            code, completed = self.invoke('worker', extra=('--job-id', job_id))
            self.assertEqual(code, 0, completed)
            self.assertEqual(completed['data']['status'], 'complete', completed)
            self.assertEqual(calls, ['cisa'])
            self.assertEqual(self.submit()[1]['data'], completed['data'])
            code, result = self.invoke(request=self.request('jobs.result', {'job_id': job_id}))
            self.assertEqual(code, 0, result)
            self.assertEqual(result['data']['result']['collection_status'], 'complete')
            self.assertEqual(result['data']['result']['steps'][0]['receipt']['kind'], 'news_run')
            self.invoke('worker', extra=('--job-id', job_id))
            self.assertEqual(calls, ['cisa'])

    def test_modified_profile_never_executes_queued_source(self):
        _, accepted = self.submit()
        self.profiles.save('News', CollectionProfileDefinition('example.com', task_ids=(),
            news_sources=('ncsc',)), recorded_at=datetime.now(timezone.utc).isoformat())
        with patch('xti.adapters.rss_atom_news.RssAtomNewsSource.fetch', side_effect=AssertionError('No changed profile')):
            code, response = self.invoke('worker', extra=('--job-id', accepted['data']['job_id']))
        self.assertNotEqual(code, 0)
        self.assertEqual(response['error']['code'], 'profile_changed')
        self.assertEqual(self.submit()[1]['data']['job_id'], accepted['data']['job_id'])

    def test_profile_pagination_and_maximum_limit(self):
        self.profiles.save('Second', CollectionProfileDefinition('example.com', task_ids=(),
            news_sources=('cisa',)), recorded_at=self.now)
        code, first = self.invoke(request=self.request('profiles.list', {'limit': 1}))
        self.assertEqual(code, 0)
        self.assertEqual(first['data']['next_offset'], 1)
        _, second = self.invoke(request=self.request('profiles.list', {'offset': 1, 'limit': 1}))
        self.assertFalse(second['data']['has_more'])
        self.assertNotEqual(first['data']['profiles'][0]['id'], second['data']['profiles'][0]['id'])
        self.assertEqual(self.invoke(request=self.request('profiles.list', {'limit': 500}))[0], 0)

    def test_malformed_requests_and_secrets_never_escape_in_errors(self):
        for raw in ('null', '[]', '{', '{"contract_version":NaN}', '"\\ud800"'):
            with self.subTest(raw=raw):
                code, response = self.invoke(raw=raw)
                self.assertNotEqual(code, 0)
                self.assertIsNone(response['data'])
        with patch('xti.interfaces.platform_engine.execute_platform_request',
                   side_effect=RuntimeError('SECRET /private/api-key')):
            code, response = self.invoke()
        self.assertNotEqual(code, 0)
        self.assertNotIn('SECRET', json.dumps(response))
        self.assertEqual(response['error']['code'], 'internal_error')

    def test_incomplete_queue_provision_does_not_silently_initialize(self):
        queue = self.context.data_dir / 'engine-jobs.sqlite3'
        queue.unlink()
        code, response = self.invoke(extra=('--describe',))
        self.assertNotEqual(code, 0)
        self.assertEqual(response['error']['code'], 'storage_error')
        self.assertFalse(queue.exists())

    def test_cli_argument_errors_do_not_echo_accidental_secret(self):
        code, response = self.invoke(extra=('--api-key', 'SECRET-should-never-echo'))
        self.assertEqual(code, 2)
        self.assertEqual(response['error']['code'], 'invalid_request')
        self.assertNotIn('SECRET', json.dumps(response))
        for prefix in (['--j'], ['--data-d', str(self.context.data_dir)],
                       ['--data-d=' + str(self.context.data_dir)], ['--unknown', 'SECRET']):
            stdout, stderr = StringIO(), StringIO()
            with self.subTest(prefix=prefix), redirect_stdout(stdout), redirect_stderr(stderr):
                code = main([*prefix, 'platform', 'request', '--root', str(self.root),
                             '--company', 'example', '--api-key', 'SECRET'])
            self.assertEqual(code, 2)
            self.assertNotIn('SECRET', stdout.getvalue() + stderr.getvalue())
            self.assertEqual(json.loads(stdout.getvalue())['error']['code'], 'invalid_request')

    def test_invalid_json_is_rejected_before_database_audit(self):
        with patch('xti.interfaces.platform_jobs.validate_jobs', side_effect=AssertionError('No audit')):
            code, response = self.invoke(raw='{}')
        self.assertEqual((code, response['error']['code']), (2, 'invalid_request'))

    def test_local_content_view_is_plain_and_does_not_claim_unchecked_is_empty(self):
        org = SQLiteOrganizationRepository(self.context.database).add(name_key='example', display_name='Example',
            reason='Content fixture', recorded_at=self.now).organization
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(['--data-dir', str(self.context.data_dir), 'organizations', 'content', org.id])
        self.assertEqual((code, stderr.getvalue()), (0, ''))
        self.assertIn('henüz içerik kontrolü yapılmadı', stdout.getvalue())
        self.assertNotIn('ilgili içerik bulunamadı', stdout.getvalue())
        self.assertNotIn('Toplam', stdout.getvalue())


class PlatformRequestValidationTests(unittest.TestCase):
    def test_strict_operation_parameters(self):
        requests = [
            PlatformEngineTests.request('jobs.submit', {'idempotency_key': 'x', 'profile_name': 'News', 'profile_revision': True}),
            PlatformEngineTests.request('organization.content', {'organization_id': str(uuid4()), 'scope_limit': 101}),
            PlatformEngineTests.request('profiles.list', {'offset': -1}),
            PlatformEngineTests.request('jobs.status', {'job_id': '../other'}),
            PlatformEngineTests.request('jobs.submit', {'idempotency_key': 'x', 'profile_name': 'News', 'profile_revision': 1, 'tenant_id': 'other'}),
        ]
        for request in requests:
            with self.subTest(request=request), self.assertRaises(EngineContractError):
                parse_platform_request(request)

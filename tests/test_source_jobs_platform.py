"""Actual CLI/JSON entry points, company fences, source failure and two-file recovery."""

from contextlib import closing, redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.company_workspaces import resolve_company_workspace
from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository, _EVENTS_DDL_V1
from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.engine import EngineContractError
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError
from tests.test_indicator_enrichment import HASH, hash_body


class SourceJobPlatformTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'platform'
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No real network')))
        self.assertEqual(self.invoke('provision')[0], 0)
        self.context = resolve_company_workspace(self.root, 'alpha')

    def invoke(self, action='request', *, operation='sources.plan', parameters=None, company='alpha', extra=(), root=None):
        request = {'contract_version': 1, 'request_id': 'source-acceptance', 'operation': operation,
                   'parameters': {} if parameters is None else parameters}
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', StringIO(json.dumps(request))):
            code = main(['platform', action, '--root', str(root or self.root), '--company', company, *extra])
        self.assertEqual(err.getvalue(), '')
        return code, json.loads(out.getvalue())

    def plan(self, **changes):
        return self.invoke(parameters={'indicator_type': 'sha256', 'value': HASH, 'sources': ['circl'], **changes})[1]['data']

    def submit(self, key='one', **changes):
        plan = self.plan(**changes)
        return self.invoke(operation='sources.jobs.submit', parameters={**plan['plan'], 'idempotency_key': key,
            'plan_sha256': plan['plan_sha256'], 'expected_workspace_id': self.context.workspace_id})

    def fetch(self, error=None):
        return patch('xti.adapters.enrichment_sources.PublicEnrichmentSource.fetch',
                     side_effect=error, return_value=(200, hash_body()))

    def test_admission_describe_and_reads_never_start_sources(self):
        with self.fetch(AssertionError('Admission must not fetch')):
            code, described = self.invoke(extra=('--describe',))
            self.assertEqual(code, 0)
            self.assertIn('sources.jobs.retry', described['data']['operations'])
            self.assertIn('sources.refresh', described['data']['additional_job_types'])
            code, accepted = self.submit(record_review=True)
            self.assertEqual(code, 0, accepted)
            job_id = accepted['data']['job_id']
            self.assertEqual(self.submit(record_review=True)[1]['data'], accepted['data'])
            for operation in ('sources.jobs.status', 'sources.jobs.result'):
                self.assertEqual(self.invoke(operation=operation, parameters={'job_id': job_id})[0], 0)
            self.assertEqual(self.invoke(operation='sources.jobs.list')[1]['data']['jobs'][0]['job_id'], job_id)

    def test_real_composition_runs_one_job_and_existing_read_contracts_show_same_evidence(self):
        _, submitted = self.submit(record_review=True)
        job_id = submitted['data']['job_id']
        with self.fetch() as fetch:
            code, completed = self.invoke('worker', extra=('--job-id', job_id))
            self.assertEqual(code, 0, completed)
            self.assertEqual(completed['data']['status'], 'complete', completed)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(self.invoke('worker', extra=('--job-id', job_id))[1]['data'], None)
            self.assertEqual(fetch.call_count, 1)
        result = self.invoke(operation='sources.jobs.result', parameters={'job_id': job_id})[1]['data']
        self.assertEqual(result['result']['status'], 'complete')
        receipt = result['result']['steps'][0]['receipt']
        code, evidence = self.invoke(operation='enrichment.run.get', parameters={'run_id': receipt['run_id']})
        self.assertEqual(code, 0, evidence)
        self.assertEqual(evidence['data']['run']['id'], receipt['run_id'])
        review_id = result['result']['steps'][1]['receipt']['review_id']
        code, evidence = self.invoke(operation='research.review.get', parameters={'review_id': review_id})
        self.assertEqual(code, 0, evidence)
        self.assertEqual(evidence['data']['review']['id'], review_id)

    def test_provider_failure_is_successful_protocol_with_failed_job_and_durable_error(self):
        _, submitted = self.submit(record_review=True)
        with self.fetch(SourceError('Controlled provider unavailable')):
            code, result = self.invoke('worker')
        self.assertEqual(code, 0, result)
        self.assertEqual(result['status'], 'complete')  # Protocol delivery, not collection success.
        self.assertEqual(result['data']['status'], 'failed')
        receipt = result['data']['steps'][0]['receipt']
        _, evidence = self.invoke(operation='enrichment.run.get', parameters={'run_id': receipt['run_id']})
        self.assertIn('unavailable', evidence['data']['run']['error'])
        _, retry = self.invoke(operation='sources.jobs.retry', parameters={'job_id': submitted['data']['job_id'],
            'idempotency_key': 'retry', 'expected_workspace_id': self.context.workspace_id})
        self.assertEqual(retry['data']['status'], 'queued')

    def test_cross_company_job_ids_and_foreign_workspace_are_rejected(self):
        _, submitted = self.submit()
        self.assertEqual(self.invoke('provision', company='beta')[0], 0)
        other = resolve_company_workspace(self.root, 'beta')
        job_id = submitted['data']['job_id']
        for operation in ('sources.jobs.status', 'sources.jobs.result', 'sources.jobs.cancel', 'sources.jobs.retry'):
            parameters = {'job_id': job_id}
            if operation.endswith(('.cancel', '.retry')):
                parameters['expected_workspace_id'] = other.workspace_id
            if operation.endswith('.retry'):
                parameters['idempotency_key'] = 'retry'
            code, response = self.invoke(operation=operation, parameters=parameters, company='beta')
            self.assertEqual(code, 3, response)
            self.assertEqual(response['error']['code'], 'not_found')
        plan = self.plan()
        code, response = self.invoke(operation='sources.jobs.submit', parameters={**plan['plan'],
            'idempotency_key': 'foreign', 'plan_sha256': plan['plan_sha256'], 'expected_workspace_id': other.workspace_id})
        self.assertEqual(response['error']['code'], 'scope_mismatch')
        self.assertNotEqual(code, 0)

    def test_fence_and_parameter_contract_rejects_arbitrary_paths_unknown_sources_and_wrong_types(self):
        for parameters in ({'indicator_type': 'sha256', 'value': HASH, 'sources': ['circl'], 'database': '/tmp/x'},
            {'indicator_type': 'sha256', 'value': HASH, 'sources': ['https://evil.example']},
            {'indicator_type': 'sha256', 'value': HASH, 'sources': ['circl'], 'record_review': 'yes'}):
            with self.subTest(parameters=parameters):
                code, result = self.invoke(parameters=parameters)
                self.assertEqual(code, 2)
                self.assertEqual(result['error']['code'], 'invalid_parameters')
        _, job = self.submit()
        code, result = self.invoke(operation='sources.jobs.cancel', parameters={'job_id': job['data']['job_id']})
        self.assertEqual(code, 2)
        self.assertEqual(result['error']['code'], 'invalid_parameters')
        for value in (True, -1, 101):
            self.assertEqual(self.invoke(operation='sources.jobs.list', parameters={'limit': value})[0], 2)

    def test_source_mutations_are_absent_from_readonly_engine(self):
        from xti.domain.engine import parse_engine_request
        for operation in ('sources.plan', 'sources.jobs.submit', 'sources.jobs.cancel', 'sources.jobs.retry'):
            with self.subTest(operation=operation), self.assertRaises(EngineContractError):
                parse_engine_request({'contract_version': 1, 'request_id': 'read-only', 'operation': operation, 'parameters': {}})

    def test_platform_backup_restores_source_receipts_and_fences_old_submissions(self):
        _, submitted = self.submit(record_review=True)
        with self.fetch():
            code, completed = self.invoke('worker')
        self.assertEqual(code, 0, completed)
        _, queued = self.submit('queued')
        output = self.base / 'backup'
        backup_platform_workspace(self.context, output)
        restored_root = self.base / 'restored'
        restored = restore_platform_workspace(restored_root, 'alpha', output)
        code, result = self.invoke(operation='sources.jobs.result', parameters={'job_id': submitted['data']['job_id']}, root=restored_root)
        self.assertEqual(code, 0, result)
        self.assertEqual(result['data']['job']['steps'], completed['data']['steps'])
        for step in completed['data']['steps']:
            operation, parameters = ('enrichment.run.get', {'run_id': step['receipt']['run_id']}) if step['key'] == 'circl' else (
                'research.review.get', {'review_id': step['receipt']['review_id']})
            self.assertEqual(self.invoke(operation=operation, parameters=parameters, root=restored_root)[0], 0)
        code, result = self.invoke(operation='sources.jobs.status', parameters={'job_id': queued['data']['job_id']}, root=restored_root)
        self.assertEqual(result['data']['status'], 'cancelled')
        self.assertEqual(result['data']['error_code'], 'restored_uncertain')
        plan = self.plan()
        code, result = self.invoke(operation='sources.jobs.submit', parameters={**plan['plan'],
            'idempotency_key': 'restored', 'plan_sha256': plan['plan_sha256'],
            'expected_workspace_id': self.context.workspace_id}, root=restored_root)
        self.assertEqual(result['error']['code'], 'scope_mismatch')
        self.assertNotEqual(restored.workspace_id, self.context.workspace_id)

    def test_core_lock_contention_records_interruption_without_network(self):
        _, submitted = self.submit()
        with LocalExecutionLock(self.context.database).acquire(), self.fetch(AssertionError('Must not send')):
            code, result = self.invoke('worker')
        self.assertEqual(result['error']['code'], 'busy')
        self.assertNotEqual(code, 0)
        result = self.invoke(operation='sources.jobs.status', parameters={'job_id': submitted['data']['job_id']})[1]['data']
        self.assertEqual(result['status'], 'interrupted')

    def test_platform_queued_cancel_and_retry_need_current_workspace(self):
        _, submitted = self.submit()
        job_id = submitted['data']['job_id']
        code, result = self.invoke(operation='sources.jobs.cancel', parameters={'job_id': job_id,
                                  'expected_workspace_id': str(uuid4())})
        self.assertEqual(result['error']['code'], 'scope_mismatch')
        parameters = {'job_id': job_id, 'expected_workspace_id': self.context.workspace_id}
        self.assertEqual(self.invoke(operation='sources.jobs.cancel', parameters=parameters)[1]['data']['status'], 'cancelled')
        self.assertEqual(self.invoke(operation='sources.jobs.retry', parameters={**parameters, 'idempotency_key': 'retry'})[1]['data']['status'], 'queued')

    def test_personal_cli_init_submit_worker_result_and_failure_exit(self):
        from xti.adapters.sqlite import SQLiteAssetRepository
        path = self.base / 'personal' / 'xti.db'
        SQLiteAssetRepository(path).initialize()
        def invoke(*args):
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(['--data-dir', str(path.parent), '--json', 'source-jobs', *args])
            return code, json.loads(out.getvalue() or err.getvalue())
        self.assertEqual(invoke('init')[0], 0)
        self.assertNotEqual(invoke('init')[0], 0)
        code, submitted = invoke('submit', HASH, '--type', 'sha256', '--source', 'circl', '--idempotency-key', 'one')
        self.assertEqual(code, 0, submitted)
        with self.fetch(SourceError('Controlled error')):
            code, done = invoke('worker')
        self.assertEqual(code, 3)
        self.assertFalse(done['ok'])
        self.assertEqual(done['data']['status'], 'failed')
        self.assertEqual(invoke('result', submitted['data']['job_id'])[0], 0)

    def test_platform_migration_command_preserves_old_read_surface(self):
        # Replace only this empty fixture queue with a genuinely v1 provisioned database.
        queue = SQLiteEngineJobRepository(self.context.data_dir / 'engine-jobs.sqlite3')
        queue.path.unlink()
        with patch('xti.adapters.sqlite_engine_jobs.ENGINE_JOB_SCHEMA_VERSION', 1), \
                patch('xti.adapters.sqlite_engine_jobs._EVENTS_DDL', _EVENTS_DDL_V1):
            queue.initialize()
        self.assertEqual(self.invoke(operation='profiles.list')[0], 0)
        code, response = self.submit()
        self.assertEqual(response['error']['code'], 'migration_required')
        code, response = self.invoke('jobs-migrate')
        self.assertEqual(code, 0, response)
        self.assertTrue(Path(response['data']['backup']).exists())
        self.assertEqual(self.submit()[0], 0)

    def test_v1_profile_history_rejects_source_only_event_kind_even_with_correct_hash(self):
        from tests.test_engine_jobs_storage import payload
        from xti.domain.engine_jobs import request_json, canonical_json, digest
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        queue = SQLiteEngineJobRepository(self.context.data_dir / 'engine-jobs.sqlite3')
        definition = payload()
        job = queue.create('legacy', request_json(definition.profile_name, definition.profile_revision), definition, recorded_at=now)
        claim = queue.claim(job.id, recorded_at=now)
        queue.finish(claim, status='interrupted', result=None, error_code='execution_uncertain', recorded_at=now)
        with closing(sqlite3.connect(queue.path)) as db:
            event = json.loads(db.execute('SELECT event_json FROM engine_job_events WHERE job_id=? AND ordinal=2', (job.id,)).fetchone()[0])
            event['kind'] = 'step_finished'
            text = canonical_json(event)
            db.execute('UPDATE engine_job_events SET kind=?,event_json=?,event_sha256=? WHERE job_id=? AND ordinal=2',
                       ('step_finished', text, digest(text), job.id))
            db.commit()
        code, response = self.invoke(operation='jobs.status', parameters={'job_id': job.id})
        self.assertEqual(response['error']['code'], 'storage_error')
        self.assertNotEqual(code, 0)

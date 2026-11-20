"""Actual CLI and company JSON social queue, isolation and two-file restore."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
import unittest
from unittest.mock import patch

from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository
from xti.application.social_discovery import SocialDiscoveryService
from xti.interfaces.entrypoint import main
from tests import test_source_jobs_platform as platform
from tests.test_social_discovery import Sources, Pages, SCOPE


class SocialJobPlatformTests(unittest.TestCase):
    def setUp(self):
        self.f = platform.SourceJobPlatformTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.sources, self.pages = Sources(), Pages()
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No live network')))
        self.enterContext(patch('xti.adapters.public_profile_pages.PublicProfilePageSource.fetch', side_effect=self.pages.fetch))
        self.enterContext(patch('xti.adapters.social_discovery_sources.SocialDiscoverySourceAdapter.collect', side_effect=self.sources.collect))
        self.enterContext(patch('xti.adapters.social_discovery_sources.SocialDiscoverySourceAdapter.search', side_effect=AssertionError('No paid search')))
        seed = SocialDiscoveryService(SQLiteSocialDiscoveryRepository(self.f.context.database),
            sources=self.sources, pages=self.pages).execute('brand.discovery.run', **SCOPE, idempotency_key='seed')['record']
        code, response = self.f.invoke(operation='brand.tracking.add', parameters={
            'discovery_id': seed['id'], 'name': 'Acme social', 'interval_seconds': 300,
            'idempotency_key': 'watch', 'expected_workspace_id': self.f.context.workspace_id})
        self.assertEqual(code, 0, response); self.watch = response['data']['record']
        self.options = dict(indicator_type='domain', value='acme.example', sources=['social-tracking'],
                            social_watch_id=self.watch['id'], social_watch_revision=1)

    def submit(self, **options):
        code, submitted = self.f.submit(**self.options, **options)
        self.assertEqual(code, 0, submitted)
        return submitted['data']

    def test_company_worker_uses_same_core_evidence_and_isolates_watch_and_result(self):
        calls = len(self.pages.calls)
        submitted = self.submit()
        self.assertEqual(len(self.pages.calls), calls)
        code, completed = self.f.invoke('worker', extra=('--job-id', submitted['job_id']))
        self.assertEqual(code, 0, completed)
        self.assertEqual(completed['data']['status'], 'partial')
        receipt = completed['data']['steps'][0]['receipt']
        code, shown = self.f.invoke(operation='brand.tracking.run.show', parameters={'identifier': receipt['run_id']})
        self.assertEqual(code, 0, shown)
        self.assertEqual(shown['data']['record']['watch_id'], self.watch['id'])
        self.assertEqual(self.f.invoke('provision', company='beta')[0], 0)
        for operation, values in [('sources.plan', self.options),
                                  ('sources.jobs.status', {'job_id': submitted['job_id']}),
                                  ('brand.tracking.run.show', {'identifier': receipt['run_id']})]:
            code, result = self.f.invoke(company='beta', operation=operation, parameters=values)
            self.assertNotEqual(code, 0, result); self.assertEqual(result['error']['code'], 'not_found')
        self.assertEqual(self.f.invoke('worker', extra=('--job-id', submitted['job_id']))[1]['data'], None)
        code, manifest = self.f.invoke(extra=('--describe',))
        self.assertEqual(manifest['data']['source_jobs']['execution_version'], 6)
        self.assertFalse(manifest['data']['source_jobs']['social_tracking']['paid_sources'])

    def test_backup_restore_preserves_social_context_result_and_fences_old_workspace(self):
        submitted = self.submit()
        code, completed = self.f.invoke('worker', extra=('--job-id', submitted['job_id']))
        self.assertEqual(code, 0, completed)
        output = self.f.base / 'social-backup'
        backup_platform_workspace(self.f.context, output)
        root = self.f.base / 'social-restore'
        restored = restore_platform_workspace(root, 'alpha', output)
        code, result = self.f.invoke(operation='sources.jobs.status', parameters={'job_id': submitted['job_id']}, root=root)
        self.assertEqual(code, 0, result); self.assertEqual(result['data'], completed['data'])
        plan = self.f.plan(**self.options)
        code, result = self.f.invoke(operation='sources.jobs.submit', root=root, parameters={**plan['plan'],
            'idempotency_key': 'after-restore', 'plan_sha256': plan['plan_sha256'],
            'expected_workspace_id': self.f.context.workspace_id})
        self.assertEqual(result['error']['code'], 'scope_mismatch')
        self.assertNotEqual(restored.workspace_id, self.f.context.workspace_id)

    def test_cli_plan_submit_worker_status_and_replay_use_existing_queue(self):
        def invoke(*args):
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(['--data-dir', str(self.f.context.data_dir), '--json', 'source-jobs', *args])
            data = json.loads(out.getvalue())['data']
            self.assertEqual((code, err.getvalue()), (3 if args[0] == 'worker' and data.get('status') == 'partial' else 0, ''), out.getvalue())
            return data
        options = ['acme.example', '--type', 'domain', '--source', 'social-tracking',
                   '--social-watch', self.watch['id'], '--social-revision', '1']
        plan = invoke('plan', *options)
        self.assertIsNone(plan['maximum_external_requests'])
        submitted = invoke('submit', *options, '--idempotency-key', 'terminal')
        done = invoke('worker', '--job-id', submitted['job_id'])
        self.assertEqual(done['status'], 'partial')
        self.assertEqual(invoke('status', submitted['job_id']), done)
        self.assertEqual(invoke('submit', *options, '--idempotency-key', 'terminal'), done)


if __name__ == '__main__': unittest.main()

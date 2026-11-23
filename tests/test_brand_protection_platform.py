from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import resolve_company_workspace
from xti.adapters.sqlite_brand_protection import SQLiteBrandProtectionRepository
from xti.application.brand_protection import BrandProtectionService
from xti.interfaces.cli import main
from tests.test_brand_protection import Sources


class BrandProtectionPlatformTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / 'platform'
        self.source = Sources()
        def make(database): return BrandProtectionService(SQLiteBrandProtectionRepository(database), self.source)
        self.enterContext(patch('xti.interfaces.brand_protection.make_brand_protection_service', side_effect=make))
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))
        self.assertEqual(self.invoke(action='provision')[0], 0)
        self.context = resolve_company_workspace(self.root, 'alpha')

    def invoke(self, operation='brand.protection.watches', values=None, *, company='alpha', action='request', extra=()):
        request = {'contract_version': 1, 'request_id': 'code-test', 'operation': operation, 'parameters': values or {}}
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', StringIO(json.dumps(request))):
            code = main(['platform', action, '--root', str(self.root), '--company', company, *extra])
        self.assertEqual(err.getvalue(), '')
        return code, json.loads(out.getvalue())

    def watch(self):
        code,response=self.invoke('brand.protection.identity.add',{'name':'Example Corp','domains':['example.com'],
            'idempotency_key':'identity','expected_workspace_id':self.context.workspace_id})
        self.assertEqual(code,0,response)
        code,response=self.invoke('brand.protection.watch.add',{'identity_id':response['data']['id'],
            'max_requests':30,'max_seconds':180,'idempotency_key':'watch','expected_workspace_id':self.context.workspace_id})
        self.assertEqual(code,0,response)
        return response['data']

    def test_scope_fence_unknown_company_and_missing_record_fail_without_network(self):
        watch = self.watch()
        code, response = self.invoke('brand.protection.run', {'identifier': watch['id'], 'expected_revision': 1,
            'idempotency_key': 'wrong', 'expected_workspace_id': '00000000-0000-0000-0000-000000000000'})
        self.assertNotEqual(code, 0); self.assertEqual(response['error']['code'], 'scope_mismatch')
        self.assertEqual(self.source.calls, 0)
        self.assertEqual(self.invoke(action='provision', company='beta')[0], 0)
        code, response = self.invoke('brand.protection.watch.show', {'identifier': watch['id']}, company='beta')
        self.assertEqual(response['error']['code'], 'not_found')
        self.assertNotEqual(self.invoke(company='unknown')[0], 0)

    def test_queue_worker_receipt_reopen_and_read_contract(self):
        watch = self.watch()
        options = {'indicator_type': 'domain', 'value': 'example.com', 'sources': ['brand-protection'],
                   'protection_watch_id': watch['id'], 'protection_watch_revision': 1, 'protection_identity_revision': 1, 'max_requests': 30}
        code, response = self.invoke('sources.plan', options)
        self.assertEqual(code, 0, response); self.assertEqual(self.source.calls, 0)
        plan = response['data']
        code, response = self.invoke('sources.jobs.submit', {**plan['plan'], 'plan_sha256': plan['plan_sha256'],
            'idempotency_key': 'job', 'expected_workspace_id': self.context.workspace_id})
        self.assertEqual(code, 0, response)
        job_id = response['data']['job_id']
        code, completed = self.invoke(action='worker', extra=('--job-id', job_id))
        self.assertEqual(code, 0, completed)
        self.assertEqual(completed['data']['status'], 'complete', completed)
        self.assertEqual(self.source.calls, 1)
        result = self.invoke('sources.jobs.result', {'job_id': job_id})[1]['data']['result']
        run_id = result['steps'][0]['receipt']['run_id']
        code, run = self.invoke('brand.protection.run.show', {'identifier': run_id})
        self.assertEqual(code, 0, run); self.assertEqual(run['data']['status'], 'complete')
        self.assertEqual(self.invoke('brand.protection.candidates')[1]['data']['items'][0]['evidence']['body']['brand']['domains'], ['example.com'])
        self.assertEqual(self.invoke(action='worker', extra=('--job-id', job_id))[1]['data'], None)
        self.assertEqual(self.source.calls, 1)

    def test_plan_requires_matching_domain_revision_and_budget(self):
        watch = self.watch()
        for changes in ({'value': 'other.example'}, {'protection_watch_revision': 2}, {'max_requests': 1}, {'max_seconds': 5}):
            code, result = self.invoke('sources.plan', {'indicator_type': 'domain', 'value': 'example.com', 'sources': ['brand-protection'],
                'protection_watch_id': watch['id'], 'protection_watch_revision': 1, 'protection_identity_revision': 1, 'max_requests': 30, **changes})
            self.assertNotEqual(code, 0, result)
        self.assertEqual(self.source.calls, 0)

    def test_core_commit_queue_crash_reuses_receipt_without_repeating_network(self):
        from xti.adapters.source_job_steps import ExistingSourceJobOperations
        from xti.interfaces.platform_jobs import make_job_service
        from xti.interfaces.source_jobs import make_source_job_service
        watch = self.watch()
        source_service = make_source_job_service(self.context)
        options = {'indicator_type': 'domain', 'value': 'example.com', 'sources': ['brand-protection'],
                   'protection_watch_id': watch['id'], 'protection_watch_revision': 1, 'protection_identity_revision': 1, 'max_requests': 30}
        plan = source_service.plan(**options)
        job = source_service.submit(**plan['plan'], plan_sha256=plan['plan_sha256'], idempotency_key='crash-job')
        original = ExistingSourceJobOperations.execute
        def crash(instance, *args, **kwargs):
            original(instance, *args, **kwargs)
            raise RuntimeError('Lost queue acknowledgement after durable core commit')
        with patch.object(ExistingSourceJobOperations, 'execute', crash), self.assertRaises(RuntimeError):
            make_job_service(self.context).work_one(job.id)
        self.assertEqual(self.source.calls, 1)
        self.assertEqual(source_service.status(job.id).status, 'interrupted')
        retry = source_service.retry(job.id, idempotency_key='explicit-retry', allow_uncertain=True)
        done = make_job_service(self.context).work_one(retry.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual(self.source.calls, 1)
        self.assertTrue(done.steps[0]['receipt']['reused_receipt'])
        self.assertEqual(done.to_dict()['execution']['requests']['attempts'], 0)

    def test_backup_restores_content_and_review_without_copying_channel_secrets(self):
        from xti.adapters.content_credentials import save_credential
        from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
        watch = self.watch()
        code, result = self.invoke('brand.protection.run', {'identifier': watch['id'], 'expected_revision': 1,
            'idempotency_key': 'run', 'expected_workspace_id': self.context.workspace_id})
        self.assertEqual(code, 0, result)
        match = self.invoke('brand.protection.candidates')[1]['data']['items'][0]
        self.assertEqual(self.invoke('brand.protection.review', {'identifier': match['id'], 'evidence_id': match['evidence_id'],
            'expected_revision': 0, 'expected_observation_revision': 1, 'decision': 'unrelated', 'reason': 'Reviewed',
            'idempotency_key': 'review', 'expected_workspace_id': self.context.workspace_id})[0], 0)
        save_credential('discord', 'default', {'token': 'controlled-private-' + 'a'*30},
                        directory=self.context.data_dir / 'content-credentials')
        backup = self.root.parent / 'backup'; backup_platform_workspace(self.context, backup)
        self.assertFalse(any('credential' in p.name for p in backup.rglob('*')))
        for path in backup.rglob('*'):
            if path.is_file(): self.assertNotIn(b'controlled-private-', path.read_bytes())
        restored_root = self.root.parent / 'restored'
        restore_platform_workspace(restored_root, 'alpha', backup)
        restored = resolve_company_workspace(restored_root, 'alpha')
        self.assertNotEqual(restored.workspace_id, self.context.workspace_id)
        current = SQLiteBrandProtectionRepository(restored.database).read('brand.protection.candidate.show', {'identifier': match['id']})
        self.assertFalse(current['needs_review']); self.assertEqual(current['review']['decision'], 'unrelated')
        self.assertFalse((restored.data_dir / 'content-credentials').exists())

    def test_terminal_commands_show_candidates_and_same_json_record(self):
        def cli(*args,as_json=True):
            out,err=StringIO(),StringIO()
            with redirect_stdout(out),redirect_stderr(err):
                code=main(['--data-dir',str(self.context.data_dir),*(['--json'] if as_json else []),'brand','protection',*args])
            self.assertEqual((code,err.getvalue()),(0,''),out.getvalue())
            return json.loads(out.getvalue())['data'] if as_json else out.getvalue()
        identity=cli('identity-add','--name','Example Corp','--domain','example.com')
        watch=cli('watch-add','--identity',identity['id'])
        cli('plan',watch['id']);self.assertEqual(self.source.calls,0)
        cli('run',watch['id']);record=cli('candidates')['items'][0]
        rendered=cli('candidate-show',record['id'],as_json=False)
        self.assertIn('Example Corp',rendered);self.assertIn('https://candidate.example/',rendered)
        cli('review',record['id'],'--evidence-id',record['evidence_id'],'--decision','unrelated','--reason','Reviewed')
        self.assertFalse(cli('candidate-show',record['id'])['needs_review'])

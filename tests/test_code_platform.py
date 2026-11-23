from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import resolve_company_workspace
from xti.adapters.sqlite_code_exposure import SQLiteCodeRepository
from xti.application.code_exposure import CodeExposureService
from xti.interfaces.cli import main
from tests.test_code_exposure import Source, Scanner


class CodePlatformTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / 'platform'
        self.source = Source()
        def make(database): return CodeExposureService(SQLiteCodeRepository(database), self.source, Scanner())
        self.enterContext(patch('xti.interfaces.code_exposure.make_code_service', side_effect=make))
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))
        self.assertEqual(self.invoke(action='provision')[0], 0)
        self.context = resolve_company_workspace(self.root, 'alpha')

    def invoke(self, operation='code.watch.list', values=None, *, company='alpha', action='request', extra=()):
        request = {'contract_version': 1, 'request_id': 'code-test', 'operation': operation, 'parameters': values or {}}
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', StringIO(json.dumps(request))):
            code = main(['platform', action, '--root', str(self.root), '--company', company, *extra])
        self.assertEqual(err.getvalue(), '')
        return code, json.loads(out.getvalue())

    def watch(self):
        code, response = self.invoke('code.watch.add', {'domain': 'example.com', 'sources': ['github-repositories'],
            'idempotency_key': 'watch', 'expected_workspace_id': self.context.workspace_id})
        self.assertEqual(code, 0, response)
        return response['data']

    def test_scope_fence_unknown_company_and_missing_record_fail_without_network(self):
        watch = self.watch()
        code, response = self.invoke('code.run', {'identifier': watch['id'], 'expected_revision': 1,
            'idempotency_key': 'wrong', 'expected_workspace_id': '00000000-0000-0000-0000-000000000000'})
        self.assertNotEqual(code, 0); self.assertEqual(response['error']['code'], 'scope_mismatch')
        self.assertEqual(self.source.calls, 0)
        self.assertEqual(self.invoke(action='provision', company='beta')[0], 0)
        code, response = self.invoke('code.watch.show', {'identifier': watch['id']}, company='beta')
        self.assertEqual(response['error']['code'], 'not_found')
        self.assertNotEqual(self.invoke(company='unknown')[0], 0)

    def test_queue_worker_receipt_reopen_and_read_contract(self):
        watch = self.watch()
        options = {'indicator_type': 'domain', 'value': 'example.com', 'sources': ['code-monitor'],
                   'code_watch_id': watch['id'], 'code_watch_revision': 1, 'max_requests': 30}
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
        code, run = self.invoke('code.run.show', {'identifier': run_id})
        self.assertEqual(code, 0, run); self.assertEqual(run['data']['status'], 'complete')
        self.assertEqual(self.invoke('code.findings')[1]['data']['items'][0]['domain'], 'example.com')
        self.assertEqual(self.invoke(action='worker', extra=('--job-id', job_id))[1]['data'], None)
        self.assertEqual(self.source.calls, 1)

    def test_plan_requires_matching_domain_revision_and_budget(self):
        watch = self.watch()
        for changes in ({'value': 'other.example'}, {'code_watch_revision': 2}, {'max_requests': 1}, {'max_seconds': 5}):
            code, result = self.invoke('sources.plan', {'indicator_type': 'domain', 'value': 'example.com', 'sources': ['code-monitor'],
                'code_watch_id': watch['id'], 'code_watch_revision': 1, 'max_requests': 30, **changes})
            self.assertNotEqual(code, 0, result)
        self.assertEqual(self.source.calls, 0)

    def test_core_commit_queue_crash_reuses_receipt_without_repeating_network(self):
        from xti.adapters.source_job_steps import ExistingSourceJobOperations
        from xti.interfaces.platform_jobs import make_job_service
        from xti.interfaces.source_jobs import make_source_job_service
        watch = self.watch()
        source_service = make_source_job_service(self.context)
        options = {'indicator_type': 'domain', 'value': 'example.com', 'sources': ['code-monitor'],
                   'code_watch_id': watch['id'], 'code_watch_revision': 1, 'max_requests': 30}
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


if __name__ == '__main__': unittest.main()

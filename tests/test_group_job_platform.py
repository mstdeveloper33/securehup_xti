"""Company JSON/CLI delivery, restore fences and fixed group job scope."""
import json
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import unittest

from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
from xti.adapters.sqlite_evidence import SQLiteEvidenceRepository
from xti.application.evidence import EvidenceService
from xti.interfaces.entrypoint import main
from tests import test_source_jobs_platform as platform
from tests import test_research_groups as groups


class GroupJobPlatformTests(unittest.TestCase):
    def setUp(self):
        self.f = platform.SourceJobPlatformTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.helper = groups.GroupTests(); self.helper.setUp(); self.addCleanup(self.helper.doCleanups)
        path = self.f.context.database
        self.helper.dns(path=path); self.helper.dns('other.example', path=path)
        service = EvidenceService(SQLiteEvidenceRepository(path))
        row = service.execute('groups.preview', indicator_type='domain', value='example.com')['records'][0]
        self.group = service.execute('groups.capture', indicator_type='domain', value='example.com',
            **row['scope'], identifier=row['id'], evidence_sha256=row['evidence_sha256'],
            expected_revision=0, idempotency_key='capture')['record']
        self.options = dict(indicator_type='domain', value='example.com', sources=['group-refresh'], group_id=row['id'])

    def submit(self, key='group'):
        code, result = self.f.submit(key=key, **self.options)
        self.assertEqual(code, 0, result)
        return result['data']

    def test_current_history_audit_and_rebuild_keep_company_write_fence(self):
        for operation in ('groups.current', 'groups.history', 'groups.changes'):
            code, result = self.f.invoke(operation=operation, parameters={'identifier': self.group['id']})
            self.assertEqual(code, 0, result)
        code, audit = self.f.invoke(operation='groups.audit')
        self.assertEqual(code, 0, audit)
        self.assertEqual(audit['data']['integrity'], 'verified')
        code, rejected = self.f.invoke(operation='groups.rebuild', parameters={'expected_workspace_id': '00000000-0000-4000-8000-000000000000'})
        self.assertNotEqual(code, 0)
        self.assertEqual(rejected['error']['code'], 'scope_mismatch')
        code, rebuilt = self.f.invoke(operation='groups.rebuild', parameters={'expected_workspace_id': self.f.context.workspace_id})
        self.assertEqual(code, 0, rebuilt)
        self.assertEqual(rebuilt['data']['event_count'], 1)
        self.assertEqual(self.f.invoke(operation='groups.show', parameters={'identifier': self.group['id']})[1]['data']['record'], self.group)

    def test_actual_worker_notification_reads_and_company_scope(self):
        submitted = self.submit()
        self.helper.dns('third.example', path=self.f.context.database)
        code, completed = self.f.invoke('worker', extra=('--job-id', submitted['job_id']))
        self.assertEqual(code, 0, completed)
        self.assertEqual(completed['data']['status'], 'complete')
        receipt = completed['data']['steps'][0]['receipt']
        code, notice = self.f.invoke(operation='groups.notification-show', parameters={'identifier': receipt['notification_id']})
        self.assertEqual(code, 0, notice)
        self.assertEqual(notice['data']['notification']['snapshot']['change']['added'], [['domain', 'third.example']])
        code, listing = self.f.invoke(operation='groups.notifications')
        self.assertEqual(code, 0, listing)
        self.assertEqual(listing['data']['records'][0]['id'], receipt['notification_id'])
        self.assertEqual(self.f.invoke('provision', company='beta')[0], 0)
        for operation, parameters in (('sources.plan', self.options),
                ('sources.jobs.status', {'job_id': submitted['job_id']}),
                ('groups.notification-show', {'identifier': receipt['notification_id']})):
            code, result = self.f.invoke(company='beta', operation=operation, parameters=parameters)
            self.assertNotEqual(code, 0, result)
            self.assertEqual(result['error']['code'], 'not_found')
        self.assertEqual(self.f.invoke(company='beta', operation='groups.notifications')[1]['data']['records'], [])
        self.assertEqual(self.f.invoke('worker', extra=('--job-id', submitted['job_id']))[1]['data'], None)

    def test_restored_jobs_groups_and_notifications_keep_proof_but_new_workspace_fence(self):
        submitted = self.submit()
        self.helper.dns('third.example', path=self.f.context.database)
        code, done = self.f.invoke('worker', extra=('--job-id', submitted['job_id']))
        self.assertEqual(code, 0, done)
        notification = done['data']['steps'][0]['receipt']['notification_id']
        original = self.f.invoke(operation='groups.notification-show', parameters={'identifier': notification})[1]['data']
        output = self.f.base / 'group-backup'
        backup_platform_workspace(self.f.context, output)
        root = self.f.base / 'group-restore'
        restored = restore_platform_workspace(root, 'alpha', output)
        self.assertNotEqual(restored.workspace_id, self.f.context.workspace_id)
        self.assertEqual(self.f.invoke(operation='sources.jobs.status', parameters={'job_id': submitted['job_id']}, root=root)[1]['data'], done['data'])
        self.assertEqual(self.f.invoke(operation='groups.notification-show', parameters={'identifier': notification}, root=root)[1]['data'], original)
        plan = self.f.plan(**self.options)
        parameters = {**plan['plan'], 'idempotency_key': 'after-restore', 'plan_sha256': plan['plan_sha256'],
            'expected_workspace_id': self.f.context.workspace_id}
        code, rejected = self.f.invoke(operation='sources.jobs.submit', parameters=parameters, root=root)
        self.assertNotEqual(code, 0); self.assertEqual(rejected['error']['code'], 'scope_mismatch')
        parameters['expected_workspace_id'] = restored.workspace_id
        code, accepted = self.f.invoke(operation='sources.jobs.submit', parameters=parameters, root=root)
        self.assertEqual(code, 0, accepted)

    def test_cli_plan_submit_queue_monitor_and_json_notifications(self):
        def invoke(*args):
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(['--data-dir', str(self.f.context.data_dir), '--json', *args])
            self.assertEqual((code, err.getvalue()), (0, ''), out.getvalue())
            return json.loads(out.getvalue())['data']
        flags = ['example.com', '--type', 'domain', '--source', 'group-refresh', '--group', self.group['id']]
        self.assertEqual(invoke('source-jobs', 'plan', *flags)['maximum_external_requests'], 0)
        job = invoke('source-jobs', 'submit', *flags, '--idempotency-key', 'terminal')
        self.helper.dns('third.example', path=self.f.context.database)
        done = invoke('source-jobs', 'worker', '--job-id', job['job_id'])
        notice = done['steps'][0]['receipt']['notification_id']
        self.assertEqual(invoke('groups', 'notification-show', notice)['notification']['id'], notice)
        self.assertEqual(invoke('groups', 'notifications')['total_count'], 1)
        self.assertEqual(invoke('source-jobs', 'submit', *flags, '--idempotency-key', 'terminal'), done)
        monitored = invoke('groups', 'monitor', self.group['id'], '--queued', '--rounds', '1')
        self.assertEqual(monitored['rounds'][0]['job_status'], 'complete')
        self.assertEqual(monitored['rounds'][0]['new_changes'], 0)


if __name__ == '__main__': unittest.main()

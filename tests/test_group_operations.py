"""Atomic notifications, managed local jobs and lossless archived group proof."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_groups import read_groups
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_journal_storage import SQLiteJournalStorageRepository
from xti.adapters.compressed_evidence import journal_bytes
from xti.application.journal_storage import JournalStorageService
from xti.domain.assets import ValidationError
from xti.domain.engine_jobs import EngineJobError
from xti.domain.source_jobs import SourceJobPayload, source_plan
from xti.interfaces.platform_jobs import initialize_jobs, make_job_service
from xti.interfaces.source_jobs import make_source_job_service
from tests import test_research_groups as fixtures

REAL_RUN, REAL_POPEN = subprocess.run, subprocess.Popen


class GroupOperationsTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.GroupTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.record = self.f.capture(self.f.pair())
        self.inbox = SQLiteInboxRepository(self.f.path)
        self.context = SimpleNamespace(data_dir=self.f.data, database=self.f.path)
        initialize_jobs(self.context)
        self.jobs = make_source_job_service(self.context)
        self.worker = make_job_service(self.context)
        self.options = dict(indicator_type='domain', value='example.com', sources=['group-refresh'], group_id=self.record['id'])
        self.archive = JournalStorageService(SQLiteJournalStorageRepository(self.f.path),
            clock=lambda: datetime.now(timezone.utc) + timedelta(days=100))

    def show(self):
        return self.f.groups.execute('groups.show', identifier=self.record['id'])['record']

    def submit(self, key='job', **changes):
        plan = self.jobs.plan(**{**self.options, **changes})
        return self.jobs.submit(**plan['plan'], plan_sha256=plan['plan_sha256'], idempotency_key=key)

    def compact(self):
        plan = self.archive.execute('journals.archive-plan', older_than_days=7)
        self.assertTrue(any(row['journal'] == 'research_group_journal' for row in plan['items']))
        return self.archive.execute('journals.archive-apply', older_than_days=7, token=plan['token'])

    def test_change_and_inbox_are_atomic_replay_preserves_read_and_human_decision(self):
        accepted = self.f.review(self.record)
        self.assertEqual(self.inbox.list().total_count, 0)
        self.f.dns('third.example')
        changed = self.f.refresh(accepted)
        item = self.inbox.list().items[0]
        proof = item.group_change['snapshot']
        self.assertEqual(proof['before']['decision'], accepted['decision'])
        self.assertEqual(proof['after']['revision'], changed['revision'])
        self.assertEqual(proof['change']['added'], [['domain', 'third.example']])
        self.assertFalse(proof['after']['review_current'])
        from xti.interfaces.inbox import detail_lines, page_lines
        self.assertIn('third.example', '\n'.join(detail_lines(self.inbox.get(item.notification.id))))
        self.assertIn('İnceleme grubu', '\n'.join(page_lines(self.inbox.list(), status='unread', next_command=None)))
        self.inbox.mark([item.notification.id], True, self.f.at.isoformat())
        self.assertEqual(self.f.refresh(accepted), changed)
        self.f.refresh(changed, 'unchanged')
        self.assertEqual(self.inbox.list().total_count, 1)
        self.assertEqual(self.inbox.list().unread_count, 0)
        self.assertEqual(self.inbox.get(item.notification.id).group_change['snapshot'], proof)
        self.assertEqual(self.show()['decision'], accepted['decision'])

    def test_notification_failure_rolls_back_the_group_and_emits_nothing(self):
        self.f.dns('third.example')
        before = self.f.path.read_bytes()
        with patch('xti.adapters.sqlite_group_notifications.next_notification_sequence', side_effect=StorageError('Controlled stop')):
            with self.assertRaises(StorageError): self.f.refresh(self.record)
        self.assertEqual(self.f.path.read_bytes(), before)
        self.assertEqual(self.show(), self.record)
        self.assertEqual(self.inbox.list().total_count, 0)

    def test_partial_checks_are_quiet_and_absence_return_are_distinct_changes(self):
        target = 'xti.adapters.sqlite_groups.preview_in'
        with patch(target, return_value=([], {'coverage_complete': False, 'limitations': ['dns_read_budget']})):
            partial = self.f.refresh(self.record, 'partial')
        self.assertEqual(self.inbox.list().total_count, 0)
        with patch(target, return_value=([], {'coverage_complete': True, 'limitations': []})):
            absent = self.f.refresh(partial, 'absent')
            same = self.f.refresh(absent, 'still-absent')
        self.assertEqual(self.inbox.list().total_count, 1)
        restored = self.f.refresh(same, 'returned')
        self.assertEqual(self.inbox.list().total_count, 2)
        self.assertEqual(restored['status'], 'current')
        self.assertEqual(self.inbox.list().items[1].group_change['snapshot']['after']['status'], 'not_in_view')

    def test_archived_group_retains_original_jobs_notifications_case_and_limits(self):
        from xti.config import Settings
        from xti.interfaces.cli import make_case_service
        accepted = self.f.review(self.record)
        cases = make_case_service(Settings(data_dir=self.f.data))
        case = cases.create('Group archive', summary='Fixture', reason='Frozen proof').case
        link = cases.add_evidence(case.id, 'research_group', accepted['id'], reason='Preserve original').evidence
        self.f.dns('third.example')
        job = self.submit(); done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'complete')
        before, notice = self.show(), self.inbox.list().items[0]
        with self.f.repo.storage._connection(readonly=True) as c:
            logical = journal_bytes(c, 'research_group_journal')
            metadata = c.execute('SELECT sequence,id,subject_id,request_key,operation,payload_sha256,chain_sha256 FROM research_group_journal').fetchall()
        archived = self.compact()
        self.assertEqual(self.show(), before)
        self.assertEqual(self.f.capture(self.record['group']), self.record)
        self.assertEqual(self.inbox.get(notice.notification.id).group_change, notice.group_change)
        self.assertEqual(self.jobs.status(job.id).to_dict(), done.to_dict())
        with self.f.repo.storage._connection(readonly=True) as c:
            self.assertEqual(journal_bytes(c, 'research_group_journal'), logical)
            self.assertEqual(c.execute('SELECT sequence,id,subject_id,request_key,operation,payload_sha256,chain_sha256 FROM research_group_journal').fetchall(), metadata)
            self.assertNotIn('cold_payload_v1', c.execute('SELECT payload_json FROM research_group_journal ORDER BY sequence DESC LIMIT 1').fetchone()[0])
            stored_case = c.execute('SELECT snapshot_json FROM case_evidence WHERE id=?', (link.id,)).fetchone()[0]
            self.assertEqual(stored_case, link.snapshot_json)
        with patch('xti.adapters.sqlite_group_projection.MAX_EVENT_BYTES', 1), self.assertRaises(StorageError): self.show()
        restored = self.f.root / 'archived-restore.db'
        backup = self.f.repo.storage.backup(self.f.root / 'archived-backup.db')
        SQLiteAssetRepository.restore(backup, restored)
        from xti.adapters.sqlite_evidence import SQLiteEvidenceRepository
        from xti.application.evidence import EvidenceService
        self.assertEqual(EvidenceService(SQLiteEvidenceRepository(restored)).execute('groups.show', identifier=before['id'])['record'], before)
        self.assertEqual(SQLiteInboxRepository(restored).get(notice.notification.id).group_change, notice.group_change)
        self.archive.execute('journals.restore', identifier=archived['event']['id'])
        self.assertEqual(self.show(), before)

    def test_corrupted_archived_group_fails_group_and_inbox_reads(self):
        self.f.dns('third.example'); self.f.refresh(self.record)
        self.compact()
        with self.f.repo.storage._connection() as c, c:
            c.execute("UPDATE journal_payload_archives SET body=x'00' WHERE journal='research_group_journal'")
        with self.assertRaises(StorageError): self.show()
        with self.assertRaises(StorageError): self.inbox.list()

    def test_notification_tampering_and_deleted_tail_are_detected(self):
        self.f.dns('third.example'); self.f.refresh(self.record)
        with self.f.repo.storage._connection() as c, c:
            checksum = c.execute('SELECT proof_sha256 FROM research_group_notifications').fetchone()[0]
            c.execute('UPDATE research_group_notifications SET proof_sha256=?', ('0'*64,))
        with self.assertRaises(StorageError): self.inbox.list()
        with self.f.repo.storage._connection() as c, c:
            c.execute('UPDATE research_group_notifications SET proof_sha256=?', (checksum,))
            c.execute('DELETE FROM research_group_notifications')
        with self.assertRaises(StorageError): self.inbox.list()

    def test_queue_plan_worker_replay_and_new_human_review_share_one_result(self):
        plan = self.jobs.plan(**self.options)
        self.assertEqual(plan['maximum_external_requests'], 0)
        self.assertEqual(plan['group']['scope'], self.record['group']['scope'])
        job = self.submit()
        accepted = self.f.review(self.record)
        self.f.dns('third.example')
        done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual(done.payload.version, 7)
        self.assertEqual(done.steps[0]['receipt']['usage']['attempts'], 0)
        self.assertEqual(self.show()['decision'], accepted['decision'])
        self.assertEqual(self.submit().to_dict(), done.to_dict())
        self.assertIsNone(self.worker.work_one(job.id))
        self.assertEqual(self.inbox.list().total_count, 1)
        with self.assertRaises(EngineJobError): self.jobs.plan(**{**self.options, 'value': 'other.example'})
        with self.assertRaises(ValidationError): source_plan(**{**self.options, 'group_id': '../escape'})
        with self.assertRaises(ValidationError): SourceJobPayload(plan['plan'], version=6).to_json()
        legacy = source_plan(indicator_type='url', value='https://example.com/', sources=['urlscan'])
        self.assertEqual(SourceJobPayload.from_json(SourceJobPayload(legacy, version=6).to_json()).version, 6)

    def test_partial_job_explicit_retry_and_cancel_preserve_data(self):
        job = self.submit()
        with patch('xti.adapters.sqlite_research.MAX_DNS_CHECKS', 1): done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'partial')
        self.assertEqual(done.steps[0]['receipt']['group_status'], 'indeterminate')
        self.assertEqual(self.inbox.list().total_count, 0)
        retry = self.jobs.retry(job.id, idempotency_key='retry')
        complete = self.worker.work_one(retry.id)
        self.assertEqual(complete.status, 'complete')
        self.assertNotEqual(complete.steps[0]['receipt']['event_id'], done.steps[0]['receipt']['event_id'])
        cancelled = self.submit('cancel'); self.jobs.cancel(cancelled.id)
        before = self.show()
        self.assertIsNone(self.worker.work_one(cancelled.id))
        self.assertEqual(self.show(), before)

    def test_upstream_order_and_invalid_clock_cannot_commit_a_group_check(self):
        from xti.adapters.source_job_groups import GroupRefreshStep
        mixed = {**self.options, 'sources': ['group-refresh', 'news:ncsc']}
        with self.assertRaises(ValidationError):
            source_plan(**mixed)
        ordered = source_plan(**mixed, source_order=['news:ncsc', 'group-refresh'])
        self.assertEqual(ordered['source_order'], ['news:ncsc', 'group-refresh'])
        with self.assertRaises(ValidationError):
            source_plan(**{**self.options, 'sources': ['news:ncsc']})
        job = self.submit()
        step = GroupRefreshStep(self.f.path, self.jobs.repository, clock=lambda: datetime(2026, 1, 1))
        with self.assertRaises(ValidationError):
            step.execute(job.payload.plan, job.id)
        self.assertEqual(self.show(), self.record)
        self.assertEqual(self.inbox.list().total_count, 0)

    def test_bounded_queued_monitor_uses_jobs_and_sleeps_without_core_lock(self):
        from xti.interfaces.research_groups import monitor_group
        from xti.adapters.worker_lock import LocalExecutionLock
        sleeps = []
        def between(seconds):
            with LocalExecutionLock(self.f.path).acquire(): sleeps.append(seconds)
        result = monitor_group(self.f.path, self.record['id'], rounds=2, interval_seconds=1, sleep=between, queued=True)
        self.assertEqual(result['execution'], 'managed_queue')
        self.assertEqual(sleeps, [1])
        self.assertEqual([r['revision'] for r in result['rounds']], [2,3])
        self.assertEqual(len(self.jobs.list()['jobs']), 2)
        self.assertEqual(self.inbox.list().total_count, 0)

    def test_process_death_after_core_commit_reuses_proof_even_after_archive(self):
        self.f.dns('third.example'); job = self.submit()
        program = '''
import os,signal,sys
from pathlib import Path
from types import SimpleNamespace
from xti.adapters.source_job_groups import GroupRefreshStep
from xti.interfaces.platform_jobs import make_job_service
original = GroupRefreshStep.execute
def crash(self, plan, job_id):
    original(self, plan, job_id)
    os.kill(os.getpid(), signal.SIGKILL)
GroupRefreshStep.execute = crash
path = Path(sys.argv[1])
make_job_service(SimpleNamespace(data_dir=path.parent,database=path)).work_one(sys.argv[2])
'''
        with patch('subprocess.run', REAL_RUN), patch('subprocess.Popen', REAL_POPEN):
            child = subprocess.run([sys.executable, '-c', program, str(self.f.path), job.id],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(child.returncode, -signal.SIGKILL, child.stderr.decode())
        original = self.show(); notice = self.inbox.list().items[0]
        self.assertEqual(original['revision'], 2)
        self.worker.recover()
        self.f.at = datetime.now(timezone.utc)
        latest = self.f.refresh(original, 'later-control')
        self.compact()
        with self.assertRaises(EngineJobError): self.jobs.retry(job.id, idempotency_key='no-consent')
        retry = self.jobs.retry(job.id, idempotency_key='recover', allow_uncertain=True)
        done = self.worker.work_one(retry.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual(done.steps[0]['receipt']['event_id'], original['history'][-1]['id'])
        self.assertEqual(done.steps[0]['receipt']['notification_id'], notice.notification.id)
        self.assertEqual(self.show(), latest)
        self.assertEqual(self.inbox.list().total_count, 1)


if __name__ == '__main__': unittest.main()

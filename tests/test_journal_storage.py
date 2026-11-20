"""Lossless archive/read/replay, corruption, atomic backup and schema upgrades."""
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite_reports import SQLiteReportRepository
from xti.adapters.sqlite_journal_storage import SQLiteJournalStorageRepository
from xti.adapters.compressed_evidence import unpack, journal_bytes
from xti.application.journal_storage import JournalStorageService
from xti.application.reports import ReportService
from xti.domain.assets import ValidationError
from xti.domain.reports import ReportError
from tests import test_evidence_delivery as evidence
from tests import test_reports as reports


class JournalStorageTests(unittest.TestCase):
    def setUp(self):
        self.f = evidence.EvidenceTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.repo = SQLiteJournalStorageRepository(self.f.f.path)
        self.service = JournalStorageService(self.repo, clock=lambda: reports.NOW + timedelta(days=100))
        self.first_report = self.f.f.capture()['record']
        self.f.f.f.apply(replace(self.f.f.item, summary='New report: 192.0.2.10 and suspect[.]example ' + ('research ' * 180).rstrip()))
        self.second_report = self.f.f.capture('second')['record']
        self.first_sighting = self.f.sight(reference='sensor:' + 'f' * 400)['record']
        self.f.sight(reference='sensor:' + 'f' * 400, idempotency_key='second-sighting')

    def plan(self):
        return self.service.execute('journals.archive-plan', older_than_days=7)

    def archive(self):
        plan = self.plan()
        self.assertGreater(plan['selected_count'], 0)
        return self.service.execute('journals.archive-apply', older_than_days=7, token=plan['token'])

    def test_archived_reads_observations_and_original_idempotency_are_identical(self):
        before = self.f.f.observe()
        with self.f.repo.storage._connection(readonly=True) as c:
            logical_before = [journal_bytes(c, table) for table in ('report_journal', 'evidence_journal', 'social_discovery_runs')]
        result = self.archive()
        self.assertTrue(Path(result['backup']).is_file())
        self.assertEqual(self.f.f.show(self.second_report['id']), self.second_report)
        self.assertEqual(self.f.f.capture()['record'], self.first_report)
        self.assertEqual(self.f.sight(reference='sensor:' + 'f' * 400)['record'], self.first_sighting)
        self.assertEqual(self.f.f.observe(), before)
        status = self.service.execute('journals.status')
        self.assertEqual(sum(row['cold_count'] for row in status['journals']), result['changed_count'])
        self.assertEqual([row['logical_bytes_with_overhead'] for row in status['journals']], logical_before)
        with self.f.repo.storage._connection(readonly=True) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM report_journal').fetchone()[0], 2)
            self.assertIn('cold_payload_v1', c.execute('SELECT payload_json FROM report_journal WHERE sequence=1').fetchone()[0])

    def test_restore_is_backed_up_lossless_and_repeated_restore_is_noop(self):
        archived = self.archive()
        restored = self.service.execute('journals.restore', identifier=archived['event']['id'])
        self.assertEqual(restored['changed_count'], archived['changed_count'])
        self.assertNotEqual(restored['backup'], archived['backup'])
        self.assertEqual(self.service.execute('journals.restore', identifier=archived['event']['id'])['changed_count'], 0)
        self.assertEqual(self.f.f.capture()['record'], self.first_report)
        self.assertEqual(sum(r['cold_count'] for r in self.service.execute('journals.status')['journals']), 0)
        self.assertEqual(self.service.execute('journals.show', identifier=archived['event']['id'])['event'], archived['event'])

    def test_backup_of_cold_database_is_self_contained_and_restores_references(self):
        self.archive()
        backup = self.repo.storage.backup(self.f.f.path.parent / 'cold-backup.db')
        restored = self.f.f.path.parent / 'cold-restored.db'
        SQLiteAssetRepository.restore(backup, restored)
        service = ReportService(SQLiteReportRepository(restored), clock=lambda: reports.NOW)
        self.assertEqual(service.execute('reports.show', identifier=self.first_report['id'])['record'], self.second_report)
        self.assertEqual(service.execute('reports.capture', source='news', identifier=self.f.f.item.id, idempotency_key='capture-one')['record'], self.first_report)
        self.assertGreater(JournalStorageService(SQLiteJournalStorageRepository(restored)).execute('journals.status')['journals'][0]['cold_count'], 0)

    def test_stale_or_foreign_plan_cannot_mutate_and_latest_record_is_protected(self):
        plan = self.plan()
        self.assertEqual(plan['protected_latest_count'], 2)
        self.f.f.capture('another-receipt')
        before = self.f.f.path.read_bytes()
        with self.assertRaises(ReportError):
            self.service.execute('journals.archive-apply', older_than_days=7, token=plan['token'])
        self.assertEqual(before, self.f.f.path.read_bytes())
        plan = self.plan()
        copied = self.f.f.path.parent / 'copy.db'
        self.repo.storage.backup(copied)
        other = JournalStorageService(SQLiteJournalStorageRepository(copied), clock=self.service.clock)
        with self.assertRaises(ReportError):
            other.execute('journals.archive-apply', older_than_days=7, token=plan['token'])

    def test_failure_after_body_moves_rolls_back_but_preserves_recovery_backup(self):
        before = self.f.f.path.read_bytes()
        with patch.object(self.repo, '_append', side_effect=StorageError('Controlled interruption')), self.assertRaises(StorageError):
            self.archive()
        self.assertEqual(self.f.f.path.read_bytes(), before)
        backups = list((self.f.f.path.parent / 'backups').glob('*.pre-journal-*.db'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.f.f.show(self.second_report['id']), self.second_report)

    def test_real_process_kill_before_commit_can_retry_without_losing_evidence(self):
        import signal, subprocess, sys
        plan = self.plan()
        program = '''
import os,signal,sys
from pathlib import Path
from datetime import datetime
from xti.adapters.sqlite_journal_storage import SQLiteJournalStorageRepository
from xti.application.journal_storage import JournalStorageService
def crash(self, connection, event, chain):
    os.kill(os.getpid(), signal.SIGKILL)
SQLiteJournalStorageRepository._append = crash
service = JournalStorageService(SQLiteJournalStorageRepository(Path(sys.argv[1])), clock=lambda: datetime.fromisoformat(sys.argv[3]))
service.execute('journals.archive-apply', older_than_days=7, token=sys.argv[2])
'''
        child = subprocess.run([sys.executable, '-c', program, str(self.f.f.path), plan['token'], self.service.clock().isoformat()],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        self.assertEqual(child.returncode, -signal.SIGKILL, child.stderr.decode())
        # An explicit writer open lets SQLite recover a hot rollback journal.
        result = self.service.execute('journals.archive-apply', older_than_days=7, token=plan['token'])
        self.assertEqual(result['changed_count'], plan['selected_count'])
        self.assertEqual(self.f.f.capture()['record'], self.first_report)
        self.assertEqual(self.f.f.show(self.second_report['id']), self.second_report)
        self.assertEqual(len(list((self.f.f.path.parent / 'backups').glob('*.pre-journal-*.db'))), 2)

    def test_missing_corrupt_and_oversize_archive_cannot_be_empty_success(self):
        self.archive()
        with self.f.repo.storage._connection() as c, c:
            c.execute("UPDATE journal_payload_archives SET body=x'00' WHERE journal='report_journal'")
        with self.assertRaises(StorageError):
            self.f.f.show(self.first_report['id'])
        with self.assertRaises(StorageError):
            self.service.execute('journals.status')

    def test_decompression_bomb_trailing_data_and_wrong_size_fail_before_materialization(self):
        import hashlib, zlib
        body = b'a' * (3 * 1024 * 1024)
        for packed, size, checksum in ((zlib.compress(body), len(body), hashlib.sha256(body).hexdigest()),
                (zlib.compress(b'abc') + b'extra', 3, hashlib.sha256(b'abc').hexdigest()),
                (zlib.compress(body), 3, hashlib.sha256(body).hexdigest())):
            with self.subTest(size=size), self.assertRaises(StorageError):
                unpack(packed, size, checksum)

    def test_deleted_archive_audit_tail_is_detected(self):
        self.archive()
        with self.f.repo.storage._connection() as c, c:
            c.execute('DELETE FROM journal_storage_events')
        with self.assertRaises(StorageError):
            self.service.execute('journals.status')

    def test_core78_upgrade_preserves_journals_and_original_backup(self):
        from xti.adapters.document_storage_schema import TABLES
        with self.f.repo.storage._connection() as c, c:
            original = c.execute('SELECT * FROM report_journal').fetchall()
            for table in TABLES:
                c.execute('DROP TABLE ' + table)
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(c)
            c.execute('PRAGMA user_version=78')
        result = self.repo.storage.migrate()
        self.assertEqual((result['from_version'], result['to_version']), (78, SCHEMA_VERSION))
        with closing(sqlite3.connect(result['backup'])) as backup, self.f.repo.storage._connection(readonly=True) as current:
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 78)
            self.assertEqual(current.execute('SELECT * FROM report_journal').fetchall(), original)
        self.assertEqual(self.f.f.show(self.second_report['id']), self.second_report)
        self.archive()

    def test_readonly_planning_does_not_create_backups_or_change_data(self):
        before = self.f.f.path.read_bytes()
        plan = self.plan()
        self.service.execute('journals.status')
        self.assertEqual(self.f.f.path.read_bytes(), before)
        self.assertFalse((self.f.f.path.parent / 'backups').exists())
        for options in ({'older_than_days': 0}, {'limit': 1001}, {'limit': True}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                self.service.execute('journals.archive-plan', **options)

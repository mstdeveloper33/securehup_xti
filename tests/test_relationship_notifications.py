"""Changed proof is delivered once, retained in a case and isolated per workspace."""
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_evidence import SQLiteEvidenceRepository
from xti.application.evidence import EvidenceService
from xti.domain.assets import ValidationError
from xti.domain.reports import ReportError
from xti.interfaces.inbox import page_lines, detail_lines
from tests import test_evidence_delivery as base
from tests import test_reports as reports


class RelationshipNotificationTests(unittest.TestCase):
    def setUp(self):
        self.f = base.EvidenceTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.path, self.service = self.f.f.path, self.f.service
        self.row = self.f.candidate()
        self.f.review(self.row)
        self.inbox = SQLiteInboxRepository(self.path)

    def change(self):
        self.f.f.f.apply(replace(self.f.f.item, summary='Corrected report: 192.0.2.10 and suspect[.]example'))
        self.f.f.capture('changed')

    def notify(self, **options):
        return self.service.execute('relationships.notify', **base.ROOT, **options)

    def test_deduplicates_changed_proof_without_mutating_decision_or_read_state(self):
        self.assertEqual(self.notify()['created_count'], 0)
        self.change()
        before = self.service.execute('relationships.show', identifier=self.row['id'])
        result = self.notify()
        self.assertEqual(result['created_count'], 1)
        notice = result['records'][0]
        self.assertEqual(self.inbox.list().total_count, 1)
        detail = self.inbox.get(notice['id'])
        self.assertEqual(detail.relationship_change['snapshot']['change']['previous']['decision'], 'accepted')
        self.assertIn('İlişki dayanağı değişti', '\n'.join(page_lines(self.inbox.list(), status='unread', next_command=None)))
        self.assertIn('--evidence-id', '\n'.join(detail_lines(detail)))
        self.inbox.mark([notice['id']], True, reports.NOW.isoformat())
        again = self.notify()
        self.assertEqual((again['created_count'], again['existing_count']), (0, 1))
        self.assertEqual(self.inbox.list().unread_count, 0)
        self.assertEqual(self.service.execute('relationships.show', identifier=self.row['id']), before)
        self.assertEqual(self.service.execute('relationships.notification-show', identifier=notice['id'])['notification']['snapshot'], notice['snapshot'])

    def test_missing_or_truncated_coverage_does_not_make_a_definitive_notification(self):
        with patch('xti.adapters.sqlite_evidence.relationship_rows', return_value=([], SimpleNamespace(limitations=('node_limit',)))):
            result = self.notify()
        self.assertEqual((result['created_count'], result['skipped_incomplete_count']), (0, 1))
        self.change()
        from xti.adapters.sqlite_evidence import relationship_rows
        def partial(*args, **kwargs):
            rows, graph = relationship_rows(*args, **kwargs)
            return [{**row, 'coverage_complete': False} for row in rows], graph
        with patch('xti.adapters.sqlite_evidence.relationship_rows', side_effect=partial):
            self.assertEqual(self.notify()['skipped_incomplete_count'], 1)
        self.assertEqual(self.inbox.list().total_count, 0)

    def test_frozen_case_survives_re_review_archive_backup_and_restore(self):
        self.change()
        notice = self.notify()['records'][0]
        resolver, cases = SQLiteCaseEvidenceSourceRepository(self.path), SQLiteCaseRepository(self.path)
        selected = resolver.resolve('relationship_review', notice['id'])
        case = cases.create(title='Changed report proof', summary='Review required', priority='medium',
            reason='Analyst investigation', recorded_at=reports.NOW.isoformat()).case
        linked = cases.add_evidence(case.id, snapshot=selected, reason='Attach frozen proof', recorded_at=reports.NOW.isoformat())
        from xti.interfaces.research import make_research_service
        from xti.application.research import research_data
        graph = research_data(make_research_service(self.path).show(**base.ROOT))
        self.assertTrue(any(node['kind'] == 'case' and node['value'] == case.id for node in graph['nodes']))
        current = next(row for row in self.service.execute('relationships.candidates', **base.ROOT)['records'] if row['id'] == self.row['id'])
        self.f.review(current, expected_revision=1, decision='uncertain', idempotency_key='updated-review')
        self.assertEqual(self.notify()['created_count'], 0)
        self.assertEqual(resolver.resolve('relationship_review', notice['id']), selected)
        from xti.adapters.sqlite_journal_storage import SQLiteJournalStorageRepository
        from xti.application.journal_storage import JournalStorageService
        archive = JournalStorageService(SQLiteJournalStorageRepository(self.path), clock=lambda: reports.NOW + timedelta(days=100))
        plan = archive.execute('journals.archive-plan', older_than_days=7)
        archived = archive.execute('journals.archive-apply', older_than_days=7, token=plan['token'])
        self.assertGreater(archived['changed_count'], 0)
        backup = SQLiteAssetRepository(self.path).backup(self.path.parent / 'notification-backup.db')
        restored = self.path.parent / 'notification-restored.db'
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteCaseEvidenceSourceRepository(restored).resolve('relationship_review', notice['id']), selected)
        self.assertEqual(SQLiteInboxRepository(restored).get(notice['id']).relationship_change['snapshot'], notice['snapshot'])
        self.assertEqual(SQLiteCaseRepository(restored).evidence_show(case.id, linked.evidence.id).snapshot_sha256, selected.snapshot_sha256)

    def test_foreign_notification_cannot_be_shown_or_added_to_another_workspace(self):
        self.change()
        notice = self.notify()['records'][0]
        other = self.path.parent / 'other.db'
        SQLiteAssetRepository(other).initialize()
        service = EvidenceService(SQLiteEvidenceRepository(other), clock=lambda: reports.NOW)
        with self.assertRaises(ReportError):
            service.execute('relationships.notification-show', identifier=notice['id'])
        with self.assertRaises(ReportError):
            SQLiteCaseEvidenceSourceRepository(other).resolve('relationship_review', notice['id'])
        self.assertEqual(SQLiteInboxRepository(other).list().total_count, 0)

    def test_corruption_or_deleted_tail_is_not_a_successful_empty_inbox(self):
        self.change(); notice = self.notify()['records'][0]
        with SQLiteAssetRepository(self.path)._connection() as c, c:
            c.execute("UPDATE relationship_review_notifications SET payload_sha256=?", ('0' * 64,))
        with self.assertRaises(StorageError):
            self.inbox.get(notice['id'])
        with self.assertRaises(StorageError):
            self.inbox.mark([notice['id']], True, reports.NOW.isoformat())
        with self.assertRaises(StorageError):
            self.notify()

    def test_capacity_failure_rolls_back_entire_window_and_keeps_decision(self):
        self.change()
        before = self.path.read_bytes()
        with patch('xti.adapters.sqlite_relationship_notifications.MAX_NOTIFICATIONS', 0), self.assertRaises(ValidationError):
            self.notify()
        self.assertEqual(self.path.read_bytes(), before)

    def test_deleted_notification_tail_does_not_become_an_empty_success(self):
        self.change(); self.notify()
        with SQLiteAssetRepository(self.path)._connection() as c, c:
            c.execute('DELETE FROM relationship_review_notifications')
        with self.assertRaises(StorageError):
            self.inbox.list()

    def test_window_continuation_and_stale_decision_cursor_are_explicit(self):
        from xti.adapters.sqlite_evidence import read_evidence
        from xti.domain.research import identity
        # A reviewed relation outside the selected first window must stay pending.
        self.change()
        first = self.notify(limit=1)
        self.assertEqual(first['examined_count'], 1)
        empty = self.notify(offset=1, expected_snapshot=first['snapshot_id'])
        self.assertEqual(empty['examined_count'], 0)
        self.assertEqual(empty['created_count'], 0)
        current = next(row for row in self.service.execute('relationships.candidates', **base.ROOT)['records'] if row['id'] == self.row['id'])
        self.f.review(current, expected_revision=1, decision='uncertain', idempotency_key='new-decision')
        with self.assertRaises(ReportError):
            self.notify(expected_snapshot=first['snapshot_id'])

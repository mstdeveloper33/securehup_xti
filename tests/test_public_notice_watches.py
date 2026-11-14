"""Explicit scope epochs, historical source evidence and transaction failure tests."""
from contextlib import closing
from dataclasses import asdict, replace
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.sqlite_public_notice_watches import SQLitePublicNoticeWatchRepository
from xti.application.public_notices import PublicNoticeService
from xti.domain.assets import ValidationError
from xti.domain.organizations import normalize_organization_target
from tests.test_public_notices import NOW, feed, item
from tests.test_collection_public_notice_receipts import FakeSource


class PublicNoticeWatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.organizations = SQLiteOrganizationRepository(self.path)
        self.repository = SQLitePublicNoticeWatchRepository(self.path)
        self.source = SQLitePublicNoticeRepository(self.path)
        self.organization = self.add_organization('Example group')
        self.link = self.link_domain('example.com')
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('Offline tests')))

    def add_organization(self, name):
        return self.organizations.add(name_key=name.casefold(), display_name=name, reason='Explicit local group.',
                                      recorded_at=NOW.isoformat()).organization

    def link_domain(self, domain, organization=None, reason='Explicit exact domain.'):
        self.storage.add(domain)
        return self.organizations.link((organization or self.organization).id,
                normalize_organization_target('domain', domain), reason=reason, recorded_at=NOW.isoformat()).link

    def configure(self, enabled=True, organization=None):
        return self.repository.configure((organization or self.organization).id, enabled=enabled,
                                         reason='Explicit monitoring choice.', recorded_at=NOW.isoformat())

    def apply(self, *records, **kwargs):
        return self.source.apply(feed(*(records or [item()])), started_at=NOW.isoformat(),
                                 finished_at=NOW.isoformat(), **kwargs)

    def show(self, organization=None, **kwargs):
        return self.repository.show((organization or self.organization).id, **kwargs)

    def last(self, organization=None):
        return self.repository.run_show(self.show(organization).runs[0].id, item_limit=500)

    def execute(self, sql, params=()):
        with closing(sqlite3.connect(self.path)) as connection:
            result = connection.execute(sql, params).fetchall()
            connection.commit()
            return result

    def counts(self):
        return tuple(self.execute(f'SELECT COUNT(*) FROM {table}')[0][0] for table in (
            'public_notice_runs', 'public_notice_changes', 'public_notice_watch_runs', 'public_notice_watch_notifications'))

    def test_opt_in_baseline_full_catalog_exact_domain_and_unchanged_rows(self):
        self.apply()
        self.assertEqual(self.repository.list().total_count, 0)
        self.configure()
        self.apply(item(), item('TitleGuess', '', Title='Example group'), item('Child', 'sub.example.com'),
                   item('SecondExact', 'example.com'), item('Other', 'other.example'), item_limit=1)
        report = self.last()
        self.assertEqual((report.run.baseline_count, report.run.matched_count), (2, 2))
        self.assertEqual({entry.notice_id for entry in report.items}, {'Example', 'SecondExact'})
        self.assertIsNone(report.notification_id)
        self.apply(item(), item('SecondExact', 'example.com'))
        report = self.last()
        self.assertEqual({entry.action for entry in report.items}, {'unchanged'})
        self.assertEqual(report.run.unchanged_count, 2)
        self.assertIsNone(report.notification_id)

    def test_new_membership_baseline_does_not_suppress_existing_updates(self):
        self.configure(); self.apply()
        self.link_domain('new.example')
        self.apply(item(PwnCount=23456), item('OldHistory', 'new.example'))
        report = self.last()
        self.assertEqual((report.run.baseline_count, report.run.updated_count), (1, 1))
        self.assertEqual(report.baseline_domains, ('new.example',))
        self.assertEqual(report.continuing_domains, ('example.com',))
        self.assertIsNotNone(report.notification_id)
        self.assertEqual((report.items[0].before.pwn_count, report.items[0].after.pwn_count), (12345, 23456))

    def test_rename_and_reason_change_preserve_epoch_and_historical_membership(self):
        self.configure(); self.apply()
        first = self.last()
        self.organizations.rename(self.organization.id, name_key='renamed group', display_name='Renamed group',
                                  reason='Display name correction.', recorded_at=NOW.isoformat())
        self.link_domain('example.com', reason='Updated justification, same membership.')
        self.apply(item(PwnCount=23456))
        changed = self.last()
        self.assertEqual(changed.run.updated_count, 1)
        self.assertEqual(self.repository.run_show(first.run.id), first)
        self.assertEqual(first.scope.organization_name, 'Example group')
        self.assertEqual(changed.scope.organization_name, 'Renamed group')
        self.assertEqual(first.scope.members[0].epoch_event_id, changed.scope.members[0].epoch_event_id)
        self.assertNotEqual(first.scope.members[0].event_id, changed.scope.members[0].event_id)

    def test_relink_between_refreshes_resets_only_that_domain(self):
        other_link = self.link_domain('other.example')
        self.configure(); self.apply(item(), item('Other', 'other.example'))
        self.organizations.unlink(self.organization.id, self.link.id, reason='Temporarily remove scope.', recorded_at=NOW.isoformat())
        self.link_domain('example.com')
        self.apply(item(PwnCount=23456), item('Other', 'other.example', PwnCount=34567))
        report = self.last()
        self.assertEqual((report.run.baseline_count, report.run.updated_count), (1, 1))
        self.assertEqual(report.baseline_domains, ('example.com',))
        self.assertEqual(report.continuing_domains, ('other.example',))
        self.assertEqual(report.scope.members[1].link_id, other_link.id)

    def test_watch_disable_and_reenable_quiet_and_source_failure_keeps_last_success(self):
        self.configure(); baseline = self.apply()
        self.configure(False)
        self.apply(item(PwnCount=23456))
        self.assertEqual(self.show().total_run_count, 1)
        self.configure(True)
        self.apply(item(PwnCount=34567))
        self.assertEqual(self.last().run.baseline_count, 1)
        self.assertIsNone(self.last().notification_id)
        before = self.counts()
        failed = self.source.record_failure(started_at=NOW.isoformat(), finished_at=NOW.isoformat(), error='Source unavailable.')
        self.assertEqual(self.counts()[1:], before[1:])
        self.assertEqual(self.show().latest_source_run, failed)
        self.assertNotEqual(self.show().latest_complete_source_run.id, baseline.run.id)
        self.apply(item(PwnCount=45678))
        self.assertEqual(self.last().run.updated_count, 1)

    def test_org_revocation_and_reactivation_between_refreshes_are_new_epoch(self):
        self.configure(); self.apply()
        self.organizations.revoke(self.organization.id, reason='Scope withdrawn.', recorded_at=NOW.isoformat())
        self.organizations.reactivate(self.organization.id, reason='Scope restored.', recorded_at=NOW.isoformat())
        self.apply(item(PwnCount=23456))
        self.assertEqual(self.last().run.baseline_count, 1)
        self.assertIsNone(self.last().notification_id)
        self.organizations.revoke(self.organization.id, reason='Scope withdrawn.', recorded_at=NOW.isoformat())
        self.apply(item(PwnCount=34567))
        self.assertEqual(self.last().run.matched_count, 0)
        self.assertEqual(self.last().scope.members, ())
        self.assertEqual(self.last().run.removed_count, 0)

    def test_empty_scope_can_be_enabled_then_new_link_is_quiet_baseline(self):
        empty = self.add_organization('Empty group')
        self.configure(organization=empty); self.apply()
        self.assertEqual(self.last(empty).scope.members, ())
        self.link_domain('example.com', organization=empty)
        self.apply(item(PwnCount=23456))
        self.assertEqual(self.last(empty).run.baseline_count, 1)
        self.assertIsNone(self.last(empty).notification_id)

    def test_source_removal_is_silent_reappearance_is_added_and_out_of_scope_is_distinct(self):
        self.configure(); self.apply(item(), item('Keep', 'unrelated.example'))
        self.apply(item('Keep', 'unrelated.example'))
        report = self.last()
        self.assertEqual(report.run.removed_count, 1)
        self.assertIsNone(report.notification_id)
        self.assertIsNone(report.items[0].after)
        self.apply(item(), item('Keep', 'unrelated.example'))
        self.assertEqual(self.last().run.added_count, 1)
        self.apply(item(domain='outside.example'), item('Keep', 'unrelated.example'))
        report = self.last()
        self.assertEqual(report.run.removed_count, 1)
        self.assertEqual(report.items[0].after.domain, 'outside.example')
        self.assertIsNone(report.notification_id)

    def test_same_domain_separate_organizations_keep_exact_evidence_and_ids(self):
        other = self.add_organization('Other group')
        self.link_domain('example.com', organization=other)
        self.configure(); self.configure(organization=other)
        self.apply(); self.apply(item(PwnCount=23456, IsVerified=False, IsFabricated=True))
        first, second = self.last(), self.last(other)
        self.assertNotEqual(first.notification_id, second.notification_id)
        self.assertNotEqual(first.run.id, second.run.id)
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            evidence = self.repository.notification_evidences(connection, (first.notification_id, second.notification_id))
        self.assertEqual(evidence[first.notification_id].organization_id, self.organization.id)
        self.assertEqual(evidence[second.notification_id].organization_id, other.id)
        self.assertFalse(evidence[first.notification_id].items[0].after.is_verified)
        self.assertTrue(evidence[first.notification_id].items[0].after.is_fabricated)

    def test_all_item_and_run_event_pages_are_readonly_and_consistent(self):
        self.configure(); self.apply()
        self.apply(item(), *(item(f'Entry{index:02d}', 'example.com') for index in range(23)))
        report = self.last()
        self.assertEqual(report.total_item_count, 24)
        first = self.repository.run_show(report.run.id)
        second = self.repository.run_show(report.run.id, offset=20)
        self.assertEqual(first.items + second.items, report.items)
        self.assertEqual(report.items[-1].action, 'unchanged')
        self.configure(False); self.configure(True)
        before = self.path.read_bytes()
        page = self.show(run_limit=1, run_offset=1, event_limit=1, event_offset=1)
        self.assertEqual((page.total_run_count, page.run_offset, page.event_offset), (2, 1, 1))
        self.assertEqual(page.events[0].action, 'disabled')
        self.repository.list(offset=1, limit=1)
        self.repository.run_show(report.run.id)
        self.assertEqual(self.path.read_bytes(), before)

    def test_configuration_validation_and_noop_never_mutate(self):
        with self.assertRaises(ValidationError):
            self.configure(False)
        with self.assertRaises(ValidationError):
            self.repository.configure(self.organization.id, enabled=1, reason='Choice.', recorded_at=NOW.isoformat())
        self.configure()
        before = self.path.read_bytes()
        self.assertEqual(self.configure().action, 'unchanged')
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(ValidationError):
            self.repository.show(str(uuid4()))
        for kwargs in ({'run_offset': -1}, {'event_offset': True}, {'run_limit': 501}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                self.show(**kwargs)

    def test_single_field_corruption_in_config_scope_run_or_notification_fails_read_and_preflight(self):
        mutations = (
            "UPDATE public_notice_watches SET revision=2",
            "UPDATE public_notice_watch_events SET reason='bad' || char(10)",
            "UPDATE public_notice_watch_runs SET scope_json='{}'",
            "UPDATE public_notice_watch_runs SET updated_count=0,unchanged_count=1 WHERE updated_count=1",
            "UPDATE public_notice_watch_runs SET source_run_id='11111111-1111-4111-8111-111111111111' WHERE sequence=2",
            "UPDATE public_notice_watch_notifications SET organization_id='11111111-1111-4111-8111-111111111111'",
            "DELETE FROM public_notice_watch_notifications",
        )
        self.configure(); self.apply(); self.apply(item(PwnCount=23456))
        original = self.path.read_bytes()
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.path.write_bytes(original)
                self.execute(mutation)
                corrupted = self.path.read_bytes()
                source = FakeSource(feed(item(PwnCount=34567)))
                service = PublicNoticeService(self.source, source, clock=lambda: NOW)
                with self.assertRaises(StorageError):
                    service.refresh()
                self.assertEqual(source.calls, 0)
                with self.assertRaises(StorageError):
                    self.source.status()
                with self.assertRaises(StorageError):
                    self.show()
                self.assertEqual(self.path.read_bytes(), corrupted)
        self.path.write_bytes(original)

    def test_notification_insert_failure_rolls_back_all_source_and_watch_writes(self):
        self.configure(); self.apply()
        before = self.counts()
        with patch('xti.adapters.sqlite_public_notice_watches.next_notification_sequence', side_effect=RuntimeError('Injected notification failure')):
            with self.assertRaises(RuntimeError):
                self.apply(item(PwnCount=23456))
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.last().run.baseline_count, 1)
        self.apply(item(PwnCount=23456))
        self.assertEqual(self.last().run.updated_count, 1)
        self.assertEqual(self.counts()[-1], 1)

    def test_historical_scope_cannot_be_narrowed_even_if_scope_digest_recomputed(self):
        self.link_domain('second.example')
        self.configure(); self.apply(item(), item('Second', 'second.example'))
        from xti.adapters.sqlite_public_notice_watches import _hash, _json
        row = self.execute('SELECT id,scope_json FROM public_notice_watch_runs')[0]
        scope = json.loads(row[1]); scope['members'].pop()
        self.execute('UPDATE public_notice_watch_runs SET scope_json=?,scope_sha256=? WHERE id=?', (_json(scope), _hash(scope), row[0]))
        with self.assertRaises(StorageError):
            self.repository.run_show(row[0])

    def test_move_to_new_domain_shows_silent_departure_and_baseline_without_double_matching(self):
        self.configure(); self.apply()
        self.link_domain('new.example')
        self.apply(item(domain='new.example'))
        report = self.last()
        self.assertEqual((report.run.matched_count, report.run.baseline_count, report.run.removed_count), (1, 1, 1))
        self.assertEqual([(row.action, row.domain) for row in report.items],
                         [('baseline', 'new.example'), ('removed', 'example.com')])
        self.assertIsNone(report.items[0].before)
        self.assertEqual((report.items[1].before.domain, report.items[1].after.domain), ('example.com', 'new.example'))
        self.assertIsNone(report.notification_id)
        self.apply(item(domain='example.com'))
        report = self.last()
        self.assertEqual((report.run.updated_count, report.run.removed_count, report.run.matched_count), (1, 0, 1))
        self.assertEqual(len(report.items), 1)
        self.assertEqual((report.items[0].before.domain, report.items[0].after.domain), ('new.example', 'example.com'))

    def test_deleted_final_run_and_notification_or_baseline_is_detected_by_append_anchor(self):
        self.configure(); self.apply()
        self.apply(item(PwnCount=23456))
        latest = self.last()
        self.execute('DELETE FROM public_notice_watch_notifications WHERE run_id=?', (latest.run.id,))
        self.execute('DELETE FROM public_notice_watch_runs WHERE id=?', (latest.run.id,))
        with self.assertRaises(StorageError):
            self.source.validate()
        with self.assertRaises(StorageError):
            self.show()
        self.execute('DELETE FROM public_notice_watch_runs')
        with self.assertRaises(StorageError):
            self.source.status()

    def test_appending_after_failure_preserves_sequence_anchor(self):
        self.configure(); self.apply()
        original = self.counts()
        with patch('xti.adapters.sqlite_public_notice_watches.next_notification_sequence', side_effect=RuntimeError('Stop before commit')):
            with self.assertRaises(RuntimeError):
                self.apply(item(PwnCount=23456))
        self.assertEqual(self.counts(), original)
        self.apply(item(PwnCount=23456))
        self.assertEqual([run.sequence for run in reversed(self.show().runs)], [1, 2])

    def test_historical_run_configuration_survives_later_disable_and_reenable(self):
        self.configure(); self.apply()
        original = self.last()
        self.configure(False); self.configure(True)
        self.assertEqual(self.repository.run_show(original.run.id), original)
        self.assertEqual(self.show().watch.revision, 3)

    def test_middle_watch_event_deletion_fails_without_mutating_source(self):
        self.configure(); self.configure(False); self.configure(True)
        self.execute('DELETE FROM public_notice_watch_events WHERE revision=2')
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.source.validate()
        self.assertEqual(self.path.read_bytes(), before)

    def test_sqlite_backup_retains_valid_allocator_and_historical_evidence(self):
        self.configure(); self.apply(); self.apply(item(PwnCount=23456))
        original = self.last()
        restored = self.path.with_name('restored.db')
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(restored)) as destination:
            source.backup(destination)
        copied = SQLitePublicNoticeWatchRepository(restored)
        self.assertEqual(copied.run_show(original.run.id), original)
        SQLitePublicNoticeRepository(restored).validate()

    def test_scope_capacity_preflight_prevents_persisting_an_unreadable_snapshot(self):
        self.configure()
        original = self.counts()
        source = FakeSource()
        with patch('xti.adapters.sqlite_public_notice_watches._MAX_SCOPE_BYTES', 10):
            with self.assertRaises(StorageError):
                PublicNoticeService(self.source, source, clock=lambda: NOW).refresh()
            self.assertEqual(source.calls, 0)
            with self.assertRaises(StorageError):
                self.apply()
        self.assertEqual(self.counts(), original)

    def test_internal_processing_rejects_nonlatest_and_pre_enable_catalog_runs(self):
        from xti.adapters.sqlite_public_notice_watches import process_public_notice_watches
        first, second = self.apply(), self.apply(item(PwnCount=23456))
        self.repository.configure(self.organization.id, enabled=True, reason='Enable after historical source.',
                                  recorded_at=(NOW + timedelta(seconds=1)).isoformat())
        before = self.counts()
        for source_run in (first.run, second.run):
            with self.subTest(source=source_run.id):
                with self.storage._connection() as connection:
                    connection.execute('BEGIN IMMEDIATE')
                    with self.assertRaises(StorageError):
                        process_public_notice_watches(connection, source_run.id)
                    connection.rollback()
                self.assertEqual(self.counts(), before)
        with self.assertRaises(StorageError):
            self.apply(item(PwnCount=34567))
        self.assertEqual(self.counts(), before)

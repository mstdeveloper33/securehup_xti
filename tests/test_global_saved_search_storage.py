"""Frozen cross-family search history, stable identities and atomic notifications."""

from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
from xti.adapters.sqlite_global_search import read_global_search_snapshot
from xti.adapters.sqlite_brand_username_reviews import SQLiteBrandUsernameReviewRepository
from xti.application.brand_username_reviews import BrandUsernameReviewService
from xti.domain.assets import ValidationError
from xti.domain.global_search import GLOBAL_SEARCH_KINDS
from xti.domain.global_saved_searches import validate_snapshot_scope
from tests import test_global_search as fixtures
from tests.test_collection_watch_cli import github


class GlobalSavedSearchStorageTests(unittest.TestCase):
    invoke = fixtures.GlobalSearchTests.invoke
    result = fixtures.GlobalSearchTests.result
    files = fixtures.GlobalSearchTests.files
    add_social = fixtures.GlobalSearchTests.add_social
    collect = fixtures.GlobalSearchTests.collect
    notice = fixtures.GlobalSearchTests.notice
    save_notices = fixtures.GlobalSearchTests.save_notices
    save_claims = fixtures.GlobalSearchTests.save_claims
    supplier = fixtures.GlobalSearchTests.supplier
    entity = fixtures.GlobalSearchTests.entity
    ioc = fixtures.GlobalSearchTests.ioc
    create_case = fixtures.GlobalSearchTests.create_case

    def setUp(self):
        fixtures.GlobalSearchTests.setUp(self)
        self.saved = SQLiteGlobalSavedSearchRepository(self.database)

    def tick(self):
        self.now = max(self.now, datetime.now(timezone.utc)) + timedelta(seconds=1)
        return self.now.isoformat()

    def add(self, name='Example watch', query='example', *, kinds=GLOBAL_SEARCH_KINDS, include_inactive=False):
        return self.saved.upsert(name_key=name.casefold(), display_name=name, query=query,
            kinds=tuple(kinds), include_inactive=include_inactive, recorded_at=self.tick())

    def run_saved(self, search_id, *, offset=0, limit=500):
        return self.saved.run(search_id, executed_at=self.tick(), offset=offset, limit=limit)

    def seed(self):
        self.collect()
        watch = self.social.add('Example social', 'example', platforms=('GitHub',)).watch
        self.maigret.responses.append({'GitHub': github('example')})
        self.social.run(watch.id)
        self.save_claims()
        self.save_notices((self.notice(),))
        self.supplier()
        self.create_case('Example case')
        self.result('organizations', 'add', 'Example organization')
        self.entity('Example actor')
        self.ioc('example-malware.net')
        return watch

    def dump(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return tuple(connection.iterdump())

    def rows(self, table):
        with closing(sqlite3.connect(self.database)) as connection:
            return connection.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()

    def mutate(self, sql, values=()):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(sql, values)
            connection.commit()

    def test_ten_families_complete_baseline_and_unchanged_repeat_share_snapshot(self):
        self.seed()
        search = self.add().saved_search
        first = self.run_saved(search.id)
        self.assertEqual({item.after.result.kind for item in first.items}, set(GLOBAL_SEARCH_KINDS))
        self.assertEqual(first.run.total_count, len(first.items))
        self.assertIsNone(first.notification_id)
        self.assertIsNone(first.run.previous_run_id)
        second = self.run_saved(search.id)
        self.assertEqual(second.run.previous_run_id, first.run.id)
        self.assertEqual(second.run.unchanged_count, first.run.total_count)
        self.assertEqual((second.run.added_count, second.run.updated_count, second.run.removed_count), (0, 0, 0))
        self.assertEqual(second.run.snapshot_sha256, first.run.snapshot_sha256)
        self.assertEqual(len(self.rows('global_search_snapshots')), 1)
        self.assertEqual(self.rows('global_saved_search_notifications'), [])
        before = self.dump()
        self.assertEqual(self.saved.run_details(first.run.id, offset=0, limit=500), first)
        self.assertEqual(self.dump(), before)

    def test_social_source_refresh_keeps_identity_and_real_review_changes_state(self):
        watch = self.social.add('Example social', 'example', platforms=('GitHub',)).watch
        self.maigret.responses.append({'GitHub': github('example')})
        self.social.run(watch.id)
        search = self.add(kinds=('social',)).saved_search
        first = self.run_saved(search.id)
        self.maigret.responses.append({'GitHub': github('example')})
        self.social.run(watch.id)
        second = self.run_saved(search.id)
        old = next(item.after for item in first.items if item.after.result.record_type == 'social_profile')
        new = next(item.after for item in second.items if item.after.result.record_type == 'social_profile')
        self.assertEqual((old.key, old.state_sha256), (new.key, new.state_sha256))
        self.assertNotEqual(old.result.record_id, new.result.record_id)
        self.assertNotEqual(old.result.source_run_id, new.result.source_run_id)
        self.assertIsNone(second.notification_id)
        self.tick()
        reviews = BrandUsernameReviewService(SQLiteBrandUsernameReviewRepository(self.database), clock=lambda: self.now)
        reviews.decide(watch.id, 'GitHub', decision='known_official', reason='Resmî hesap olarak incelendi.')
        third = self.run_saved(search.id)
        self.assertEqual((third.run.added_count, third.run.updated_count, third.run.removed_count), (0, 1, 0))
        self.assertIsNotNone(third.notification_id)
        changed = next(item for item in third.items if item.action == 'updated')
        self.assertEqual(changed.before.key, changed.after.key)
        self.assertNotEqual(changed.before.state_sha256, changed.after.state_sha256)

    def test_repeated_snapshot_validates_scope_once_but_audits_every_run(self):
        search = self.add(kinds=('domain',)).saved_search
        for _ in range(20):
            last = self.run_saved(search.id)
        self.assertEqual(len(self.rows('global_search_snapshots')), 1)
        target = 'xti.adapters.sqlite_global_saved_searches.validate_snapshot_scope'
        with patch(target, wraps=validate_snapshot_scope) as validate:
            self.saved.run_details(last.run.id, offset=0, limit=1)
        self.assertEqual(validate.call_count, 1)
        self.mutate('UPDATE global_saved_search_runs SET diff_sha256=? WHERE id=?', ('0' * 64, last.run.id))
        with patch(target, wraps=validate_snapshot_scope) as validate:
            with self.assertRaises(StorageError):
                self.saved.run_details(last.run.id, offset=0, limit=1)
        self.assertEqual(validate.call_count, 1)
        self.mutate('UPDATE global_saved_search_runs SET diff_sha256=? WHERE id=?', (last.run.diff_sha256, last.run.id))
        self.saved.upsert(name_key=search.name_key, display_name='EXAMPLE WATCH', query=search.query,
            kinds=search.kinds, include_inactive=False, recorded_at=self.tick())
        changed = self.run_saved(search.id)
        self.assertEqual(changed.run.snapshot_sha256, last.run.snapshot_sha256)
        with patch(target, wraps=validate_snapshot_scope) as validate:
            self.saved.run_details(changed.run.id, offset=0, limit=1)
        self.assertEqual(validate.call_count, 2)

    def test_catalog_refresh_and_failed_attempt_do_not_create_semantic_notifications(self):
        self.save_claims()
        self.save_notices((self.notice(),))
        search = self.add(kinds=('ransomware', 'public-notice')).saved_search
        first = self.run_saved(search.id)
        self.save_claims()
        self.save_notices((self.notice(),))
        second = self.run_saved(search.id)
        self.assertEqual(second.run.unchanged_count, first.run.total_count)
        self.assertIsNone(second.notification_id)
        self.assertNotEqual(first.run.snapshot_sha256, second.run.snapshot_sha256)
        at = self.tick()
        self.tc_claims.record_failure(started_at=at, finished_at=at, error='Kontrollü kaynak kesintisi.')
        third = self.run_saved(search.id)
        self.assertEqual(third.run.unchanged_count, first.run.total_count)
        self.assertIsNone(third.notification_id)
        coverage = next(value for value in third.coverage if value.source == 'threatcluster')
        self.assertEqual(coverage.latest_run_status, 'failed')
        self.assertNotEqual(coverage.latest_run_id, coverage.latest_success_run_id)

    def test_removed_only_is_silent_and_changed_current_match_notifies_once(self):
        self.save_notices((self.notice('ExampleOne'), self.notice('ExampleTwo')))
        search = self.add(kinds=('public-notice',)).saved_search
        first = self.run_saved(search.id)
        self.save_notices((self.notice('ExampleOne'),))
        removed = self.run_saved(search.id)
        self.assertEqual((removed.run.total_count, removed.run.removed_count), (1, 1))
        self.assertIsNone(removed.notification_id)
        missing = next(item for item in removed.items if item.action == 'removed')
        self.assertIsNotNone(missing.before)
        self.assertIsNone(missing.after)
        self.save_notices((replace(self.notice('ExampleOne'), pwn_count=100),))
        changed = self.run_saved(search.id)
        self.assertEqual(changed.run.updated_count, 1)
        self.assertIsNotNone(changed.notification_id)
        repeated = self.run_saved(search.id)
        self.assertIsNone(repeated.notification_id)
        self.assertEqual(len(self.rows('global_saved_search_notifications')), 1)
        self.assertEqual(self.saved.run_details(first.run.id, offset=0, limit=500), first)

    def test_notice_category_order_preserves_proof_without_semantic_notification(self):
        notice = replace(self.notice(), data_classes=('Email addresses', 'Passwords'))
        self.save_notices((notice,))
        search = self.add(kinds=('public-notice',)).saved_search
        first = self.run_saved(search.id)
        reordered = replace(notice, data_classes=tuple(reversed(notice.data_classes)))
        self.save_notices((reordered,))
        second = self.run_saved(search.id)
        self.assertEqual((second.run.unchanged_count, second.run.updated_count), (1, 0))
        self.assertIsNone(second.notification_id)
        self.assertEqual(first.items[0].after.state_sha256, second.items[0].after.state_sha256)
        self.assertNotEqual(first.items[0].after.result.details, second.items[0].after.result.details)
        self.assertNotEqual(first.run.snapshot_sha256, second.run.snapshot_sha256)
        self.save_notices((replace(reordered, data_classes=('Passwords',)),))
        changed = self.run_saved(search.id)
        self.assertEqual(changed.run.updated_count, 1)
        self.assertIsNotNone(changed.notification_id)
        self.assertEqual(self.saved.run_details(first.run.id, offset=0, limit=500), first)

    def test_definition_changes_back_and_reactivation_are_new_silent_baselines(self):
        original = self.add(query='example', kinds=('domain',)).saved_search
        first = self.run_saved(original.id)
        self.add(query='other', kinds=('domain',))
        self.add(query='example', kinds=('domain',))
        reset = self.run_saved(original.id)
        self.assertIsNone(reset.run.previous_run_id)
        self.assertIsNone(reset.notification_id)
        self.assertNotEqual(reset.run.event_id, first.run.event_id)
        self.saved.disable(original.id, reason='Geçici olarak kapat.', recorded_at=self.tick())
        with self.assertRaises(ValidationError):
            self.run_saved(original.id)
        self.assertEqual(self.add(query='example', kinds=('domain',)).action, 'reactivated')
        resumed = self.run_saved(original.id)
        self.assertIsNone(resumed.run.previous_run_id)
        self.assertIsNone(resumed.notification_id)
        self.assertEqual(self.saved.run_details(first.run.id, offset=0, limit=500).saved_search, original)
        details = self.saved.details(original.id, event_offset=0, event_limit=2, run_offset=0, run_limit=1)
        self.assertEqual((details.total_event_count, details.total_run_count), (5, 3))
        self.assertTrue(details.has_more_events)
        self.assertTrue(details.has_more_runs)

    def test_all_historical_items_and_search_definitions_are_pageable(self):
        self.seed()
        search = self.add().saved_search
        full = self.run_saved(search.id)
        pages = [self.saved.run_details(full.run.id, offset=offset, limit=2)
                 for offset in range(0, full.total_item_count + 2, 2)]
        self.assertEqual([item for page in pages for item in page.items], list(full.items))
        self.assertTrue(all(page.total_item_count == full.total_item_count for page in pages))
        self.assertFalse(pages[-1].has_more)
        self.assertEqual(pages[-1].items, ())
        self.add(name='Another watch', kinds=('domain',))
        first = self.saved.list(active_only=True, offset=0, limit=1)
        second = self.saved.list(active_only=True, offset=1, limit=1)
        self.assertEqual((first.total_count, second.total_count), (2, 2))
        self.assertTrue(first.has_more)
        self.assertFalse(second.has_more)
        self.assertNotEqual(first.items[0].saved_search.id, second.items[0].saved_search.id)

    def test_notification_fault_rolls_back_run_and_new_snapshot(self):
        search = self.add(kinds=('domain',)).saved_search
        self.run_saved(search.id)
        SQLiteAssetRepository(self.database).add('another-example.com')
        before = self.dump()
        with patch('xti.adapters.sqlite_global_saved_searches.next_notification_sequence',
                   side_effect=RuntimeError('Injected notification failure')):
            with self.assertRaisesRegex(RuntimeError, 'Injected'):
                self.run_saved(search.id)
        self.assertEqual(self.dump(), before)
        result = self.run_saved(search.id)
        self.assertEqual(result.run.added_count, 1)
        self.assertIsNotNone(result.notification_id)

    def test_writer_lock_covers_source_read_and_history_save_in_one_connection(self):
        search = self.add(kinds=('domain',)).saved_search
        original = self.saved._storage._connection
        openings, statements, attempted = [], [], []

        @contextmanager
        def traced(**options):
            openings.append(options)
            with original(**options) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        def interleave(connection, *args, **kwargs):
            self.assertTrue(connection.in_transaction)
            with closing(sqlite3.connect(self.database, timeout=0)) as writer:
                with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                    writer.execute("UPDATE assets SET value='changed.example' WHERE value='example.com'")
                attempted.append(True)
            return read_global_search_snapshot(connection, *args, **kwargs)

        with patch.object(self.saved._storage, '_connection', traced), patch(
            'xti.adapters.sqlite_global_saved_searches.read_global_search_snapshot', side_effect=interleave):
            report = self.run_saved(search.id)
        self.assertEqual(attempted, [True])
        self.assertEqual(len(openings), 1)
        self.assertEqual(sum(value == 'BEGIN IMMEDIATE' for value in statements), 1)
        self.assertEqual(report.items[0].after.result.display_value, 'example.com')

    def test_corrupt_snapshot_definition_run_chain_or_missing_notification_fail_closed(self):
        search = self.add(kinds=('domain',)).saved_search
        first = self.run_saved(search.id)
        SQLiteAssetRepository(self.database).add('another-example.com')
        second = self.run_saved(search.id)
        changes = (
            ('global_search_snapshots', 'payload_json', '{"broken":true}', 'sha256', first.run.snapshot_sha256),
            ('global_saved_search_events', 'definition_sha256', '0' * 64, 'id', first.run.event_id),
            ('global_saved_search_runs', 'previous_run_id', None, 'id', second.run.id),
            ('global_saved_search_runs', 'diff_sha256', '0' * 64, 'id', first.run.id),
        )
        for table, column, value, key, identifier in changes:
            with self.subTest(table=table, column=column):
                with closing(sqlite3.connect(self.database)) as connection:
                    old = connection.execute(f'SELECT {column} FROM {table} WHERE {key}=?', (identifier,)).fetchone()[0]
                self.mutate(f'UPDATE {table} SET {column}=? WHERE {key}=?', (value, identifier))
                before = self.dump()
                with self.assertRaises(StorageError):
                    self.saved.run_details(second.run.id, offset=0, limit=1)
                self.assertEqual(self.dump(), before)
                self.mutate(f'UPDATE {table} SET {column}=? WHERE {key}=?', (old, identifier))
        self.mutate('DELETE FROM global_saved_search_notifications WHERE id=?', (second.notification_id,))
        with self.assertRaises(StorageError):
            self.saved.list(active_only=True, offset=0, limit=50)

    def test_history_payload_limit_is_checked_before_json_materialization(self):
        search = self.add(kinds=('domain',)).saved_search
        first = self.run_saved(search.id)
        before = self.dump()
        with patch('xti.adapters.sqlite_global_saved_searches.MAX_WATCH_TOTAL_SNAPSHOT_BYTES', 1), patch(
            'xti.adapters.sqlite_global_saved_searches.snapshot_from_json', side_effect=AssertionError('No payload parsing')):
            with self.assertRaisesRegex(StorageError, 'boyut sınırını'):
                self.saved.run_details(first.run.id, offset=0, limit=1)
        self.assertEqual(self.dump(), before)
        with patch('xti.adapters.sqlite_global_saved_searches.MAX_WATCH_RUNS', 1):
            with self.assertRaises(StorageError):
                self.run_saved(search.id)
        self.assertEqual(self.dump(), before)

    def test_new_snapshot_source_row_and_byte_limits_fail_without_partial_history(self):
        SQLiteAssetRepository(self.database).add('another-example.com')
        search = self.add(kinds=('domain',)).saved_search
        before = self.dump()
        for target, value in (
            ('xti.adapters.sqlite_global_search.MAX_SEARCH_ROWS', 1),
            ('xti.domain.global_saved_searches.MAX_WATCH_SNAPSHOT_BYTES', 1),
            ('xti.adapters.sqlite_global_saved_searches.MAX_WATCH_TOTAL_SNAPSHOT_BYTES', 1),
        ):
            with self.subTest(target=target), patch(target, value):
                with self.assertRaises(StorageError):
                    self.run_saved(search.id)
            self.assertEqual(self.dump(), before)
        self.assertEqual(len(self.run_saved(search.id).items), 2)

    def test_malformed_current_source_maps_to_storage_failure_without_writes(self):
        search = self.add(kinds=('domain',)).saved_search
        self.mutate("UPDATE assets SET value='bad domain' WHERE value='example.com'")
        before = self.dump()
        with self.assertRaisesRegex(StorageError, 'kaynak kanıtı bozuk'):
            self.run_saved(search.id)
        self.assertEqual(self.dump(), before)

    def test_historical_read_uses_frozen_evidence_not_current_source_records(self):
        self.save_notices((self.notice(),))
        search = self.add(kinds=('public-notice',)).saved_search
        first = self.run_saved(search.id)
        self.save_notices((replace(self.notice(), title='Changed current title'),))
        self.add(query='Changed', kinds=('public-notice',))
        self.mutate('UPDATE public_notice_changes SET state_sha256=?', ('0' * 64,))
        before = self.dump()
        self.assertEqual(self.saved.run_details(first.run.id, offset=0, limit=500), first)
        with self.assertRaises(StorageError):
            self.run_saved(search.id)
        self.assertEqual(self.dump(), before)

    def test_missing_store_reads_never_initialize(self):
        missing = self.data.parent / 'missing' / 'xti.db'
        with patch.object(SQLiteAssetRepository, 'initialize', side_effect=AssertionError('No initialization')):
            with self.assertRaises(StorageError):
                SQLiteGlobalSavedSearchRepository(missing).list(active_only=True, offset=0, limit=1)
        self.assertFalse(missing.parent.exists())


if __name__ == '__main__':
    unittest.main()

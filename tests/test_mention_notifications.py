"""Exact source scope, crash-safe inbox handoff and historical v1 compatibility."""

from contextlib import closing
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_mention_notifications import SQLiteMentionNotificationBridge
from xti.adapters.sqlite_mentions import SQLiteMentionRepository
from xti.domain.assets import ValidationError
from xti.domain.global_saved_searches import (
    GLOBAL_SEARCH_WATCH_VERSION, MENTION_SCOPED_WATCH_VERSION, GlobalSavedSearch,
    canonical_json, definition_json, definition_from_json,
)
from xti.domain.mentions import MentionRequest, MentionResponse, build_query, request_key
from tests.test_mentions_integration import hit, request


class MentionScopedDefinitionTests(unittest.TestCase):
    def test_legacy_definition_bytes_and_hash_input_are_exactly_unchanged(self):
        value = GlobalSavedSearch(str(uuid4()), 'my search', 'My Search', 'example',
            ('mention',), False, True, 1, '2026-11-16T12:00:00+00:00', '2026-11-16T12:00:00+00:00')
        old = asdict(value)
        del old['mention_request_key']
        previous = canonical_json({'rule_version': GLOBAL_SEARCH_WATCH_VERSION, 'search': old})
        self.assertEqual(definition_json(value), previous)
        self.assertEqual(definition_from_json(previous), value)
        with self.assertRaises(ValueError):
            definition_from_json(canonical_json({'rule_version': GLOBAL_SEARCH_WATCH_VERSION,
                                                'search': asdict(value)}))

    def test_v2_requires_a_single_exact_mention_scope_and_roundtrips(self):
        scope = request_key(request())
        value = GlobalSavedSearch(str(uuid4()), 'managed search', 'Managed Search', scope,
            ('mention',), False, True, 1, '2026-11-16T12:00:00+00:00', '2026-11-16T12:00:00+00:00', scope)
        self.assertEqual(definition_from_json(definition_json(value)), value)
        self.assertIn(MENTION_SCOPED_WATCH_VERSION, definition_json(value))
        for changed in (replace(value, query='Example'), replace(value, kinds=('news',)),
                        replace(value, include_inactive=True), replace(value, mention_request_key='bad')):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                definition_from_json(definition_json(changed))


class MentionNotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'data' / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.mentions = SQLiteMentionRepository(self.path)
        self.bridge = SQLiteMentionNotificationBridge(self.path)
        self.watches = SQLiteGlobalSavedSearchRepository(self.path)
        self.inbox = SQLiteInboxRepository(self.path)
        self.group_id = str(uuid4())
        self.now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
        self.target = request(kind='organization')
        self.addCleanup(patch.stopall)
        patch('socket.socket.connect', side_effect=AssertionError('No network')).start()
        patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')).start()

    def tick(self):
        self.now += timedelta(seconds=1)
        return self.now.isoformat()

    def save(self, *hits, selected=None, failure=False):
        selected = selected or self.target
        at = self.tick()
        if failure:
            return self.mentions.record_failure(selected, error='Controlled source failure',
                started_at=at, finished_at=at)
        return self.mentions.apply(selected, MentionResponse(build_query(selected.target),
            'provider-request', tuple(hits), 1), started_at=at, finished_at=at)

    def notify(self, source, *, group_id=None, selected=None, operation_id=None):
        return self.bridge.notify(group_id=group_id or self.group_id,
            request=selected or source.request, mention_run_id=source.id,
            operation_id=operation_id or str(uuid4()), executed_at=self.tick())

    def test_exact_scope_excludes_same_name_other_target_and_poisoned_result_text(self):
        selected = self.save(hit())
        other = replace(self.target, target=replace(self.target.target, id=str(uuid4())))
        self.save(hit(title='Other result ' + request_key(self.target)), selected=other)
        report = self.notify(selected)
        self.assertEqual(report.run.total_count, 1)
        self.assertEqual(report.items[0].after.result.matched_field, 'mention_request_key')
        self.assertEqual(report.saved_search.mention_request_key, request_key(self.target))
        self.assertEqual(report.coverage[0].latest_run_id, selected.id)
        self.assertEqual(report.coverage[0].latest_success_run_id, selected.id)
        self.assertIsNone(report.notification_id)
        self.assertEqual(self.inbox.list('all').total_count, 0)

    def test_new_changed_same_and_rank_only_results_use_existing_inbox(self):
        self.notify(self.save(hit()))
        changed = self.notify(self.save(hit(title='Changed article'), hit(url='https://publisher.example/new')))
        self.assertEqual((changed.run.added_count, changed.run.updated_count), (1, 1))
        self.assertIsNotNone(changed.notification_id)
        details = self.inbox.get(changed.notification_id)
        self.assertEqual(details.global_search_change, changed)
        self.assertEqual(details.notification.global_search_run_id, changed.run.id)
        same = self.notify(self.save(hit(title='Changed article', score=0.01)))
        self.assertEqual((same.run.total_count, same.run.unchanged_count, same.run.removed_count), (2, 2, 0))
        self.assertIsNone(same.notification_id)
        empty = self.notify(self.save())
        self.assertEqual((empty.run.total_count, empty.run.removed_count), (2, 0))
        self.assertIsNone(empty.notification_id)
        self.assertEqual(self.inbox.list('all').total_count, 1)
        self.inbox.mark((changed.notification_id,), True, self.tick())
        self.assertEqual(self.inbox.list('unread').unread_count, 0)
        self.assertEqual(self.watches.run_details(changed.run.id, offset=0, limit=50), changed)

    def test_empty_first_success_is_silent_then_first_result_notifies(self):
        baseline = self.notify(self.save())
        self.assertIsNone(baseline.notification_id)
        report = self.notify(self.save(hit()))
        self.assertEqual(report.run.added_count, 1)
        self.assertIsNotNone(report.notification_id)

    def test_same_operation_returns_frozen_report_after_later_sources_without_writes(self):
        self.notify(self.save(hit()))
        source, operation_id = self.save(hit(title='Changed')), str(uuid4())
        original = self.notify(source, operation_id=operation_id)
        self.save(hit(title='Later current article'))
        before = self.path.read_bytes()
        repeated = self.notify(source, operation_id=operation_id)
        self.assertEqual(repeated, original)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.inbox.list('all').total_count, 1)

    def test_operation_scope_group_and_source_conflicts_are_rejected_without_writes(self):
        source, operation_id = self.save(hit()), str(uuid4())
        self.notify(source, operation_id=operation_id)
        other = self.save(hit())
        altered = replace(self.target, topic='news')
        before = self.path.read_bytes()
        for kwargs in ({'group_id': str(uuid4())}, {'selected': altered}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                self.notify(source, operation_id=operation_id, **kwargs)
        with self.assertRaises(ValidationError):
            self.notify(other, operation_id=operation_id)
        self.assertEqual(self.path.read_bytes(), before)

    def test_failure_wrong_request_and_unknown_source_do_not_create_a_baseline(self):
        failure = self.save(failure=True)
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.notify(failure)
        self.assertEqual(self.path.read_bytes(), before)
        successful = self.save(hit())
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.notify(successful, selected=replace(self.target, topic='news'))
        with self.assertRaises(ValidationError):
            self.notify(replace(successful, id=str(uuid4())))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.watches.list(active_only=True, offset=0, limit=50).total_count, 0)

    def test_delayed_notification_reads_exact_historical_source_cutoff(self):
        first = self.save(hit(title='First source article'))
        later = self.save(hit(title='Later source article'))
        self.save(failure=True)
        baseline = self.notify(first)
        self.assertEqual(baseline.items[0].after.result.display_value, 'First source article')
        self.assertEqual(baseline.coverage[0].latest_run_id, first.id)
        changed = self.notify(later)
        self.assertEqual(changed.items[0].before.result.display_value, 'First source article')
        self.assertEqual(changed.items[0].after.result.display_value, 'Later source article')
        self.assertEqual(changed.coverage[0].latest_run_id, later.id)
        self.assertIsNotNone(changed.notification_id)

    def test_out_of_order_source_or_second_operation_for_same_source_rejected(self):
        first = self.save(hit())
        later = self.save(hit(title='Later'))
        self.notify(later)
        before = self.path.read_bytes()
        for source in (first, later):
            with self.subTest(source=source.id), self.assertRaises(ValidationError):
                self.notify(source)
        self.assertEqual(self.path.read_bytes(), before)

    def test_group_scopes_have_independent_quiet_baselines(self):
        source = self.save(hit())
        first = self.notify(source)
        second = self.notify(source, group_id=str(uuid4()))
        self.assertNotEqual(first.saved_search.id, second.saved_search.id)
        self.assertEqual((first.run.previous_run_id, second.run.previous_run_id), (None, None))
        self.assertEqual(self.inbox.list('all').total_count, 0)

    def test_notification_failure_rolls_back_comparison_and_binding_then_retry_once(self):
        self.notify(self.save(hit()))
        source, operation_id = self.save(hit(title='Changed')), str(uuid4())
        before = self.path.read_bytes()
        with patch('xti.adapters.sqlite_global_saved_searches.next_notification_sequence',
                   side_effect=StorageError('Controlled inbox failure')):
            with self.assertRaises(StorageError):
                self.notify(source, operation_id=operation_id)
        self.assertEqual(self.path.read_bytes(), before)
        result = self.notify(source, operation_id=operation_id)
        self.assertIsNotNone(result.notification_id)
        self.assertEqual(self.notify(source, operation_id=operation_id), result)
        self.assertEqual(self.inbox.list('all').total_count, 1)

    def test_disabled_managed_watch_is_not_silently_reenabled_or_overwritten(self):
        source, operation_id = self.save(hit()), str(uuid4())
        original = self.notify(source, operation_id=operation_id)
        watch = original.saved_search
        self.watches.disable(watch.id, reason='Paused explicitly', recorded_at=self.tick())
        source2 = self.save(hit(title='Changed'))
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.notify(source2)
        with self.assertRaises(ValidationError):
            self.watches.upsert(name_key=watch.name_key, display_name=watch.display_name,
                query='different', kinds=('mention',), include_inactive=False, recorded_at=self.tick())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.notify(source, operation_id=operation_id), original)

    def test_generic_run_id_is_idempotent_and_rejects_a_changed_query_scope(self):
        self.storage.add('example.com')
        watch = self.watches.upsert(name_key='example', display_name='Example', query='example',
            kinds=('domain',), include_inactive=False, recorded_at=self.tick()).saved_search
        identifier = str(uuid4())
        baseline = self.watches.run(watch.id, executed_at=self.tick(), offset=0, limit=50, run_id=identifier)
        self.storage.add('other.example')
        before = self.path.read_bytes()
        repeated = self.watches.run(watch.id, executed_at=self.tick(), offset=0, limit=50, run_id=identifier)
        self.assertEqual(repeated, baseline)
        self.assertEqual(self.path.read_bytes(), before)
        self.watches.upsert(name_key='example', display_name='Example', query='other',
            kinds=('domain',), include_inactive=False, recorded_at=self.tick())
        with self.assertRaises(ValidationError):
            self.watches.run(watch.id, executed_at=self.tick(), offset=0, limit=50, run_id=identifier)

    def test_generic_run_cannot_advance_a_group_owned_baseline_or_block_pending_receipt(self):
        original = self.notify(self.save(hit()))
        source = self.save(hit(title='Pending group change'))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValidationError, 'firma grubu'):
            self.watches.run(original.saved_search.id, executed_at=self.tick(), offset=0, limit=50)
        self.assertEqual(self.path.read_bytes(), before)
        report = self.notify(source)
        self.assertEqual(report.run.updated_count, 1)
        self.assertIsNotNone(report.notification_id)
        self.assertEqual(report.run.previous_run_id, original.run.id)

    def test_user_disable_and_monitor_cannot_mutate_group_owned_search(self):
        from xti.adapters.worker_lock import LocalExecutionLock
        from xti.application.global_saved_searches import GlobalSavedSearchService
        from xti.application.global_saved_search_monitor import GlobalSavedSearchMonitor
        first = self.notify(self.save(hit()))
        source = self.save(hit(title='Group managed update'))
        service = GlobalSavedSearchService(self.watches, LocalExecutionLock(self.path), clock=lambda: self.now)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValidationError, 'mentions groups disable'):
            service.disable(first.saved_search.id, reason='Use owning group instead')
        with self.assertRaisesRegex(ValidationError, 'mentions groups monitor'):
            GlobalSavedSearchMonitor(service).run(first.saved_search.id)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIsNotNone(self.notify(source).notification_id)

    def test_legacy_fixture_refuses_to_remove_typed_scope_without_mutation(self):
        from tests.mention_groups_legacy_fixture import remove_mention_group_schema
        scope = request_key(self.target)
        self.watches.upsert(name_key='typed scope', display_name='Typed Scope', query=scope,
            kinds=('mention',), include_inactive=False, recorded_at=self.tick(), mention_request_key=scope)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            before = connection.execute('SELECT type,name,sql FROM sqlite_schema ORDER BY name').fetchall()
            with self.assertRaisesRegex(ValueError, 'typed search scope'):
                remove_mention_group_schema(connection)
            self.assertEqual(connection.execute('SELECT type,name,sql FROM sqlite_schema ORDER BY name').fetchall(), before)

    def test_corrupt_operation_binding_fails_closed(self):
        first = self.save(hit())
        self.notify(first)
        second = self.save(hit(title='Changed'))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE mention_notification_operations SET request_key=?', ('a' * 64,))
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.notify(second)
        self.assertEqual(self.path.read_bytes(), before)

    def test_backup_restore_keeps_frozen_notices_read_state_and_idempotency(self):
        self.notify(self.save(hit()))
        source, operation_id = self.save(hit(title='Changed')), str(uuid4())
        report = self.notify(source, operation_id=operation_id)
        self.inbox.mark((report.notification_id,), True, self.tick())
        old = self.inbox.get(report.notification_id)
        backup, restored = self.root / 'backup.db', self.root / 'restored' / 'xti.db'
        self.storage.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteInboxRepository(restored).get(report.notification_id), old)
        bridge = SQLiteMentionNotificationBridge(restored)
        self.assertEqual(bridge.notify(group_id=self.group_id, request=source.request,
            mention_run_id=source.id, operation_id=operation_id, executed_at=self.tick()), report)

    def test_inbox_terminal_explains_company_scope_without_presenting_hash_as_query(self):
        from xti.interfaces.inbox import page_lines, detail_lines
        self.notify(self.save(hit()))
        report = self.notify(self.save(hit(title='New title')))
        page = '\n'.join(page_lines(self.inbox.list('all'), status='all', next_command=None))
        detail = '\n'.join(detail_lines(self.inbox.get(report.notification_id)))
        self.assertIn('Firma/tedarikçi içerikleri değişti', page)
        self.assertIn('Kaydedilmiş Tavily çalışmasının kanıtı karşılaştırıldı', detail)
        self.assertNotIn(request_key(self.target), page)
        self.assertNotIn(request_key(self.target), detail)
        self.assertIn('search-watch run-show ' + report.run.id, detail)

    def test_preflight_is_read_only_and_rejects_disabled_scope_or_name_collision(self):
        before = self.path.read_bytes()
        self.bridge.validate(group_id=self.group_id, requests=(self.target,))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.watches.list(active_only=True, offset=0, limit=50).total_count, 0)
        report = self.notify(self.save(hit()))
        self.watches.disable(report.saved_search.id, reason='Explicit pause', recorded_at=self.tick())
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.bridge.validate(group_id=self.group_id, requests=(self.target,))
        self.assertEqual(self.path.read_bytes(), before)
        from xti.adapters.sqlite_mention_notifications import _watch_name
        another_group = str(uuid4())
        name = _watch_name(another_group, self.target)
        self.watches.upsert(name_key=name.casefold(), display_name=name, query='unrelated',
            kinds=('domain',), include_inactive=False, recorded_at=self.tick())
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.bridge.validate(group_id=another_group, requests=(self.target,))
        self.assertEqual(self.path.read_bytes(), before)

    def test_preflight_rejects_known_count_and_minimum_byte_limits_without_writes(self):
        self.notify(self.save(hit()))
        before = self.path.read_bytes()
        for name, maximum in (('MAX_WATCHES', 1), ('MAX_WATCH_EVENTS', 1),
                              ('MAX_WATCH_RUNS', 1), ('MAX_WATCH_TOTAL_SNAPSHOT_BYTES', 1),
                              ('MAX_WATCH_SNAPSHOT_BYTES', 1)):
            with self.subTest(limit=name), patch('xti.adapters.sqlite_mention_notifications.' + name, maximum):
                with self.assertRaises(StorageError):
                    self.bridge.validate(group_id=str(uuid4()), requests=(self.target,))
            self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(ValidationError):
            self.bridge.validate(group_id=self.group_id, requests=(self.target, self.target))
        self.assertEqual(self.path.read_bytes(), before)

    def test_group_disabled_watch_preflight_stops_before_credentials_and_metered_fetch(self):
        from tests.test_mention_groups_service import MentionGroupServiceTests
        fixture = MentionGroupServiceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        first = fixture.service.run(fixture.group.id)['run']
        attempt = first.attempts[0]
        watch_run = SQLiteGlobalSavedSearchRepository(fixture.path).run_details(
            attempt.notification_run_id, offset=0, limit=50)
        fixture.now += timedelta(seconds=1)
        SQLiteGlobalSavedSearchRepository(fixture.path).disable(watch_run.saved_search.id,
            reason='Explicitly pause managed search', recorded_at=fixture.now.isoformat())
        fixture.now += timedelta(hours=1)
        fixture.factory.reset_mock()
        fixture.source.fetch.reset_mock()
        before = fixture.path.read_bytes()
        with self.assertRaises(ValidationError):
            fixture.service.run(fixture.group.id)
        fixture.factory.assert_not_called()
        fixture.source.fetch.assert_not_called()
        self.assertEqual(fixture.path.read_bytes(), before)
        self.assertEqual(len(fixture.repository.runs(fixture.group.id)), 1)
        self.assertEqual(fixture.repository.budget(fixture.group.id,
            at=fixture.now.isoformat()).used_queries, 2)


if __name__ == '__main__':
    unittest.main()

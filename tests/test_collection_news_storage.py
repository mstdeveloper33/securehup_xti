"""Atomic source/receipt writes, historical notification scope and retry safety."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_collection_news import SQLiteCollectionNewsSearches
from xti.adapters.sqlite_collection_receipts import record_collection_step_receipt
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
from xti.adapters.sqlite_news import SQLiteNewsRepository, read_news_catalog
from xti.domain.assets import ValidationError
from xti.domain.collection_history import CollectionFrozenPlan, CollectionFrozenUnit
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.global_saved_searches import GLOBAL_SEARCH_WATCH_VERSION
from xti.domain.news import NEWS_POLICY, NewsFeed
from tests.test_news_storage import article

SOURCES = ('cisa', 'ncsc', 'cert-fr')


class CollectionNewsStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.storage.add('example.com')
        self.clock = datetime(2026, 11, 16, tzinfo=timezone.utc)
        self.history = SQLiteCollectionHistoryRepository(self.path)
        self.news = SQLiteNewsRepository(self.path)
        self.watches = SQLiteGlobalSavedSearchRepository(self.path)
        self.bridge = SQLiteCollectionNewsSearches(self.path)
        self.search = self.watches.upsert(name_key='example', display_name='Example', query='example',
            kinds=('news',), include_inactive=False, recorded_at=self.tick()).saved_search
        self.target, = self.bridge.plan((self.search.id,))
        self.definition = CollectionProfileDefinition('example.com', task_ids=(),
            news_sources=SOURCES, search_watch_ids=(self.search.id,))
        self.plan = CollectionFrozenPlan(self.definition, tuple(
            CollectionFrozenUnit('news-refresh:' + source, 'news_refresh', source, 'example.com', None, NEWS_POLICY)
            for source in SOURCES) + (CollectionFrozenUnit('search-watch:' + self.search.id, 'search_watch',
                'local', 'example.com', self.target, GLOBAL_SEARCH_WATCH_VERSION),))
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network in storage tests')))

    def tick(self):
        self.clock += timedelta(seconds=1)
        return self.clock.isoformat()

    def begin(self):
        return self.history.begin(self.plan, started_at=self.tick())

    def source(self, source, *, operation=None, key='one', failure=False):
        at = self.tick()
        if failure:
            return self.news.record_failure(source, started_at=at, finished_at=at,
                                            error='Publisher unavailable', operation=operation)
        return self.news.apply(NewsFeed(source, at, 'a' * 64, (article(key, source=source),)),
                               started_at=at, finished_at=at, operation=operation).run

    def refresh(self, details):
        result = {}
        for step in details.steps[:3]:
            operation = self.history.start_step(details.session.id, step.id, started_at=self.tick())
            result[step.source] = self.source(step.source, operation=operation).id
        return result

    def search_operation(self, details):
        return self.history.start_step(details.session.id, details.steps[-1].id, started_at=self.tick())

    def counts(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return tuple(connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in (
                'news_runs', 'news_snapshots', 'news_articles', 'global_saved_search_runs',
                'global_saved_search_notifications', 'collection_step_receipts'))

    def test_source_success_and_failure_roll_back_with_receipt_failure(self):
        details = self.begin()
        operation = self.history.start_step(details.session.id, details.steps[0].id, started_at=self.tick())
        original = self.counts()
        def fail(connection, token, **arguments):
            record_collection_step_receipt(connection, token, **arguments)
            self.assertEqual(self.counts(), original)
            raise RuntimeError('Controlled post-receipt failure')
        for failure in (False, True):
            with self.subTest(failure=failure), patch('xti.adapters.sqlite_news.record_collection_step_receipt', side_effect=fail):
                with self.assertRaises(RuntimeError):
                    self.source('cisa', operation=operation, failure=failure)
            self.assertEqual(self.counts(), original)
            self.assertEqual(self.history.get(details.session.id).steps[0].status, 'running')

    def test_wrong_source_operation_fails_without_writing(self):
        details = self.begin()
        operation = self.history.start_step(details.session.id, details.steps[0].id, started_at=self.tick())
        original = self.counts()
        with self.assertRaises(ValidationError):
            self.news.validate_operation('ncsc', operation)
        with self.assertRaises(ValidationError):
            self.source('ncsc', operation=operation)
        self.assertEqual(self.counts(), original)

    def test_notification_uses_exact_source_cutoffs_and_retry_is_idempotent(self):
        details = self.begin()
        cutoffs = self.refresh(details)
        operation = self.search_operation(details)
        later = self.source('cisa', key='later')
        report = self.bridge.run(self.target, operation=operation, executed_at=self.tick())
        self.assertEqual(report.run.total_count, 3)
        self.assertEqual({item.source: item.latest_run_id for item in report.coverage}, cutoffs)
        self.assertNotIn(later.id, {item.after.result.source_run_id for item in report.items})
        original = self.counts()
        repeated = self.bridge.run(self.target, operation=operation, executed_at=self.tick())
        self.assertEqual(repeated, report)
        self.assertEqual(self.counts(), original)
        self.assertEqual(self.history.get(details.session.id).receipts[-1].result_id, report.run.id)
        with closing(sqlite3.connect(self.path)) as connection:
            catalog = read_news_catalog(connection, through_run_ids=cutoffs)
        self.assertEqual(len(catalog.articles), 3)
        self.assertEqual(len(self.news.catalog().articles), 4)

    def test_search_snapshot_inbox_and_receipt_roll_back_together(self):
        self.watches.run(self.search.id, executed_at=self.tick(), offset=0, limit=20)
        details = self.begin()
        self.refresh(details)
        operation = self.search_operation(details)
        original = self.counts()
        def fail(connection, token, **arguments):
            record_collection_step_receipt(connection, token, **arguments)
            self.assertEqual(self.counts(), original)
            raise RuntimeError('Controlled atomic notification failure')
        with patch('xti.adapters.sqlite_collection_news.record_collection_step_receipt', side_effect=fail):
            with self.assertRaises(RuntimeError):
                self.bridge.run(self.target, operation=operation, executed_at=self.tick())
        self.assertEqual(self.counts(), original)
        report = self.bridge.run(self.target, operation=operation, executed_at=self.tick())
        self.assertIsNotNone(report.notification_id)
        self.assertEqual(self.counts()[4], 1)

    def test_changed_definition_and_return_to_old_values_reject_old_collection(self):
        details = self.begin()
        self.refresh(details)
        operation = self.search_operation(details)
        self.watches.upsert(name_key='example', display_name='Example', query='changed', kinds=('news',),
                            include_inactive=False, recorded_at=self.tick())
        original = self.counts()
        with self.assertRaises(ValidationError):
            self.bridge.run(self.target, operation=operation, executed_at=self.tick())
        self.assertEqual(self.counts(), original)
        self.watches.upsert(name_key='example', display_name='Example', query='example', kinds=('news',),
                            include_inactive=False, recorded_at=self.tick())
        with self.assertRaises(ValidationError):
            self.bridge.run(self.target, operation=operation, executed_at=self.tick())
        self.assertEqual(self.counts(), original)

    def test_disable_and_reactivate_identical_watch_rejects_frozen_event(self):
        details = self.begin()
        self.refresh(details)
        operation = self.search_operation(details)
        self.watches.disable(self.search.id, reason='Temporarily disabled', recorded_at=self.tick())
        self.watches.upsert(name_key='example', display_name='Example', query='example', kinds=('news',),
                            include_inactive=False, recorded_at=self.tick())
        original = self.counts()
        with self.assertRaises(ValidationError):
            self.bridge.run(self.target, operation=operation, executed_at=self.tick())
        self.assertEqual(self.counts(), original)

    def test_newer_baseline_for_same_watch_event_rejects_old_source_cutoffs(self):
        details = self.begin()
        self.refresh(details)
        operation = self.search_operation(details)
        self.source('cisa', key='newer')
        self.watches.run(self.search.id, executed_at=self.tick(), offset=0, limit=20)
        original = self.counts()
        with self.assertRaisesRegex(ValidationError, 'daha yeni'):
            self.bridge.run(self.target, operation=operation, executed_at=self.tick())
        self.assertEqual(self.counts(), original)

"""Publisher news joins audited search, watches, engine and source readiness."""

from contextlib import closing
from dataclasses import asdict, fields, make_dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.engine_records import SQLiteEngineRecordRepository
from xti.adapters.source_readiness import SQLiteSourceReadinessRepository
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
from xti.adapters.sqlite_global_search import SQLiteGlobalSearchRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_news import SQLiteNewsRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.global_saved_searches import GlobalSavedSearchService
from xti.application.global_search import GlobalSearchService
from xti.application.source_readiness import SourceReadinessService
from xti.application.sources import SourceCatalogService
from xti.domain.engine import EngineContractError, parse_record_reference, reference_for_result
from xti.domain.global_search import GLOBAL_SEARCH_KINDS
from xti.domain.global_saved_searches import make_match
from xti.domain.news import NewsArticle, NewsFeed, news_id
from xti.interfaces.engine import engine_manifest
from tests.test_global_search import LEGACY_SEARCH_KINDS


NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


def article(source='cisa', entry='entry:one', **changes):
    value = NewsArticle(news_id(source, entry), source, entry,
                        'https://publisher.example/news/one', 'Example security bulletin',
                        'The report mentions example.com.', False,
                        '2026-11-14T12:00:00+00:00', None, 'Sat, 14 Nov 2026 12:00:00 GMT', None)
    return replace(value, **changes)


def feed(articles=(), *, source='cisa', at=None):
    return NewsFeed(source, at or NOW.isoformat(), 'a' * 64, tuple(articles))


class NewsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'data' / 'xti.db'
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteNewsRepository(self.path)
        self.now = NOW
        self.search = GlobalSearchService(SQLiteGlobalSearchRepository(self.path), clock=lambda: self.now)
        self.watches = GlobalSavedSearchService(SQLiteGlobalSavedSearchRepository(self.path),
                                               LocalExecutionLock(self.path), clock=lambda: self.now)
        self.records = SQLiteEngineRecordRepository(self.path)
        self.readiness = SQLiteSourceReadinessRepository(self.path, self.root / 'project')
        self.addCleanup(patch.stopall)
        patch('socket.socket.connect', side_effect=AssertionError('No network')).start()
        patch('socket.getaddrinfo', side_effect=AssertionError('No DNS')).start()

    def tick(self):
        self.now += timedelta(seconds=1)
        return self.now.isoformat()

    def save(self, *articles, source='cisa'):
        at = self.tick()
        return self.repository.apply(feed(articles, source=source, at=at), started_at=at, finished_at=at)

    def run_watch(self, identifier):
        self.tick()
        return self.watches.run(identifier)

    def test_three_news_sources_and_all_current_scopes_are_visible_without_collection(self):
        before = self.path.read_bytes()
        empty = self.search.search('example')
        self.assertEqual(set(empty.kinds), set(GLOBAL_SEARCH_KINDS))
        self.assertEqual(len(empty.kinds), len(GLOBAL_SEARCH_KINDS))
        self.assertEqual({item.source for item in empty.coverage if item.kind == 'news'}, {'cisa', 'ncsc', 'cert-fr'})
        self.assertTrue(all(item.latest_run_id is None for item in empty.coverage if item.kind == 'news'))
        self.assertEqual(self.path.read_bytes(), before)
        first = article()
        second = article('ncsc')
        self.save(first)
        self.save(second, source='ncsc')
        before = self.path.read_bytes()
        result = self.search.search('example.com', kinds=('news',), limit=1)
        self.assertEqual((result.total_match_count, len(result.results), result.has_more), (2, 1, True))
        self.assertEqual(result.results[0].matched_field, 'summary')
        self.assertEqual(self.path.read_bytes(), before)
        all_rows = self.search.search('example.com', kinds=('news',)).results
        self.assertEqual({row.record_id for row in all_rows}, {first.id, second.id})
        self.assertEqual({reference_for_result(row).namespace for row in all_rows}, {'cisa', 'ncsc'})

    def test_eleven_families_share_one_search_and_each_record_resolves(self):
        from tests.test_engine_records import EngineRecordTests
        fixture = EngineRecordTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.seed_all()
        at = datetime.now(timezone.utc).isoformat()
        SQLiteNewsRepository(fixture.database).apply(feed((article(),), at=at), started_at=at, finished_at=at)
        before = fixture.files()
        result = fixture.service.search('example')
        self.assertEqual({hit.kind for hit in result.results}, set(LEGACY_SEARCH_KINDS) | {'news'})
        self.assertEqual({scope.kind for scope in result.coverage}, set(GLOBAL_SEARCH_KINDS))
        for hit in result.results:
            with self.subTest(kind=hit.kind, source=hit.source):
                detail = fixture.records.get(reference_for_result(hit), limit=1)
                self.assertEqual(detail['record']['id'], hit.record_id)
        self.assertEqual(fixture.files(), before)

    def test_watches_ignore_collection_refresh_and_rolloff_but_report_content_change(self):
        original = article()
        self.save(original)
        watch = self.watches.add('Example news', 'example.com', kinds=('news',)).saved_search
        baseline = self.run_watch(watch.id)
        self.assertIsNone(baseline.notification_id)
        self.save(original)
        repeated = self.run_watch(watch.id)
        self.assertEqual((repeated.run.added_count, repeated.run.updated_count, repeated.run.unchanged_count), (0, 0, 1))
        self.assertIsNone(repeated.notification_id)
        self.save()  # A rolling feed no longer contains the old article.
        rolled = self.run_watch(watch.id)
        self.assertEqual((rolled.run.unchanged_count, rolled.run.removed_count), (1, 0))
        self.assertIsNone(rolled.notification_id)
        changed_article = replace(original, summary='Updated report mentions example.com and new findings.')
        self.save(changed_article)
        changed = self.run_watch(watch.id)
        self.assertEqual((changed.run.added_count, changed.run.updated_count), (0, 1))
        self.assertIsNotNone(changed.notification_id)
        self.assertEqual(changed.items[0].before.result.record_id, changed.items[0].after.result.record_id)
        before_report = self.watches.show_run(changed.run.id)
        self.save(replace(original, title='A later title'))
        self.assertEqual(self.watches.show_run(changed.run.id), before_report)
        detail = SQLiteInboxRepository(self.path).get(changed.notification_id)
        self.assertEqual(detail.global_search_change.run.id, changed.run.id)

    def test_schema65_watch_scope_and_frozen_history_do_not_expand_silently(self):
        SQLiteAssetRepository(self.path).add('example.com')
        legacy = self.watches.add('Legacy all', 'example', kinds=LEGACY_SEARCH_KINDS).saved_search
        old = self.run_watch(legacy.id)
        with closing(sqlite3.connect(self.path)) as connection:
            before = connection.execute('SELECT definition_json,definition_sha256 FROM global_saved_search_events WHERE search_id=?', (legacy.id,)).fetchall()
            snapshot = connection.execute('SELECT payload_json FROM global_search_snapshots WHERE sha256=?', (old.run.snapshot_sha256,)).fetchone()
        self.save(article())
        repeated = self.run_watch(legacy.id)
        self.assertEqual((repeated.run.added_count, repeated.run.updated_count), (0, 0))
        self.assertEqual(repeated.saved_search.kinds, LEGACY_SEARCH_KINDS)
        self.assertIsNone(repeated.notification_id)
        self.assertEqual(self.watches.show_run(old.run.id), old)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT definition_json,definition_sha256 FROM global_saved_search_events WHERE search_id=?', (legacy.id,)).fetchall(), before)
            self.assertEqual(connection.execute('SELECT payload_json FROM global_search_snapshots WHERE sha256=?', (old.run.snapshot_sha256,)).fetchone(), snapshot)
        self.tick()
        widened = self.watches.add('Legacy all', 'example').saved_search
        self.assertEqual(widened.revision, legacy.revision + 1)
        self.assertIn('news', widened.kinds)
        new_baseline = self.run_watch(legacy.id)
        self.assertIsNone(new_baseline.run.previous_run_id)
        self.assertIsNone(new_baseline.notification_id)
        self.assertEqual({item.after.result.kind for item in new_baseline.items}, {'domain', 'news'})
        self.assertEqual(self.watches.show_run(old.run.id), old)

    def test_backup_restore_preserves_news_and_frozen_notification_read_state(self):
        original = article()
        self.save(original)
        watch = self.watches.add('Recovery news', 'example.com', kinds=('news',)).saved_search
        self.run_watch(watch.id)
        self.save(replace(original, summary='New report about example.com'))
        changed = self.run_watch(watch.id)
        inbox = SQLiteInboxRepository(self.path)
        inbox.mark((changed.notification_id,), True, self.tick())
        notice = inbox.get(changed.notification_id)
        self.save()  # Keep an archived article absent from the latest feed too.
        catalog = self.repository.catalog()
        backup = self.root / 'backup.db'
        restored = self.root / 'restored' / 'xti.db'
        SQLiteAssetRepository(self.path).backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteNewsRepository(restored).catalog(), catalog)
        self.assertEqual(SQLiteInboxRepository(restored).get(changed.notification_id), notice)
        recovered = GlobalSavedSearchService(SQLiteGlobalSavedSearchRepository(restored),
                                            LocalExecutionLock(restored), clock=lambda: self.now)
        self.assertEqual(recovered.show_run(changed.run.id), self.watches.show_run(changed.run.id))
        self.tick()
        repeat = recovered.run(watch.id)
        self.assertIsNone(repeat.notification_id)
        self.assertEqual((repeat.run.unchanged_count, repeat.run.removed_count), (1, 0))

    def test_engine_news_is_typed_source_bound_and_read_only(self):
        original = article()
        run = self.save(original).run
        self.assertGreaterEqual(set(engine_manifest()['operations']),
                                {'search', 'record.get', 'sources.status', 'components.list'})
        hit = self.search.search('example', kinds=('news',)).results[0]
        reference = parse_record_reference(reference_for_result(hit).to_dict())
        before = self.path.read_bytes()
        detail = self.records.get(reference)
        self.assertEqual(detail['record']['id'], original.id)
        self.assertEqual(detail['record']['summary'], original.summary)
        self.assertEqual(detail['provenance']['source']['key'], 'cisa')
        self.assertEqual(detail['provenance']['last_change_run_id'], run.id)
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(EngineContractError) as error:
            self.records.get(replace(reference, namespace='ncsc'))
        self.assertEqual(error.exception.code, 'not_found')
        with self.assertRaises(EngineContractError):
            parse_record_reference({**reference.to_dict(), 'namespace': 'arbitrary-source'})

    def test_news_watch_semantics_are_bound_to_typed_identity_and_visible_metadata(self):
        value = article()
        self.save(value)
        hit = self.search.search('example.com', kinds=('news',)).results[0]
        reference = reference_for_result(hit).to_dict()
        identity = tuple(value for key in sorted(reference) for value in (key, reference[key]))
        make_match(hit, identity, asdict(value))
        for semantic, result in (({**asdict(value), 'summary': 'Unrelated summary'}, hit),
                                 ({**asdict(value), 'id': 'a' * 64}, hit),
                                 ({**asdict(value), 'hidden': 'unexpected'}, hit),
                                 (asdict(value), replace(hit, display_value='Forged title')),
                                 (asdict(value), replace(hit, source='ncsc')),
                                 (asdict(value), replace(hit, status='confirmed_breach'))):
            with self.subTest(semantic=semantic, result=result), self.assertRaises(ValueError):
                make_match(result, identity, semantic)

    def test_news_sources_are_described_as_free_passive_metadata(self):
        sources = {source.identifier: source for source in SourceCatalogService().list()}
        for key in ('cisa', 'ncsc', 'cert-fr'):
            entry = sources['news:' + key]
            self.assertFalse(entry.credential_required)
            self.assertFalse(entry.paid_dependency)
            self.assertFalse(entry.contacts_monitored_target)
            self.assertIn('news refresh --source ' + key, entry.commands)
            self.assertTrue(any('atıf' in value or 'yayıncı' in value or 'özgün' in value for value in entry.limits))

    def test_engine_projection_does_not_publish_new_internal_fields(self):
        original = article()
        self.save(original)
        catalog = self.repository.catalog()
        extended_type = make_dataclass('NewsArticle', [(field.name, field.type) for field in fields(original)] + [('internal_secret', str)])
        extended_type.__module__ = 'xti.domain.news'
        extended = extended_type(**{field.name: getattr(original, field.name) for field in fields(original)}, internal_secret='must-stay-local')
        frozen = replace(catalog, articles=(replace(catalog.articles[0], article=extended),))
        hit = self.search.search('example', kinds=('news',)).results[0]
        with patch('xti.adapters.engine_records.read_news_catalog', return_value=frozen):
            detail = self.records.get(reference_for_result(hit))
        self.assertNotIn('internal_secret', detail['record'])
        self.assertNotIn('must-stay-local', str(detail))

    def test_readiness_distinguishes_never_empty_and_failed_with_retained_history(self):
        rows = {item.identifier: item for item in self.readiness.snapshot().sources}
        self.assertEqual(rows['news:cisa'].latest_status, 'never')
        self.assertIsNone(rows['news:cisa'].record_count)
        empty = self.save(source='ncsc').run
        success = self.save(article()).run
        at = self.tick()
        self.repository.record_failure('cisa', started_at=at, finished_at=at, error='Publisher timeout')
        SQLiteAssetRepository(self.path).add('unmatched.example')
        before = self.path.read_bytes()
        rows = {item.identifier: item for item in self.readiness.snapshot(domain='unmatched.example').sources}
        self.assertEqual((rows['news:ncsc'].latest_status, rows['news:ncsc'].record_count), ('complete', 0))
        self.assertEqual(rows['news:ncsc'].last_success_at, empty.finished_at)
        self.assertEqual((rows['news:cisa'].latest_status, rows['news:cisa'].record_count), ('failed', 1))
        self.assertEqual(rows['news:cisa'].last_success_at, success.finished_at)
        self.assertIn('domain filtresinden bağımsız', rows['news:cisa'].scope)
        self.assertEqual(self.path.read_bytes(), before)
        report = SourceReadinessService(self.readiness, clock=lambda: self.now).show()
        self.assertTrue(next(row for row in report.sources if row.evidence.identifier == 'news:cisa').needs_attention)
        hit = self.search.search('example', kinds=('news',)).results[0]
        self.assertTrue(hit.current)
        scope = next(row for row in self.search.search('example', kinds=('news',)).coverage if row.source == 'cisa')
        self.assertEqual((scope.latest_run_status, scope.examined_count), ('failed', 1))
        self.assertEqual(scope.latest_success_run_id, success.id)


if __name__ == '__main__':
    unittest.main()

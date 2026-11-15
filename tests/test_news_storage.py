"""Rolling feed evidence, historical differences and transactional source failures."""

from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_news import SQLiteNewsRepository, read_news_catalog
from xti.domain.assets import ValidationError
from xti.domain.news import NewsArticle, NewsFeed, articles_json, news_id


def article(key='one', *, source='cisa', title='Example news', summary='Publisher summary'):
    return NewsArticle(news_id(source, key), source, key, f'https://example.com/{key}',
                       title, summary, False, None, None, None, None)


class NewsStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'data' / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.repository = SQLiteNewsRepository(self.path)
        self.clock = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)

    def tick(self):
        self.clock += timedelta(seconds=1)
        return self.clock.isoformat()

    def apply(self, *items, source='cisa', limit=20, offset=0, response='a'):
        at = self.tick()
        return self.repository.apply(NewsFeed(source, at, response * 64, tuple(items)),
                                     started_at=at, finished_at=at, limit=limit, offset=offset)

    def failure(self, source='cisa'):
        at = self.tick()
        return self.repository.record_failure(source, started_at=at, finished_at=at,
                                               error='Source temporarily unavailable')

    def rows(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return {table: connection.execute(f'SELECT rowid,* FROM {table} ORDER BY rowid').fetchall()
                    for table in ('news_runs', 'news_snapshots', 'news_articles')}

    def test_rolling_feed_retains_old_articles_and_distinguishes_seen_from_changed(self):
        first = self.apply(article('one'), article('two'))
        second = self.apply(article('two'))
        records = {item.article.source_entry_id: item for item in self.repository.catalog().articles}
        self.assertEqual(len(records), 2)
        self.assertEqual((second.run.added_count, second.run.updated_count, second.run.unchanged_count), (0, 0, 1))
        self.assertEqual([change.action for change in second.changes], ['unchanged'])
        self.assertEqual(second.changes[0].after, article('two'))
        self.assertEqual(records['one'].last_seen_run_id, first.run.id)
        self.assertEqual(records['two'].last_seen_run_id, second.run.id)
        self.assertEqual(records['two'].last_change_run_id, first.run.id)
        self.assertEqual(records['two'].first_run_id, first.run.id)
        self.assertLess(records['two'].first_seen_at, records['two'].last_seen_at)

    def test_changed_article_has_frozen_before_after_even_after_later_changes(self):
        old = article()
        original = self.apply(old)
        changed = self.apply(replace(old, title='Corrected report'))
        self.apply(replace(old, title='Third version'))
        frozen = self.repository.run_show(changed.run.id)
        self.assertEqual(frozen, changed)
        self.assertEqual(frozen.changes[0].before.title, 'Example news')
        self.assertEqual(frozen.changes[0].after.title, 'Corrected report')
        self.assertEqual(self.repository.run_show(original.run.id).changes[0].after, old)

    def test_unchanged_run_retains_full_original_evidence_after_a_later_update(self):
        original = article()
        self.apply(original)
        unchanged = self.apply(original)
        self.apply(replace(original, title='Later corrected title'))
        frozen = self.repository.run_show(unchanged.run.id)
        self.assertEqual(frozen, unchanged)
        self.assertEqual(frozen.total_change_count, 1)
        self.assertEqual(frozen.changes[0].action, 'unchanged')
        self.assertEqual((frozen.changes[0].before, frozen.changes[0].after), (original, original))

    def test_sources_with_same_entry_id_have_separate_identity_and_failure_status(self):
        self.apply(article())
        ncsc = self.apply(article(source='ncsc'), source='ncsc')
        failed = self.failure('ncsc')
        catalog = self.repository.catalog()
        self.assertEqual(len({item.article.id for item in catalog.articles}), 2)
        statuses = {source.source.key: source for source in catalog.sources}
        self.assertEqual(statuses['ncsc'].latest_run, failed)
        self.assertEqual(statuses['ncsc'].latest_complete_run, ncsc.run)
        self.assertEqual(statuses['ncsc'].article_count, 1)
        self.assertIsNone(statuses['cert-fr'].latest_run)

    def test_empty_success_failure_and_never_fetched_remain_distinct(self):
        first = self.apply(article())
        failed = self.failure()
        before = self.repository.catalog().articles
        self.assertEqual(self.repository.run_show(failed.id).changes, ())
        empty = self.apply()
        self.assertEqual((empty.run.status, empty.run.article_count), ('complete', 0))
        self.assertEqual(self.repository.catalog().articles, before)
        status = self.repository.status()
        cisa = next(item for item in status.sources if item.source.key == 'cisa')
        self.assertEqual(cisa.latest_complete_run, empty.run)
        self.assertEqual(cisa.article_count, 1)
        self.assertEqual(self.repository.run_show(first.run.id).total_change_count, 1)

    def test_identical_parsed_evidence_reuses_snapshot_despite_changed_http_bytes(self):
        first = self.apply(article(), response='a')
        second = self.apply(article(), response='b')
        self.assertEqual(first.run.snapshot_sha256, second.run.snapshot_sha256)
        self.assertNotEqual(first.run.content_sha256, second.run.content_sha256)
        self.assertEqual(len(self.rows()['news_snapshots']), 1)
        self.assertEqual(len(self.rows()['news_runs']), 2)

    def test_pagination_does_not_truncate_committed_evidence_and_history(self):
        report = self.apply(*(article(str(i)) for i in range(5)), limit=1, offset=1)
        self.assertEqual((report.total_change_count, len(report.changes), report.offset), (5, 1, 1))
        self.assertEqual(len(self.repository.catalog().articles), 5)
        pages = [self.repository.run_show(report.run.id, limit=2, offset=i) for i in (0, 2, 4)]
        self.assertEqual(len({item.after.id for page in pages for item in page.changes}), 5)
        self.failure()
        status = self.repository.status(source_key='cisa', limit=1, offset=1)
        self.assertEqual((status.total_run_count, len(status.recent_runs)), (2, 1))
        self.assertEqual(status.recent_runs[0], report.run)

    def test_database_failure_after_run_insert_rolls_back_snapshot_run_and_articles(self):
        self.apply(article())
        before = self.rows()
        insert = self.repository._insert_run
        def fail(connection, run, previous):
            insert(connection, run, previous)
            raise sqlite3.OperationalError('Controlled failure before projection commit')
        with patch.object(self.repository, '_insert_run', side_effect=fail), self.assertRaises(StorageError):
            self.apply(article('second'))
        self.assertEqual(self.rows(), before)
        self.repository.validate()

    def test_corrupt_snapshot_chain_or_projection_is_rejected_without_repair(self):
        self.apply(article())
        backup = self.storage.backup(self.root / 'backup.db')
        mutations = (
            "UPDATE news_snapshots SET payload_json='{}'",
            "UPDATE news_runs SET chain_sha256='" + 'f' * 64 + "'",
            "UPDATE news_articles SET record_json='{}'",
            "UPDATE news_articles SET last_seen_at='2026-11-15T11:00:00+00:00'",
            'DELETE FROM news_articles',
            'DELETE FROM news_snapshots',
        )
        for i, sql in enumerate(mutations):
            with self.subTest(sql=sql):
                path = self.root / f'corrupt-{i}' / 'xti.db'
                SQLiteAssetRepository.restore(backup, path)
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute(sql)
                before = path.read_bytes()
                repository = SQLiteNewsRepository(path)
                for operation in (repository.validate, repository.catalog, repository.status):
                    with self.assertRaises(StorageError):
                        operation()
                    self.assertEqual(path.read_bytes(), before)

    def test_unselected_source_corruption_and_unowned_snapshot_are_not_hidden(self):
        self.apply(article(source='ncsc'), source='ncsc')
        with closing(sqlite3.connect(self.path)) as connection, connection:
            raw = articles_json('cisa', ())
            connection.execute('INSERT INTO news_snapshots VALUES (?,?,?)',
                               (hashlib.sha256(raw.encode('ascii')).hexdigest(), 'cisa', raw))
        with self.assertRaises(StorageError):
            self.repository.status(source_key='cisa', limit=1)

    def test_capacity_limits_preserve_prior_data_atomically(self):
        self.apply(article())
        for setting, limit in (('MAX_NEWS_ARTICLES', 1), ('MAX_NEWS_RUNS', 1)):
            with self.subTest(setting=setting):
                before = self.rows()
                with patch('xti.adapters.sqlite_news.' + setting, limit), self.assertRaises(StorageError):
                    self.apply(article('second'))
                self.assertEqual(self.rows(), before)
        size = len(articles_json('cisa', (article(),)))
        with patch('xti.adapters.sqlite_news.MAX_NEWS_TOTAL_BYTES', size):
            before = self.rows()
            with self.assertRaises(StorageError):
                self.apply(article('second'))
            self.assertEqual(self.rows(), before)

    def test_invalid_inputs_and_stale_write_leave_existing_database_unchanged(self):
        self.apply(article())
        before = self.rows()
        at = self.clock.isoformat()
        malformed = NewsFeed('cisa', at, 'a' * 64, (article(source='ncsc'),))
        operations = (
            lambda: self.repository.apply(malformed, started_at=at, finished_at=at),
            lambda: self.repository.status(limit=0),
            lambda: self.repository.status(source_key='unreviewed'),
            lambda: self.repository.run_show('invalid'),
            lambda: self.repository.record_failure('cisa', started_at=at, finished_at=at, error='\x1b[31m'),
            lambda: self.repository.record_failure('cisa', started_at='2026-11-15T10:00:00+00:00',
                                                   finished_at='2026-11-15T10:00:00+00:00', error='Earlier clock'),
        )
        for operation in operations:
            with self.assertRaises(ValidationError):
                operation()
            self.assertEqual(self.rows(), before)

    def test_read_uses_one_consistent_transaction_while_another_writer_finishes(self):
        first = self.apply(article())
        with closing(sqlite3.connect(self.path)) as writer:
            writer.execute('PRAGMA journal_mode=WAL')
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            connection.execute('SELECT COUNT(*) FROM news_runs').fetchone()
            self.apply(article('second'), source='cisa')
            snapshot = read_news_catalog(connection)
        self.assertEqual(len(snapshot.articles), 1)
        self.assertEqual(next(item for item in snapshot.sources if item.source.key == 'cisa').latest_run, first.run)
        self.assertEqual(len(self.repository.catalog().articles), 2)

    def test_backup_restore_preserves_complete_history_and_reading_missing_path_creates_nothing(self):
        first = self.apply(article())
        changed = self.apply(article(title='Updated'))
        self.failure()
        backup = self.storage.backup(self.root / 'backup.db')
        restored = self.root / 'restored' / 'xti.db'
        SQLiteAssetRepository.restore(backup, restored)
        repository = SQLiteNewsRepository(restored)
        self.assertEqual(repository.catalog(), self.repository.catalog())
        self.assertEqual(repository.run_show(first.run.id), first)
        self.assertEqual(repository.run_show(changed.run.id), changed)
        missing = self.root / 'missing' / 'xti.db'
        with self.assertRaises(StorageError):
            SQLiteNewsRepository(missing).catalog()
        self.assertFalse(missing.parent.exists())


if __name__ == '__main__':
    unittest.main()

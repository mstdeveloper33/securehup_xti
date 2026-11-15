"""Explicit schema65→66 preserves saved searches, notifications and all old rows."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.news_schema import NEWS_DDL
from xti.adapters.news_schema_metadata import TABLES as NEWS_TABLES
from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
from xti.adapters.sqlite_news import SQLiteNewsRepository
from tests.news_legacy_fixture import remove_news_schema


def manifest(path):
    with closing(sqlite3.connect(Path(path).absolute().as_uri() + '?mode=ro', uri=True)) as connection:
        result = {}
        for table in sorted(VERSION_TABLES[65]):
            name = '"' + table.replace('"', '""') + '"'
            result[table] = (
                connection.execute(f'PRAGMA table_info({name})').fetchall(),
                connection.execute(f'SELECT rowid,* FROM {name} ORDER BY rowid').fetchall(),
                connection.execute('SELECT type,name,sql FROM sqlite_schema WHERE tbl_name=? ORDER BY name',
                                   (table,)).fetchall(),
            )
        result['sqlite_sequence'] = connection.execute('SELECT name,seq FROM sqlite_sequence ORDER BY name').fetchall()
        return result


class NewsMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'data' / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()

    def legacy(self):
        self.storage.add('example.com')
        repository = SQLiteGlobalSavedSearchRepository(self.path)
        now = datetime.now(timezone.utc)
        saved = repository.upsert(name_key='example', display_name='Example', query='example',
                                  kinds=('domain',), include_inactive=False, recorded_at=now.isoformat())
        self.watch_id = saved.saved_search.id
        self.baseline = repository.run(self.watch_id, executed_at=(now + timedelta(seconds=1)).isoformat(), offset=0, limit=20)
        self.storage.add('example.org')
        self.changed = repository.run(self.watch_id, executed_at=(now + timedelta(seconds=2)).isoformat(), offset=0, limit=20)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE assets SET rowid=rowid+100')
            connection.execute('UPDATE global_saved_search_notifications SET read_at=created_at')
            remove_news_schema(connection)
            connection.execute('PRAGMA user_version=65')
            self.assertEqual(validate_schema(connection, allow_legacy=True), 65)
        return self.storage

    def test_additive_migration_preserves_all_old_rows_rowids_ddl_evidence_and_read_state(self):
        storage = self.legacy()
        before = manifest(self.path)
        result = storage.migrate()
        self.assertEqual((result['from_version'], result['to_version']), (65, 66))
        self.assertEqual(VERSION_TABLES[66] - VERSION_TABLES[65], NEWS_TABLES.keys())
        self.assertEqual(manifest(self.path), before)
        self.assertEqual(manifest(result['backup']), before)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
            for table in NEWS_TABLES:
                self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)
        with closing(sqlite3.connect(result['backup'])) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 65)
        old = SQLiteGlobalSavedSearchRepository(self.path)
        self.assertEqual(old.run_details(self.baseline.run.id, offset=0, limit=20), self.baseline)
        # Read status is intentionally different from the originally returned notification;
        # historical run evidence and its identity are nevertheless unchanged.
        report = old.run_details(self.changed.run.id, offset=0, limit=20)
        self.assertEqual(report.run, self.changed.run)
        self.assertEqual(report.items, self.changed.items)
        self.assertEqual(self.storage.inspect()['news_article_count'], 0)
        self.assertEqual(len(SQLiteNewsRepository(self.path).catalog().sources), 3)
        repeated = storage.migrate()
        self.assertFalse(repeated['changed'])
        self.assertIsNone(repeated['backup'])
        self.assertEqual(manifest(self.path), before)

    def test_partial_migration_failure_rolls_back_and_keeps_each_unique_backup(self):
        self.legacy()
        before = manifest(self.path)
        backups = {}
        def fail(connection):
            for statement in NEWS_DDL[:2]:
                connection.execute(statement)
            raise sqlite3.OperationalError('Controlled schema66 migration interruption')
        with patch('xti.adapters.sqlite.create_news_schema', side_effect=fail):
            for count in (1, 2):
                with self.assertRaises(StorageError):
                    self.storage.migrate()
                self.assertEqual(manifest(self.path), before)
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), 65)
                paths = list((self.path.parent / 'backups').glob('*.db'))
                self.assertEqual(len(paths), count)
                for path, original in backups.items():
                    self.assertEqual(path.read_bytes(), original)
                backups = {path: path.read_bytes() for path in paths}
        restored = self.root / 'restored' / 'xti.db'
        SQLiteAssetRepository.restore(next(iter(backups)), restored)
        self.assertEqual(manifest(restored), before)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(next(iter(backups)), restored)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(manifest(restored), before)
        self.assertEqual(manifest(self.path), before)

    def test_read_and_init_require_explicit_migration_without_creating_any_backup(self):
        self.legacy()
        before = self.path.read_bytes()
        with patch('socket.socket.connect', side_effect=AssertionError('No network')):
            for operation in (self.storage.initialize, self.storage.inspect, self.storage.list,
                              SQLiteNewsRepository(self.path).catalog):
                with self.subTest(operation=operation), self.assertRaisesRegex(StorageError, 'migrate'):
                    operation()
                self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / 'backups').exists())

    def test_fake_legacy_version_cannot_hide_new_tables_or_trigger_backup(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('PRAGMA user_version=65')
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.storage.migrate()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / 'backups').exists())

    def test_source_and_success_failure_constraints_are_part_of_validated_schema(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('DROP TABLE news_articles')
            connection.execute(NEWS_DDL[2].replace("CHECK (source_key IN ('cisa','ncsc','cert-fr'))", ''))
            connection.execute(NEWS_DDL[-1])
        with self.assertRaises(StorageError):
            self.storage.inspect()

    def test_fixture_refuses_populated_news_before_dropping_any_table(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('INSERT INTO news_snapshots VALUES (?,?,?)', ('a' * 64, 'cisa', '{}'))
            before = connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
            with self.assertRaisesRegex(ValueError, 'schema66'):
                remove_news_schema(connection)
            self.assertEqual(connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall(), before)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM news_snapshots').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()

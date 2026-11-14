"""Additive schema58 catalog migration preserves preexisting CTI and organizations."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from tests.public_notice_watch_legacy_fixture import remove_public_notice_watch_schema

from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_attack_catalog import SQLiteAttackCatalogRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from tests.test_attack_catalog import parsed
from tests.test_mitre_attack import NOW
from tests.collection_v60_fixture import collection_layout_v60
CATALOG_TABLES = ('attack_catalog_changes', 'attack_catalog_phases', 'attack_catalog_relationships', 'attack_catalog_entities', 'attack_catalog_runs')

def rows(path, version):
    with closing(sqlite3.connect(path)) as connection:
        return {table: connection.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall() for table in sorted(VERSION_TABLES[version])}

class AttackCatalogMigrationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.storage.add('example.com')
        SQLiteCtiKnowledgeRepository(self.path).sync_attack_snapshot(replace(parsed(), catalog=None), recorded_at=NOW.isoformat())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            collection_layout_v60(connection)
            remove_public_notice_watch_schema(connection)
            connection.execute("DROP TABLE IF EXISTS public_notice_changes")
            connection.execute("DROP TABLE IF EXISTS public_notice_runs")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_notifications")
            for table in CATALOG_TABLES:
                connection.execute(f'DROP TABLE {table}')
            connection.execute('PRAGMA user_version=57')
            self.assertEqual(validate_schema(connection, allow_legacy=True), 57)

    def test_migration_preserves_all57_rows_and_no_historic_catalog_is_invented(self):
        before = rows(self.path, 57)
        result = self.storage.migrate()
        self.assertEqual((result['from_version'], result['to_version']), (57, SCHEMA_VERSION))
        self.assertEqual(rows(self.path, 57), before)
        self.assertEqual(SQLiteAttackCatalogRepository(self.path).status().run_count, 0)
        self.assertEqual(rows(result['backup'], 57), before)
        with closing(sqlite3.connect(result['backup'])) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 57)
        self.assertFalse(self.storage.migrate()['changed'])
        self.assertEqual(SQLiteOrganizationRepository(self.path).list().total_count, 0)

    def test_legacy_read_requires_explicit_migration_without_creating_backup(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, 'migrate'):
            SQLiteAttackCatalogRepository(self.path).status()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root / 'backups').exists())

    def test_partial_ddl_rolls_back_and_recovery_backup_restores_without_overwrite(self):
        before = rows(self.path, 57)

        def fail(connection):
            connection.execute('CREATE TABLE attack_catalog_runs (id TEXT PRIMARY KEY NOT NULL)')
            raise sqlite3.OperationalError('controlled catalog migration failure')
        with patch('xti.adapters.sqlite.create_attack_catalog_schema', side_effect=fail):
            with self.assertRaises(StorageError):
                self.storage.migrate()
        self.assertEqual(rows(self.path, 57), before)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 57)
        backups = list((self.root / 'backups').glob('*.db'))
        self.assertEqual(len(backups), 1)
        restored = self.root / 'restored.db'
        SQLiteAssetRepository.restore(backups[0], restored)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(rows(restored, 57), before)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(backups[0], restored)

    def test_current_catalog_backup_restores_history_and_evidence(self):
        self.storage.migrate()
        SQLiteCtiKnowledgeRepository(self.path).sync_attack_snapshot(parsed(), recorded_at=NOW.isoformat())
        original = SQLiteAttackCatalogRepository(self.path).get('T1059.001')
        backup = self.root / 'full.db'
        self.storage.backup(backup)
        restored = self.root / 'restored.db'
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteAttackCatalogRepository(restored).get('T1059.001'), original)
        self.assertEqual(rows(restored, SCHEMA_VERSION), rows(self.path, SCHEMA_VERSION))

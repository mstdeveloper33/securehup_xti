"""A genuine core79 database upgrades with unchanged rows and a usable backup."""
from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.schema import VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from tests.case_evidence_v79_fixture import case_evidence_layout_v79
from tests import test_cases as base


class RelationshipNotificationMigrationTests(unittest.TestCase):
    def setUp(self):
        self.f = base.CaseTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.case = self.f.create_case()
        self.link = self.f.service.add_evidence(self.case.id, 'finding', self.f.insert_finding(), reason='Preserve old evidence').evidence
        with closing(sqlite3.connect(self.f.path)) as c, c:
            c.execute('UPDATE case_evidence SET rowid=rowid+100')
            case_evidence_layout_v79(c)
            c.execute('PRAGMA user_version=79')
            self.assertEqual(validate_schema(c, allow_legacy=True), 79)

    def manifest(self, path):
        with closing(sqlite3.connect(path)) as c:
            return {table: c.execute(f'SELECT rowid,* FROM {table} ORDER BY rowid').fetchall() for table in VERSION_TABLES[79]}

    def test_upgrade_preserves_all_old_rows_and_rowids_and_never_auto_migrates(self):
        before = self.manifest(self.f.path)
        with self.assertRaises(StorageError):
            self.f.service.show(self.case.id)
        result = self.f.storage.migrate()
        self.assertEqual((result['from_version'], result['to_version']), (79, 81))
        self.assertEqual(self.manifest(self.f.path), before)
        self.assertEqual(self.manifest(result['backup']), before)
        self.assertEqual(self.f.service.evidence_show(self.case.id, self.link.id), self.link)
        with self.f.storage._connection(readonly=True) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM relationship_review_notifications').fetchone()[0], 0)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertFalse(self.f.storage.migrate()['changed'])

    def test_interrupted_upgrade_rolls_back_and_old_backup_can_be_restored(self):
        from xti.adapters.relationship_notification_schema import create
        before = self.manifest(self.f.path)
        def fail(connection):
            create(connection)
            raise KeyboardInterrupt('Interrupted before schema commit')
        with patch('xti.adapters.sqlite.create_relationship_notification_schema', side_effect=fail), self.assertRaises(KeyboardInterrupt):
            self.f.storage.migrate()
        self.assertEqual(self.manifest(self.f.path), before)
        backups = list((self.f.path.parent / 'backups').glob('*.db'))
        self.assertEqual(len(backups), 1)
        restored = self.f.path.parent / 'restored' / 'xti.db'
        SQLiteAssetRepository.restore(backups[0], restored)
        self.assertEqual(self.manifest(restored), before)
        self.assertTrue(SQLiteAssetRepository(restored).migrate()['changed'])
        self.assertEqual(self.manifest(restored), before)

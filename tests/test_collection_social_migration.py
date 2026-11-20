"""Schema85 rebuild remains explicit, atomic and recoverable with old receipts."""
from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.collection_social_schema import migrate_collection_social_schema
from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import StorageError
from tests import test_collection_news_storage as fixtures
from tests.collection_v84_fixture import collection_layout_v84


class CollectionSocialMigrationTests(unittest.TestCase):
    def test_interrupted_rebuild_preserves_old_rowids_and_restorable_backup(self):
        f = fixtures.CollectionNewsStorageTests(); f.setUp(); self.addCleanup(f.doCleanups)
        session = f.begin(); f.refresh(session)
        with closing(sqlite3.connect(f.path)) as c, c:
            c.execute('UPDATE collection_step_receipts SET rowid=rowid+200')
            collection_layout_v84(c); c.execute('PRAGMA user_version=84')
            self.assertEqual(validate_schema(c, allow_legacy=True), 84)
            before = c.execute('SELECT rowid,* FROM collection_step_receipts ORDER BY rowid').fetchall()
        original = f.path.read_bytes()
        with self.assertRaises(StorageError): f.history.get(session.session.id)
        self.assertEqual(f.path.read_bytes(), original)
        def interrupted(connection):
            migrate_collection_social_schema(connection)
            raise KeyboardInterrupt('Controlled interruption before commit')
        with patch('xti.adapters.sqlite.migrate_collection_social_schema', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            f.storage.migrate()
        self.assertEqual(f.path.read_bytes(), original)
        backups = list((f.path.parent / 'backups').glob('*.db'))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as c:
            self.assertEqual(validate_schema(c, allow_legacy=True), 84)
            self.assertEqual(c.execute('SELECT rowid,* FROM collection_step_receipts ORDER BY rowid').fetchall(), before)
        outcome = f.storage.migrate()
        self.assertEqual(outcome['to_version'], SCHEMA_VERSION)
        with f.storage._connection(readonly=True) as c:
            after = c.execute('SELECT rowid,* FROM collection_step_receipts ORDER BY rowid').fetchall()
            self.assertEqual([r[:-1] for r in after], before)
            self.assertTrue(all(r[-1] is None for r in after))
        self.assertEqual(len(f.history.get(session.session.id).receipts), 3)

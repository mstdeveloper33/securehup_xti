"""55 to 56 collection history migration never invents old collection sessions."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.domain.collection_profiles import CollectionProfileDefinition

NOW='2026-11-14T08:00:00+00:00'

class CollectionHistoryMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'xti.db'
        self.storage=SQLiteAssetRepository(self.path);self.storage.initialize()
        self.asset,_=self.storage.add('example.com')
        repo=SQLiteCollectionProfileRepository(self.path)
        repo.save('Daily profile',CollectionProfileDefinition('example.com'),recorded_at=NOW)
        self.profile=repo.details('Daily profile')
        with closing(sqlite3.connect(self.path)) as connection,connection:
            connection.execute('DROP TABLE collection_step_receipts')
            connection.execute('DROP TABLE collection_session_steps')
            connection.execute('DROP TABLE collection_sessions')
            connection.execute('PRAGMA user_version=55')
            self.assertEqual(validate_schema(connection,allow_legacy=True),55)

    def test_migration_preserves_profile_history_and_creates_no_invented_sessions(self):
        result=self.storage.migrate()
        self.assertEqual((result['from_version'],result['to_version']),(55,SCHEMA_VERSION))
        self.assertEqual(self.storage.list(),[self.asset])
        self.assertEqual(SQLiteCollectionProfileRepository(self.path).details('Daily profile'),self.profile)
        self.assertEqual(SQLiteCollectionHistoryRepository(self.path).list().sessions,())
        with closing(sqlite3.connect(result['backup'])) as connection:
            self.assertEqual(validate_schema(connection,allow_legacy=True),55)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM collection_profile_events').fetchone()[0],1)
        repeated=self.storage.migrate()
        self.assertFalse(repeated['changed']);self.assertIsNone(repeated['backup'])

    def test_legacy_read_is_byte_preserving_and_instructs_explicit_migration(self):
        before=self.path.read_bytes()
        with self.assertRaisesRegex(StorageError,'migrate'):
            SQLiteCollectionHistoryRepository(self.path).list()
        self.assertEqual(self.path.read_bytes(),before)
        self.assertFalse((self.path.parent/'backups').exists())

    def test_ddl_failure_rolls_back_and_preserves_usable_recovery_snapshot(self):
        def broken(connection):
            connection.execute('CREATE TABLE collection_sessions (id TEXT PRIMARY KEY NOT NULL)')
            raise sqlite3.OperationalError('controlled history migration failure')
        with patch('xti.adapters.sqlite.create_collection_history_schema',side_effect=broken):
            with self.assertRaises(StorageError):self.storage.migrate()
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection,allow_legacy=True),55)
        backups=list((self.path.parent/'backups').glob('*.db'))
        self.assertEqual(len(backups),1)
        restored=self.path.parent/'restored.db'
        SQLiteAssetRepository.restore(backups[0],restored)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(SQLiteCollectionProfileRepository(restored).details('Daily profile'),self.profile)

if __name__=='__main__':unittest.main()

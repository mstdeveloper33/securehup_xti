from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.code_exposure_schema import create
from xti.adapters.schema import validate_schema, SCHEMA_VERSION
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from tests.case_evidence_v88_fixture import case_evidence_layout_v88


class CodeMigrationTests(unittest.TestCase):
    def test_code_ddl_failure_keeps_old_data_and_unique_restorable_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'original' / 'xti.db'
            storage = SQLiteAssetRepository(path); storage.initialize(); storage.add('example.com')
            with closing(sqlite3.connect(path)) as connection, connection:
                case_evidence_layout_v88(connection)
                connection.execute('PRAGMA user_version=88')
                self.assertEqual(validate_schema(connection, allow_legacy=True), 88)
                before_assets = connection.execute('SELECT rowid,* FROM assets ORDER BY rowid').fetchall()
            original = path.read_bytes()
            def interrupted(connection):
                create(connection)
                raise KeyboardInterrupt('Interruption after code89 DDL before commit')
            with patch('xti.adapters.sqlite.create_code_exposure_schema', side_effect=interrupted):
                for _ in range(2):
                    with self.assertRaises(KeyboardInterrupt): storage.migrate()
                    self.assertEqual(path.read_bytes(), original)
            backups = list((path.parent / 'backups').glob('*.db'))
            self.assertEqual(len(backups), 2)
            restored = Path(temporary) / 'restored' / 'xti.db'
            SQLiteAssetRepository.restore(backups[0], restored)
            with self.assertRaises(StorageError): SQLiteAssetRepository.restore(backups[0], restored)
            self.assertEqual(storage.migrate()['to_version'], SCHEMA_VERSION)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
                self.assertEqual(connection.execute('SELECT rowid,* FROM assets ORDER BY rowid').fetchall(), before_assets)


if __name__ == '__main__': unittest.main()

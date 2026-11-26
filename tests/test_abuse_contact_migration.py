"""Schema100 to schema101 abuse-contact migration is backed up and lossless."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.abuse_contact_schema import TABLES as CONTACT_TABLES
from xti.adapters.sqlite import SQLiteAssetRepository


class AbuseContactMigrationTests(unittest.TestCase):
    def test_schema100_upgrade_publishes_recoverable_snapshot_and_preserves_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data" / "xti.db"
            storage = SQLiteAssetRepository(path); storage.initialize()
            asset, _created = storage.add("preserved.example")
            connection = sqlite3.connect(path)
            try:
                connection.execute("PRAGMA foreign_keys=OFF")
                for table in reversed(tuple(CONTACT_TABLES)):
                    connection.execute(f"DROP TABLE {table}")
                connection.execute("PRAGMA user_version=100")
                connection.commit()
            finally:
                connection.close()

            result = storage.migrate()
            self.assertTrue(result["changed"])
            self.assertEqual((result["from_version"], result["to_version"]), (100, 101))
            self.assertEqual({item.id: item.value for item in storage.list()}[asset.id],
                             "preserved.example")
            self.assertEqual(storage.inspect()["schema_version"], 101)
            with storage._connection(readonly=True) as current:
                for table in CONTACT_TABLES:
                    self.assertEqual(current.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

            snapshot = Path(result["backup"])
            self.assertTrue(snapshot.is_file())
            with closing(sqlite3.connect(snapshot)) as backup:
                self.assertEqual(backup.execute("PRAGMA user_version").fetchone()[0], 100)
                self.assertEqual(backup.execute("SELECT value FROM assets WHERE id=?", (asset.id,)).fetchone()[0],
                                 "preserved.example")
                for table in CONTACT_TABLES:
                    self.assertIsNone(backup.execute(
                        "SELECT name FROM sqlite_schema WHERE type='table' AND name=?", (table,),
                    ).fetchone())


if __name__ == "__main__":
    unittest.main()

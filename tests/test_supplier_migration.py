"""Schema 51 to 52 supplier-inventory migration."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository


class SupplierMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"

    def version_fifty_one(self) -> Path:
        storage = SQLiteAssetRepository(self.path)
        storage.initialize()
        storage.add("example.com")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP INDEX supplier_candidate_resolutions_candidate_sequence")
            connection.execute("DROP INDEX supplier_candidate_evidence_candidate_sequence")
            connection.execute("DROP INDEX supplier_candidates_status_current")
            connection.execute("DROP TABLE supplier_candidate_resolution_events")
            connection.execute("DROP TABLE supplier_candidate_evidence")
            connection.execute("DROP TABLE supplier_candidates")
            connection.execute("DROP INDEX supplier_events_supplier_sequence")
            connection.execute("DROP INDEX suppliers_active_name")
            connection.execute("DROP TABLE supplier_events")
            connection.execute("DROP TABLE suppliers")
            connection.execute("DROP TABLE IF EXISTS case_activities")
            connection.execute("DROP TABLE IF EXISTS case_tasks")
            connection.execute("DROP TABLE IF EXISTS case_evidence")
            connection.execute("DROP TABLE IF EXISTS cases")
            connection.execute("DROP TABLE IF EXISTS collection_profile_events")
            connection.execute("DROP TABLE IF EXISTS collection_profiles")
            connection.execute("PRAGMA user_version=51")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 51)
        return self.path

    @staticmethod
    def version(path: Path) -> int:
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v51_migrates_with_backup_empty_tables_and_preserved_data(self):
        path = self.version_fifty_one()
        result = SQLiteAssetRepository(path).migrate()
        self.assertEqual(
            (result["from_version"], result["to_version"]), (51, SCHEMA_VERSION),
        )
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(
                connection.execute("SELECT value FROM assets").fetchall(),
                [("example.com",)],
            )
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0], 0)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM supplier_events").fetchone()[0], 0,
            )

        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 51)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 51)
            self.assertEqual(
                connection.execute("SELECT value FROM assets").fetchall(),
                [("example.com",)],
            )

    def test_v51_read_is_blocked_without_mutation(self):
        path = self.version_fifty_one()
        before = path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteSupplierRepository(path).list(active_only=True, limit=10)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.version(path), 51)
        self.assertFalse((path.parent / "backups").exists())

    def test_failed_creation_rolls_back_and_keeps_valid_backup(self):
        path = self.version_fifty_one()

        def incomplete(connection):
            connection.execute("CREATE TABLE suppliers (id TEXT PRIMARY KEY NOT NULL)")
            raise sqlite3.OperationalError("controlled supplier migration failure")

        with patch(
            "xti.adapters.sqlite.create_supplier_inventory_schema", side_effect=incomplete,
        ):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 51)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 51)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 51)


if __name__ == "__main__":
    unittest.main()

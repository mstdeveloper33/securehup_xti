"""Schema 53 to 54 case-management migration."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.application.suppliers import SupplierService


class CaseMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"

    def version_fifty_three(self):
        storage = SQLiteAssetRepository(self.path)
        storage.initialize()
        supplier = SupplierService(SQLiteSupplierRepository(self.path)).add(
            "Korunan Tedarikçi", domain="vendor.example",
            relationship_type="cloud", criticality="high",
            reason="Vaka migration sırasında korunacak tedarikçi.",
        ).supplier
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP INDEX case_activities_case_sequence")
            connection.execute("DROP INDEX case_tasks_case_status_due")
            connection.execute("DROP INDEX case_evidence_case_active_updated")
            connection.execute("DROP INDEX cases_status_priority_updated")
            connection.execute("DROP TABLE case_activities")
            connection.execute("DROP TABLE case_tasks")
            connection.execute("DROP TABLE case_evidence")
            connection.execute("DROP TABLE cases")
            connection.execute("DROP TABLE IF EXISTS collection_profile_events")
            connection.execute("DROP TABLE IF EXISTS collection_profiles")
            connection.execute("DROP TABLE IF EXISTS collection_step_receipts")
            connection.execute("DROP TABLE IF EXISTS collection_session_steps")
            connection.execute("DROP TABLE IF EXISTS collection_sessions")
            connection.execute("PRAGMA user_version=53")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 53)
        return supplier.id

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v53_migrates_with_backup_and_preserves_old_data(self):
        supplier_id = self.version_fifty_three()
        result = SQLiteAssetRepository(self.path).migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (53, SCHEMA_VERSION))
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(connection.execute("SELECT id FROM suppliers").fetchall(), [(supplier_id,)])
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0], 0)
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 53)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 53)

    def test_v53_read_is_blocked_without_mutation(self):
        self.version_fifty_three()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteCaseRepository(self.path).list(status=None, priority=None, limit=10)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_failed_creation_rolls_back_and_keeps_valid_backup(self):
        self.version_fifty_three()

        def incomplete(connection):
            connection.execute("CREATE TABLE cases (id TEXT PRIMARY KEY NOT NULL)")
            raise sqlite3.OperationalError("controlled case migration failure")

        with patch("xti.adapters.sqlite.create_case_schema", side_effect=incomplete):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(self.path).migrate()
        self.assertEqual(self.version(self.path), 53)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 53)
        backups = list((self.path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 53)


if __name__ == "__main__":
    unittest.main()

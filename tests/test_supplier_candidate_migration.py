"""Schema 52 to 53 supplier-candidate migration."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_supplier_candidates import SQLiteSupplierCandidateRepository
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.application.suppliers import SupplierService


class SupplierCandidateMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"

    def version_fifty_two(self) -> tuple[Path, str]:
        storage = SQLiteAssetRepository(self.path)
        storage.initialize()
        supplier = SupplierService(SQLiteSupplierRepository(self.path)).add(
            "Korunan Tedarikçi", domain="vendor.example",
            relationship_type="cloud", criticality="high",
            reason="Geçiş sırasında korunması gereken tedarikçi.",
        ).supplier
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP INDEX supplier_candidate_resolutions_candidate_sequence")
            connection.execute("DROP INDEX supplier_candidate_evidence_candidate_sequence")
            connection.execute("DROP INDEX supplier_candidates_status_current")
            connection.execute("DROP TABLE supplier_candidate_resolution_events")
            connection.execute("DROP TABLE supplier_candidate_evidence")
            connection.execute("DROP TABLE supplier_candidates")
            connection.execute("DROP TABLE IF EXISTS case_activities")
            connection.execute("DROP TABLE IF EXISTS case_tasks")
            connection.execute("DROP TABLE IF EXISTS case_evidence")
            connection.execute("DROP TABLE IF EXISTS cases")
            connection.execute("DROP TABLE IF EXISTS collection_profile_events")
            connection.execute("DROP TABLE IF EXISTS collection_profiles")
            connection.execute("PRAGMA user_version=52")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 52)
        return self.path, supplier.id

    @staticmethod
    def version(path: Path) -> int:
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v52_migrates_with_backup_and_preserves_supplier(self):
        path, supplier_id = self.version_fifty_two()
        result = SQLiteAssetRepository(path).migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (52, SCHEMA_VERSION))
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(
                connection.execute("SELECT id FROM suppliers").fetchall(), [(supplier_id,)],
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM supplier_candidates").fetchone()[0], 0,
            )
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 52)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 52)

    def test_v52_read_is_blocked_without_mutation(self):
        path, _ = self.version_fifty_two()
        before = path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteSupplierCandidateRepository(path).list(
                status=None, current_only=False, limit=10,
            )
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((path.parent / "backups").exists())

    def test_failed_creation_rolls_back_and_keeps_valid_backup(self):
        path, _ = self.version_fifty_two()

        def incomplete(connection):
            connection.execute("CREATE TABLE supplier_candidates (id TEXT PRIMARY KEY NOT NULL)")
            raise sqlite3.OperationalError("controlled candidate migration failure")

        with patch(
            "xti.adapters.sqlite.create_supplier_candidate_schema", side_effect=incomplete,
        ):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 52)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 52)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 52)


if __name__ == "__main__":
    unittest.main()

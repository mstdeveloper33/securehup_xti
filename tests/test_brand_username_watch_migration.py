"""Schema 46 to 47 adds empty, recoverable username watch storage."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_watches import (
    SQLiteBrandUsernameWatchRepository,
)


TABLES = (
    "brand_username_review_notifications",
    "brand_username_review_events",
    "brand_username_watch_run_items",
    "brand_username_watch_runs",
    "brand_username_watch_events",
    "brand_username_watches",
)


class BrandUsernameWatchMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "legacy" / "xti.db"

    def version_forty_six(self):
        SQLiteAssetRepository(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            for table in TABLES:
                connection.execute(f"DROP TABLE {table}")
            connection.execute("DROP INDEX IF EXISTS supplier_candidate_resolutions_candidate_sequence")
            connection.execute("DROP INDEX IF EXISTS supplier_candidate_evidence_candidate_sequence")
            connection.execute("DROP INDEX IF EXISTS supplier_candidates_status_current")
            connection.execute("DROP TABLE IF EXISTS supplier_candidate_resolution_events")
            connection.execute("DROP TABLE IF EXISTS supplier_candidate_evidence")
            connection.execute("DROP TABLE IF EXISTS supplier_candidates")
            connection.execute("DROP INDEX IF EXISTS supplier_events_supplier_sequence")
            connection.execute("DROP INDEX IF EXISTS suppliers_active_name")
            connection.execute("DROP TABLE IF EXISTS supplier_events")
            connection.execute("DROP TABLE IF EXISTS suppliers")
            connection.execute("DROP TABLE IF EXISTS case_activities")
            connection.execute("DROP TABLE IF EXISTS case_tasks")
            connection.execute("DROP TABLE IF EXISTS case_evidence")
            connection.execute("DROP TABLE IF EXISTS cases")
            connection.execute("PRAGMA user_version=46")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 46)
        return self.path

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v46_migrates_with_backup_and_empty_watch_storage(self):
        path = self.version_forty_six()
        result = SQLiteAssetRepository(path).migrate()
        self.assertEqual(
            (result["from_version"], result["to_version"]),
            (46, SCHEMA_VERSION),
        )
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in TABLES
            ), (0, 0, 0, 0, 0, 0))
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 46)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 46)

    def test_failed_creation_rolls_back_and_keeps_valid_v46_backup(self):
        path = self.version_forty_six()

        def incomplete(connection):
            connection.execute(
                "CREATE TABLE brand_username_watches (id TEXT PRIMARY KEY)"
            )
            raise sqlite3.OperationalError("controlled failure")

        with patch(
            "xti.adapters.sqlite.create_brand_username_watch_schema",
            side_effect=incomplete,
        ):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 46)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual((len(backups), self.version(backups[0])), (1, 46))

    def test_v46_reads_never_migrate_or_create_watch_tables(self):
        path = self.version_forty_six()
        before = path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteBrandUsernameWatchRepository(path).list(
                active_only=True, limit=10,
            )
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.version(path), 46)


if __name__ == "__main__":
    unittest.main()

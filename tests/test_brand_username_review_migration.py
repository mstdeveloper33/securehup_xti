"""Schema 47 to 48 adds empty, recoverable social profile reviews."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_reviews import (
    SQLiteBrandUsernameReviewRepository,
)


class BrandUsernameReviewMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "legacy" / "xti.db"

    def version_forty_seven(self):
        SQLiteAssetRepository(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE brand_username_review_notifications")
            connection.execute("DROP TABLE brand_username_review_events")
            connection.execute(
                "ALTER TABLE brand_username_watches DROP COLUMN source_key"
            )
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
            connection.execute("DROP TABLE IF EXISTS collection_profile_events")
            connection.execute("DROP TABLE IF EXISTS collection_profiles")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_notifications")
            connection.execute("DROP TABLE IF EXISTS attack_catalog_changes")
            connection.execute("DROP TABLE IF EXISTS attack_catalog_phases")
            connection.execute("DROP TABLE IF EXISTS attack_catalog_relationships")
            connection.execute("DROP TABLE IF EXISTS attack_catalog_entities")
            connection.execute("DROP TABLE IF EXISTS attack_catalog_runs")
            connection.execute("DROP TABLE IF EXISTS organization_link_events")
            connection.execute("DROP TABLE IF EXISTS organization_links")
            connection.execute("DROP TABLE IF EXISTS organization_events")
            connection.execute("DROP TABLE IF EXISTS organizations")
            connection.execute("DROP TABLE IF EXISTS collection_step_receipts")
            connection.execute("DROP TABLE IF EXISTS collection_session_steps")
            connection.execute("DROP TABLE IF EXISTS collection_sessions")
            connection.execute("PRAGMA user_version=47")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 47)
        return self.path

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v47_migrates_with_backup_and_empty_review_storage(self):
        path = self.version_forty_seven()
        result = SQLiteAssetRepository(path).migrate()
        self.assertEqual(
            (result["from_version"], result["to_version"]),
            (47, SCHEMA_VERSION),
        )
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM brand_username_review_events"
            ).fetchone()[0], 0)
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 47)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 47)

    def test_failed_creation_rolls_back_and_keeps_valid_v47_backup(self):
        path = self.version_forty_seven()

        def incomplete(connection):
            connection.execute(
                "CREATE TABLE brand_username_review_events (id TEXT PRIMARY KEY)"
            )
            raise sqlite3.OperationalError("controlled failure")

        with patch(
            "xti.adapters.sqlite.create_brand_username_review_schema",
            side_effect=incomplete,
        ):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 47)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual((len(backups), self.version(backups[0])), (1, 47))

    def test_v47_reads_never_migrate_or_create_review_table(self):
        path = self.version_forty_seven()
        before = path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteBrandUsernameReviewRepository(path).states(
                "00000000-0000-0000-0000-000000000000"
            )
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.version(path), 47)


if __name__ == "__main__":
    unittest.main()

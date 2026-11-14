"""Schema 45 to 46 adds empty, recoverable cross-source review history."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomware_source_reviews import (
    SQLiteRansomwareSourceReviewRepository,
)


TABLE = "ransomware_source_review_events"


class RansomwareSourceReviewMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "legacy" / "xti.db"

    def version_forty_five(self):
        SQLiteAssetRepository(self.path).initialize()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(f"DROP TABLE {TABLE}")
            connection.execute("DROP TABLE IF EXISTS ransomware_source_review_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_review_notifications")
            connection.execute("DROP TABLE IF EXISTS brand_username_review_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_runs")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_watches")
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
            connection.execute("PRAGMA user_version=45")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 45)
        return self.path

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v45_migrates_with_backup_and_empty_review_history(self):
        path = self.version_forty_five()
        result = SQLiteAssetRepository(path).migrate()
        self.assertEqual(
            (result["from_version"], result["to_version"]), (45, SCHEMA_VERSION),
        )
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(
                connection.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0], 0,
            )
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 45)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 45)

    def test_failed_creation_rolls_back_and_keeps_valid_v45_backup(self):
        path = self.version_forty_five()

        def incomplete(connection):
            connection.execute(
                "CREATE TABLE ransomware_source_review_events (id TEXT PRIMARY KEY)"
            )
            raise sqlite3.OperationalError("controlled failure")

        with patch(
            "xti.adapters.sqlite.create_ransomware_source_review_schema",
            side_effect=incomplete,
        ):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 45)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual((len(backups), self.version(backups[0])), (1, 45))

    def test_v45_reads_never_migrate_or_create_review_table(self):
        path = self.version_forty_five()
        before = path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteRansomwareSourceReviewRepository(path).states()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.version(path), 45)


if __name__ == "__main__":
    unittest.main()

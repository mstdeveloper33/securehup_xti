"""Version 2 evidence and reviews survive migration to the current layout."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import APPLICATION_ID, ASSETS_DDL, FINDINGS_DDL, SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_jobs import SQLiteJobRepository


class JobMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(ASSETS_DDL)
            for statement in FINDINGS_DDL:
                connection.execute(statement)
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_notes")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_tag_events")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_tags")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_notifications")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_run_items")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_runs")
            connection.execute("DROP TABLE IF EXISTS cti_saved_search_events")
            connection.execute("DROP TABLE IF EXISTS cti_saved_searches")
            connection.execute("DROP TABLE IF EXISTS cti_relationship_assertion_events")
            connection.execute("DROP TABLE IF EXISTS cti_relationship_assertions")
            connection.execute("DROP TABLE IF EXISTS cti_relationships")
            connection.execute("DROP TABLE IF EXISTS cti_entity_assertion_events")
            connection.execute("DROP TABLE IF EXISTS cti_entity_assertions")
            connection.execute("DROP TABLE IF EXISTS cti_entities")
            connection.execute("DROP TABLE IF EXISTS cti_feed_run_items")
            connection.execute("DROP TABLE IF EXISTS cti_feed_runs")
            connection.execute("DROP TABLE IF EXISTS cti_indicator_assertion_events")
            connection.execute("DROP TABLE IF EXISTS cti_indicator_assertions")
            connection.execute("DROP TABLE IF EXISTS cti_indicators")
            connection.execute("DROP TABLE IF EXISTS ubuntu_asset_package_events")
            connection.execute("DROP TABLE IF EXISTS ubuntu_asset_packages")
            for table in ("webhook_delivery_attempts", "webhook_deliveries", "webhook_destination_events", "webhook_destinations"):
                connection.execute(f"DROP TABLE IF EXISTS {table}")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_cycle_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_cycles")
            connection.execute("DROP TABLE IF EXISTS ransomware_identity_review_events")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_sessions")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_notifications")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_events")
            connection.execute("DROP TABLE IF EXISTS ransomware_watches")
            connection.execute("DROP TABLE IF EXISTS ransomware_claim_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomware_claim_runs")
            connection.execute("DROP TABLE IF EXISTS ransomlook_claim_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomlook_claim_runs")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_events")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watches")
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
            connection.execute("PRAGMA user_version=2")
            connection.execute("INSERT INTO assets VALUES ('asset-1', 'example.com', '2026-01-01')")
            connection.execute(
                "INSERT INTO observations VALUES ('observation-1', 'example-support.net', "
                "'EXAMPLE-SUPPORT.NET', 'source.txt', 'source-hash', 1, NULL, '2026-01-02')"
            )
            connection.execute(
                "INSERT INTO findings VALUES ('finding-1', 'asset-1', 'example.com', "
                "'example-support.net', 'rules-v1', '[\"reason\"]', 'uncertain', '2026-01-02', '2026-01-02')"
            )
            connection.execute("INSERT INTO finding_observations VALUES ('finding-1', 'observation-1')")
            connection.execute(
                "INSERT INTO reviews VALUES ('review-1', 'finding-1', 'uncertain', 'Ek bilgi gerekli', '2026-01-03')"
            )
        self.repo = SQLiteAssetRepository(self.path)

    def snapshot(self, path):
        with closing(sqlite3.connect(path)) as connection:
            return {
                table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in ("assets", "observations", "findings", "finding_observations", "reviews")
            }

    def version(self, path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v2_migration_preserves_all_evidence_and_creates_v2_backup(self):
        before = self.snapshot(self.path)
        migrated = self.repo.migrate()
        self.assertEqual(migrated["from_version"], 2)
        self.assertEqual(migrated["to_version"], SCHEMA_VERSION)
        self.assertEqual(self.snapshot(self.path), before)
        self.assertEqual(self.version(self.path), SCHEMA_VERSION)
        backup = Path(migrated["backup"])
        self.assertEqual(self.version(backup), 2)
        self.assertEqual(self.snapshot(backup), before)
        self.assertEqual(SQLiteJobRepository(self.path).list(), [])
        self.assertEqual(self.repo.inspect()["job_count"], 0)
        second = self.repo.migrate()
        self.assertIs(second["changed"], False)
        self.assertEqual(len(list(backup.parent.glob("*.db"))), 1)

    def test_v2_usage_requires_explicit_migration_without_writes(self):
        before = self.path.read_bytes()
        for action in (self.repo.initialize, self.repo.inspect, SQLiteJobRepository(self.path).list):
            with self.subTest(action=action):
                with self.assertRaisesRegex(StorageError, "migrate"):
                    action()
                self.assertEqual(self.path.read_bytes(), before)

    def test_v2_failed_migration_rolls_back_tables_and_version(self):
        before = self.snapshot(self.path)

        def broken(connection):
            connection.execute("CREATE TABLE scan_partial (id TEXT)")
            connection.execute("DROP TABLE IF EXISTS ubuntu_asset_package_events")
            connection.execute("DROP TABLE IF EXISTS ubuntu_asset_packages")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_cycle_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_cycles")
            connection.execute("DROP TABLE IF EXISTS ransomware_identity_review_events")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_sessions")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_notifications")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_events")
            connection.execute("DROP TABLE IF EXISTS ransomware_watches")
            connection.execute("DROP TABLE IF EXISTS ransomware_claim_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomware_claim_runs")
            connection.execute("DROP TABLE IF EXISTS ransomlook_claim_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomlook_claim_runs")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_events")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watches")
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
            connection.execute("PRAGMA user_version=3")
            raise sqlite3.OperationalError("Injected migration failure")

        with patch("xti.adapters.sqlite.create_jobs_schema", side_effect=broken):
            with self.assertRaises(StorageError):
                self.repo.migrate()
        self.assertEqual(self.snapshot(self.path), before)
        self.assertEqual(self.version(self.path), 2)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 2)
        backups = list((self.path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 2)
        self.assertEqual(self.snapshot(backups[0]), before)
        self.repo.migrate()
        self.assertEqual(self.version(self.path), SCHEMA_VERSION)

    def test_v2_backup_restore_preserves_source_version_until_migrate(self):
        before = self.path.read_bytes()
        backup = self.path.parent / "v2-backup.db"
        restored = self.path.parent / "restored" / "xti.db"
        self.repo.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(self.version(restored), 2)
        self.assertEqual(self.snapshot(restored), self.snapshot(self.path))
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(self.version(restored), SCHEMA_VERSION)
        self.assertEqual(self.version(backup), 2)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

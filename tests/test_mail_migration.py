"""Schema 12 upgrades add empty append-only mail-DNS evidence safely."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import (
    SCHEMA_VERSION, SURFACE_MAIL_DDL, VERSION_TABLES, validate_schema,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.surface import SurfaceService


class MailMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def version_twelve(self):
        path = self.root / "legacy" / "xti.db"
        storage = SQLiteAssetRepository(path)
        storage.initialize()
        storage.add("example.com")
        SurfaceService(
            storage, SQLiteSurfaceRepository(path),
            clock=lambda: datetime(2026, 10, 29, 12, tzinfo=timezone.utc),
        ).approve("example.com", "Kendi kök alan adım")
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("DROP INDEX nvd_window_restart_events_sync_recorded")
            connection.execute("DROP TABLE nvd_window_restart_events")
            connection.execute("DROP TABLE nvd_window_syncs")
            connection.execute("DROP TABLE vulnerability_change_notifications")
            connection.execute("DROP TABLE vulnerability_reassessment_items")
            connection.execute("DROP TABLE vulnerability_reassessment_runs")
            connection.execute("DROP TABLE asset_criticality_events")
            connection.execute("DROP TABLE asset_criticalities")
            connection.execute("DROP TABLE vulnerability_exposure_suppression_events")
            connection.execute("DROP TABLE vulnerability_exposure_suppressions")
            connection.execute("DROP TABLE vulnerability_remediation_events")
            connection.execute("DROP TABLE vulnerability_remediations")
            connection.execute("DROP TABLE asset_package_events")
            connection.execute("DROP TABLE vulnerability_vendor_package_evidence_events")
            connection.execute("DROP TABLE vulnerability_vendor_package_evidence")
            connection.execute("DROP TABLE asset_packages")
            connection.execute("DROP TABLE vulnerability_exposure_evidence_events")
            connection.execute("DROP TABLE vulnerability_exposure_evidence")
            connection.execute("DROP TABLE vulnerability_exposure_events")
            connection.execute("DROP TABLE vulnerability_exposures")
            connection.execute("DROP TABLE asset_product_events")
            connection.execute("DROP TABLE asset_products")
            connection.execute("DROP TABLE nvd_cve_events")
            connection.execute("DROP TABLE nvd_cve_records")
            connection.execute("DROP TABLE epss_scores")
            connection.execute("DROP TABLE kev_entry_events")
            connection.execute("DROP TABLE kev_entries")
            connection.execute("DROP TABLE vulnerability_source_runs")
            connection.execute("DROP TABLE surface_cname_checks")
            connection.execute("DROP TABLE surface_change_notifications")
            connection.execute("DROP TABLE surface_service_checks")
            connection.execute("DROP TABLE surface_mail_checks")
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
            connection.execute("PRAGMA user_version=12")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 12)
        return path

    @staticmethod
    def rows(path, tables):
        with closing(sqlite3.connect(path)) as connection:
            return {
                table: connection.execute(
                    f"SELECT * FROM {table} ORDER BY rowid"
                ).fetchall()
                for table in tables
            }

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return validate_schema(connection, allow_legacy=True)

    def test_version_twelve_migrates_with_backup_and_preserves_old_rows(self):
        path = self.version_twelve()
        before = self.rows(path, VERSION_TABLES[12])
        result = SQLiteAssetRepository(path).migrate()
        self.assertEqual(
            (result["from_version"], result["to_version"]), (12, SCHEMA_VERSION),
        )
        self.assertEqual(self.version(path), SCHEMA_VERSION)
        self.assertEqual(self.rows(path, VERSION_TABLES[12]), before)
        self.assertEqual(self.rows(path, ("surface_mail_checks",)), {
            "surface_mail_checks": [],
        })
        self.assertEqual(
            SQLiteAssetRepository(path).inspect()["surface_mail_check_count"], 0,
        )
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 12)
        self.assertEqual(self.rows(backup, VERSION_TABLES[12]), before)

    def test_failed_mail_schema_creation_rolls_back_and_keeps_v12_backup(self):
        path = self.version_twelve()
        before = self.rows(path, VERSION_TABLES[12])

        def incomplete(connection):
            connection.execute(SURFACE_MAIL_DDL[0])
            raise sqlite3.OperationalError("controlled mail schema failure")

        with patch("xti.adapters.sqlite.create_surface_mail_schema", side_effect=incomplete):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 12)
        self.assertEqual(self.rows(path, VERSION_TABLES[12]), before)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 12)

        SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), SCHEMA_VERSION)

    def test_version_twelve_reads_never_migrate_or_create_mail_table(self):
        path = self.version_twelve()
        before = path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteAssetRepository(path).inspect()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.version(path), 12)


if __name__ == "__main__":
    unittest.main()

"""Schema 38 to 39 adds an empty, recoverable webhook outbox."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_webhooks import SQLiteWebhookRepository


_TABLES = (
    "webhook_delivery_attempts", "webhook_deliveries",
    "webhook_destination_events", "webhook_destinations",
)


class WebhookMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def version_thirty_eight(self):
        path = self.root / "legacy" / "xti.db"
        SQLiteAssetRepository(path).initialize()
        SQLiteAssetRepository(path).add("example.com")
        with closing(sqlite3.connect(path)) as connection, connection:
            for table in _TABLES:
                connection.execute(f"DROP TABLE {table}")
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
            connection.execute("PRAGMA user_version=38")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 38)
        return path

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v38_migrates_with_backup_and_empty_webhook_tables(self):
        path = self.version_thirty_eight()
        result = SQLiteAssetRepository(path).migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (38, SCHEMA_VERSION))
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(
                tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in _TABLES),
                (0, 0, 0, 0),
            )
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 38)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 38)

    def test_failed_creation_rolls_back_and_keeps_valid_v38_backup(self):
        path = self.version_thirty_eight()

        def incomplete(connection):
            connection.execute("CREATE TABLE webhook_destinations (id TEXT PRIMARY KEY)")
            raise sqlite3.OperationalError("controlled failure")

        with patch("xti.adapters.sqlite.create_webhook_schema", side_effect=incomplete):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 38)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 38)

    def test_v38_reads_never_migrate_or_create_webhook_tables(self):
        path = self.version_thirty_eight()
        before = path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteWebhookRepository(path).list_destinations(active_only=True, limit=10)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.version(path), 38)


if __name__ == "__main__":
    unittest.main()

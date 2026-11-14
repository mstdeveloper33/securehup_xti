"""Legacy data is preserved by explicit migration and recoverable snapshots."""

from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import APPLICATION_ID, SCHEMA_VERSION, SQLiteAssetRepository, StorageError
from tests.test_findings_cli import CLIHarness


class MigrationTests(CLIHarness, unittest.TestCase):
    legacy_asset = (
        "9bb7b9f3-ea2e-4c3d-9e77-c3656052453a",
        "example.com",
        "2026-01-02T03:04:05+00:00",
    )

    def create_legacy(self, path=None):
        path = path or self.data / "xti.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TABLE assets (id TEXT PRIMARY KEY NOT NULL, "
                "value TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)"
            )
            connection.execute("INSERT INTO assets VALUES (?, ?, ?)", self.legacy_asset)
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
            connection.execute("DROP TABLE IF EXISTS collection_step_receipts")
            connection.execute("DROP TABLE IF EXISTS collection_session_steps")
            connection.execute("DROP TABLE IF EXISTS collection_sessions")
            connection.execute("PRAGMA user_version=1")
        return path

    def inspect_legacy_rows(self, path):
        with closing(sqlite3.connect(path)) as connection:
            return (
                connection.execute("PRAGMA user_version").fetchone()[0],
                connection.execute("SELECT id, value, created_at FROM assets ORDER BY id").fetchall(),
            )

    def test_explicit_migration_keeps_asset_identity_and_creates_a_legacy_snapshot(self):
        database = self.create_legacy()
        result = self.success_json(self.run_cli("migrate"))
        self.assertIs(result["changed"], True)
        self.assertEqual(result["from_version"], 1)
        self.assertEqual(result["to_version"], SCHEMA_VERSION)
        backup = Path(result["backup"])
        self.assertTrue(backup.is_file())
        self.assertEqual(backup.parent.resolve(), (self.data / "backups").resolve())
        self.assertEqual(self.inspect_legacy_rows(backup), (1, [self.legacy_asset]))
        self.assertEqual(self.inspect_legacy_rows(database), (SCHEMA_VERSION, [self.legacy_asset]))
        assets = self.success_json(self.run_cli("assets", "list"))["assets"]
        self.assertEqual(assets, [dict(zip(("id", "value", "created_at"), self.legacy_asset))])
        self.assertEqual(self.findings(), [])
        self.assertEqual(self.success_json(self.run_cli("doctor"))["integrity"], "ok")
        self.import_source(self.write_source("example-support.net\n"))
        self.assertEqual(len(self.findings()), 1)
        self.assertEqual(self.inspect_legacy_rows(backup), (1, [self.legacy_asset]))

    def test_repeated_migration_is_noop_without_another_backup(self):
        database = self.create_legacy()
        self.success_json(self.run_cli("migrate"))
        before = database.read_bytes()
        backups_before = set((self.data / "backups").iterdir())
        result = self.success_json(self.run_cli("migrate"))
        self.assertIs(result["changed"], False)
        self.assertEqual(result["from_version"], SCHEMA_VERSION)
        self.assertEqual(result["to_version"], SCHEMA_VERSION)
        self.assertIsNone(result["backup"])
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(set((self.data / "backups").iterdir()), backups_before)

    def test_legacy_read_or_init_instructs_explicit_migration_without_changing_file(self):
        database = self.create_legacy()
        before = database.read_bytes()
        for arguments in (("assets", "list"), ("doctor",), ("init",), ("findings", "list")):
            with self.subTest(arguments=arguments):
                error = self.error_json(self.run_cli(*arguments), 1)
                self.assertIn("migrate", error["message"])
                self.assertEqual(database.read_bytes(), before)

    def test_restore_preserves_legacy_format_until_explicit_migration(self):
        source = self.create_legacy(self.root / "legacy-snapshot.db")
        before = source.read_bytes()
        self.success_json(self.run_cli("restore", str(source)))
        self.assertEqual(self.inspect_legacy_rows(self.data / "xti.db"), (1, [self.legacy_asset]))
        self.error_json(self.run_cli("assets", "list"), 1)
        self.success_json(self.run_cli("migrate"))
        self.assertEqual(
            self.inspect_legacy_rows(self.data / "xti.db"), (SCHEMA_VERSION, [self.legacy_asset]),
        )
        self.assertEqual(source.read_bytes(), before)

    def test_failed_backup_leaves_legacy_database_usable_for_retry(self):
        database = self.create_legacy()
        blocker = self.data / "backups"
        blocker.write_bytes(b"existing user file")
        before = database.read_bytes()
        self.error_json(self.run_cli("migrate"), 1)
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(self.inspect_legacy_rows(database), (1, [self.legacy_asset]))
        self.assertEqual(blocker.read_bytes(), b"existing user file")
        blocker.unlink()
        self.success_json(self.run_cli("migrate"))
        self.assertEqual(self.inspect_legacy_rows(database), (SCHEMA_VERSION, [self.legacy_asset]))

    def test_schema_failure_rolls_back_ddl_and_version_but_keeps_recovery_snapshot(self):
        database = self.create_legacy()

        def fail_after_partial_schema(connection):
            connection.execute("CREATE TABLE incomplete_migration (value TEXT)")
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
            connection.execute("DROP TABLE IF EXISTS ransomware_source_review_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_review_notifications")
            connection.execute("DROP TABLE IF EXISTS brand_username_review_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_runs")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_watches")
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            raise sqlite3.OperationalError("simulated failure during schema change")

        with patch("xti.adapters.sqlite.create_findings_schema", side_effect=fail_after_partial_schema):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(database).migrate()

        self.assertEqual(self.inspect_legacy_rows(database), (1, [self.legacy_asset]))
        with closing(sqlite3.connect(database)) as connection:
            tables = connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        self.assertEqual(tables, [("assets",)])
        backups = list((self.data / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.inspect_legacy_rows(backups[0]), (1, [self.legacy_asset]))
        self.success_json(self.run_cli("migrate"))
        self.assertEqual(self.inspect_legacy_rows(database), (SCHEMA_VERSION, [self.legacy_asset]))
        self.assertEqual(self.inspect_legacy_rows(backups[0]), (1, [self.legacy_asset]))

    def test_future_schema_is_rejected_without_backup_or_modification(self):
        database = self.create_legacy()
        with closing(sqlite3.connect(database)) as connection, connection:
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
            connection.execute("DROP TABLE IF EXISTS ransomware_source_review_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_review_notifications")
            connection.execute("DROP TABLE IF EXISTS brand_username_review_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_runs")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_watches")
            connection.execute("PRAGMA user_version=999")
        before = database.read_bytes()
        self.error_json(self.run_cli("migrate"), 1)
        self.assertEqual(database.read_bytes(), before)
        self.assertFalse((self.data / "backups").exists())

    def test_unrelated_and_corrupt_databases_are_never_migrated(self):
        self.data.mkdir()
        database = self.data / "xti.db"
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("CREATE TABLE private_data (value TEXT)")
            connection.execute("INSERT INTO private_data VALUES ('preserve')")
        for contents in (database.read_bytes(), b"not a database"):
            with self.subTest(contents=contents[:20]):
                database.write_bytes(contents)
                self.error_json(self.run_cli("migrate"), 1)
                self.assertEqual(database.read_bytes(), contents)
                self.assertFalse((self.data / "backups").exists())

    def test_missing_database_migration_does_not_initialize_storage(self):
        self.error_json(self.run_cli("migrate"), 1)
        self.assertFalse(self.data.exists())


if __name__ == "__main__":
    unittest.main()

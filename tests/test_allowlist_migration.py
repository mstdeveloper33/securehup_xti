"""Version seven upgrades add exceptions without rewriting existing evidence."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tests.public_notice_watch_legacy_fixture import remove_public_notice_watch_schema

from xti.adapters.schema import (
    ALLOWLIST_DDL,
    ALLOWLIST_V8_DDL,
    APPLICATION_ID,
    ASSESSMENTS_DDL,
    ASSETS_DDL,
    FINDINGS_DDL,
    INBOX_DDL,
    JOBS_DDL,
    MONITOR_DDL,
    OPERATIONS_DDL,
    SCHEMA_VERSION,
    VERSION_TABLES,
    validate_schema,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_allowlist import SQLiteAllowlistRepository


AT = "2026-10-29T09:00:00+00:00"
V7_TABLES = tuple(sorted(VERSION_TABLES[7]))


class AllowlistMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def legacy(self):
        path = self.root / "legacy" / "xti.db"
        path.parent.mkdir()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(ASSETS_DDL)
            for statements in (
                FINDINGS_DDL, JOBS_DDL, ASSESSMENTS_DDL, OPERATIONS_DDL,
                INBOX_DDL, MONITOR_DDL,
            ):
                for statement in statements:
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
            remove_public_notice_watch_schema(connection)
            connection.execute("DROP TABLE IF EXISTS public_notice_changes")
            connection.execute("DROP TABLE IF EXISTS public_notice_runs")
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
            connection.execute("PRAGMA user_version=7")
            connection.execute("INSERT INTO assets VALUES ('asset-1', 'example.com', ?)", (AT,))
            connection.execute(
                "INSERT INTO observations VALUES "
                "('obs-1', 'example-support.net', 'example-support.net', "
                "'fixture', 'digest', 1, NULL, ?)", (AT,),
            )
            connection.execute(
                "INSERT INTO findings VALUES "
                "('finding-1', 'asset-1', 'example.com', 'example-support.net', "
                "'rules-v1', '[\"fixture\"]', 'dismissed', ?, ?)", (AT, AT),
            )
            connection.execute("INSERT INTO finding_observations VALUES ('finding-1', 'obs-1')")
            connection.execute(
                "INSERT INTO reviews VALUES "
                "('review-1', 'finding-1', 'dismissed', 'Meşru alan adı', ?)", (AT,),
            )
            self.assertEqual(validate_schema(connection, allow_legacy=True), 7)
        return path

    def version_eight(self):
        path = self.legacy()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            for statement in ALLOWLIST_V8_DDL:
                connection.execute(statement)
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
            remove_public_notice_watch_schema(connection)
            connection.execute("DROP TABLE IF EXISTS public_notice_changes")
            connection.execute("DROP TABLE IF EXISTS public_notice_runs")
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
            connection.execute("PRAGMA user_version=8")
            connection.execute(
                "INSERT INTO allowlist_entries VALUES "
                "('entry-1', 'asset-1', 'example.com', 'example-support.net', "
                "1, 'Kalıcı meşru hizmet', ?, ?)", (AT, AT),
            )
            connection.execute(
                "INSERT INTO allowlist_events VALUES "
                "('event-1', 'entry-1', 'added', 'Kalıcı meşru hizmet', ?)", (AT,),
            )
            self.assertEqual(validate_schema(connection, allow_legacy=True), 8)
        return path

    @staticmethod
    def rows(path, tables):
        with closing(sqlite3.connect(path)) as connection:
            return {
                table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in tables
            }

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return validate_schema(connection, allow_legacy=True)

    def test_version_seven_migrates_with_backup_and_preserves_every_old_row(self):
        path = self.legacy()
        before = self.rows(path, V7_TABLES)
        result = SQLiteAssetRepository(path).migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (7, SCHEMA_VERSION))
        self.assertTrue(result["changed"])
        self.assertEqual(self.version(path), SCHEMA_VERSION)
        self.assertEqual(self.rows(path, V7_TABLES), before)
        self.assertEqual(
            self.rows(path, ("allowlist_entries", "allowlist_events")),
            {"allowlist_entries": [], "allowlist_events": []},
        )
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 7)
        self.assertEqual(self.rows(backup, V7_TABLES), before)
        info = SQLiteAssetRepository(path).inspect()
        self.assertEqual((info["allowlist_count"], info["active_allowlist_count"]), (0, 0))

    def test_partial_allowlist_schema_failure_rolls_back_and_keeps_recovery_copy(self):
        path = self.legacy()
        before = self.rows(path, V7_TABLES)

        def incomplete(connection):
            connection.execute(ALLOWLIST_DDL[0])
            raise sqlite3.OperationalError("Controlled allowlist failure")

        with patch("xti.adapters.sqlite.create_allowlist_schema", side_effect=incomplete):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 7)
        self.assertEqual(self.rows(path, V7_TABLES), before)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 7)
        self.assertEqual(self.rows(backups[0], V7_TABLES), before)

        SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), SCHEMA_VERSION)

    def test_version_eight_adds_expiration_fields_without_changing_policy_history(self):
        path = self.version_eight()
        before = self.rows(path, VERSION_TABLES[8])
        result = SQLiteAssetRepository(path).migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (8, SCHEMA_VERSION))
        self.assertEqual(self.version(path), SCHEMA_VERSION)
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 8)
        self.assertEqual(self.rows(backup, VERSION_TABLES[8]), before)
        with closing(sqlite3.connect(path)) as connection:
            entry = connection.execute(
                "SELECT id, asset_id, asset_value, domain, active, expires_at, "
                "reason, created_at, updated_at FROM allowlist_entries"
            ).fetchone()
            event = connection.execute(
                "SELECT id, entry_id, action, expires_at, reason, created_at "
                "FROM allowlist_events"
            ).fetchone()
        self.assertEqual(entry, (
            "entry-1", "asset-1", "example.com", "example-support.net", 1, None,
            "Kalıcı meşru hizmet", AT, AT,
        ))
        self.assertEqual(event, (
            "event-1", "entry-1", "added", None, "Kalıcı meşru hizmet", AT,
        ))
        details = SQLiteAllowlistRepository(path).get("entry-1")
        self.assertTrue(details.entry.active)
        self.assertIsNone(details.entry.expires_at)

    def test_failed_version_eight_rebuild_rolls_back_and_keeps_v8_backup(self):
        path = self.version_eight()
        before = self.rows(path, VERSION_TABLES[8])

        def incomplete(connection):
            connection.execute("DROP INDEX allowlist_active_asset_domain")
            raise sqlite3.OperationalError("Controlled expiry migration failure")

        with patch("xti.adapters.sqlite.migrate_allowlist_expiry_schema", side_effect=incomplete):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 8)
        self.assertEqual(self.rows(path, VERSION_TABLES[8]), before)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 8)
        self.assertEqual(self.rows(backups[0], VERSION_TABLES[8]), before)

    def test_legacy_reads_never_migrate_implicitly(self):
        path = self.legacy()
        before = path.read_bytes()
        repository = SQLiteAssetRepository(path)
        for action in (repository.initialize, repository.inspect, repository.list):
            with self.subTest(action=action), self.assertRaisesRegex(StorageError, "migrate"):
                action()
            self.assertEqual(path.read_bytes(), before)
        self.assertFalse((path.parent / "backups").exists())

    def test_backup_restore_preserves_entry_and_append_only_event_history(self):
        path = self.legacy()
        SQLiteAssetRepository(path).migrate()
        repository = SQLiteAllowlistRepository(path)
        entry, _ = repository.activate(
            "asset-1", "example.com", "example-support.net", "Meşru hizmet", AT, None,
        )
        repository.revoke(
            entry.id, "Yeniden değerlendirilecek", "2026-10-29T10:00:00+00:00",
        )
        repository.activate(
            "asset-1", "example.com", "example-support.net", "Tekrar doğrulandı",
            "2026-10-29T11:00:00+00:00", None,
        )
        tables = (*VERSION_TABLES[SCHEMA_VERSION], "sqlite_sequence")
        before = self.rows(path, tables)
        backup = self.root / "policy-backup.db"
        SQLiteAssetRepository(path).backup(backup)
        restored = self.root / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(self.version(restored), SCHEMA_VERSION)
        self.assertEqual(self.rows(restored, tables), before)
        details = SQLiteAllowlistRepository(restored).get(entry.id)
        self.assertTrue(details.entry.active)
        self.assertEqual(
            tuple(event.action for event in details.events),
            ("added", "revoked", "reactivated"),
        )

    def test_changed_policy_constraints_are_rejected_without_mutation(self):
        path = self.legacy()
        SQLiteAssetRepository(path).migrate()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("DROP TABLE allowlist_events")
            connection.execute(
                ALLOWLIST_DDL[1].replace(
                    " CHECK (action IN ('added', 'reactivated', 'updated', 'revoked'))", "",
                )
            )
            connection.execute(ALLOWLIST_DDL[3])
        before = path.read_bytes()
        with self.assertRaisesRegex(StorageError, "istisna kayıt düzeni"):
            SQLiteAssetRepository(path).inspect()
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

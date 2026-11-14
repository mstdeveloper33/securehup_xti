"""Session schema upgrades preserve evidence, read state and recovery snapshots."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import (
    APPLICATION_ID, ASSETS_DDL, FINDINGS_DDL, JOBS_DDL, ASSESSMENTS_DDL,
    OPERATIONS_DDL, INBOX_DDL, MONITOR_DDL, SCHEMA_VERSION, VERSION_TABLES,
    validate_schema,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError


AT = "2026-10-29T00:00:00+00:00"
OLD_TABLES = (
    "assets", "observations", "findings", "finding_observations", "reviews",
    "scan_jobs", "scan_attempts", "finding_assessments", "provider_cooldowns",
    "cleanup_runs", "notifications",
)


class MonitorMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def legacy(self, version=6):
        path = self.root / f"v{version}" / "xti.db"
        path.parent.mkdir()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(ASSETS_DDL)
            for minimum, statements in ((2, FINDINGS_DDL), (3, JOBS_DDL),
                                        (4, ASSESSMENTS_DDL), (5, OPERATIONS_DDL),
                                        (6, INBOX_DDL)):
                if version >= minimum:
                    for statement in statements:
                        connection.execute(statement)
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
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
            connection.execute("DROP TABLE IF EXISTS collection_step_receipts")
            connection.execute("DROP TABLE IF EXISTS collection_session_steps")
            connection.execute("DROP TABLE IF EXISTS collection_sessions")
            connection.execute(f"PRAGMA user_version={version}")
            connection.execute("INSERT INTO assets VALUES ('asset-1', 'example.com', ?)", (AT,))
            if version >= 2:
                for number, status in ((1, "suspicious"), (2, "new")):
                    domain = f"example-support{number}.net"
                    connection.execute(
                        "INSERT INTO observations VALUES (?, ?, ?, 'source', 'fixture', ?, NULL, ?)",
                        (f"obs-{number}", domain, domain, number, AT),
                    )
                    connection.execute(
                        "INSERT INTO findings VALUES (?, 'asset-1', 'example.com', ?, 'rules-v1', "
                        "'[\"fixture\"]', ?, ?, ?)", (f"finding-{number}", domain, status, AT, AT),
                    )
                    connection.execute("INSERT INTO finding_observations VALUES (?, ?)",
                                       (f"finding-{number}", f"obs-{number}"))
                connection.execute(
                    "INSERT INTO reviews VALUES ('review-1', 'finding-1', 'suspicious', 'İncelendi', ?)",
                    (AT,),
                )
            if version >= 3:
                connection.execute(
                    "INSERT INTO scan_jobs VALUES ('job-1', '[\"example.com\"]', 0, 'crt.sh', "
                    "'rules-v1', 'failed', ?, ?, 1)", (AT, AT),
                )
                connection.execute(
                    "INSERT INTO scan_attempts VALUES ('attempt-1', 'job-1', 1, 'failed', ?, ?, "
                    "NULL, 'Kaynak hatası', '[]', NULL)", (AT, AT),
                )
            if version >= 4:
                connection.execute(
                    "INSERT INTO finding_assessments VALUES ('check-1', 'finding-1', ?)",
                    ('{"legacy_payload":"retain verbatim"}',),
                )
            if version >= 5:
                connection.execute(
                    "INSERT INTO provider_cooldowns VALUES ('crt.sh', ?, ?, 'retry_after')", (AT, AT),
                )
                connection.execute(
                    "INSERT INTO cleanup_runs VALUES ('cleanup-1', ?, ?, 2, ?, 'prior-backup.db')",
                    (AT, AT, "a" * 64),
                )
            if version >= 6:
                for number, sequence, read_at in ((1, 17, AT), (2, 29, None)):
                    connection.execute(
                        "INSERT INTO notifications VALUES (?, ?, ?, 'finding_created', 'new', ?, ?)",
                        (sequence, f"notice-{number}", f"finding-{number}", AT, read_at),
                    )
                # A retired sequence must not become reusable after migration.
                connection.execute("UPDATE sqlite_sequence SET seq = 99 WHERE name = 'notifications'")
            self.assertEqual(validate_schema(connection, allow_legacy=True), version)
        return path

    @staticmethod
    def rows(path, tables):
        with closing(sqlite3.connect(path)) as connection:
            return {name: connection.execute(f"SELECT * FROM {name} ORDER BY rowid").fetchall()
                    for name in tables}

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return validate_schema(connection, allow_legacy=True)

    def seed_run(self, path, *, status="running"):
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "INSERT INTO monitor_runs VALUES ('run-1', '[\"example.com\"]', '[\"crt.sh\"]', "
                "0, 'rules-v1', 3, 300, 900, ?, ?, ?, ?, ?)",
                (status, AT, None if status == "running" else AT,
                 None if status == "running" else 1.5, None if status == "running" else "cycles"),
            )
            connection.execute("INSERT INTO monitor_jobs VALUES ('run-1', 1, 'crt.sh', 'job-1')")

    def test_version_six_preserves_all_rows_read_state_and_sequence_without_backfill(self):
        self.assertEqual(VERSION_TABLES[6], frozenset(OLD_TABLES))
        path = self.legacy()
        tables = (*OLD_TABLES, "sqlite_sequence")
        before = self.rows(path, tables)
        repository = SQLiteAssetRepository(path)
        with patch("xti.adapters.sqlite.backfill_inbox", side_effect=AssertionError("No second inbox backfill")):
            result = repository.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (6, SCHEMA_VERSION))
        self.assertEqual(self.version(path), SCHEMA_VERSION)
        self.assertEqual(self.rows(path, tables), before)
        self.assertEqual(self.rows(path, ("monitor_runs", "monitor_jobs")),
                         {"monitor_runs": [], "monitor_jobs": []})
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 6)
        self.assertEqual(self.rows(backup, tables), before)
        info = repository.inspect()
        self.assertEqual((info["monitor_count"], info["running_monitor_count"]), (0, 0))
        self.assertEqual((info["notification_count"], info["unread_notification_count"]), (2, 1))

    def test_versions_one_through_five_keep_old_rows_and_empty_session_history(self):
        for version in range(1, 6):
            with self.subTest(version=version):
                path = self.legacy(version)
                tables = VERSION_TABLES[version]
                before = self.rows(path, tables)
                result = SQLiteAssetRepository(path).migrate()
                self.assertEqual(self.version(path), SCHEMA_VERSION)
                self.assertEqual(self.rows(path, tables), before)
                self.assertEqual(self.rows(Path(result["backup"]), tables), before)
                self.assertEqual(self.version(Path(result["backup"])), version)
                self.assertEqual(self.rows(path, ("monitor_runs", "monitor_jobs")),
                                 {"monitor_runs": [], "monitor_jobs": []})
                self.assertEqual(len(self.rows(path, ("notifications",))["notifications"]),
                                 0 if version == 1 else 2)

    def test_new_database_has_valid_empty_session_tables(self):
        path = self.root / "new" / "xti.db"
        repository = SQLiteAssetRepository(path)
        repository.initialize()
        self.assertEqual(self.version(path), SCHEMA_VERSION)
        self.assertEqual(self.rows(path, ("monitor_runs", "monitor_jobs")),
                         {"monitor_runs": [], "monitor_jobs": []})
        self.assertEqual(repository.inspect()["monitor_count"], 0)

    def test_partial_schema_failure_rolls_back_but_keeps_original_backup(self):
        path = self.legacy()
        before = self.rows(path, (*OLD_TABLES, "sqlite_sequence"))

        def incomplete(connection):
            connection.execute(MONITOR_DDL[0])
            raise sqlite3.OperationalError("Controlled schema failure")

        with patch("xti.adapters.sqlite.create_monitor_schema", side_effect=incomplete):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 6)
        self.assertEqual(self.rows(path, (*OLD_TABLES, "sqlite_sequence")), before)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 6)
        self.assertEqual(self.rows(backups[0], (*OLD_TABLES, "sqlite_sequence")), before)
        SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), SCHEMA_VERSION)

    def test_failed_backup_does_not_begin_session_ddl(self):
        path = self.legacy()
        before = path.read_bytes()
        with patch.object(SQLiteAssetRepository, "backup", side_effect=StorageError("Backup failed")):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 6)
        self.assertEqual(path.read_bytes(), before)

    def test_old_read_and_init_never_migrate_implicitly(self):
        path = self.legacy()
        before = path.read_bytes()
        repository = SQLiteAssetRepository(path)
        for action in (repository.inspect, repository.list, repository.initialize):
            with self.subTest(action=action), self.assertRaisesRegex(StorageError, "migrate"):
                action()
            self.assertEqual(path.read_bytes(), before)
        self.assertFalse((path.parent / "backups").exists())

    def test_repeated_migration_preserves_session_rows_and_does_not_create_new_backup(self):
        path = self.legacy()
        repository = SQLiteAssetRepository(path)
        repository.migrate()
        self.seed_run(path)
        before = path.read_bytes()
        backups = set((path.parent / "backups").iterdir())
        self.assertEqual(repository.migrate(), {"from_version": SCHEMA_VERSION,
                                               "to_version": SCHEMA_VERSION,
                                               "changed": False, "backup": None})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(set((path.parent / "backups").iterdir()), backups)
        self.assertEqual(repository.inspect()["running_monitor_count"], 1)

    def test_backup_restore_retains_active_session_links_and_legacy_read_state(self):
        path = self.legacy()
        repository = SQLiteAssetRepository(path)
        repository.migrate()
        self.seed_run(path)
        tables = (*VERSION_TABLES[SCHEMA_VERSION], "sqlite_sequence")
        before = self.rows(path, tables)
        backup = self.root / "monitor-backup.db"
        repository.backup(backup)
        restored = self.root / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(self.version(restored), SCHEMA_VERSION)
        self.assertEqual(self.rows(restored, tables), before)
        self.assertEqual(SQLiteAssetRepository(restored).inspect()["running_monitor_count"], 1)
        restored_bytes = restored.read_bytes()
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(restored.read_bytes(), restored_bytes)

    def test_unknown_version_is_rejected_without_mutation_or_backup(self):
        path = self.legacy()
        with closing(sqlite3.connect(path)) as connection:
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
            connection.execute("PRAGMA user_version=888")
        before = path.read_bytes()
        with self.assertRaises(StorageError):
            SQLiteAssetRepository(path).migrate()
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((path.parent / "backups").exists())

    def test_changed_session_constraints_are_rejected(self):
        path = self.root / "changed" / "xti.db"
        repository = SQLiteAssetRepository(path)
        repository.initialize()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("DROP TABLE monitor_jobs")
            connection.execute(MONITOR_DDL[1].replace(" CHECK (cycle BETWEEN 1 AND 1000)", ""))
        before = path.read_bytes()
        with self.assertRaisesRegex(StorageError, "izleme denemesi"):
            repository.inspect()
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

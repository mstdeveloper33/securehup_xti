"""Explicit inbox upgrades retain legacy data and recover from partial failures."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from tests.public_notice_watch_legacy_fixture import remove_public_notice_watch_schema

from xti.adapters.schema import (
    APPLICATION_ID, ASSETS_DDL, FINDINGS_DDL, JOBS_DDL, ASSESSMENTS_DDL,
    OPERATIONS_DDL, INBOX_DDL, SCHEMA_VERSION, VERSION_TABLES, validate_schema,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError


RECORDED_AT = "2026-09-01T00:00:00+00:00"
MIGRATED_AT = datetime(2026, 10, 29, 1, 2, 3, tzinfo=timezone.utc)
LEGACY_TABLES = (
    "assets", "observations", "findings", "finding_observations", "reviews",
    "scan_jobs", "scan_attempts", "finding_assessments", "provider_cooldowns",
    "cleanup_runs",
)


class InboxMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def create_legacy(self, version=5):
        path = self.root / f"v{version}" / "xti.db"
        path.parent.mkdir()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(ASSETS_DDL)
            for minimum, statements in ((2, FINDINGS_DDL), (3, JOBS_DDL),
                                        (4, ASSESSMENTS_DDL), (5, OPERATIONS_DDL)):
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
            connection.execute(f"PRAGMA user_version={version}")
            connection.execute("INSERT INTO assets VALUES ('asset-1', 'example.com', ?)",
                               (RECORDED_AT,))
            if version >= 2:
                for number, status in enumerate(("new", "suspicious", "dismissed", "uncertain"), 1):
                    domain = f"example-support{number}.net"
                    # Deliberately decreasing timestamps: insertion order is authoritative.
                    created_at = f"2026-08-{10 - number:02d}T00:00:00+00:00"
                    connection.execute(
                        "INSERT INTO observations VALUES (?, ?, ?, 'source', 'source-hash', ?, NULL, ?)",
                        (f"observation-{number}", domain, domain, number, RECORDED_AT),
                    )
                    connection.execute(
                        "INSERT INTO findings VALUES (?, 'asset-1', 'example.com', ?, 'rules-v1', "
                        "'[\"reason\"]', ?, ?, ?)",
                        (f"finding-{number}", domain, status, created_at, RECORDED_AT),
                    )
                    connection.execute("INSERT INTO finding_observations VALUES (?, ?)",
                                       (f"finding-{number}", f"observation-{number}"))
                    if status != "new":
                        connection.execute("INSERT INTO reviews VALUES (?, ?, ?, 'İncelendi', ?)",
                                           (f"review-{number}", f"finding-{number}", status, RECORDED_AT))
            if version >= 3:
                connection.execute(
                    "INSERT INTO scan_jobs VALUES ('job-1', '[\"example.com\"]', 0, 'crt.sh', "
                    "'rules-v1', 'failed', ?, ?, 1)", (RECORDED_AT, RECORDED_AT),
                )
                connection.execute(
                    "INSERT INTO scan_attempts VALUES ('attempt-1', 'job-1', 1, 'failed', ?, ?, "
                    "NULL, 'Kaynak yanıt vermedi', '[]', NULL)", (RECORDED_AT, RECORDED_AT),
                )
            if version >= 4:
                # Migration must retain even opaque payloads; it does not rewrite evidence.
                connection.execute("INSERT INTO finding_assessments VALUES ('check-1', 'finding-1', ?)",
                                   ('{"legacy_evidence":"preserve exactly"}',))
            if version >= 5:
                connection.execute(
                    "INSERT INTO provider_cooldowns VALUES ('crt.sh', ?, ?, 'retry_after')",
                    ("2026-09-01T00:01:00+00:00", RECORDED_AT),
                )
                connection.execute(
                    "INSERT INTO cleanup_runs VALUES ('cleanup-1', ?, ?, 2, ?, '/tmp/preserved.db')",
                    (RECORDED_AT, "2026-01-01T00:00:00+00:00", "a" * 64),
                )
            self.assertEqual(validate_schema(connection, allow_legacy=True), version)
        return path

    @staticmethod
    def snapshot(path, tables):
        with closing(sqlite3.connect(path)) as connection:
            return {table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                    for table in tables}

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return validate_schema(connection, allow_legacy=True)

    def test_versions_one_through_five_preserve_every_old_row_and_original_backup(self):
        self.assertEqual(VERSION_TABLES[5], frozenset(LEGACY_TABLES))
        for version in range(1, 6):
            with self.subTest(version=version):
                path = self.create_legacy(version)
                old_tables = VERSION_TABLES[version]
                before = self.snapshot(path, old_tables)
                repository = SQLiteAssetRepository(path)
                with patch("xti.adapters.sqlite.datetime") as clock:
                    clock.now.return_value = MIGRATED_AT
                    result = repository.migrate()
                self.assertEqual((result["from_version"], result["to_version"]),
                                 (version, SCHEMA_VERSION))
                self.assertTrue(result["changed"])
                self.assertEqual(self.version(path), SCHEMA_VERSION)
                self.assertEqual(self.snapshot(path, old_tables), before)
                backup = Path(result["backup"])
                self.assertEqual(self.version(backup), version)
                self.assertEqual(self.snapshot(backup, old_tables), before)
                rows = self.snapshot(path, ("notifications",))["notifications"]
                expected_count = 0 if version == 1 else 4
                self.assertEqual(len(rows), expected_count)
                self.assertEqual([row[0] for row in rows], list(range(1, expected_count + 1)))
                self.assertEqual([row[2] for row in rows],
                                 [f"finding-{number}" for number in range(1, expected_count + 1)])
                self.assertEqual(len({row[1] for row in rows}), expected_count)
                for row in rows:
                    self.assertEqual(str(UUID(row[1])), row[1])
                    self.assertEqual(row[3:], ("finding_created", "existing", MIGRATED_AT.isoformat(), None))
                info = repository.inspect()
                self.assertEqual(info["notification_count"], expected_count)
                self.assertEqual(info["unread_notification_count"], expected_count)
                self.assertEqual(info["cleanup_count"], int(version >= 5))
                self.assertEqual(info["cooldown_count"], int(version >= 5))

    def test_new_database_has_empty_valid_inbox(self):
        path = self.root / "new" / "xti.db"
        repository = SQLiteAssetRepository(path)
        repository.initialize()
        self.assertEqual(self.version(path), SCHEMA_VERSION)
        self.assertEqual(self.snapshot(path, ("notifications",)), {"notifications": []})
        self.assertEqual(repository.inspect()["notification_count"], 0)
        self.assertEqual(repository.inspect()["unread_notification_count"], 0)

    def test_missing_autoincrement_is_rejected_even_when_sqlite_sequence_still_exists(self):
        path = self.root / "changed-layout" / "xti.db"
        repository = SQLiteAssetRepository(path)
        repository.initialize()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("DROP TABLE notifications")
            for statement in INBOX_DDL:
                connection.execute(statement.replace("AUTOINCREMENT ", ""))
            self.assertEqual(connection.execute(
                "SELECT name FROM sqlite_schema WHERE name = 'sqlite_sequence'"
            ).fetchall(), [("sqlite_sequence",)])
        before = path.read_bytes()
        backup = self.root / "invalid-backup.db"
        for action in (repository.inspect, repository.initialize, repository.migrate,
                       lambda: repository.backup(backup)):
            with self.subTest(action=action), self.assertRaisesRegex(StorageError, "bildirim sıra"):
                action()
            self.assertEqual(path.read_bytes(), before)
        self.assertFalse(backup.exists())

    def test_canonical_inbox_remains_valid_after_vacuum(self):
        path = self.create_legacy()
        repository = SQLiteAssetRepository(path)
        repository.migrate()
        before = self.snapshot(path, (*LEGACY_TABLES, "notifications", "sqlite_sequence"))
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("VACUUM")
        self.assertEqual(self.version(path), SCHEMA_VERSION)
        self.assertEqual(self.snapshot(path, (*LEGACY_TABLES, "notifications", "sqlite_sequence")), before)
        self.assertEqual(repository.inspect()["notification_count"], 4)

    def test_old_reads_and_init_require_migration_without_mutating_database(self):
        path = self.create_legacy()
        before = path.read_bytes()
        repository = SQLiteAssetRepository(path)
        for action in (repository.initialize, repository.list, repository.inspect):
            with self.subTest(action=action), self.assertRaisesRegex(StorageError, "migrate"):
                action()
            self.assertEqual(path.read_bytes(), before)
        self.assertFalse((path.parent / "backups").exists())

    def test_repeated_migration_keeps_identity_read_state_and_creates_no_backup(self):
        path = self.create_legacy()
        repository = SQLiteAssetRepository(path)
        repository.migrate()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("UPDATE notifications SET read_at = ? WHERE sequence = 1",
                               (MIGRATED_AT.isoformat(),))
        before = path.read_bytes()
        backups = set((path.parent / "backups").iterdir())
        self.assertEqual(repository.migrate(), {"from_version": SCHEMA_VERSION,
                                               "to_version": SCHEMA_VERSION,
                                               "backup": None, "changed": False})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(set((path.parent / "backups").iterdir()), backups)
        self.assertEqual(repository.inspect()["unread_notification_count"], 3)

    def test_failed_backup_prevents_any_schema_change(self):
        path = self.create_legacy()
        blocker = path.parent / "backups"
        blocker.write_bytes(b"existing file")
        before = path.read_bytes()
        with self.assertRaises(StorageError):
            SQLiteAssetRepository(path).migrate()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.version(path), 5)
        self.assertEqual(blocker.read_bytes(), b"existing file")

    def test_partial_backfill_failure_rolls_back_new_table_and_sequence_and_can_retry(self):
        path = self.create_legacy()
        repository = SQLiteAssetRepository(path)
        before = self.snapshot(path, LEGACY_TABLES)
        with patch("xti.adapters.schema.uuid4", side_effect=[uuid4(), sqlite3.OperationalError("disk full")]):
            with self.assertRaises(StorageError):
                repository.migrate()
        self.assertEqual(self.version(path), 5)
        self.assertEqual(self.snapshot(path, LEGACY_TABLES), before)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute(
                "SELECT name FROM sqlite_schema WHERE name IN ('notifications', 'sqlite_sequence')"
            ).fetchall(), [])
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 5)
        self.assertEqual(self.snapshot(backups[0], LEGACY_TABLES), before)
        repository.migrate()
        self.assertEqual(self.version(path), SCHEMA_VERSION)
        self.assertEqual(self.snapshot(path, LEGACY_TABLES), before)
        self.assertEqual(repository.inspect()["notification_count"], 4)
        self.assertEqual(len(list((path.parent / "backups").glob("*.db"))), 2)

    def test_commit_failure_rolls_back_all_migration_work_and_keeps_valid_backup(self):
        path = self.create_legacy()
        before = self.snapshot(path, LEGACY_TABLES)
        real_connect = sqlite3.connect

        class BrokenCommit(sqlite3.Connection):
            def commit(self):
                raise sqlite3.OperationalError("Injected commit failure")

        def connect(*args, **kwargs):
            return real_connect(*args, **kwargs, factory=BrokenCommit)

        with patch("xti.adapters.sqlite.sqlite3.connect", side_effect=connect):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 5)
        self.assertEqual(self.snapshot(path, LEGACY_TABLES), before)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 5)
        self.assertEqual(self.snapshot(backups[0], LEGACY_TABLES), before)

    def test_legacy_restore_keeps_format_until_migration_and_never_changes_source(self):
        path = self.create_legacy()
        original = path.read_bytes()
        restored = self.root / "restored-legacy" / "xti.db"
        SQLiteAssetRepository.restore(path, restored)
        self.assertEqual(self.version(restored), 5)
        self.assertEqual(self.snapshot(restored, LEGACY_TABLES), self.snapshot(path, LEGACY_TABLES))
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteAssetRepository(restored).inspect()
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(SQLiteAssetRepository(restored).inspect()["notification_count"], 4)
        self.assertEqual(path.read_bytes(), original)

    def test_current_backup_restore_preserves_inbox_and_does_not_overwrite_existing_files(self):
        path = self.create_legacy()
        repository = SQLiteAssetRepository(path)
        repository.migrate()
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("UPDATE notifications SET read_at = ? WHERE sequence IN (1, 3)",
                               (MIGRATED_AT.isoformat(),))
        tables = (*LEGACY_TABLES, "notifications", "sqlite_sequence")
        before = self.snapshot(path, tables)
        backup = self.root / "current-backup.db"
        restored = self.root / "restored-current" / "xti.db"
        repository.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(self.version(restored), SCHEMA_VERSION)
        self.assertEqual(self.snapshot(backup, tables), before)
        self.assertEqual(self.snapshot(restored, tables), before)
        self.assertEqual(SQLiteAssetRepository(restored).inspect()["unread_notification_count"], 2)
        backup_bytes, restored_bytes = backup.read_bytes(), restored.read_bytes()
        with self.assertRaises(StorageError):
            repository.backup(backup)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(backup.read_bytes(), backup_bytes)
        self.assertEqual(restored.read_bytes(), restored_bytes)


if __name__ == "__main__":
    unittest.main()

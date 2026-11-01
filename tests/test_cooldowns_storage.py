"""Provider waits survive restart, competing extensions and explicit migrations."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from xti.adapters.schema import (
    APPLICATION_ID, ASSETS_DDL, FINDINGS_DDL, JOBS_DDL, ASSESSMENTS_DDL,
    SCHEMA_VERSION, validate_schema,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.sqlite_assessments import SQLiteAssessmentRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.domain.assets import ValidationError
from tests.test_assessments_storage import checked


RECORDED_AT = "2026-10-28T12:00:00+00:00"
DEADLINE = "2026-10-28T12:10:00+00:00"


class CooldownStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.repo = SQLiteCooldownRepository(self.path)

    def test_new_instance_reads_wait_without_writing_or_clearing_expired_state(self):
        saved = self.repo.extend("crt.sh", DEADLINE, RECORDED_AT, "retry_after")
        before = self.path.read_bytes()
        reopened = SQLiteCooldownRepository(self.path)
        self.assertEqual(reopened.get("crt.sh"), saved)
        self.assertEqual(reopened.list(), (saved,))
        self.assertIsNone(reopened.get("urlscan"))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.assets.inspect()["cooldown_count"], 1)

    def test_independent_provider_waits_and_sorted_listing(self):
        urlscan = self.repo.extend("urlscan", DEADLINE, RECORDED_AT, "rate_limit")
        crt = self.repo.extend("crt.sh", "2026-10-28T12:00:01Z", RECORDED_AT, "request_spacing")
        self.assertEqual(self.repo.list(), (crt, urlscan))
        self.assertEqual(self.repo.get("urlscan"), urlscan)
        self.assertEqual(self.repo.get("crt.sh"), crt)

    def test_offsets_normalize_and_later_instant_wins_instead_of_text_order(self):
        earlier = self.repo.extend("urlscan", "2026-10-28T15:09:00+03:00",
                                   "2026-10-28T15:00:00+03:00", "rate_limit")
        self.assertEqual(earlier.not_before, "2026-10-28T12:09:00+00:00")
        self.assertEqual(earlier.recorded_at, RECORDED_AT)
        later = self.repo.extend("urlscan", DEADLINE, RECORDED_AT, "retry_after")
        self.assertEqual(later.not_before, DEADLINE)
        self.assertEqual(self.repo.get("urlscan"), later)

    def test_shorter_or_equal_extension_preserves_previous_receipt_and_reason(self):
        original = self.repo.extend("crt.sh", DEADLINE, RECORDED_AT, "retry_after")
        before = self.path.read_bytes()
        for deadline in ("2026-10-28T12:00:02Z", "2026-10-28T15:10:00+03:00"):
            with self.subTest(deadline=deadline):
                saved = self.repo.extend("crt.sh", deadline, "2026-10-28T12:00:01Z", "request_spacing")
                self.assertEqual(saved, original)
                self.assertEqual(self.path.read_bytes(), before)

    def test_maximum_utc_deadline_is_preserved_without_numeric_overflow(self):
        maximum = datetime.max.replace(tzinfo=timezone.utc).isoformat()
        saved = self.repo.extend("urlscan", maximum, RECORDED_AT, "provider_wait")
        self.assertEqual(saved.not_before, maximum)
        self.assertEqual(SQLiteCooldownRepository(self.path).get("urlscan"), saved)
        self.assertEqual(self.repo.extend("urlscan", DEADLINE, RECORDED_AT, "request_spacing"), saved)

    def test_deadline_before_receipt_is_rejected_as_input_and_corrupt_state(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.repo.extend("crt.sh", "2026-10-28T11:59:59Z", RECORDED_AT, "rate_limit")
        self.assertEqual(self.path.read_bytes(), before)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO provider_cooldowns VALUES (?, ?, ?, ?)",
                               ("crt.sh", "2026-10-28T11:59:59Z", RECORDED_AT, "rate_limit"))
        before = self.path.read_bytes()
        for action in (self.repo.list, lambda: self.repo.get("crt.sh"),
                       lambda: self.repo.extend("crt.sh", DEADLINE, RECORDED_AT, "retry_after")):
            with self.assertRaises(StorageError):
                action()
            self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_arguments_are_rejected_without_mutating_database(self):
        before = self.path.read_bytes()
        arguments = [
            ("unknown", DEADLINE, RECORDED_AT, "rate_limit"),
            ("urlscan", DEADLINE, RECORDED_AT, "arbitrary"),
            ("urlscan", "2026-10-28T12:00:00", RECORDED_AT, "rate_limit"),
            ("urlscan", DEADLINE, "invalid", "rate_limit"),
            ("urlscan", "2026-10-28 12:00:00Z", RECORDED_AT, "rate_limit"),
            ("urlscan", "2026-10-28T12:00:00.0000001Z", RECORDED_AT, "rate_limit"),
            ("urlscan", "9999-12-31T23:59:59-23:59", RECORDED_AT, "rate_limit"),
            ("urlscan", None, RECORDED_AT, "rate_limit"),
        ]
        for item in arguments:
            with self.subTest(arguments=item), self.assertRaises(ValidationError):
                self.repo.extend(*item)
            self.assertEqual(self.path.read_bytes(), before)
        for provider in ("unknown", None, []):
            with self.subTest(provider=provider), self.assertRaises(ValidationError):
                self.repo.get(provider)

    def test_corrupt_rows_fail_closed_and_cannot_be_replaced_with_new_wait(self):
        for column, value in (("not_before", "invalid"), ("recorded_at", "2026-10-28"),
                              ("reason", "invalid")):
            with self.subTest(column=column):
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    connection.execute("DELETE FROM provider_cooldowns")
                self.repo.extend("urlscan", DEADLINE, RECORDED_AT, "rate_limit")
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    connection.execute(f"UPDATE provider_cooldowns SET {column} = ?", (value,))
                before = self.path.read_bytes()
                for action in (
                    lambda: self.repo.get("urlscan"), self.repo.list,
                    lambda: self.repo.extend("urlscan", "2027-01-01T00:00:00Z", RECORDED_AT, "provider_wait"),
                ):
                    with self.assertRaises(StorageError):
                        action()
                    self.assertEqual(self.path.read_bytes(), before)

    def test_unknown_stored_provider_is_not_silently_ignored_by_listing(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO provider_cooldowns VALUES (?, ?, ?, ?)",
                               ("unexpected", DEADLINE, RECORDED_AT, "rate_limit"))
        with self.assertRaises(StorageError):
            self.repo.list()

    def test_missing_database_reads_and_extensions_do_not_initialize(self):
        missing = Path(self.temp.name) / "absent" / "xti.db"
        repository = SQLiteCooldownRepository(missing)
        for action in (repository.list, lambda: repository.get("crt.sh"),
                       lambda: repository.extend("crt.sh", DEADLINE, RECORDED_AT, "rate_limit")):
            with self.assertRaises(StorageError):
                action()
            self.assertFalse(missing.parent.exists())

    def test_competing_extensions_keep_longest_deadline(self):
        barrier = threading.Barrier(2)

        def extend(deadline):
            repository = SQLiteCooldownRepository(self.path)
            barrier.wait(timeout=5)
            return repository.extend("urlscan", deadline, RECORDED_AT, "rate_limit")

        with ThreadPoolExecutor(max_workers=2) as executor:
            short = executor.submit(extend, "2026-10-28T12:01:00Z")
            long = executor.submit(extend, DEADLINE)
            short.result(timeout=10)
            long.result(timeout=10)
        self.assertEqual(self.repo.get("urlscan").not_before, DEADLINE)
        self.assertEqual(len(self.repo.list()), 1)

    def test_failed_commit_rolls_back_extension(self):
        original = self.repo.extend("crt.sh", DEADLINE, RECORDED_AT, "retry_after")
        real_connect = sqlite3.connect

        class BrokenCommit(sqlite3.Connection):
            def commit(self):
                raise sqlite3.OperationalError("Injected disk failure")

        def connect(*args, **kwargs):
            return real_connect(*args, **kwargs, factory=BrokenCommit)

        with patch("xti.adapters.sqlite.sqlite3.connect", side_effect=connect):
            with self.assertRaises(StorageError):
                self.repo.extend("crt.sh", "2026-10-28T13:00:00Z", RECORDED_AT, "rate_limit")
        self.assertEqual(self.repo.get("crt.sh"), original)

    def test_backup_restore_preserves_wait_and_cleanup_audit(self):
        saved = self.repo.extend("urlscan", DEADLINE, RECORDED_AT, "rate_limit")
        audit = ("run-1", RECORDED_AT, "2026-07-01T00:00:00+00:00", 3, "a" * 64, "/tmp/backup.db")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO cleanup_runs VALUES (?, ?, ?, ?, ?, ?)", audit)
        destination = self.path.parent / "backup.db"
        restored = self.path.parent / "restored" / "xti.db"
        self.assets.backup(destination)
        SQLiteAssetRepository.restore(destination, restored)
        self.assertEqual(SQLiteCooldownRepository(restored).list(), (saved,))
        with closing(sqlite3.connect(restored)) as connection:
            self.assertEqual(connection.execute("SELECT * FROM cleanup_runs").fetchall(), [audit])
        self.assertEqual(SQLiteAssetRepository(restored).inspect()["cleanup_count"], 1)


class OperationsMigrationTests(unittest.TestCase):
    TABLES = ("assets", "observations", "findings", "finding_observations", "reviews",
              "scan_jobs", "scan_attempts", "finding_assessments")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(ASSETS_DDL)
            for statement in FINDINGS_DDL + JOBS_DDL + ASSESSMENTS_DDL:
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
            connection.execute("PRAGMA user_version=4")
            connection.execute("INSERT INTO assets VALUES ('asset-1', 'example.com', ?)", (RECORDED_AT,))
            connection.execute(
                "INSERT INTO observations VALUES ('observation-1', 'example-support.net', "
                "'example-support.net', 'https://crt.sh/?id=42', 'source-hash', 1, NULL, ?)", (RECORDED_AT,),
            )
            connection.execute(
                "INSERT INTO findings VALUES ('finding-1', 'asset-1', 'example.com', "
                "'example-support.net', 'rules-v1', '[\"reason\"]', 'uncertain', ?, ?)",
                (RECORDED_AT, RECORDED_AT),
            )
            connection.execute("INSERT INTO finding_observations VALUES ('finding-1', 'observation-1')")
            connection.execute("INSERT INTO reviews VALUES ('review-1', 'finding-1', 'uncertain', 'Ek inceleme', ?)",
                               (RECORDED_AT,))
            connection.execute(
                "INSERT INTO scan_jobs VALUES ('job-1', '[\"example.com\"]', 0, 'crt.sh', "
                "'rules-v1', 'failed', ?, ?, 1)", (RECORDED_AT, RECORDED_AT),
            )
            connection.execute(
                "INSERT INTO scan_attempts VALUES ('attempt-1', 'job-1', 1, 'failed', ?, ?, "
                "NULL, 'Kaynak yanıt vermedi', '[]', NULL)", (RECORDED_AT, RECORDED_AT),
            )
            connection.execute("INSERT INTO finding_assessments VALUES ('check-1', 'finding-1', ?)",
                               (json.dumps(asdict(checked())),))
        self.assets = SQLiteAssetRepository(self.path)

    def snapshot(self, path):
        with closing(sqlite3.connect(path)) as connection:
            return {table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                    for table in self.TABLES}

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v4_upgrade_preserves_every_previous_row_and_recovery_snapshot(self):
        before = self.snapshot(self.path)
        result = self.assets.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (4, SCHEMA_VERSION))
        self.assertEqual(self.snapshot(self.path), before)
        backup = Path(result["backup"])
        self.assertIn(f"pre-v{SCHEMA_VERSION}-", backup.name)
        self.assertEqual(self.version(backup), 4)
        self.assertEqual(self.snapshot(backup), before)
        self.assertEqual(SQLiteCooldownRepository(self.path).list(), ())
        self.assertEqual(SQLiteAssessmentRepository(self.path).list("finding-1")[0].id, "check-1")
        self.assertEqual(SQLiteJobRepository(self.path).get("job-1").attempts[0].error, "Kaynak yanıt vermedi")
        self.assertEqual(self.assets.inspect()["cleanup_count"], 0)
        current = self.path.read_bytes()
        self.assertFalse(self.assets.migrate()["changed"])
        self.assertEqual(self.path.read_bytes(), current)
        self.assertEqual(len(list(backup.parent.glob("*.db"))), 1)

    def test_v4_read_and_init_require_explicit_migration_without_any_writes(self):
        before = self.path.read_bytes()
        for action in (self.assets.initialize, self.assets.inspect, self.assets.list,
                       SQLiteCooldownRepository(self.path).list,
                       lambda: SQLiteCooldownRepository(self.path).get("crt.sh")):
            with self.subTest(action=action), self.assertRaisesRegex(StorageError, "migrate"):
                action()
            self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_failed_operations_migration_rolls_back_new_tables_and_version(self):
        before = self.snapshot(self.path)

        def broken(connection):
            connection.execute("CREATE TABLE provider_cooldowns_partial (provider TEXT)")
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
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            raise sqlite3.OperationalError("Injected migration failure")

        with patch("xti.adapters.sqlite.create_operations_schema", side_effect=broken):
            with self.assertRaises(StorageError):
                self.assets.migrate()
        self.assertEqual(self.version(self.path), 4)
        self.assertEqual(self.snapshot(self.path), before)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 4)
        backups = list((self.path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 4)
        self.assertEqual(self.snapshot(backups[0]), before)
        self.assets.migrate()
        self.assertEqual(self.version(self.path), SCHEMA_VERSION)

    def test_v4_backup_restore_keeps_legacy_format_until_migration(self):
        before = self.path.read_bytes()
        destination = self.path.parent / "legacy.db"
        restored = self.path.parent / "restored" / "xti.db"
        self.assets.backup(destination)
        SQLiteAssetRepository.restore(destination, restored)
        self.assertEqual(self.version(restored), 4)
        self.assertEqual(self.snapshot(restored), self.snapshot(self.path))
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteCooldownRepository(restored).list()
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(self.version(restored), SCHEMA_VERSION)
        self.assertEqual(self.snapshot(restored), self.snapshot(self.path))
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

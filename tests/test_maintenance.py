"""Cleanup deletes only reviewed orphan selections and keeps recovery evidence."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_assessments import SQLiteAssessmentRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.sqlite_maintenance import SQLiteMaintenanceRepository
from xti.application.maintenance import MaintenanceService
from xti.domain.assets import ValidationError
from xti.domain.enrichment import ProbeResult


NOW = datetime(2026, 10, 28, 12, 34, 56, tzinfo=timezone.utc)
CUTOFF = NOW.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=90)


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        asset, _ = self.storage.add("example.com")
        self.repo = SQLiteMaintenanceRepository(self.path)
        self.service = MaintenanceService(self.repo, clock=lambda: NOW)
        self.seed("old-1", "2026-01-01T00:00:00+00:00")
        self.seed("old-2", "2026-02-01T00:00:00+00:00")
        self.seed("linked", "2026-01-01T00:00:00+00:00", domain="example-support.net")
        self.seed("recent", "2026-10-01T00:00:00+00:00")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("finding", asset.id, asset.value, "example-support.net", "rules-test", '["similar"]',
                 "new", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
            )
            connection.execute("INSERT INTO finding_observations VALUES ('finding', 'linked')")
        SQLiteFindingRepository(self.path).review_finding("finding", "dismissed", "Manuel inceleme")
        SQLiteAssessmentRepository(self.path).append("finding", ProbeResult(
            domain="example-support.net", started_at=NOW.isoformat(), finished_at=NOW.isoformat(),
            policy_version="test", dns_status="nxdomain", addresses=(), tls_status="not_checked",
            http_status="not_checked", http_status_code=None, connected_address=None,
            errors=(), notes=("Fixture",),
        ))
        SQLiteJobRepository(self.path).create(("example.com",), False, "crt.sh", "rules-test")

    def seed(self, identifier, timestamp, *, observed_at=None, domain="unrelated.net"):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO observations VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                (identifier, domain, domain, "fixture:" + identifier, "hash:" + identifier,
                 observed_at, timestamp),
            )

    def rows(self, path=None):
        with closing(sqlite3.connect(path or self.path)) as connection:
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )]
            return {table: connection.execute('SELECT * FROM "' + table + '" ORDER BY rowid').fetchall()
                    for table in tables}

    def test_preview_and_usage_are_read_only_without_lock_or_backup_files(self):
        before = self.path.read_bytes()
        entries = set(self.root.iterdir())
        first = self.service.preview()
        second = MaintenanceService(self.repo, clock=lambda: NOW + timedelta(hours=2)).preview()
        self.assertEqual(first, second)
        self.assertEqual(first.cutoff, CUTOFF.isoformat())
        self.assertEqual((first.eligible_count, first.selected_count, first.remaining_count), (2, 2, 0))
        self.assertEqual(first.protected_count, 1)
        self.assertEqual(first.invalid_time_count, 0)
        usage = self.service.usage()
        self.assertEqual(usage.observation_count, 4)
        self.assertEqual(usage.linked_observation_count, 1)
        self.assertEqual(usage.database_bytes, self.path.stat().st_size)
        self.assertEqual(usage.logical_bytes, usage.database_bytes)
        self.assertGreaterEqual(usage.reusable_bytes, 0)
        self.assertEqual(usage.wal_bytes + usage.journal_bytes, 0)
        self.assertEqual(self.service.history(), ())
        self.assertEqual(set(self.root.iterdir()), entries)
        self.assertEqual(self.path.read_bytes(), before)

    def test_apply_preserves_linked_dismissed_evidence_and_every_other_table(self):
        before = self.rows()
        plan = self.service.preview()
        result = self.service.apply(plan.token)
        self.assertEqual(result.plan, plan)
        self.assertEqual(result.deleted_count, 2)
        self.assertIsNotNone(result.run)
        after = self.rows()
        self.assertEqual([row[0] for row in after["observations"]], ["linked", "recent"])
        for table in before:
            if table not in {"observations", "cleanup_runs"}:
                self.assertEqual(after[table], before[table], table)
        self.assertEqual(self.service.history(), (result.run,))
        self.assertEqual(self.rows(Path(result.backup)), before)
        self.assertEqual(Path(result.backup).stat().st_mode & 0o777, 0o600)
        restored = self.root / "restored.db"
        SQLiteAssetRepository.restore(Path(result.backup), restored)
        self.assertEqual(self.rows(restored), before)

    def test_dates_use_local_ingestion_utc_and_strict_cutoff(self):
        self.seed("boundary", CUTOFF.isoformat())
        self.seed("offset-old", (CUTOFF - timedelta(seconds=1)).astimezone(
            timezone(timedelta(hours=3))).isoformat())
        self.seed("ancient-source", NOW.isoformat(), observed_at="1900-01-01T00:00:00+00:00")
        self.seed("bad", "not-a-date")
        self.seed("naive", "2026-01-01T00:00:00")
        self.seed("future", (NOW + timedelta(days=1)).isoformat())
        plan = self.service.preview()
        self.assertEqual(plan.eligible_count, 3)
        self.assertEqual(plan.invalid_time_count, 3)
        self.service.apply(plan.token)
        identifiers = {row[0] for row in self.rows()["observations"]}
        self.assertNotIn("offset-old", identifiers)
        self.assertTrue({"boundary", "ancient-source", "bad", "naive", "future", "linked"} <= identifiers)

    def test_batch_limit_and_remaining_count_require_new_preview_after_apply(self):
        plan = self.service.preview(limit=1)
        self.assertEqual((plan.eligible_count, plan.selected_count, plan.remaining_count), (2, 1, 1))
        result = self.service.apply(plan.token, limit=1)
        self.assertEqual(result.deleted_count, 1)
        self.assertNotIn("old-1", {row[0] for row in self.rows()["observations"]})
        with self.assertRaises(ValidationError):
            self.service.apply(plan.token, limit=1)
        next_plan = self.service.preview(limit=1)
        self.assertNotEqual(next_plan.token, plan.token)
        self.service.apply(next_plan.token, limit=1)
        self.assertEqual(len(self.service.history()), 2)

    def test_empty_apply_does_not_create_backup_audit_or_write_database(self):
        self.service.apply(self.service.preview().token)
        plan = self.service.preview()
        before = self.path.read_bytes()
        backup_files = list((self.root / "backups").iterdir())
        result = self.service.apply(plan.token)
        self.assertEqual(result.deleted_count, 0)
        self.assertIsNone(result.backup)
        self.assertIsNone(result.run)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list((self.root / "backups").iterdir()), backup_files)
        self.assertEqual(len(self.service.history()), 1)

    def test_changes_to_any_eligible_row_or_selection_invalidate_before_backup(self):
        changes = [
            "UPDATE observations SET raw_domain='changed.net' WHERE id='old-2'",
            "UPDATE observations SET ingested_at='2026-10-01T00:00:00+00:00' WHERE id='old-2'",
            "DELETE FROM observations WHERE id='old-2'",
            "INSERT INTO finding_observations VALUES ('finding', 'old-2')",
        ]
        for statement in changes:
            with self.subTest(statement=statement):
                # Each isolated database copy keeps the test mutations separate.
                copy = self.root / f"copy-{len(list(self.root.glob('copy-*')))}.db"
                self.storage.backup(copy)
                repository = SQLiteMaintenanceRepository(copy)
                service = MaintenanceService(repository, clock=lambda: NOW)
                plan = service.preview(limit=1)
                with closing(sqlite3.connect(copy)) as connection, connection:
                    connection.execute(statement)
                before = copy.read_bytes()
                with patch.object(repository._storage, "backup") as backup:
                    with self.assertRaises(ValidationError):
                        service.apply(plan.token, limit=1)
                    backup.assert_not_called()
                self.assertEqual(copy.read_bytes(), before)

    def test_new_eligible_row_invalidates_but_new_recent_row_is_not_deleted(self):
        plan = self.service.preview()
        self.seed("new-recent", NOW.isoformat())
        self.assertEqual(self.service.preview().token, plan.token)
        self.seed("new-old", "2026-01-01T00:00:00+00:00")
        before = self.rows()
        with self.assertRaises(ValidationError):
            self.service.apply(plan.token)
        self.assertEqual(self.rows(), before)

    def test_token_is_bound_to_database_day_and_policy_parameters(self):
        plan = self.service.preview()
        copied = self.root / "copy.db"
        self.storage.backup(copied)
        other = MaintenanceService(SQLiteMaintenanceRepository(copied), clock=lambda: NOW)
        tomorrow = MaintenanceService(self.repo, clock=lambda: NOW + timedelta(days=1))
        for apply in (lambda: other.apply(plan.token), lambda: tomorrow.apply(plan.token),
                      lambda: self.service.apply(plan.token, older_than_days=91),
                      lambda: self.service.apply(plan.token, limit=1)):
            with self.subTest(apply=apply), self.assertRaises(ValidationError):
                apply()
        self.assertFalse((self.root / "backups").exists())

    def test_failed_backup_does_not_delete_or_append_audit(self):
        before = self.rows()
        with patch.object(self.repo._storage, "backup", side_effect=StorageError("Disk dolu")):
            with self.assertRaises(StorageError):
                self.service.apply(self.service.preview().token)
        self.assertEqual(self.rows(), before)

    def test_failed_delete_rolls_back_partial_deletion_and_keeps_recovery_backup(self):
        before = self.rows()

        def broken_delete(connection, selected):
            connection.execute("DELETE FROM observations WHERE id=?", (selected[0],))
            raise sqlite3.OperationalError("Injected failure")

        with patch.object(self.repo, "_delete", side_effect=broken_delete):
            with self.assertRaises(StorageError):
                self.service.apply(self.service.preview().token)
        self.assertEqual(self.rows(), before)
        backups = list((self.root / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.rows(backups[0]), before)

    def test_failed_audit_or_interrupt_rolls_back_all_deletes(self):
        before = self.rows()
        for failure in (sqlite3.OperationalError("No space"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(self.repo, "_record", side_effect=failure):
                    with self.assertRaises(StorageError if isinstance(failure, sqlite3.Error) else KeyboardInterrupt):
                        self.service.apply(self.service.preview().token)
                self.assertEqual(self.rows(), before)

    def test_writer_lock_spans_backup_and_deletion(self):
        original_backup = self.repo._storage.backup
        attempts = []

        def try_write_then_backup(destination):
            with closing(sqlite3.connect(self.path, timeout=0)) as connection:
                try:
                    connection.execute("INSERT INTO assets VALUES ('racing', 'race.net', 'time')")
                except sqlite3.OperationalError as error:
                    attempts.append(str(error))
                else:
                    self.fail("Concurrent writer was not excluded")
            return original_backup(destination)

        with patch.object(self.repo._storage, "backup", side_effect=try_write_then_backup):
            self.service.apply(self.service.preview().token)
        self.assertEqual(len(attempts), 1)
        self.assertIn("locked", attempts[0])

    def test_history_uses_insertion_order_even_when_clock_moves_backwards(self):
        first = self.service.apply(self.service.preview(limit=1).token, limit=1).run
        earlier = MaintenanceService(self.repo, clock=lambda: NOW - timedelta(hours=2))
        second = earlier.apply(earlier.preview(limit=1).token, limit=1).run
        self.assertEqual(self.service.history(), (second, first))
        self.assertEqual(self.service.history(limit=1), (second,))

    def test_reusable_pages_are_reported_without_vacuum_or_physical_shrink_claim(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE observations SET raw_domain=? WHERE id='old-1'", ("x" * 100000,))
        before = self.service.usage()
        self.service.apply(self.service.preview().token)
        after = self.service.usage()
        self.assertGreater(after.reusable_bytes, before.reusable_bytes)
        self.assertEqual(after.database_bytes, before.database_bytes)
        self.assertEqual(after.observation_count, before.observation_count - 2)

    def test_missing_database_does_not_create_directory_or_file(self):
        path = self.root / "absent" / "xti.db"
        service = MaintenanceService(SQLiteMaintenanceRepository(path), clock=lambda: NOW)
        for operation in (service.usage, service.preview, service.history,
                          lambda: service.apply("0" * 64)):
            with self.subTest(operation=operation), self.assertRaises(StorageError):
                operation()
            self.assertFalse(path.parent.exists())

    def test_usage_does_not_follow_symlink_sidecar(self):
        outside = self.root / "other.txt"
        outside.write_text("private")
        sidecar = self.path.with_name(self.path.name + "-journal")
        sidecar.symlink_to(outside)
        with self.assertRaises(StorageError):
            self.service.usage()
        self.assertEqual(outside.read_text(), "private")

    def test_corrupted_history_is_rejected_without_rewriting_it(self):
        self.service.apply(self.service.preview().token)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE cleanup_runs SET token='bad'")
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.service.history()
        self.assertEqual(self.path.read_bytes(), before)


class MaintenanceServiceTests(unittest.TestCase):
    def test_invalid_parameters_are_rejected_before_repository_access(self):
        repository = Mock()
        service = MaintenanceService(repository, clock=lambda: NOW)
        for days, limit in ((6, 1), (3651, 1), (True, 1), (90, 0), (90, 10001), (90, True)):
            with self.subTest(days=days, limit=limit):
                with self.assertRaises(ValidationError):
                    service.preview(days, limit)
                with self.assertRaises(ValidationError):
                    service.apply("0" * 64, days, limit)
        for token in ("", "x" * 64, "a" * 63, "A" * 64, None, "a" * 64 + "\n"):
            with self.subTest(token=token), self.assertRaises(ValidationError):
                service.apply(token)
        for limit in (0, 101, True):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                service.history(limit)
        self.assertEqual(repository.mock_calls, [])

    def test_naive_clock_is_rejected_before_read_or_write(self):
        repository = Mock()
        service = MaintenanceService(repository, clock=lambda: NOW.replace(tzinfo=None))
        with self.assertRaises(ValidationError):
            service.preview()
        with self.assertRaises(ValidationError):
            service.apply("0" * 64)
        self.assertEqual(repository.mock_calls, [])


if __name__ == "__main__":
    unittest.main()

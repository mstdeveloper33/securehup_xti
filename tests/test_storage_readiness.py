"""Read-only disk, backup, retention and recovery readiness."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock

from xti.adapters.filesystem_storage_readiness import FileSystemStorageReadinessRepository
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_maintenance import SQLiteMaintenanceRepository
from xti.application.storage_readiness import StorageReadinessService
from xti.domain.assets import ValidationError
from xti.interfaces.storage_readiness import report_lines


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


class StorageReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "data"
        self.path = self.root / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.storage.add("example.com")
        self.service = StorageReadinessService(
            SQLiteMaintenanceRepository(self.path),
            FileSystemStorageReadinessRepository(self.path),
            clock=lambda: NOW,
        )

    def backup(self, name="xti-test.db", *, at=None):
        path = self.root / "backups" / name
        self.storage.backup(path)
        timestamp = (at or NOW - timedelta(hours=1)).timestamp()
        os.utime(path, (timestamp, timestamp))
        return path

    def test_missing_backup_is_visible_without_writes(self):
        before_database = self.path.read_bytes()
        before_entries = {item.name for item in self.root.iterdir()}
        report = self.service.show()
        self.assertEqual(report.backup_status, "missing")
        self.assertEqual(report.managed_backup_count, 0)
        self.assertEqual(report.local_recovery_status, "attention")
        self.assertIn("create_backup", report.next_steps)
        self.assertEqual(report.retention_status, "clear")
        self.assertEqual(self.path.read_bytes(), before_database)
        self.assertEqual({item.name for item in self.root.iterdir()}, before_entries)

    def test_current_managed_backup_is_integrity_checked_and_counted(self):
        backup = self.backup()
        before_database = self.path.read_bytes()
        before_backup = backup.read_bytes()
        report = self.service.show(backup_stale_after_days=7)
        self.assertEqual(report.backup_status, "current")
        self.assertEqual(report.managed_backup_count, 1)
        self.assertEqual(report.latest_backup_path, str(backup.absolute()))
        self.assertEqual(report.latest_backup_schema_version, SCHEMA_VERSION)
        self.assertGreater(report.backup_directory_bytes, 0)
        self.assertEqual(report.local_recovery_status, "ready")
        self.assertIn("copy_off_device", report.next_steps)
        self.assertIn("test_restore", report.next_steps)
        self.assertEqual(self.path.read_bytes(), before_database)
        self.assertEqual(backup.read_bytes(), before_backup)

    @unittest.skipUnless(os.name == "posix", "POSIX permissions required")
    def test_shared_data_and_backup_permissions_are_visible_without_changing_them(self):
        backup = self.backup()
        self.root.chmod(0o775)
        backup.parent.chmod(0o755)
        before = {path: path.read_bytes() for path in (self.path, backup)}
        report = self.service.show()
        self.assertEqual(report.permission_status, "attention")
        self.assertEqual(report.local_recovery_status, "attention")
        self.assertIn("review_directory_permissions", report.next_steps)
        self.assertEqual(
            [(item.status, item.mode) for item in report.directory_permissions],
            [("writable_by_others", "0775"), ("accessible_by_others", "0755"),
             ("missing", None)],
        )
        self.assertIn("Grup veya diğer kullanıcılar yazabilir", "\n".join(report_lines(report)))
        self.assertEqual({path: path.read_bytes() for path in (self.path, backup)}, before)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o775)
        self.assertEqual(backup.parent.stat().st_mode & 0o777, 0o755)

        # An operator can explicitly tighten access; the next read reflects it.
        self.root.chmod(0o700)
        backup.parent.chmod(0o700)
        report = self.service.show()
        self.assertEqual((report.permission_status, report.local_recovery_status), ("private", "ready"))

    @unittest.skipUnless(os.name == "posix", "POSIX permissions required")
    def test_scheduled_backup_directory_is_included_in_permission_readiness(self):
        self.backup()
        scheduled = self.root / "scheduled-backups"
        scheduled.mkdir(mode=0o700)
        scheduled.chmod(0o770)
        report = self.service.show()
        self.assertEqual(report.permission_status, "attention")
        self.assertEqual(report.directory_permissions[-1].status, "writable_by_others")

    def test_invalid_latest_backup_is_reported_without_hiding_older_valid_copy(self):
        valid = self.backup("older.db", at=NOW - timedelta(hours=2))
        broken = self.root / "backups" / "newer.db"
        broken.write_bytes(b"not a sqlite backup")
        timestamp = (NOW - timedelta(hours=1)).timestamp()
        os.utime(broken, (timestamp, timestamp))
        before = {path.name: path.read_bytes() for path in (valid, broken, self.path)}
        report = self.service.show()
        self.assertEqual(report.managed_backup_count, 2)
        self.assertEqual(report.latest_backup_path, str(broken.absolute()))
        self.assertEqual(report.backup_status, "invalid")
        self.assertIsNotNone(report.backup_error)
        self.assertEqual(report.local_recovery_status, "attention")
        self.assertIn("create_backup", report.next_steps)
        self.assertEqual(
            {path.name: path.read_bytes() for path in (valid, broken, self.path)}, before,
        )

    def test_stale_backup_and_retention_preview_are_separate_attention_items(self):
        self.backup(at=NOW - timedelta(days=8))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "old", "unrelated.net", "unrelated.net", "fixture:old", "hash:old",
                    1, None, "2026-01-01T00:00:00+00:00",
                ),
            )
        before = self.path.read_bytes()
        report = self.service.show(backup_stale_after_days=7, retention_days=90)
        self.assertEqual(report.backup_status, "stale")
        self.assertEqual(report.retention_status, "attention")
        self.assertEqual(report.cleanup_eligible_count, 1)
        self.assertIn("review_retention", report.next_steps)
        self.assertEqual(self.path.read_bytes(), before)

    def test_symlink_backup_is_ignored_and_invalid_policy_stops_before_repositories(self):
        outside = Path(self.temp.name) / "outside.db"
        outside.write_bytes(b"private")
        backup_directory = self.root / "backups"
        backup_directory.mkdir()
        (backup_directory / "link.db").symlink_to(outside)
        report = self.service.show()
        self.assertEqual(report.managed_backup_count, 0)
        self.assertGreaterEqual(report.ignored_entry_count, 1)
        self.assertEqual(outside.read_bytes(), b"private")

        maintenance, filesystem = Mock(), Mock()
        service = StorageReadinessService(maintenance, filesystem, clock=lambda: NOW)
        for stale_days, retention_days in ((0, 90), (3651, 90), (True, 90), (7, 6), (7, True)):
            with self.subTest(stale_days=stale_days, retention_days=retention_days):
                with self.assertRaises(ValidationError):
                    service.show(
                        backup_stale_after_days=stale_days,
                        retention_days=retention_days,
                    )
        self.assertEqual(maintenance.mock_calls, [])
        self.assertEqual(filesystem.mock_calls, [])


if __name__ == "__main__":
    unittest.main()

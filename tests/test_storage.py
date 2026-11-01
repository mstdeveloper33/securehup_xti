"""Persistence, duplicate prevention and non-destructive recovery checks."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SCHEMA_VERSION, SQLiteAssetRepository, StorageError
from xti.application.assets import AssetService
from xti.domain.assets import ValidationError


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data" / "xti.db"
        self.repository = SQLiteAssetRepository(self.path)
        self.repository.initialize()
        self.service = AssetService(self.repository)

    def test_reopening_preserves_assets_and_initialization_is_idempotent(self):
        asset, created = self.service.add("example.com")
        self.assertTrue(created)
        reopened = SQLiteAssetRepository(self.path)
        reopened.initialize()
        self.assertEqual(reopened.list(), [asset])
        report = reopened.inspect()
        self.assertEqual(report["asset_count"], 1)
        self.assertEqual(report["schema_version"], SCHEMA_VERSION)
        self.assertEqual(report["integrity"], "ok")

    def test_normalized_duplicates_preserve_original_identity(self):
        first, first_created = self.service.add("example.com")
        second, second_created = self.service.add("  EXAMPLE.COM.  ")
        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first, second)
        self.assertEqual(self.service.list(), [first])

    def test_validation_failure_does_not_store_an_asset(self):
        self.service.add("example.com")
        with self.assertRaises(ValidationError):
            self.service.add("https://another.example")
        self.assertEqual([asset.value for asset in self.service.list()], ["example.com"])

    def test_backup_is_a_snapshot_and_restores_into_a_new_database(self):
        original, _ = self.service.add("example.com")
        snapshot = self.root / "backups" / "first.db"
        result = self.repository.backup(snapshot)
        self.assertEqual(Path(result), snapshot)
        self.service.add("later.example")
        destination = self.root / "restored" / "xti.db"
        SQLiteAssetRepository.restore(snapshot, destination)
        restored = SQLiteAssetRepository(destination)
        self.assertEqual(restored.list(), [original])
        self.assertEqual(restored.inspect()["integrity"], "ok")
        self.assertEqual(len(self.repository.list()), 2)

    def test_backup_refuses_to_replace_an_existing_file(self):
        destination = self.root / "existing.db"
        destination.write_bytes(b"must remain unchanged")
        with self.assertRaises(StorageError):
            self.repository.backup(destination)
        self.assertEqual(destination.read_bytes(), b"must remain unchanged")

    def test_restore_refuses_to_overwrite_the_live_database(self):
        first, _ = self.service.add("example.com")
        snapshot = self.root / "backup.db"
        self.repository.backup(snapshot)
        second, _ = self.service.add("second.example")
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(snapshot, self.path)
        self.assertEqual({item.id for item in self.repository.list()}, {first.id, second.id})

    def test_missing_initialization_does_not_create_storage(self):
        path = self.root / "uncreated" / "xti.db"
        repository = SQLiteAssetRepository(path)
        for operation in (repository.list, repository.inspect, lambda: repository.add("example.com")):
            with self.subTest(operation=operation):
                with self.assertRaises(StorageError):
                    operation()
                self.assertFalse(path.exists())
                self.assertFalse(path.parent.exists())

    def test_newer_database_version_is_not_silently_changed(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
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
            connection.execute("PRAGMA user_version = 999")
        for operation in (self.repository.initialize, self.repository.list, self.repository.inspect):
            with self.subTest(operation=operation):
                with self.assertRaises(StorageError):
                    operation()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 999)

    def test_unrelated_database_cannot_be_read_or_restored(self):
        unrelated = self.root / "unrelated.db"
        with closing(sqlite3.connect(unrelated)) as connection, connection:
            connection.execute("CREATE TABLE private_data (value TEXT)")
            connection.execute("INSERT INTO private_data VALUES ('keep')")
        repository = SQLiteAssetRepository(unrelated)
        with self.assertRaises(StorageError):
            repository.list()
        destination = self.root / "invalid-restore" / "xti.db"
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(unrelated, destination)
        self.assertFalse(destination.exists())
        with closing(sqlite3.connect(unrelated)) as connection, connection:
            self.assertEqual(connection.execute("SELECT value FROM private_data").fetchone()[0], "keep")

    def test_corrupt_backup_is_rejected_without_creating_a_database(self):
        corrupt = self.root / "corrupt.db"
        corrupt.write_bytes(b"this is not a database")
        destination = self.root / "corrupt-restore" / "xti.db"
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(corrupt, destination)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()

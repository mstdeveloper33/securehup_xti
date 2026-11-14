"""Verified backup publication and fail-closed, receipt-owned retention."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.scheduled_backups import ScheduledBackupMaintenance
from xti.domain.assets import ValidationError

NOW = "2026-11-14T12:00:00+00:00"
EARLIER = "2026-11-14T11:00:00+00:00"


class ScheduledBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "xti.db"
        self.storage = SQLiteAssetRepository(self.database)
        self.storage.initialize(); self.asset, _ = self.storage.add("example.com")
        self.repository = ScheduledBackupMaintenance(self.database)
        self.profile_id = str(uuid4())

    def backup(self, *, keep=7, when=NOW):
        return self.repository.backup_and_prune(profile_id=self.profile_id, recorded_at=when, keep=keep)

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file() and not path.is_symlink()}

    def test_preflight_and_invalid_retention_are_readonly_and_disk_guard_prevents_any_backup(self):
        before = self.files()
        ready = self.repository.preflight(keep=7)
        self.assertGreaterEqual(ready.required_bytes, 2*self.database.stat().st_size + 64*1024*1024)
        for keep in (0, 31, True, "7"):
            with self.assertRaises(ValidationError): self.backup(keep=keep)
        with patch("xti.adapters.scheduled_backups.shutil.disk_usage", return_value=Mock(free=1)), self.assertRaises(StorageError):
            self.backup()
        self.assertEqual(self.files(), before)
        self.assertFalse(self.repository.directory.exists())

    def test_unique_verified_backups_restore_all_data_without_overwrite(self):
        first, second = self.backup(), self.backup()
        self.assertNotEqual(first.path, second.path)
        self.assertTrue(first.restore_verified)
        self.assertEqual(hashlib.sha256(Path(first.path).read_bytes()).hexdigest(), first.sha256)
        restored = self.root / "manual-restored.db"
        SQLiteAssetRepository.restore(Path(first.path), restored)
        self.assertEqual(SQLiteAssetRepository(restored).list(), [self.asset])
        with self.assertRaises(StorageError): SQLiteAssetRepository.restore(Path(second.path), restored)
        with patch("xti.adapters.scheduled_backups.uuid4", return_value=Path(first.path).stem.removeprefix("scheduled-")):
            with self.assertRaises(StorageError): self.backup()
        self.assertEqual(hashlib.sha256(Path(first.path).read_bytes()).hexdigest(), first.sha256)

    def test_retention_uses_receipt_sequence_and_never_touches_foreign_manual_or_migration_backups(self):
        first = self.backup(keep=2)
        foreign = self.repository.directory / "manual.db"; foreign.write_bytes(b"foreign contents")
        folder = self.root / "backups"; folder.mkdir()
        manual, migration = folder / "manual.db", folder / "migration-v58.db"
        self.storage.backup(manual); self.storage.backup(migration)
        original = (manual.read_bytes(), migration.read_bytes())
        second = self.backup(keep=2, when=EARLIER)
        third = self.backup(keep=2, when=EARLIER)
        self.assertFalse(Path(first.path).exists())
        self.assertTrue(Path(second.path).exists()); self.assertTrue(Path(third.path).exists())
        self.assertEqual(third.retired_paths, (first.path,))
        self.assertEqual(foreign.read_bytes(), b"foreign contents")
        self.assertTrue(any("manual.db" in warning for warning in third.warnings))
        self.assertEqual((manual.read_bytes(), migration.read_bytes()), original)

    def test_missing_changed_receipt_or_owned_file_fail_before_deletion(self):
        first = self.backup(keep=1)
        backup = Path(first.path); manifest = self.repository.directory / "ownership.json"
        original_backup, original_manifest = backup.read_bytes(), manifest.read_bytes()
        def changed_receipt():
            data = json.loads(original_manifest)
            data["payload"]["entries"][0]["state"] = "retired"
            manifest.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")))
        for mutation in (lambda: manifest.unlink(), changed_receipt, lambda: backup.unlink(), lambda: backup.write_bytes(b"changed")):
            with self.subTest(mutation=mutation):
                mutation(); before = self.files()
                with self.assertRaises(StorageError): self.backup(keep=1)
                self.assertEqual(self.files(), before)
                backup.write_bytes(original_backup); manifest.write_bytes(original_manifest)

    def test_symlink_rejected_and_hardlink_retention_never_deletes_external_alias(self):
        first = self.backup(keep=1); owned = Path(first.path)
        outside = self.root / "important.db"; original = owned.read_bytes(); outside.write_bytes(original)
        owned.unlink(); owned.symlink_to(outside)
        with self.assertRaises(StorageError): self.backup(keep=1)
        self.assertEqual(outside.read_bytes(), original); self.assertTrue(owned.is_symlink())
        owned.unlink(); owned.hardlink_to(outside)
        self.backup(keep=1)
        self.assertFalse(owned.exists())
        self.assertEqual(outside.read_bytes(), original)

    def test_foreign_entries_preserved_but_reserved_unreceipted_backup_fails_closed(self):
        self.repository.directory.mkdir()
        foreign = self.repository.directory / "notes.txt"; foreign.write_text("keep me")
        report = self.backup(keep=1)
        self.assertTrue(any("notes.txt" in warning for warning in report.warnings))
        orphan = self.repository.directory / f"scheduled-{uuid4()}.db"; orphan.write_bytes(b"unreceipted")
        before = self.files()
        with self.assertRaises(StorageError): self.backup(keep=1)
        self.assertEqual(self.files(), before)

    def test_restore_failure_publishes_no_backup_and_keeps_existing_files(self):
        first = self.backup(keep=1); before = self.files()
        with patch.object(SQLiteAssetRepository, "restore", side_effect=StorageError("controlled restore failure")), self.assertRaises(StorageError):
            self.backup(keep=1)
        self.assertEqual(self.files(), before)
        self.assertTrue(Path(first.path).exists())
        self.assertFalse(tuple(self.root.glob(".xti-scheduled-verify-*")))

    def test_retention_failure_is_recoverable_without_missing_owned_file_ambiguity(self):
        first = self.backup(keep=1)
        original_unlink = Path.unlink
        def fail_retire(path, *args, **kwargs):
            if str(path) == first.path:
                raise OSError("controlled retirement interruption")
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", fail_retire), self.assertRaises(StorageError): self.backup(keep=1)
        manifest = json.loads((self.repository.directory / "ownership.json").read_bytes())
        self.assertEqual(manifest["payload"]["entries"][0]["state"], "retired")
        self.assertTrue(Path(first.path).exists())
        self.repository.preflight(keep=1)
        report = self.backup(keep=1)
        self.assertFalse(Path(first.path).exists())
        self.assertEqual(len(tuple(self.repository.directory.glob("scheduled-*.db"))), 1)
        self.assertTrue(Path(report.path).exists())

    def test_changed_old_backup_during_new_snapshot_stops_retention(self):
        first = self.backup(keep=1); old = Path(first.path)
        original_restore = SQLiteAssetRepository.restore
        def change_after_restore(source, destination):
            original_restore(source, destination)
            old.write_bytes(b"changed during snapshot")
        with patch.object(SQLiteAssetRepository, "restore", side_effect=change_after_restore), self.assertRaises(StorageError):
            self.backup(keep=1)
        self.assertEqual(old.read_bytes(), b"changed during snapshot")

    def test_managed_directory_symlink_and_shared_write_permission_fail_closed(self):
        outside = self.root / "external"; outside.mkdir()
        self.repository.directory.symlink_to(outside)
        with self.assertRaises(StorageError): self.backup()
        self.assertEqual(tuple(outside.iterdir()), ())
        self.repository.directory.unlink(); self.repository.directory.mkdir(mode=0o777); self.repository.directory.chmod(0o777)
        with self.assertRaises(StorageError): self.backup()

    def test_crash_after_file_publication_recovers_reserved_backup_even_with_staged_hardlink(self):
        self.backup(keep=1)
        publish = self.repository._publish_manifest
        alias = self.root / "surviving-stage.db"
        def interrupted(entries, *, expected):
            if len(entries) == 2 and entries[-1]["state"] == "retained":
                alias.hardlink_to(self.repository.directory / entries[-1]["file"])
                raise KeyboardInterrupt()
            return publish(entries, expected=expected)
        with patch.object(self.repository, "_publish_manifest", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            self.backup(keep=1)
        manifest = json.loads((self.repository.directory / "ownership.json").read_bytes())
        self.assertEqual(manifest["payload"]["entries"][-1]["state"], "creating")
        original_alias = alias.read_bytes()
        before = self.files(); self.repository.preflight(keep=1); self.assertEqual(self.files(), before)
        resumed = self.backup(keep=1)
        self.assertTrue(Path(resumed.path).exists())
        self.assertEqual(alias.read_bytes(), original_alias)
        self.assertEqual(len(tuple(self.repository.directory.glob("scheduled-*.db"))), 1)

    def test_absent_reserved_file_is_retired_and_next_backup_completes(self):
        self.backup(keep=1)
        original_link = __import__("os").link
        def fail_publication(source, destination, *args, **kwargs):
            if Path(destination).name.startswith("scheduled-"):
                raise KeyboardInterrupt()
            return original_link(source, destination, *args, **kwargs)
        with patch("xti.adapters.scheduled_backups.os.link", side_effect=fail_publication), self.assertRaises(KeyboardInterrupt):
            self.backup(keep=1)
        manifest = json.loads((self.repository.directory / "ownership.json").read_bytes())
        reserved = manifest["payload"]["entries"][-1]
        self.assertEqual(reserved["state"], "creating")
        self.assertFalse((self.repository.directory / reserved["file"]).exists())
        self.backup(keep=1)
        manifest = json.loads((self.repository.directory / "ownership.json").read_bytes())
        self.assertEqual(manifest["payload"]["entries"][1]["state"], "retired")
        self.assertEqual(len(tuple(self.repository.directory.glob("scheduled-*.db"))), 1)

    def test_retired_manifest_directory_sync_precedes_any_old_backup_deletion(self):
        first = self.backup(keep=1)
        sync = self.repository._sync_directory
        successful_retired_sync = False
        def synced(path):
            nonlocal successful_retired_sync
            sync(path)
            manifest = json.loads((self.repository.directory / "ownership.json").read_bytes())
            if manifest["payload"]["entries"][0]["state"] == "retired":
                successful_retired_sync = True
        original_unlink = Path.unlink
        def observed_unlink(path, *args, **kwargs):
            if str(path) == first.path:
                self.assertTrue(successful_retired_sync)
            return original_unlink(path, *args, **kwargs)
        with patch.object(self.repository, "_sync_directory", side_effect=synced), patch.object(Path, "unlink", observed_unlink):
            self.backup(keep=1)
        self.assertFalse(Path(first.path).exists())

    def test_directory_sync_failure_before_retention_preserves_old_backups(self):
        first = self.backup(keep=1)
        sync = self.repository._sync_directory
        def failed_sync(path):
            manifest = json.loads((self.repository.directory / "ownership.json").read_bytes())
            if manifest["payload"]["entries"][0]["state"] == "retired":
                raise OSError("controlled directory sync failure")
            sync(path)
        with patch.object(self.repository, "_sync_directory", side_effect=failed_sync), self.assertRaises(StorageError):
            self.backup(keep=1)
        self.assertTrue(Path(first.path).exists())
        self.backup(keep=1)
        self.assertFalse(Path(first.path).exists())


if __name__ == "__main__":
    unittest.main()

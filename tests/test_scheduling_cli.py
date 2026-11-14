"""CLI acceptance for file-only scheduling and verified, scoped backup maintenance."""

from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository
from tests import test_collection_watch_cli as fixtures


class SchedulingCLITests(unittest.TestCase):
    setUp = fixtures.CollectionWatchCLITests.setUp
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files

    def save_profile(self):
        return self.result("profiles", "save", "Günlük profil", "example.com")

    def assert_no_collection(self):
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])
        self.assertEqual(self.maigret.calls, [])
        self.assertEqual((self.threatcluster.calls, self.ransomlook.calls), (0, 0))

    def test_generate_keeps_database_unchanged_and_never_activates_service(self):
        self.save_profile()
        before = self.files()
        output = self.data.parent / "Linux zamanlama $ örnek%"
        with patch("subprocess.run", side_effect=AssertionError("No service activation")):
            generated = self.result(
                "schedule", "generate", "Günlük profil", "--output", str(output),
                "--at", "09:30", "--timezone", "Europe/Istanbul", "--weekday", "Mon",
            )
        self.assertEqual(generated["calendar"], "Mon *-*-* 09:30:00 Europe/Istanbul")
        for key in ("service_file", "timer_file", "instructions_file"):
            self.assertTrue(Path(generated[key]).is_file())
        self.assertEqual(self.files(), before)
        original = {path.name: path.read_bytes() for path in output.iterdir()}
        code, _, _ = self.invoke(
            "schedule", "generate", "Günlük profil", "--output", str(output), "--at", "10:00",
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(original, {path.name: path.read_bytes() for path in output.iterdir()})
        self.assert_no_collection()

    def test_prepare_verifies_restore_and_only_prunes_its_owned_backups(self):
        self.save_profile()
        original = self.database.read_bytes()
        manual = self.data / "manual.db"
        SQLiteAssetRepository(self.database).backup(manual)
        manual_bytes = manual.read_bytes()
        first = self.result("schedule", "prepare", "Günlük profil", "--keep", "1")
        self.assertTrue(first["backup"]["restore_verified"])
        self.assertEqual(first["recovered_sessions"], [])
        first_path = Path(first["backup"]["path"])
        self.assertTrue(first_path.is_file())
        second = self.result("schedule", "prepare", "Günlük profil", "--keep", "1")
        second_path = Path(second["backup"]["path"])
        self.assertTrue(second_path.is_file())
        self.assertFalse(first_path.exists())
        self.assertEqual(second["backup"]["retired_paths"], [str(first_path)])
        restored = self.data.parent / "restored.db"
        SQLiteAssetRepository.restore(second_path, restored)
        with closing(sqlite3.connect(restored)) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("SELECT count(*) FROM collection_profiles").fetchone()[0], 1)
        self.assertEqual(manual.read_bytes(), manual_bytes)
        self.assertEqual(self.database.read_bytes(), original)
        self.assert_no_collection()

    def test_invalid_schedule_or_revoked_profile_does_not_mutate_data(self):
        self.save_profile()
        output = self.data.parent / "invalid schedule"
        before = self.files()
        code, _, _ = self.invoke(
            "schedule", "generate", "Günlük profil", "--output", str(output), "--at", "25:00",
        )
        self.assertNotEqual(code, 0)
        self.assertFalse(output.exists())
        self.assertEqual(self.files(), before)
        self.result("profiles", "revoke", "Günlük profil", "--reason", "Zamanlama durduruldu.")
        before = self.files()
        code, _, _ = self.invoke("schedule", "prepare", "Günlük profil")
        self.assertNotEqual(code, 0)
        self.assertEqual(self.files(), before)
        self.assert_no_collection()


if __name__ == "__main__":
    unittest.main()

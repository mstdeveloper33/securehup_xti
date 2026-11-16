"""Exercise the public commands across independent processes."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from xti.adapters.schema import SCHEMA_VERSION


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.project = Path(__file__).resolve().parents[1]

    def run_cli(self, *arguments, data_dir=None):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(self.project / "src")
        return subprocess.run(
            [sys.executable, "-m", "xti", "--data-dir", str(data_dir or self.data), "--json", *arguments],
            text=True, capture_output=True, check=False, timeout=15,
            env=environment, cwd=self.project,
        )

    def success_json(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertIs(parsed["ok"], True)
        return parsed["data"]

    def error_json(self, result, expected_code):
        self.assertEqual(result.returncode, expected_code)
        self.assertEqual(result.stdout, "")
        parsed = json.loads(result.stderr)
        self.assertIs(parsed["ok"], False)
        self.assertTrue(parsed["error"]["code"])
        self.assertTrue(parsed["error"]["message"])
        return parsed

    def test_init_add_list_and_doctor_across_processes(self):
        self.success_json(self.run_cli("init"))
        added = self.success_json(self.run_cli("assets", "add", "EXAMPLE.COM."))
        self.assertIs(added["created"], True)
        listed = self.success_json(self.run_cli("assets", "list"))
        self.assertEqual([asset["value"] for asset in listed["assets"]], ["example.com"])
        doctor = self.success_json(self.run_cli("doctor"))
        self.assertEqual(doctor["status"], "ready")
        self.assertEqual(doctor["asset_count"], 1)
        duplicate = self.success_json(self.run_cli("assets", "add", "example.com"))
        self.assertIs(duplicate["created"], False)
        self.assertEqual(duplicate["asset"], added["asset"])
        self.assertEqual(self.success_json(self.run_cli("assets", "list")), listed)

    def test_backup_restore_round_trip_preserves_assets(self):
        self.success_json(self.run_cli("init"))
        self.success_json(self.run_cli("assets", "add", "example.com"))
        snapshot = self.root / "snapshot.db"
        self.success_json(self.run_cli("backup", "--output", str(snapshot)))
        restored = self.root / "restored"
        self.success_json(self.run_cli("restore", str(snapshot), data_dir=restored))
        listed = self.success_json(self.run_cli("assets", "list", data_dir=restored))
        self.assertEqual([asset["value"] for asset in listed["assets"]], ["example.com"])
        denied = self.run_cli("restore", str(snapshot), data_dir=restored)
        self.error_json(denied, 1)
        self.assertEqual(self.success_json(self.run_cli("assets", "list", data_dir=restored)), listed)

    def test_storage_readiness_validates_managed_backup_without_changing_data(self):
        self.success_json(self.run_cli("init"))
        self.success_json(self.run_cli("assets", "add", "example.com"))
        backup = Path(self.success_json(self.run_cli("backup"))["backup"])
        database = self.data / "xti.db"
        before_database = database.read_bytes()
        before_backup = backup.read_bytes()
        report = self.success_json(self.run_cli(
            "storage", "readiness", "--backup-stale-after-days", "7",
            "--retention-days", "90",
        ))
        self.assertEqual(report["backup_status"], "current")
        self.assertEqual(report["local_recovery_status"], "ready")
        self.assertEqual(report["managed_backup_count"], 1)
        self.assertEqual(report["latest_backup_schema_version"], SCHEMA_VERSION)
        self.assertEqual(report["permission_status"], "private")
        self.assertEqual(
            [(item["status"], item["mode"]) for item in report["directory_permissions"]],
            [("private", "0700"), ("private", "0700"), ("missing", None)],
        )
        self.assertEqual(database.read_bytes(), before_database)
        self.assertEqual(backup.read_bytes(), before_backup)

    def test_missing_init_reports_error_without_creating_data(self):
        result = self.run_cli("assets", "list")
        self.error_json(result, 1)
        self.assertFalse(self.data.exists())

    def test_invalid_domain_uses_validation_exit_code_without_mutation(self):
        self.success_json(self.run_cli("init"))
        before = self.success_json(self.run_cli("assets", "list"))
        rejected = self.run_cli("assets", "add", "https://example.com")
        self.error_json(rejected, 2)
        self.assertEqual(self.success_json(self.run_cli("assets", "list")), before)

    def test_analyze_combines_stored_evidence_without_mutation(self):
        self.success_json(self.run_cli("init"))
        self.success_json(self.run_cli("assets", "add", "example.com"))
        database = self.data / "xti.db"
        before = database.read_bytes()

        report = self.success_json(self.run_cli("analyze", "EXAMPLE.COM"))

        self.assertEqual(report["asset_value"], "example.com")
        self.assertIs(report["stored_data_only"], True)
        self.assertEqual(report["vulnerability_scope"], "disabled")
        self.assertEqual(report["findings"]["total"], 0)
        self.assertEqual(report["ioc_catalog_status"], "empty")
        self.assertEqual(database.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

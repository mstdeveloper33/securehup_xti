"""Portable checks for the acceptance harness; real systemd/tmpfs run in Linux CI."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("linux_operations_acceptance", PROJECT / "scripts/check-linux-operations.py")
OPERATIONS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OPERATIONS)


class LinuxOperationsAcceptanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="xti-operations-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_transport_failure_recovery_preserves_history_and_uses_one_call_per_attempt(self):
        result = OPERATIONS.source_outages(self.root)
        self.assertEqual(result["passed_modes"], ["timeout", "disconnect", "429", "503", "malformed"])
        self.assertTrue(result["previous_success_preserved"])
        calls = OPERATIONS.calls(self.root / "source-control.json")
        self.assertEqual(len(calls), 11)
        self.assertEqual(len({call["pid"] for call in calls}), 11)

    def test_capacity_counts_pages_and_identity_preserving_restore(self):
        result = OPERATIONS.capacity(self.root, (10, 25))
        self.assertEqual([item["domains"] for item in result], [10, 25])
        self.assertTrue(all(item["database_bytes"] > 0 for item in result))
        self.assertTrue(all(item["backup_restore_seconds"] > 0 for item in result))

    def test_bounded_endurance_reports_actual_rounds_without_duplicate_change(self):
        result = OPERATIONS.endurance(self.root, 0)
        self.assertEqual(result["rounds"], 1)
        self.assertGreater(result["elapsed_seconds"], 0)
        self.assertIn("not a 24/7", result["scope"])

    def test_low_disk_guard_never_uses_an_ordinary_directory(self):
        marker = self.root / "keep.txt"
        marker.write_bytes(b"unrelated contents")
        with self.assertRaises(RuntimeError):
            OPERATIONS.low_disk(self.root)
        self.assertEqual(tuple(self.root.iterdir()), (marker,))
        self.assertEqual(marker.read_bytes(), b"unrelated contents")

    def test_expected_low_disk_error_reads_legacy_cli_stderr_and_preserves_records(self):
        control = self.root / "control.json"
        environment, _ = OPERATIONS.seed(self.root / "data", control)
        injection = self.root / "disk-injection"
        injection.mkdir()
        (injection / "sitecustomize.py").write_text(
            "from types import SimpleNamespace\n"
            "from xti.adapters import scheduled_backups\n"
            "scheduled_backups.shutil.disk_usage = lambda path: SimpleNamespace(total=50331648, used=50331647, free=1)\n")
        environment["PYTHONPATH"] = os.pathsep.join((str(injection), str(PROJECT / "src"), str(PROJECT)))
        database = self.root / "data/xti.db"
        before = database.read_bytes()
        result = OPERATIONS.cli(environment, "schedule", "prepare", "acceptance", expected=1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "storage_error")
        self.assertIn("boş alan gerekli", result["error"]["message"])
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(OPERATIONS.calls(control), [])
        self.assertFalse((database.parent / "scheduled-backups").exists())

    def test_source_injection_works_through_actual_xti_launcher_and_refuses_network(self):
        control = self.root / "control.json"
        environment, _ = OPERATIONS.seed(self.root / "data", control)
        injection = self.root / "injection"
        injection.mkdir()
        (injection / "sitecustomize.py").write_text(
            "import os\nfrom tests.operations_worker import install\ninstall(os.environ['XTI_OPERATIONS_CONTROL'])\n")
        environment["PYTHONPATH"] = os.pathsep.join((str(injection), str(PROJECT)))
        result = OPERATIONS.run([str(PROJECT / "xti"), "--json", "collect", "--profile", "acceptance"], environment)
        self.assertTrue(json.loads(result)["ok"])
        self.assertEqual(len(OPERATIONS.calls(control)), 1)
        denied = OPERATIONS.run([str(PROJECT / "scripts/python"), "-c",
                                "import socket; socket.create_connection(('example.com',443))"],
                               environment, expected=1)
        self.assertEqual(denied, "")

    def test_systemd_scope_refuses_non_linux_before_seeding(self):
        with patch.object(OPERATIONS.sys, "platform", "darwin"), self.assertRaises(RuntimeError):
            OPERATIONS.systemd_acceptance(self.root)
        self.assertEqual(tuple(self.root.iterdir()), ())

    def test_failure_report_destination_cannot_overwrite_existing_evidence(self):
        report = self.root / "report.json"
        report.write_text("keep")
        with self.assertRaises(RuntimeError):
            OPERATIONS.main(["--duration-seconds", "60", "--low-disk-directory", str(self.root),
                             "--report", str(report)])
        self.assertEqual(report.read_text(), "keep")

    def test_service_cleanup_requires_stopped_state_and_attempts_disable_after_stop_failure(self):
        seen = []
        def active(arguments, **kwargs):
            seen.append(arguments)
            if "stop" in arguments:
                raise OSError("controlled lost control reply")
            if "show" in arguments:
                return SimpleNamespace(returncode=0, stdout="LoadState=loaded\nActiveState=active\nControlGroup=\nUnitFileState=linked-runtime\n")
            return SimpleNamespace(returncode=0, stdout="")
        with patch.object(OPERATIONS.subprocess, "run", side_effect=active), self.assertRaises(OPERATIONS.UnconfirmedCleanup):
            OPERATIONS.stop_owned_units({}, "owned.service", "owned.timer")
        self.assertTrue(any("disable" in arguments for arguments in seen))

    def test_unconfirmed_service_stop_retains_workspace_and_records_failure(self):
        report = self.root / "report.json"
        workspace = self.root / "workspace"
        workspace.mkdir()
        marker = workspace / "evidence"
        marker.write_bytes(b"retain on unconfirmed shutdown")
        with patch.object(OPERATIONS.sys, "platform", "linux"), \
                patch.object(OPERATIONS, "validate_low_disk_mount", return_value=self.root), \
                patch.object(OPERATIONS.tempfile, "mkdtemp", return_value=str(workspace)), \
                patch.object(OPERATIONS, "source_outages", return_value={}), \
                patch.object(OPERATIONS, "capacity", return_value=[]), \
                patch.object(OPERATIONS, "low_disk", return_value={}), \
                patch.object(OPERATIONS, "systemd_acceptance", side_effect=OPERATIONS.UnconfirmedCleanup("controlled stop uncertainty")), \
                patch.object(OPERATIONS, "summary"):
            code = OPERATIONS.main(["--duration-seconds", "60", "--low-disk-directory", str(self.root),
                                    "--report", str(report)])
        self.assertEqual(code, 1)
        outcome = json.loads(report.read_text())
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["preserved_workspace"], str(workspace))
        self.assertEqual(marker.read_bytes(), b"retain on unconfirmed shutdown")


if __name__ == "__main__":
    unittest.main()

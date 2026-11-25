"""Offline team-handoff plan, secret safety and disposable acceptance."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xti_handoff_script", PROJECT / "scripts" / "handoff.py")
assert SPEC is not None and SPEC.loader is not None
HANDOFF = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HANDOFF
SPEC.loader.exec_module(HANDOFF)


class HandoffTests(unittest.TestCase):
    def test_feature_and_source_catalogs_are_current(self) -> None:
        check, counts = HANDOFF.feature_catalog_check()
        self.assertEqual(check.state, "pass")
        self.assertGreater(counts["active"], 0)
        self.assertEqual(
            counts["active"] + counts["requirement_bound"] + counts["waiting"],
            counts["total"],
        )
        sources = HANDOFF.source_requirements()
        self.assertEqual(sources["count"], 55)
        self.assertEqual(sources["active"], 33)
        self.assertEqual(sources["blocked_requirement"], 15)
        self.assertEqual(sources["not_implemented"], 7)

    def test_plan_still_fails_closed_for_required_repository_errors(self) -> None:
        required_failure = HANDOFF._check(
            "catalog", "Catalog", "fail", required=True, detail="broken",
        )
        optional_block = HANDOFF._check(
            "optional", "Optional", "blocked_requirement", required=False, detail="missing",
        )
        self.assertEqual(HANDOFF.overall_state([required_failure, optional_block]), "fail")

    def test_repository_delivery_files_and_version_markers_are_current(self) -> None:
        checks = HANDOFF.repository_checks()
        self.assertTrue(checks)
        self.assertTrue(all(item.state == "pass" for item in checks), checks)

    def test_safe_environment_does_not_forward_secrets_or_user_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = os.environ.copy()
            try:
                for name in HANDOFF.SECRET_ENVIRONMENT:
                    os.environ[name] = "must-not-be-forwarded"
                os.environ["HOME"] = "/secret/home"
                os.environ["XDG_CONFIG_HOME"] = "/secret/config"
                environment = HANDOFF._safe_environment(root)
            finally:
                os.environ.clear()
                os.environ.update(before)
            for name in HANDOFF.SECRET_ENVIRONMENT:
                self.assertNotIn(name, environment)
            self.assertEqual(environment["HOME"], str(root / "home"))
            self.assertEqual(environment["XDG_CONFIG_HOME"], str(root / "config"))
            self.assertEqual(environment["XTI_DATA_DIR"], str(root / "data"))

    def test_optional_blocks_do_not_fail_core_but_required_blocks_do(self) -> None:
        optional = HANDOFF._check(
            "optional", "Optional", "blocked_requirement", required=False, detail="missing",
        )
        passed = HANDOFF._check("core", "Core", "pass", required=True, detail="ok")
        blocked = HANDOFF._check(
            "workspace", "Workspace", "blocked_requirement", required=True, detail="old",
        )
        failed = HANDOFF._check("broken", "Broken", "fail", required=True, detail="bad")
        self.assertEqual(HANDOFF.overall_state([passed, optional]), "pass")
        self.assertEqual(HANDOFF.overall_state([passed, blocked, optional]), "blocked_requirement")
        self.assertEqual(HANDOFF.overall_state([passed, failed, optional]), "fail")

    def test_missing_workspace_is_a_remediable_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            check = HANDOFF.workspace_check(Path(directory) / "missing")
        self.assertEqual(check.state, "blocked_requirement")
        self.assertTrue(check.required)
        self.assertEqual(check.action, "./setup")

    def test_report_file_is_private_and_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "handoff.json"
            HANDOFF.write_new_json(destination, {"ok": True})
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(destination.read_text()), {"ok": True})
            with self.assertRaises(FileExistsError):
                HANDOFF.write_new_json(destination, {"ok": False})

    def test_core_handoff_runs_in_disposable_storage_without_printing_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            environment = os.environ.copy()
            environment.update({
                "XTI_DATA_DIR": str(data),
                "HOME": str(root / "home"),
                "XDG_CONFIG_HOME": str(root / "config"),
                "TAVILY_API_KEY": "tvly-secret-not-output-12345",
            })
            (root / "home").mkdir(mode=0o700)
            (root / "config").mkdir(mode=0o700)
            setup = subprocess.run(
                [str(PROJECT / "setup"), "--core-only"],
                cwd=PROJECT, env=environment, capture_output=True, text=True,
                timeout=180, check=False,
            )
            self.assertEqual(setup.returncode, 0, setup.stderr)
            result = subprocess.run(
                [str(PROJECT / "handoff"), "--profile", "core", "--data-dir", str(data), "--json"],
                cwd=PROJECT, env=environment, capture_output=True, text=True,
                timeout=240, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("tvly-secret-not-output-12345", result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual(report["overall_state"], "pass")
            self.assertTrue(report["core_ready"])
            self.assertTrue(all(
                item["state"] == "pass"
                for item in report["checks"] if item["required"]
            ))
            self.assertEqual(
                next(item for item in report["checks"] if item["identifier"] == "optional.tavily")["state"],
                "pass",
            )


if __name__ == "__main__":
    unittest.main()

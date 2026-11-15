"""Brand installation acceptance with isolated fake package operations."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from xti.adapters.tool_installation import brand_installation_lock, ToolInstallationError


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xti_brand_setup_tests", PROJECT / "scripts/setup_brand.py")
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class BrandSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="xti-brand-install-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "project with spaces"
        self.root.mkdir()
        for name in (
            "scripts/setup-brand", "scripts/setup_brand.py", "scripts/bootstrap-python",
            "src/xti/__init__.py", "src/xti/adapters/__init__.py",
            "src/xti/adapters/tool_installation.py", "src/xti/adapters/installation_process.py",
            "src/xti/adapters/installation_transaction.py", "constraints/brand.txt", "pyproject.toml",
        ):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT / name, destination)
        self.venv = self.root / ".venv"
        self.bin = self.root / "fake-bin"
        self.bin.mkdir()
        self.log = self.root / "calls.jsonl"
        self.pid = self.root / "child.pid"
        self.driver = self.root / "driver.py"
        self.driver.write_text('''
import importlib.util
import os
from pathlib import Path
import sys
from unittest.mock import patch
path = Path(__file__).parent / "scripts/setup_brand.py"
spec = importlib.util.spec_from_file_location("brand_setup", path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
with patch.object(helper, "stable_bootstrap", return_value=Path(os.environ["XTI_TEST_BOOTSTRAP"])):
    raise SystemExit(helper.main(sys.argv[1:]))
''')
        self.fake_python = self.bin / "bootstrap"
        self.fake_source = f'''#!{sys.executable}
import fcntl
import json
import os
from pathlib import Path
import signal
import sys
import time
args = sys.argv[1:]
stage = "venv" if args[:2] == ["-m", "venv"] else (
    "install" if "install" in args else "pip-check" if "check" in args else "verify")
lock = Path(os.environ["XTI_TEST_ROOT"]) / ".brand-install.lock"
with lock.open("rb") as stream:
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        pass
    else:
        raise SystemExit("installer lock was not held")
if stage == "verify":
    fd = int(args[args.index("--installation-lock-fd") + 1])
    assert os.fstat(fd).st_ino == lock.stat().st_ino
with Path(os.environ["XTI_TEST_LOG"]).open("a") as stream:
    stream.write(json.dumps({{"stage": stage, "args": args, "cwd": os.getcwd(),
                            "home": os.environ.get("HOME"), "pythonpath": os.environ.get("PYTHONPATH"),
                            "pip_target": os.environ.get("PIP_TARGET"),
                            "git_config": os.environ.get("GIT_CONFIG_GLOBAL"),
                            "path": os.environ.get("PATH")}}) + "\\n")
if os.environ.get("XTI_TEST_BLOCK") == stage:
    Path(os.environ["XTI_TEST_PID"]).write_text(str(os.getpid()))
    if os.environ.get("XTI_TEST_IGNORE_TERM"):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(0.05)
if os.environ.get("XTI_TEST_FAIL") == stage:
    raise SystemExit(7)
if stage == "verify" and (Path(__file__).parents[1] / "missing-news").exists():
    raise SystemExit("feedparser paketi eksik")
if stage == "venv":
    target = Path(args[2])
    (target / "bin").mkdir()
    script = target / "bin/python"
    script.write_bytes(Path(__file__).read_bytes())
    script.chmod(0o700)
elif stage == "install":
    (Path(__file__).parent / "maigret").write_text("canonical:" + str(Path(__file__).parent))
elif stage == "verify":
    print("Marka araçları doğrulandı.")
'''
        self.fake_python.write_text(self.fake_source)
        self.fake_python.chmod(0o700)
        self.git = self.bin / "git"
        self.git.write_text("#!/bin/sh\nexit 0\n")
        self.git.chmod(0o700)
        self.environment = dict(os.environ, PATH=str(self.bin), PYTHONPATH=str(self.root / "src"),
                                PYTHONDONTWRITEBYTECODE="1",
                                XTI_TEST_ROOT=str(self.root), XTI_TEST_LOG=str(self.log),
                                XTI_TEST_PID=str(self.pid), XTI_TEST_BOOTSTRAP=str(self.fake_python))
        for name in ("XTI_TEST_FAIL", "XTI_TEST_BLOCK", "XTI_TEST_IGNORE_TERM"):
            self.environment.pop(name, None)
        self.evidence = self.root / "evidence.bin"
        self.evidence.write_bytes(b"existing evidence\x00\xff")

    def run_setup(self, *arguments, cwd=None):
        return subprocess.run([sys.executable, str(self.driver), *arguments],
                              cwd=cwd or self.root, env=self.environment,
                              capture_output=True, text=True, timeout=15)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    @staticmethod
    def snapshot(path):
        result = {}
        for item in sorted(path.rglob("*")):
            key = str(item.relative_to(path))
            if item.is_symlink():
                result[key] = ("symlink", os.readlink(item))
            elif item.is_dir():
                result[key] = ("dir", item.stat().st_mode)
            elif item.is_file():
                result[key] = ("file", item.read_bytes(), item.stat().st_mode)
        return result

    def existing(self):
        (self.venv / "bin").mkdir(parents=True)
        python = self.venv / "bin/python"
        python.write_text(self.fake_source)
        python.chmod(0o700)
        (self.venv / "operator-settings").write_bytes(b"keep unchanged\x00\xff")
        return self.snapshot(self.venv)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / ".brand-install.json").exists())
        self.assertEqual(self.evidence.read_bytes(), b"existing evidence\x00\xff")

    def test_fresh_install_uses_final_venv_and_pinned_project_constraints(self):
        self.assert_success(self.run_setup())
        calls = self.calls()
        self.assertEqual([row["stage"] for row in calls], ["venv", "install", "pip-check", "verify"])
        self.assertEqual(calls[0]["args"], ["-m", "venv", str(self.venv)])
        command = calls[1]["args"]
        self.assertIn("--isolated", command)
        self.assertEqual(command[command.index("--constraint") + 1], str(self.root / "constraints/brand.txt"))
        self.assertEqual(command[-1], str(self.root) + "[brand,news]")
        self.assertIn(str(self.venv / "bin"), (self.venv / "bin/maigret").read_text())

    def test_force_preserves_exact_previous_environment_and_old_backups(self):
        before = self.existing()
        unrelated = self.root / ".venv-backup-older"
        unrelated.mkdir()
        (unrelated / "keep").write_text("old")
        self.assert_success(self.run_setup("--force"))
        backups = [path for path in self.root.glob(".venv-backup-*") if path != unrelated]
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.snapshot(backups[0]), before)
        self.assertEqual((unrelated / "keep").read_text(), "old")

    def test_ready_repeat_and_check_need_no_git_and_never_install(self):
        before = self.existing()
        self.git.unlink()
        for arguments in ((), ("--check",)):
            with self.subTest(arguments=arguments):
                self.assert_success(self.run_setup(*arguments))
        self.assertEqual([row["stage"] for row in self.calls()], ["pip-check", "verify"] * 2)
        self.assertEqual(self.snapshot(self.venv), before)

    def test_missing_news_check_preserves_old_environment_and_default_setup_upgrades_it(self):
        self.existing()
        (self.venv / "missing-news").write_text("Old environment has no reader")
        before = self.snapshot(self.venv)
        result = self.run_setup("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.snapshot(self.venv), before)
        self.assertFalse(list(self.root.glob(".venv-backup-*")))
        self.assert_success(self.run_setup())
        backups = list(self.root.glob(".venv-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.snapshot(backups[0]), before)
        self.assertFalse((self.venv / "missing-news").exists())
        self.assertEqual([row["stage"] for row in self.calls()],
                         ["pip-check", "verify", "pip-check", "verify", "venv", "install", "pip-check", "verify"])

    def test_failed_create_install_dependency_check_or_verifier_restores_exact_old_environment(self):
        before = self.existing()
        for stage, label in (
            ("venv", "Python ortamı oluşturma"), ("install", "Paket kurulumu"),
            ("pip-check", "Bağımlılık kontrolü"), ("verify", "Araç kimliği ve katalog doğrulaması"),
        ):
            with self.subTest(stage=stage):
                self.environment["XTI_TEST_FAIL"] = stage
                result = self.run_setup("--force")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(label + ":", result.stderr)
                self.assertEqual(self.snapshot(self.venv), before)
                self.assertFalse((self.root / ".brand-install.json").exists())
                self.assertEqual(self.evidence.read_bytes(), b"existing evidence\x00\xff")
        self.assertEqual(len(list(self.root.glob(".venv-failed-*"))), 4)

    def test_stage_diagnostics_preserve_cleanup_and_interruption_exception_types(self):
        for error in (HELPER.ProcessCleanupError("child may still write"), HELPER.SetupInterrupted("signal")):
            with self.subTest(error=type(error).__name__), patch.object(HELPER, "_run_command", side_effect=error):
                with self.assertRaises(type(error)) as caught:
                    HELPER.run_command(["python"], cwd=self.root, lock_fd=1, timeout=1, stage="Paket kurulumu")
                self.assertIs(caught.exception, error)

    def test_failed_first_install_keeps_candidate_without_ready_environment(self):
        self.environment["XTI_TEST_FAIL"] = "install"
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.venv.exists())
        self.assertEqual(len(list(self.root.glob(".venv-failed-*"))), 1)

    def test_failed_check_does_not_reinstall(self):
        before = self.existing()
        self.environment["XTI_TEST_FAIL"] = "verify"
        self.assertNotEqual(self.run_setup("--check").returncode, 0)
        self.assertEqual(self.snapshot(self.venv), before)
        self.assertEqual([row["stage"] for row in self.calls()], ["pip-check", "verify"])
        self.assertFalse(list(self.root.glob(".venv-backup-*")))

    def test_missing_git_stops_before_replacement(self):
        before = self.existing()
        self.git.unlink()
        result = self.run_setup("--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("git gerekiyor", result.stderr)
        self.assertEqual(self.snapshot(self.venv), before)
        self.assertFalse(list(self.root.glob(".venv-backup-*")))

    def test_missing_check_and_recover_do_not_create_environment(self):
        self.assertNotEqual(self.run_setup("--check").returncode, 0)
        self.assert_success(self.run_setup("--recover"))
        self.assertFalse(self.venv.exists())
        self.assertEqual(self.calls(), [])

    def test_legacy_lock_backup_and_marker_are_preserved_even_on_recover(self):
        before = self.existing()
        paths = (self.root / ".venv-install.lock", self.root / ".venv-backup", self.venv / ".xti-installing")
        for path in paths:
            path.write_bytes(b"unowned legacy file")
            for option in ("--force", "--check", "--recover"):
                with self.subTest(path=path.name, option=option):
                    result = self.run_setup(option)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("elle inceleme", result.stderr)
                    self.assertEqual(path.read_bytes(), b"unowned legacy file")
            path.unlink()
            self.assertEqual(self.snapshot(self.venv), before)
        self.assertEqual(self.calls(), [])

    def test_symlink_and_non_directory_environment_are_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep").write_text("original")
        self.venv.symlink_to(outside, target_is_directory=True)
        self.assertNotEqual(self.run_setup("--force").returncode, 0)
        self.assertEqual((outside / "keep").read_text(), "original")
        self.venv.unlink()
        self.venv.write_text("not environment")
        self.assertNotEqual(self.run_setup("--force").returncode, 0)
        self.assertEqual(self.venv.read_text(), "not environment")

    def test_shared_runtime_and_exclusive_installer_locks_block_all_modes(self):
        before = self.existing()
        for exclusive in (False, True):
            with brand_installation_lock(self.root, exclusive=exclusive):
                for arguments in ((), ("--force",), ("--check",), ("--recover",)):
                    result = self.run_setup(*arguments)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("sürüyor", result.stderr)
        self.assertEqual(self.snapshot(self.venv), before)
        self.assertEqual(self.calls(), [])

    def test_parent_cwd_may_be_inside_previous_environment(self):
        self.existing()
        self.assert_success(self.run_setup("--force", cwd=self.venv))
        self.assertEqual(self.calls()[0]["cwd"], str(self.root))

    def test_relative_path_is_anchored_before_leaving_previous_environment(self):
        self.existing()
        self.environment["PATH"] = "../fake-bin"
        self.assert_success(self.run_setup("--force", cwd=self.venv))
        self.assertTrue(all(row["path"] == str(self.bin) for row in self.calls()))

    def test_caller_pip_and_python_configuration_does_not_redirect_installation(self):
        self.environment.update(PIP_TARGET=str(self.root / "unrelated"),
                                GIT_CONFIG_GLOBAL=str(self.root / "user-git-config"))
        self.assert_success(self.run_setup())
        install = next(row for row in self.calls() if row["stage"] == "install")
        self.assertIsNone(install["pip_target"])
        self.assertIsNone(install["pythonpath"])
        self.assertEqual(install["git_config"], os.devnull)
        self.assertNotEqual(install["home"], self.environment.get("HOME"))
        self.assertFalse((self.root / "unrelated").exists())

    def test_bootstrap_rejects_interpreter_prefix_inside_managed_environment(self):
        for prefix in (self.venv, self.root / ".venv-backup-old", self.root / ".venv-failed-old"):
            with self.subTest(prefix=prefix), patch.object(HELPER.sys, "prefix", str(prefix)):
                with self.assertRaises(ToolInstallationError):
                    HELPER.stable_bootstrap(self.root)

    def pending(self, *, active=True):
        before = self.existing()
        data = HELPER.TRANSACTION.prepare(self.root)
        if active:
            HELPER.TRANSACTION.activate(self.root, data)
            (self.venv / "partial").write_text("new")
        return before, data

    def test_pending_journal_blocks_default_check_and_force(self):
        before, data = self.pending()
        for arguments in ((), ("--check",), ("--force",)):
            result = self.run_setup(*arguments)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--recover", result.stderr)
        self.assertEqual(self.snapshot(HELPER.TRANSACTION.paths(self.root, data["transaction"])["backup"]), before)
        self.assertEqual(self.calls(), [])

    def test_new_journal_and_legacy_lock_are_ambiguous_and_never_recovered(self):
        _, data = self.pending()
        legacy = self.root / ".venv-install.lock"
        legacy.mkdir()
        (legacy / "pid").write_text("12345")
        before = self.snapshot(self.root)
        result = self.run_setup("--recover")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("elle inceleme", result.stderr)
        after = self.snapshot(self.root)
        before.pop(".brand-install.lock", None)
        after.pop(".brand-install.lock", None)
        self.assertEqual(after, before)
        self.assertEqual(HELPER.TRANSACTION.load(self.root), data)

    def test_legacy_owner_appearing_during_failure_prevents_automatic_rollback(self):
        before = self.existing()
        def failed_command(*arguments, **keywords):
            (self.root / ".venv-install.lock").mkdir()
            raise ToolInstallationError("failed while another owner appeared")
        with brand_installation_lock(self.root, exclusive=True) as descriptor:
            with patch.object(HELPER, "run_command", side_effect=failed_command):
                with self.assertRaisesRegex(ToolInstallationError, "elle inceleme"):
                    HELPER.install(self.root, self.fake_python, descriptor)
        self.assertTrue((self.root / ".brand-install.json").exists())
        backup = next(self.root.glob(".venv-backup-*"))
        self.assertEqual(self.snapshot(backup), before)
        self.assertNotEqual(self.snapshot(self.venv), before)

    def test_recovery_is_repeatable_network_free_and_restores_previous_bytes(self):
        before, data = self.pending()
        self.git.unlink()
        self.fake_python.unlink()
        self.assert_success(self.run_setup("--recover"))
        self.assert_success(self.run_setup("--recover"))
        self.assertEqual(self.snapshot(self.venv), before)
        failed = HELPER.TRANSACTION.paths(self.root, data["transaction"])["failed"]
        self.assertEqual((failed / "partial").read_text(), "new")
        self.assertEqual(self.calls(), [])

    def test_committed_recovery_keeps_verified_new_environment(self):
        _, data = self.pending()
        HELPER.TRANSACTION.write(self.root, dict(data, phase="committed"))
        self.assert_success(self.run_setup("--recover"))
        self.assertEqual((self.venv / "partial").read_text(), "new")

    def test_foreign_directory_is_not_changed_by_recovery(self):
        _, data = self.pending()
        paths = HELPER.TRANSACTION.paths(self.root, data["transaction"])
        paths["failed"].mkdir()
        (paths["failed"] / "foreign").write_text("keep")
        before = self.snapshot(self.root)
        self.assertNotEqual(self.run_setup("--recover").returncode, 0)
        # The persistent lock can be created, but transaction files stay identical.
        after = self.snapshot(self.root)
        before.pop(".brand-install.lock", None)
        after.pop(".brand-install.lock", None)
        self.assertEqual(after, before)

    def test_excessively_nested_journal_is_rejected_without_traceback_or_file_changes(self):
        self.existing()
        journal = self.root / ".brand-install.json"
        journal.write_text('{"version":' + '[' * 2000 + '0' + ']' * 2000 + '}')
        before = self.snapshot(self.root)
        result = self.run_setup("--recover")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("günlüğü güvenle okunamadı", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        after = self.snapshot(self.root)
        before.pop(".brand-install.lock", None)
        after.pop(".brand-install.lock", None)
        self.assertEqual(after, before)

    def test_unconfirmed_child_shutdown_leaves_journal_for_explicit_recovery(self):
        before = self.existing()
        with brand_installation_lock(self.root, exclusive=True) as descriptor:
            with patch.object(HELPER, "run_command", side_effect=HELPER.ProcessCleanupError("unconfirmed")):
                with self.assertRaises(HELPER.ProcessCleanupError):
                    HELPER.install(self.root, self.fake_python, descriptor)
        self.assertTrue((self.root / ".brand-install.json").exists())
        self.assert_success(self.run_setup("--recover"))
        self.assertEqual(self.snapshot(self.venv), before)

    def blocked_install(self, *, stage="install", ignore_term=False):
        self.environment["XTI_TEST_BLOCK"] = stage
        if ignore_term:
            self.environment["XTI_TEST_IGNORE_TERM"] = "1"
        process = subprocess.Popen([sys.executable, str(self.driver), "--force"],
                                   cwd=self.root, env=self.environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_process, process)
        deadline = time.monotonic() + 5
        while not self.pid.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(self.pid.exists(), process.poll())
        return process, int(self.pid.read_text())

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)

    def test_sigterm_reaps_package_child_before_restoring_environment(self):
        before = self.existing()
        process, child = self.blocked_install(ignore_term=True)
        process.send_signal(signal.SIGTERM)
        _, stderr = process.communicate(timeout=8)
        self.assertNotEqual(process.returncode, 0, stderr)
        self.assertEqual(self.snapshot(self.venv), before)
        self.assertFalse((self.root / ".brand-install.json").exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    def test_sigkill_keeps_child_lock_then_explicit_recovery_restores_environment(self):
        before = self.existing()
        process, child = self.blocked_install()
        try:
            process.kill()
            process.wait(timeout=5)
            result = self.run_setup("--recover")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("sürüyor", result.stderr)
            self.assertTrue((self.root / ".brand-install.json").exists())
        finally:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate(timeout=5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.run_setup("--recover")
            if result.returncode == 0:
                break
            time.sleep(0.02)
        self.assert_success(result)
        self.assertEqual(self.snapshot(self.venv), before)

    def test_interrupted_verification_never_starts_reinstallation(self):
        before = self.existing()
        self.environment["XTI_TEST_BLOCK"] = "verify"
        process = subprocess.Popen([sys.executable, str(self.driver)], cwd=self.root,
                                   env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_process, process)
        deadline = time.monotonic() + 5
        while not self.pid.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(self.pid.exists())
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=5)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(self.snapshot(self.venv), before)
        self.assertFalse(list(self.root.glob(".venv-backup-*")))
        self.assertEqual([row["stage"] for row in self.calls()], ["pip-check", "verify"])


if __name__ == "__main__":
    unittest.main()

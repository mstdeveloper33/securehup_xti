"""Installer subprocess acceptance with closed PATH, temp projects and no network."""

import fcntl
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
import uuid
from unittest.mock import patch

from xti.domain.component_pins import HARVESTER_PIN


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMIT = HARVESTER_PIN.commit
UV_VARIABLES = ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "UV_PYTHON_BIN_DIR")
SPEC = importlib.util.spec_from_file_location("xti_test_harvester_setup", PROJECT_ROOT / "scripts/setup_harvester.py")
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


BLOCK_HELPER = '''
def block(stage):
    if os.environ.get("XTI_TEST_BLOCK_STAGE") == stage:
        import signal
        import time
        if os.environ.get("XTI_TEST_IGNORE_TERM"):
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        Path(os.environ["XTI_TEST_CHILD_PID"]).write_text(str(os.getpid()))
        while True:
            time.sleep(0.1)
def fail(stage):
    if os.environ.get("XTI_TEST_FAIL_STAGE") == stage:
        raise SystemExit(7)
'''


class HarvesterSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="xti-harvester-setup-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "project with spaces"
        self.scripts = self.root / "scripts"
        self.scripts.mkdir(parents=True)
        for relative in (
            "scripts/setup-harvester", "scripts/setup_harvester.py", "scripts/python",
            "scripts/bootstrap-python", "scripts/run_python.py",
            "src/xti/__init__.py", "src/xti/adapters/__init__.py",
            "src/xti/adapters/tool_installation.py", "src/xti/domain/__init__.py",
            "src/xti/adapters/installation_process.py",
            "src/xti/adapters/installation_transaction.py",
            "src/xti/domain/component_pins.py",
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT_ROOT / relative, destination)
        self.installer = self.scripts / "setup-harvester"
        self.bin = Path(temporary.name).resolve() / "fake-bin"
        self.bin.mkdir()
        (self.bin / "dirname").symlink_to(shutil.which("dirname"))
        self.parent = self.root / ".tools"
        self.checkout = self.parent / "theharvester"
        self.git_log = self.root / "git-calls.jsonl"
        self.uv_log = self.root / "uv-call.json"
        self.cli_log = self.root / "cli-smoke.json"
        self.child_pid = self.root / "child.pid"
        self.environment = {
            key: value for key, value in os.environ.items()
            if key not in UV_VARIABLES and not key.startswith("XTI_TEST_")
        }
        self.environment.update(
            PATH=str(self.bin), XTI_PYTHON=sys.executable,
            XTI_TEST_GIT_LOG=str(self.git_log), XTI_TEST_UV_LOG=str(self.uv_log),
            XTI_TEST_CLI_LOG=str(self.cli_log), XTI_TEST_CHILD_PID=str(self.child_pid),
        )
        self.write_executable(self.bin / "git", '''
import json
import os
from pathlib import Path
import sys
''' + BLOCK_HELPER + f'''
args = sys.argv[1:]
with Path(os.environ["XTI_TEST_GIT_LOG"]).open("a") as target:
    target.write(json.dumps(args) + "\\n")
if args[0] == "clone":
    directory = Path(args[-1])
    (directory / ".git").mkdir()
    (directory / ".git/origin").write_text({HARVESTER_PIN.repository!r})
    (directory / ".git/HEAD").write_text({COMMIT!r})
    block("clone")
    fail("clone")
else:
    directory = Path(args[1])
    command = args[2]
    block(command)
    fail(command)
    if command == "remote":
        print((directory / ".git/origin").read_text())
    elif command == "status":
        dirty = directory / ".git/dirty"
        print(dirty.read_text() if dirty.exists() else "")
    elif command == "rev-parse":
        print((directory / ".git/HEAD").read_text())
    elif command == "checkout":
        (directory / ".git/HEAD").write_text(args[-1])
''')

    def write_executable(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
        path.chmod(0o700)

    def add_uv(self, path=None, label="path"):
        path = path or self.bin / "uv"
        cli_body = '''
import json
import os
from pathlib import Path
import sys
''' + BLOCK_HELPER + '''
Path(os.environ["XTI_TEST_CLI_LOG"]).write_text(json.dumps({
    "cwd": str(Path.cwd()), "args": sys.argv[1:],
    "home": os.environ.get("HOME"),
    "config": os.environ.get("XDG_CONFIG_HOME"),
    "cache": os.environ.get("XDG_CACHE_HOME"),
    "database": os.environ.get("THEHARVESTER_RUN_DB"),
}))
block("smoke")
fail("smoke")
'''
        self.write_executable(path, f'''
import json
import os
from pathlib import Path
import sys
import shlex
{BLOCK_HELPER}
data = {{
    "label": {label!r}, "args": sys.argv[1:], "cwd": str(Path.cwd()),
    "environment": {{name: os.environ.get(name) for name in {UV_VARIABLES!r}}},
    "project_environment": os.environ.get("UV_PROJECT_ENVIRONMENT"),
    "redirects": {{name: os.environ.get(name) for name in ("UV_PROJECT", "UV_WORKING_DIR", "UV_ACTIVE", "VIRTUAL_ENV")}},
}}
Path(os.environ["XTI_TEST_UV_LOG"]).write_text(json.dumps(data))
block("uv")
fail("uv")
executable = Path.cwd() / ".venv/bin/theHarvester"
executable.parent.mkdir(parents=True)
interpreter = executable.parent / "python"
interpreter.symlink_to({sys.executable!r})
script = executable.with_suffix(".py")
script.write_text({cli_body!r})
executable.write_text("#!/bin/sh\\nexec " + shlex.quote(str(interpreter)) + " " + shlex.quote(str(script)) + ' "$@"\\n')
executable.chmod(0o700)
''')

    def existing(self, *, installed=False):
        (self.checkout / ".git").mkdir(parents=True)
        (self.checkout / ".git/origin").write_text(HARVESTER_PIN.repository)
        (self.checkout / ".git/HEAD").write_text(COMMIT)
        (self.checkout / "personal-config.yaml").write_bytes(b"private: keep\x00exact\n")
        if installed:
            self.add_uv()
            result = self.run_installer("--force")
            self.assertEqual(result.returncode, 0, result.stderr)
            (self.checkout / "personal-config.yaml").write_bytes(b"private: keep\x00exact\n")
        return self.snapshot(self.checkout)

    @staticmethod
    def snapshot(path):
        result = {}
        for item in sorted(path.rglob("*")):
            relative = str(item.relative_to(path))
            if item.is_symlink():
                result[relative] = ("symlink", os.readlink(item))
            elif item.is_file():
                result[relative] = ("file", item.read_bytes(), item.stat().st_mode)
            elif item.is_dir():
                result[relative] = ("dir", item.stat().st_mode)
        return result

    def run_installer(self, *arguments, cwd=None):
        return subprocess.run(
            [str(self.installer), *arguments], cwd=cwd or self.root, env=self.environment,
            capture_output=True, text=True, timeout=15, check=False,
        )

    def assert_success(self, result, label="path"):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"theHarvester hazır: {COMMIT}", result.stdout)
        call = json.loads(self.uv_log.read_text())
        self.assertEqual(call["label"], label)
        self.assertEqual(call["args"], ["sync", "--frozen", "--no-dev", "--no-editable", "--project", str(self.checkout)])
        self.assertEqual(call["cwd"], str(self.checkout))
        self.assertEqual(call["project_environment"], str(self.checkout / ".venv"))
        self.assertTrue(all(value is None for value in call["redirects"].values()))
        smoke = json.loads(self.cli_log.read_text())
        self.assertEqual(smoke["cwd"], str(self.parent))
        self.assertEqual(smoke["args"], ["--help"])
        self.assertNotEqual(smoke["home"], self.environment.get("HOME"))
        self.assertTrue(Path(smoke["config"]).is_relative_to(smoke["home"]))
        self.assertTrue(Path(smoke["cache"]).is_relative_to(smoke["home"]))
        self.assertTrue(Path(smoke["database"]).is_relative_to(smoke["home"]))
        launcher = (self.checkout / ".venv/bin/theHarvester").read_text()
        self.assertIn(str(self.checkout / ".venv/bin/python"), launcher)
        self.assertNotIn(".theharvester-candidate-", launcher)
        self.assertNotIn(".theharvester-backup-", launcher)
        return call

    def test_project_local_uv_is_used_without_changing_path(self):
        self.add_uv(self.parent / "uv/bin/uv", "project-local")
        call = self.assert_success(self.run_installer(), "project-local")
        self.assertEqual(call["environment"], {
            "UV_CACHE_DIR": str(self.parent / "uv-cache"),
            "UV_PYTHON_INSTALL_DIR": str(self.parent / "python"),
            "UV_PYTHON_BIN_DIR": str(self.parent / "python-bin"),
        })

    def test_path_uv_has_priority_over_project_local_uv(self):
        self.add_uv(self.parent / "uv/bin/uv", "project-local")
        self.add_uv()
        self.assert_success(self.run_installer())

    def test_relative_path_uv_survives_checkout_directory_change(self):
        self.add_uv(label="relative-path")
        self.environment["PATH"] = "../fake-bin"
        self.assert_success(self.run_installer(), "relative-path")

    def test_missing_relative_path_uv_is_not_rediscovered_after_chdir(self):
        self.add_uv(self.parent / "uv/bin/uv", "project-local")
        self.add_uv(self.root / "fake-bin/uv", "wrong-working-directory")
        self.environment["PATH"] = "../fake-bin"
        self.assert_success(self.run_installer(), "project-local")

    def test_explicit_uv_directories_are_preserved(self):
        self.add_uv()
        overrides = {name: str(self.root / "operator choice" / name.lower()) for name in UV_VARIABLES}
        self.environment.update(overrides)
        call = self.assert_success(self.run_installer())
        self.assertEqual(call["environment"], overrides)

    def test_caller_environment_cannot_redirect_uv_into_an_unrelated_project(self):
        self.add_uv()
        outside = self.root / "another-project"
        outside.mkdir()
        (outside / "keep").write_bytes(b"do not prune")
        for name in ("UV_PROJECT_ENVIRONMENT", "UV_PROJECT", "UV_WORKING_DIR", "VIRTUAL_ENV"):
            self.environment[name] = str(outside)
        self.environment["UV_ACTIVE"] = "1"
        self.assert_success(self.run_installer())
        self.assertEqual(self.snapshot(outside), {"keep": ("file", b"do not prune", (outside / "keep").stat().st_mode)})

    def test_smoke_check_leaves_checkout_even_when_installer_starts_there(self):
        self.existing()
        self.add_uv()
        self.assert_success(self.run_installer(cwd=self.checkout))

    def test_missing_uv_stops_before_clone_or_tool_directory_creation(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("uv aracı gerekiyor", result.stderr)
        self.assertIn(".tools/uv/bin/uv", result.stderr)
        self.assertFalse(self.parent.exists())
        self.assertFalse(self.git_log.exists())

    def test_non_executable_local_uv_is_rejected_without_mutation(self):
        path = self.parent / "uv/bin/uv"
        self.add_uv(path, "unusable")
        path.chmod(0o600)
        before = path.read_bytes()
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.checkout.exists())
        self.assertFalse(self.git_log.exists())
        self.assertEqual(path.read_bytes(), before)

    def test_help_invalid_and_missing_check_recover_do_not_create_tools(self):
        for args, code in ((["--help"], 0), (["--invalid"], 2), (["--force", "--check"], 2),
                           (["--check"], 1), (["--recover"], 0)):
            with self.subTest(args=args):
                result = self.run_installer(*args)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertFalse(self.parent.exists())
                self.assertFalse(self.git_log.exists())

    def test_default_repeat_and_check_use_no_uv_or_network_and_keep_lock_inode(self):
        self.add_uv()
        self.assert_success(self.run_installer())
        lock = self.parent / ".theharvester.lock"
        lock_inode = lock.stat().st_ino
        before = self.snapshot(self.checkout)
        (self.bin / "uv").unlink()
        self.uv_log.unlink()
        for args in ((), ("--check",)):
            self.git_log.unlink()
            result = self.run_installer(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(self.uv_log.exists())
            self.assertEqual(self.snapshot(self.checkout), before)
            calls = [json.loads(line) for line in self.git_log.read_text().splitlines()]
            self.assertTrue(all(call[2] in ("remote", "status", "rev-parse") for call in calls))
            self.assertEqual(lock.stat().st_ino, lock_inode)

    def test_force_retains_previous_bytes_and_builds_final_executable_at_canonical_path(self):
        before = self.existing(installed=True)
        old_backups = set(self.parent.glob(".theharvester-backup-*"))
        self.assert_success(self.run_installer("--force"))
        backups = set(self.parent.glob(".theharvester-backup-*")) - old_backups
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.snapshot(backups.pop()), before)
        self.assertFalse((self.parent / ".theharvester-install.json").exists())

    def test_failures_restore_exact_previous_checkout_and_quarantine_candidate(self):
        before = self.existing(installed=True)
        for stage in ("clone", "fetch", "checkout", "uv", "smoke"):
            with self.subTest(stage=stage):
                self.environment["XTI_TEST_FAIL_STAGE"] = stage
                failed_before = set(self.parent.glob(".theharvester-failed-*"))
                result = self.run_installer("--force")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertNotIn("theHarvester hazır", result.stdout)
                self.assertEqual(self.snapshot(self.checkout), before)
                self.assertEqual(len(set(self.parent.glob(".theharvester-failed-*")) - failed_before), 1)
                self.assertFalse((self.parent / ".theharvester-install.json").exists())
        self.environment.pop("XTI_TEST_FAIL_STAGE")
        self.assertEqual(self.run_installer("--check").returncode, 0)

    def test_new_install_failure_preserves_failed_candidate_without_reporting_ready(self):
        self.add_uv()
        self.environment["XTI_TEST_FAIL_STAGE"] = "smoke"
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("theHarvester hazır", result.stdout)
        self.assertFalse(self.checkout.exists())
        self.assertEqual(len(list(self.parent.glob(".theharvester-failed-*"))), 1)

    def test_check_failure_does_not_install_or_change_existing_files(self):
        before = self.existing()
        self.add_uv()
        result = self.run_installer("--check")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.snapshot(self.checkout), before)
        self.assertFalse(self.uv_log.exists())
        self.assertFalse(list(self.parent.glob(".theharvester-backup-*")))

    def test_rejects_wrong_origin_dirty_checkout_and_wrong_commit_check(self):
        self.existing()
        self.add_uv()
        for relative, value, option in (
            (".git/origin", "https://example.invalid/foreign.git", "--force"),
            (".git/dirty", " M tracked-file", "--force"),
            (".git/HEAD", "0" * 40, "--check"),
        ):
            path = self.checkout / relative
            original = path.read_bytes() if path.exists() else None
            path.write_text(value)
            before = self.snapshot(self.checkout)
            result = self.run_installer(option)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(self.snapshot(self.checkout), before)
            self.assertFalse(self.uv_log.exists())
            if original is None:
                path.unlink()
            else:
                path.write_bytes(original)

    def test_rejects_symlink_parent_checkout_git_and_nonrepo(self):
        foreign = self.root / "foreign"
        foreign.mkdir()
        (foreign / "keep").write_text("untouched")
        self.add_uv()
        for target in (self.parent, self.checkout, self.checkout / ".git"):
            if target != self.parent:
                target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(foreign, target_is_directory=True)
            result = self.run_installer("--force")
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual((foreign / "keep").read_text(), "untouched")
            target.unlink()
        self.assertEqual(self.run_installer("--force").returncode, 1)
        self.assertFalse(self.uv_log.exists())

    def transaction(self, old_position="backup", new_position="canonical", *, committed=False, old=True):
        self.parent.mkdir(exist_ok=True)
        transaction = str(uuid.uuid4())
        paths = HELPER.journal_paths(self.parent, transaction)
        old_id = None
        if old:
            paths[old_position].mkdir()
            (paths[old_position] / "old-data").write_bytes(b"old\x00data")
            old_id = HELPER.identity(paths[old_position])
        paths[new_position].mkdir()
        (paths[new_position] / "new-data").write_bytes(b"new\x00data")
        data = {"version": 1, "transaction": transaction,
                "phase": "committed" if committed else "prepared", "old": old_id,
                "new": HELPER.identity(paths[new_position])}
        (self.parent / ".theharvester-install.json").write_text(json.dumps(data))
        return paths, data

    def test_recover_each_rename_boundary_and_partial_rollback_without_commands(self):
        for old, new in (("canonical", "candidate"), ("backup", "candidate"),
                         ("backup", "canonical"), ("backup", "failed"), ("canonical", "failed")):
            with self.subTest(old=old, new=new):
                paths, data = self.transaction(old, new)
                result = self.run_installer("--recover")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(HELPER.identity(self.checkout), data["old"])
                self.assertEqual(HELPER.identity(paths["failed"]), data["new"])
                self.assertEqual((self.checkout / "old-data").read_bytes(), b"old\x00data")
                self.assertFalse(self.git_log.exists())
                self.assertFalse(self.uv_log.exists())
                self.assertEqual(self.run_installer("--recover").returncode, 0)
                # Only the fixture removes its own previous scenario.
                shutil.rmtree(self.checkout)

    def test_recover_new_install_and_committed_transaction(self):
        paths, data = self.transaction(old=False)
        self.assertEqual(self.run_installer("--recover").returncode, 0)
        self.assertFalse(self.checkout.exists())
        self.assertEqual(HELPER.identity(paths["failed"]), data["new"])
        paths, data = self.transaction(committed=True)
        self.assertEqual(self.run_installer("--recover").returncode, 0)
        self.assertEqual(HELPER.identity(self.checkout), data["new"])
        self.assertEqual(HELPER.identity(paths["backup"]), data["old"])
        self.assertFalse(self.git_log.exists())

    def test_pending_journal_blocks_install_and_check_until_explicit_recovery(self):
        self.transaction()
        for args in ((), ("--check",), ("--force",)):
            result = self.run_installer(*args)
            self.assertEqual(result.returncode, 1)
            self.assertIn("--recover", result.stderr)
            self.assertFalse(self.git_log.exists())
        self.assertEqual(self.run_installer("--recover").returncode, 0)

    def test_recovery_rejects_malformed_foreign_and_symlink_paths_without_mutation(self):
        paths, data = self.transaction()
        journal = self.parent / ".theharvester-install.json"
        for value in ("{", "[]", json.dumps(dict(data, transaction="../../foreign")),
                      json.dumps(dict(data, old=[True, 1])), json.dumps(dict(data, phase="unknown")),
                      json.dumps(dict(data, foreign="path"))):
            journal.write_text(value)
            before = self.snapshot(self.parent)
            self.assertEqual(self.run_installer("--recover").returncode, 1)
            after = self.snapshot(self.parent)
            before.pop(".theharvester.lock", None)
            after.pop(".theharvester.lock", None)
            self.assertEqual(before, after)
        journal.write_text(json.dumps(data))
        foreign = paths["canonical"].with_name("unrelated")
        paths["canonical"].rename(foreign)
        paths["canonical"].mkdir()
        self.assertEqual(self.run_installer("--recover").returncode, 1)
        self.assertTrue(paths["backup"].is_dir())
        paths["canonical"].rmdir()
        paths["canonical"].symlink_to(foreign, target_is_directory=True)
        self.assertEqual(self.run_installer("--recover").returncode, 1)
        self.assertTrue(paths["backup"].is_dir())
        self.assertTrue((foreign / "new-data").exists())
        paths["canonical"].unlink()
        foreign.rename(paths["canonical"])
        journal.unlink()
        journal.symlink_to(self.root / "missing-journal")
        self.assertEqual(self.run_installer("--recover").returncode, 1)
        self.assertTrue(paths["backup"].is_dir())

    def test_exclusive_and_shared_locks_block_install_and_recovery(self):
        self.parent.mkdir()
        lock = self.parent / ".theharvester.lock"
        with lock.open("w") as stream:
            for operation in (fcntl.LOCK_EX, fcntl.LOCK_SH):
                fcntl.flock(stream, operation | fcntl.LOCK_NB)
                for args in (("--force",), ("--recover",), ("--check",)):
                    result = self.run_installer(*args)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("sürüyor", result.stderr)
                fcntl.flock(stream, fcntl.LOCK_UN)
        self.assertFalse(self.git_log.exists())

    def start_blocked(self, stage="uv", arguments=("--force",)):
        self.environment["XTI_TEST_BLOCK_STAGE"] = stage
        self.environment["XTI_TEST_IGNORE_TERM"] = "1"
        process = subprocess.Popen([str(self.installer), *arguments], cwd=self.root,
                                   env=self.environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_process, process)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not self.child_pid.exists():
            if process.poll() is not None:
                self.fail("installer exited before child: " + repr(process.communicate()))
            time.sleep(0.02)
        self.assertTrue(self.child_pid.exists(), "child was not launched")
        child = int(self.child_pid.read_text())
        self.addCleanup(self.stop_group, child)
        return process, child

    @staticmethod
    def stop_group(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)

    def test_sigterm_reaps_owned_group_then_restores_previous_installation(self):
        before = self.existing()
        self.add_uv()
        process, child = self.start_blocked()
        process.terminate()
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 1, stdout + stderr)
        self.assertEqual(self.snapshot(self.checkout), before)
        self.assertFalse((self.parent / ".theharvester-install.json").exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    def test_sigkill_leaves_child_lock_until_child_stops_then_explicit_recovery_works(self):
        before = self.existing()
        self.add_uv()
        process, child = self.start_blocked()
        process.kill()
        process.communicate(timeout=5)
        result = self.run_installer("--recover")
        self.assertEqual(result.returncode, 1)
        self.assertIn("sürüyor", result.stderr)
        self.assertTrue((self.parent / ".theharvester-install.json").exists())
        self.stop_group(child)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.run_installer("--recover")
            if result.returncode == 0:
                break
            time.sleep(0.02)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(self.checkout), before)

    def test_timeout_kills_owned_process_group_and_returns_control(self):
        self.parent.mkdir()
        program = self.bin / "timeout-child"
        self.write_executable(program, '''
import os
from pathlib import Path
import signal
import time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path(os.environ["XTI_TEST_CHILD_PID"]).write_text(str(os.getpid()))
while True:
    time.sleep(0.1)
''')
        with (self.parent / ".theharvester.lock").open("w") as lock:
            with self.assertRaises(subprocess.TimeoutExpired):
                HELPER.run_command([program], cwd=self.parent, lock_fd=lock.fileno(), timeout=1,
                                   environment=self.environment)
        child = int(self.child_pid.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)


    def test_repeated_termination_during_cleanup_cannot_leave_a_child_writing(self):
        before = self.existing()
        self.add_uv()
        process, child = self.start_blocked()
        process.terminate()
        time.sleep(0.2)
        process.terminate()
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 1, stdout + stderr)
        self.assertEqual(self.snapshot(self.checkout), before)
        self.assertFalse((self.parent / ".theharvester-install.json").exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    def test_interrupted_existing_verification_does_not_start_reinstallation(self):
        before = self.existing(installed=True)
        self.uv_log.unlink()
        self.git_log.unlink()
        process, child = self.start_blocked("smoke", arguments=())
        process.terminate()
        process.communicate(timeout=10)
        self.assertEqual(process.returncode, 1)
        self.assertEqual(self.snapshot(self.checkout), before)
        self.assertFalse(self.uv_log.exists())
        calls = [json.loads(line) for line in self.git_log.read_text().splitlines()]
        self.assertFalse(any(call[0] == "clone" or "fetch" in call for call in calls))
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    def test_output_limit_stops_a_running_command_before_timeout(self):
        self.parent.mkdir()
        program = self.bin / "noisy-child"
        self.write_executable(program, '''
import os
from pathlib import Path
import sys
import time
Path(os.environ["XTI_TEST_CHILD_PID"]).write_text(str(os.getpid()))
sys.stdout.buffer.write(b"x" * (2 * 1024 * 1024))
sys.stdout.flush()
time.sleep(10)
''')
        started = time.monotonic()
        with (self.parent / ".theharvester.lock").open("w") as lock:
            with self.assertRaisesRegex(HELPER.ToolInstallationError, "boyut"):
                HELPER.run_command([program], cwd=self.parent, lock_fd=lock.fileno(), timeout=8,
                                   environment=self.environment)
        self.assertLess(time.monotonic() - started, 5)
        child = int(self.child_pid.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(child, 0)

    def test_exited_leader_cannot_leave_a_background_writer_on_success_or_failure(self):
        self.parent.mkdir()
        marker = self.root / "late-write"
        program = self.bin / "spawning-command"
        for exit_code in (0, 7):
            self.write_executable(program, f'''
import os
import time
from pathlib import Path
if os.fork() == 0:
    time.sleep(0.8)
    Path({str(marker)!r}).write_text("must not happen")
    os._exit(0)
os._exit({exit_code})
''')
            with (self.parent / ".theharvester.lock").open("w") as lock:
                if exit_code:
                    with self.assertRaises(HELPER.ToolInstallationError):
                        HELPER.run_command([program], cwd=self.parent, lock_fd=lock.fileno(), timeout=5)
                else:
                    HELPER.run_command([program], cwd=self.parent, lock_fd=lock.fileno(), timeout=5)
            time.sleep(1)
            self.assertFalse(marker.exists())

    def test_unconfirmed_child_shutdown_preserves_journal_for_later_recovery(self):
        before = self.existing()
        with HELPER.tool_installation_lock(self.parent, exclusive=True) as lock:
            with patch.object(HELPER, "run_command", side_effect=HELPER.ProcessCleanupError("shutdown denied")):
                with self.assertRaises(HELPER.ProcessCleanupError):
                    HELPER.install(self.parent, self.bin / "git", self.bin / "uv", lock)
        self.assertTrue((self.parent / ".theharvester-install.json").is_file())
        backups = list(self.parent.glob(".theharvester-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.snapshot(backups[0]), before)
        self.assertNotEqual(self.snapshot(self.checkout), before)
        self.assertEqual(self.run_installer("--recover").returncode, 0)
        self.assertEqual(self.snapshot(self.checkout), before)

    def test_signal_permission_failure_is_a_controlled_cleanup_error(self):
        process = unittest.mock.Mock(pid=12345)
        with patch.object(HELPER.os, "killpg", side_effect=PermissionError("denied")):
            with self.assertRaises(HELPER.ProcessCleanupError):
                HELPER.terminate_group(process)
        process.wait.assert_not_called()

    def test_signal_between_spawn_and_handle_assignment_keeps_child_lock_for_recovery(self):
        self.parent.mkdir()
        command = self.bin / "launch-window-child"
        self.write_executable(command, "import time\ntime.sleep(10)\n")
        real_popen = subprocess.Popen
        launched = []

        def interrupted_launch(*arguments, **keywords):
            process = real_popen(*arguments, **keywords)
            launched.append(process)
            os.kill(os.getpid(), signal.SIGTERM)
            return process

        try:
            with HELPER.interruption_handlers():
                with HELPER.tool_installation_lock(self.parent, exclusive=True) as descriptor:
                    with patch.object(HELPER.subprocess, "Popen", side_effect=interrupted_launch):
                        with self.assertRaises(HELPER.ProcessCleanupError):
                            HELPER.run_command([command], cwd=self.parent, lock_fd=descriptor, timeout=5)
            self.assertEqual(len(launched), 1)
            self.assertIsNone(launched[0].poll())
            # The unknown child outlives the launcher handle, so the caller must
            # retain its journal rather than recover across this live lock.
            with self.assertRaises(HELPER.ToolInstallationError):
                with HELPER.tool_installation_lock(self.parent, exclusive=True):
                    self.fail("recovery acquired a live child's installation lock")
        finally:
            for process in launched:
                HELPER.terminate_group(process)
        with HELPER.tool_installation_lock(self.parent, exclusive=True):
            pass

    def test_every_command_inherits_lock_descriptor(self):
        self.parent.mkdir()
        command = self.bin / "lock-probe"
        self.write_executable(command, '''
import fcntl
import os
from pathlib import Path
with (Path.cwd() / ".theharvester.lock").open("r") as stream:
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("locked")
    else:
        raise SystemExit("lock not inherited")
''')
        with HELPER.tool_installation_lock(self.parent, exclusive=True) as descriptor:
            result = HELPER.run_command([command], cwd=self.parent, lock_fd=descriptor, timeout=5)
            self.assertEqual(result, "locked")


if __name__ == "__main__":
    unittest.main()

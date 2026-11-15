"""Managed brand environments cannot be replaced under running XTI commands."""

from contextlib import redirect_stderr
from io import StringIO
import importlib.util
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from xti.adapters.maigret_username import MaigretUsernameSource
from xti.adapters.sherlock_username import SherlockUsernameSource
from xti.adapters.source_readiness import LocalSourceInstallationInspector
from xti.adapters.tool_installation import (
    BRAND_JOURNAL_NAME, BRAND_LOCK_NAME, ToolInstallationError,
    brand_installation_lock,
)
from xti.ports.discovery import SourceError
from tests import test_maigret_username as maigret_fixture
from tests import test_sherlock_username as sherlock_fixture


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("brand_runtime_verifier", PROJECT / "scripts/verify_brand_install.py")
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class BrandRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="xti-brand-runtime-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / "project with spaces"
        self.root.mkdir()
        for relative in (
            "scripts/python", "scripts/bootstrap-python", "scripts/run_python.py",
            "src/xti/__init__.py", "src/xti/adapters/__init__.py",
            "src/xti/adapters/tool_installation.py",
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT / relative, destination)
        self.environment = dict(os.environ)
        self.environment.pop("XTI_PYTHON", None)
        self.environment["PYTHONDONTWRITEBYTECODE"] = "1"

    def run_python(self, code, *, environment=None):
        return subprocess.run(
            [str(self.root / "scripts/python"), "-c", code], cwd=self.root,
            env=environment or self.environment, text=True, capture_output=True,
            timeout=10, check=False,
        )

    def make_venv(self):
        subprocess.run([sys._base_executable, "-m", "venv", "--without-pip", str(self.root / ".venv")],
                       check=True, capture_output=True, timeout=15)
        return self.root / ".venv/bin/python"

    def assert_exclusive_denied(self):
        with self.assertRaises(ToolInstallationError):
            with brand_installation_lock(self.root, exclusive=True):
                self.fail("A live reader allowed installation")

    def start(self, code):
        process = subprocess.Popen(
            [str(self.root / "scripts/python"), "-u", "-c", code],
            cwd=self.root, env=self.environment, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True,
        )
        self.addCleanup(self.finish, process)
        return process

    @staticmethod
    def finish(process):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()

    def line(self, process):
        self.assertTrue(select.select([process.stdout], [], [], 8)[0], "Runtime did not signal readiness")
        result = process.stdout.readline().strip()
        self.assertTrue(result, "Runtime exited without a readiness message")
        return result

    def test_default_and_external_override_select_expected_supported_python(self):
        executable = self.make_venv()
        result = self.run_python("import sys; print(sys.prefix)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.root / ".venv"))
        override = dict(self.environment, XTI_PYTHON=sys._base_executable)
        result = self.run_python("import sys; print(sys.prefix == sys.base_prefix)", environment=override)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "True"))
        self.assertTrue(executable.exists())

    def test_global_lock_survives_exec_and_blocks_install_until_command_finishes(self):
        process = self.start("import sys; print('ready', flush=True); sys.stdin.read()")
        self.assertEqual(self.line(process), "ready")
        self.assert_exclusive_denied()
        inode = (self.root / BRAND_LOCK_NAME).stat().st_ino
        process.communicate("", timeout=5)
        self.assertEqual(process.returncode, 0)
        with brand_installation_lock(self.root, exclusive=True):
            self.assertEqual((self.root / BRAND_LOCK_NAME).stat().st_ino, inode)

    def test_child_inherits_exec_lock_after_parent_is_killed(self):
        code = (
            "import subprocess, sys, time; "
            "subprocess.Popen([sys.executable, '-u', '-c', "
            "\"import sys; print('child-ready', flush=True); sys.stdin.read()\"], close_fds=False); "
            "time.sleep(60)"
        )
        process = self.start(code)
        self.assertEqual(self.line(process), "child-ready")
        process.kill()
        process.wait(timeout=5)
        self.assert_exclusive_denied()
        process.stdin.close()
        deadline = time.monotonic() + 5
        while True:
            try:
                with brand_installation_lock(self.root, exclusive=True):
                    break
            except ToolInstallationError:
                if time.monotonic() >= deadline:
                    self.fail("Child did not release inherited lock after EOF")
                time.sleep(0.02)

    def test_active_install_stops_launch_before_target_execution(self):
        marker = self.root / "executed"
        with brand_installation_lock(self.root, exclusive=True):
            result = self.run_python(f"from pathlib import Path; Path({str(marker)!r}).write_text('wrong')")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("XTI başlatılamadı", result.stderr)
        self.assertFalse(marker.exists())

    def test_pending_install_uses_base_python_without_importing_partial_site(self):
        executable = self.make_venv()
        site = next((self.root / ".venv/lib").glob("python*/site-packages"))
        marker = self.root / "unsafe-site-import"
        (site / "unsafe.pth").write_text(f"import pathlib; pathlib.Path({str(marker)!r}).write_text('wrong')\n")
        (self.root / BRAND_JOURNAL_NAME).write_text("pending")
        result = self.run_python("import sys; print(sys.prefix == sys.base_prefix)")
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "True"), result.stderr)
        self.assertFalse(marker.exists())
        result = self.run_python("raise AssertionError('wrong')",
                                 environment=dict(self.environment, XTI_PYTHON=str(executable)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--recover", result.stderr)
        self.assertFalse(marker.exists())

    def test_bootstrap_remains_outside_managed_venv_even_with_override(self):
        executable = self.make_venv()
        result = subprocess.run(
            [str(self.root / "scripts/bootstrap-python"), "-c", "import sys; print(sys.prefix == sys.base_prefix)"],
            env=dict(self.environment, XTI_PYTHON=str(executable)), capture_output=True,
            text=True, timeout=10,
        )
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "True"), result.stderr)

    def test_managed_stub_override_is_never_probed_before_lock_or_during_recovery(self):
        marker = self.root / "managed-stub-executed"
        for folder in (".venv", ".venv-backup-old", ".venv-candidate-old", ".venv-failed-old"):
            stub = self.root / folder / "bin/python"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                f"#!{sys._base_executable}\nfrom pathlib import Path\n"
                f"Path({str(marker)!r}).touch()\nprint({sys._base_executable!r})\n"
            )
            stub.chmod(0o700)
            alias = self.root / "python-alias"
            alias.symlink_to(stub)
            try:
                for candidate in (stub, alias):
                    environment = dict(self.environment, XTI_PYTHON=str(candidate))
                    with brand_installation_lock(self.root, exclusive=True):
                        result = self.run_python("print('wrong')", environment=environment)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(marker.exists())
                    (self.root / BRAND_JOURNAL_NAME).write_text("pending")
                    try:
                        result = self.run_python("print('wrong')", environment=environment)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("--recover", result.stderr)
                        self.assertFalse(marker.exists())
                    finally:
                        (self.root / BRAND_JOURNAL_NAME).unlink()
            finally:
                alias.unlink()

    def test_activated_path_walks_past_managed_stubs_to_later_external_python(self):
        managed_bin = self.root / ".venv/bin"
        external_bin = self.root / "external base bin"
        managed_bin.mkdir(parents=True)
        external_bin.mkdir()
        marker = self.root / "managed-path-executed"
        for name in ("python3.14", "python3.13", "python3.12", "python3.11", "python3", "python"):
            stub = managed_bin / name
            stub.write_text(f"#!{sys._base_executable}\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n")
            stub.chmod(0o700)
        (external_bin / "python3.14").symlink_to(sys._base_executable)
        (external_bin / "dirname").symlink_to(shutil.which("dirname"))
        environment = dict(self.environment, PATH=str(managed_bin) + os.pathsep + str(external_bin))
        result = subprocess.run(
            [str(self.root / "scripts/bootstrap-python"), "-c", "import sys; print(sys.prefix == sys.base_prefix)"],
            env=environment, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "True"), result.stderr)
        with brand_installation_lock(self.root, exclusive=True):
            result = self.run_python("print('wrong')", environment=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())
        (self.root / BRAND_JOURNAL_NAME).write_text("pending")
        result = self.run_python("import sys; print(sys.prefix == sys.base_prefix)", environment=environment)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "True"), result.stderr)
        self.assertFalse(marker.exists())

    def test_caller_sitecustomize_is_loaded_only_after_lock_and_never_during_recovery(self):
        custom = self.root / "custom-path"
        custom.mkdir()
        marker = self.root / "site-marker"
        (custom / "sitecustomize.py").write_text(
            "import fcntl\nfrom pathlib import Path\n"
            f"with Path({str(self.root / BRAND_LOCK_NAME)!r}).open('rb') as stream:\n"
            "    try:\n        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
            "    except BlockingIOError:\n        state = 'protected'\n"
            "    else:\n        state = 'unsafe'\n"
            f"Path({str(marker)!r}).write_text(state)\n"
        )
        environment = dict(self.environment, PYTHONPATH=str(custom))
        with brand_installation_lock(self.root, exclusive=True):
            result = self.run_python("print('wrong')", environment=environment)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())
        result = self.run_python("print('ready')", environment=environment)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "ready"), result.stderr)
        self.assertEqual(marker.read_text(), "protected")
        marker.unlink()
        (self.root / BRAND_JOURNAL_NAME).write_text("pending")
        result = self.run_python("print('core-ready')", environment=environment)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, "core-ready"), result.stderr)
        self.assertFalse(marker.exists())

    def test_symlink_or_file_managed_environment_is_not_executed_or_reported_ready(self):
        foreign = self.root / "foreign"
        binary = foreign / "bin/python"
        binary.parent.mkdir(parents=True)
        marker = self.root / "foreign-executed"
        binary.write_text(f"#!{sys._base_executable}\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n")
        binary.chmod(0o700)
        venv = self.root / ".venv"
        for kind in ("symlink", "file"):
            if kind == "symlink":
                venv.symlink_to(foreign, target_is_directory=True)
            else:
                venv.write_text("keep")
            try:
                result = self.run_python("import sys; print(sys.prefix == sys.base_prefix)")
                self.assertEqual((result.returncode, result.stdout.strip()), (0, "True"), result.stderr)
                for source in ("maigret", "sherlock"):
                    self.assertEqual(LocalSourceInstallationInspector(self.root).inspect(source)[0], "invalid")
                self.assertFalse(marker.exists())
            finally:
                venv.unlink()

    def test_unknown_override_is_an_explicit_failure(self):
        result = self.run_python("print('wrong')", environment=dict(self.environment, XTI_PYTHON="/missing/python"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("XTI_PYTHON", result.stderr)
        self.assertNotIn("wrong", result.stdout)

    def test_metadata_busy_or_pending_never_executes_or_changes_files(self):
        inspector = LocalSourceInstallationInspector(self.root)
        with patch("subprocess.run", side_effect=AssertionError("process")), \
             patch("socket.create_connection", side_effect=AssertionError("network")):
            before = sorted(self.root.rglob("*"))
            self.assertEqual(inspector.inspect("maigret")[0], "missing")
            self.assertEqual(sorted(self.root.rglob("*")), before)
            self.assertFalse((self.root / BRAND_LOCK_NAME).exists())
            with brand_installation_lock(self.root, exclusive=True):
                before = sorted(self.root.rglob("*"))
                for source in ("maigret", "sherlock"):
                    self.assertEqual(inspector.inspect(source)[0], "invalid")
                self.assertEqual(sorted(self.root.rglob("*")), before)
            (self.root / BRAND_JOURNAL_NAME).write_text("pending")
            for source in ("maigret", "sherlock"):
                state, error = inspector.inspect(source)
                self.assertEqual(state, "invalid")
                self.assertIn("--recover", error)

    def test_legacy_artifacts_prevent_social_workers_and_keep_core_available(self):
        for name in (".venv-install.lock", ".venv-backup", ".venv/.xti-installing"):
            artifact = self.root / name
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("keep")
            try:
                for source_type in (MaigretUsernameSource, SherlockUsernameSource):
                    source = source_type(project_dir=self.root, runner=lambda *a, **k: self.fail("worker"))
                    with self.assertRaisesRegex(SourceError, "--recover"):
                        source.preview("samplebrand", platforms=("GitHub",), request_timeout=5)
                result = self.run_python("print('core-ready')")
                self.assertEqual((result.returncode, result.stdout.strip()), (0, "core-ready"), result.stderr)
                self.assertEqual(artifact.read_text(), "keep")
            finally:
                artifact.unlink()

    def test_social_adapters_hold_lock_during_lookup_worker_and_parse(self):
        for source_type, fixture, platform, parser_name in (
            (MaigretUsernameSource, maigret_fixture, "GitHub", "parse_maigret_ndjson"),
            (SherlockUsernameSource, sherlock_fixture, "Carrd", "parse_sherlock_ndjson"),
        ):
            database = self.root / (platform + ".json")
            digest = fixture.database_fixture(database)
            original_parser = getattr(fixture, parser_name)
            calls = []

            def locate():
                self.assert_exclusive_denied()
                return database

            def parse(*args, **kwargs):
                self.assert_exclusive_denied()
                return original_parser(*args, **kwargs)

            def runner(command, *, cwd, pass_fds, **kwargs):
                self.assert_exclusive_denied()
                self.assertEqual(len(pass_fds), 1)
                self.assertEqual(os.fstat(pass_fds[0]).st_ino, (self.root / BRAND_LOCK_NAME).stat().st_ino)
                calls.append(command)
                if command[-1] == "--version":
                    return subprocess.CompletedProcess(command, 0, "maigret 0.6.6\n", "")
                if source_type is MaigretUsernameSource:
                    report = Path(cwd) / "reports/report_samplebrand_ndjson.json"
                    report.parent.mkdir()
                else:
                    report = Path(cwd) / "results.ndjson"
                report.write_bytes(fixture.ndjson(fixture.result()))
                return subprocess.CompletedProcess(command, 0, "", "")

            extra = {"executable_locator": lambda: "/fake/maigret"} if source_type is MaigretUsernameSource else {
                "python_locator": lambda: sys.executable, "version_locator": lambda: "0.16.2",
            }
            source = source_type(project_dir=self.root, runner=runner, database_locator=locate,
                                 database_sha256=digest, **extra)
            module = source_type.__module__
            with patch(module + "." + parser_name, side_effect=parse):
                result = source.preview("samplebrand", platforms=(platform,), request_timeout=5)
            self.assertEqual(len(result.matches), 1)
            self.assertTrue(calls)
            with brand_installation_lock(self.root, exclusive=True):
                pass

    def test_social_adapters_release_lock_on_failed_worker(self):
        with patch.object(MaigretUsernameSource, "_preview_locked", side_effect=SourceError("failure")):
            with self.assertRaises(SourceError):
                MaigretUsernameSource(project_dir=self.root).preview("samplebrand", platforms=("GitHub",), request_timeout=5)
        with brand_installation_lock(self.root, exclusive=True):
            pass

    def test_verifier_rejects_wrong_fd_and_keeps_owned_exclusive_lock(self):
        with patch.object(VERIFIER, "PROJECT", self.root):
            other = self.root / "other"
            other.write_text("untouched")
            with other.open() as stream:
                with self.assertRaises(VERIFIER.VerificationError):
                    VERIFIER._validate_installation_lock(stream.fileno())
            for invalid in (-1, 10**100, True):
                with self.assertRaises(VERIFIER.VerificationError):
                    VERIFIER._validate_installation_lock(invalid)
            with brand_installation_lock(self.root, exclusive=True) as descriptor:
                VERIFIER._validate_installation_lock(descriptor)
                with self.assertRaises(ToolInstallationError):
                    with brand_installation_lock(self.root, exclusive=False):
                        pass
            self.assertEqual(other.read_text(), "untouched")

    def test_verifier_passes_install_lock_to_its_child_without_unlocking(self):
        prefix = self.root / ".venv"
        executable = prefix / "bin/maigret"
        executable.parent.mkdir(parents=True)
        executable.write_text("fixture")
        executable.chmod(0o700)
        with patch.object(VERIFIER, "PROJECT", self.root), \
             patch.object(VERIFIER.sys, "prefix", str(prefix)), \
             patch.object(VERIFIER, "_verify_constraints"), \
             patch.object(VERIFIER, "_verify_distribution"), \
             patch.object(VERIFIER, "files", return_value=self.root), \
             patch.object(VERIFIER, "write_maigret_database"), \
             patch.object(VERIFIER, "write_sherlock_database"):
            with brand_installation_lock(self.root, exclusive=True) as descriptor:
                def child(command, *, pass_fds, **kwargs):
                    self.assertEqual(pass_fds, (descriptor,))
                    self.assert_exclusive_denied()
                    return subprocess.CompletedProcess(command, 0, "maigret 0.6.6\n", "")
                with patch.object(VERIFIER.subprocess, "run", side_effect=child) as run:
                    VERIFIER.verify(prefix, installation_lock_fd=descriptor)
                run.assert_called_once()
                self.assert_exclusive_denied()

    def test_standalone_verifier_refuses_pending_install_before_verification(self):
        (self.root / BRAND_JOURNAL_NAME).write_text("pending")
        with patch.object(VERIFIER, "PROJECT", self.root), \
             patch.object(VERIFIER, "_verify_locked") as verify, redirect_stderr(StringIO()):
            self.assertEqual(VERIFIER.main(["--prefix", str(self.root / ".venv")]), 1)
        verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()

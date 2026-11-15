"""Harvester install/use exclusion, inherited locks and read-only readiness."""

from contextlib import ExitStack
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from tests.test_theharvester_archive import payload, report
from xti.adapters.source_readiness import LocalSourceInstallationInspector
from xti.adapters.theharvester_archive import (
    REVIEWED_UPSTREAM_COMMIT, TheHarvesterArchiveSource, parse_theharvester_jsonl,
)
from xti.adapters.tool_installation import (
    JOURNAL_NAME, LOCK_NAME, ToolInstallationError, pending_installation,
    tool_installation_lock,
)
from xti.ports.discovery import SourceError


# A startup deadline for loaded CI hosts, not a lock latency requirement.
PROCESS_TIMEOUT_SECONDS = 30
_HOLDER = """
from pathlib import Path
import sys
from xti.adapters.tool_installation import tool_installation_lock
with tool_installation_lock(Path(sys.argv[1]), exclusive=sys.argv[2] == 'exclusive'):
    print('locked', flush=True)
    sys.stdin.read()
"""
_INHERITED_CHILD = """
import os, select, sys
os.fstat(int(sys.argv[1]))
print('inherited', flush=True)
# The bound also prevents an orphan if the test runner itself is interrupted.
if select.select([sys.stdin], [], [], 30)[0]:
    sys.stdin.read(1)
"""
_SUPERVISOR = """
from pathlib import Path
import subprocess, sys
from xti.adapters.tool_installation import tool_installation_lock
with tool_installation_lock(Path(sys.argv[1]), exclusive=True) as descriptor:
    child = subprocess.Popen(
        [sys.executable, '-c', sys.argv[2], str(descriptor)],
        stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
        pass_fds=(descriptor,),
    )
    child.wait()
"""


class ToolInstallationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.tools = self.root / ".tools"
        self.tools.mkdir()
        self.lock_path = self.tools / LOCK_NAME
        self.journal_path = self.tools / JOURNAL_NAME

    def start_process(self, script, *arguments, pass_fds=()):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        process = subprocess.Popen(
            [sys.executable, "-c", script, *(str(item) for item in arguments)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=environment, pass_fds=pass_fds,
        )

        def cleanup():
            if process.poll() is None:
                process.kill()
            # Closing stdin releases any inherited child, including after the
            # supervisor was killed. The child also has its own safety deadline.
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
                process.stdin = None
            process.communicate(timeout=PROCESS_TIMEOUT_SECONDS + 5)

        self.addCleanup(cleanup)
        return process

    def expect_ready(self, process, expected):
        ready, _, _ = select.select([process.stdout], [], [], PROCESS_TIMEOUT_SECONDS)
        self.assertTrue(ready, f"Lock fixture did not start (exit={process.poll()!r})")
        self.assertEqual(process.stdout.readline().strip(), expected)

    def assert_busy(self, *, exclusive):
        with self.assertRaises(ToolInstallationError):
            with tool_installation_lock(self.tools, exclusive=exclusive):
                self.fail("A conflicting lock entered the critical section")

    def snapshot(self):
        result = {}
        for path in (self.tools, *sorted(self.tools.rglob("*"))):
            metadata = path.lstat()
            content = (
                os.readlink(path) if stat.S_ISLNK(metadata.st_mode)
                else path.read_bytes() if stat.S_ISREG(metadata.st_mode) else None
            )
            result[str(path.relative_to(self.root))] = (
                metadata.st_ino, metadata.st_mode, metadata.st_mtime_ns, content,
            )
        return result

    def installed_source(self, runner):
        checkout = self.tools / "theharvester"
        executable = checkout / ".venv" / "bin" / "theHarvester"
        executable.parent.mkdir(parents=True)
        executable.write_text("#!/bin/sh\n", encoding="ascii")
        executable.chmod(0o700)
        executable.with_name("python").symlink_to(sys.executable)
        (checkout / ".git").mkdir()
        (checkout / ".git" / "HEAD").write_text(
            REVIEWED_UPSTREAM_COMMIT + "\n", encoding="ascii",
        )
        return TheHarvesterArchiveSource(
            runner=runner, checkout_locator=lambda: checkout,
            executable_locator=lambda: executable,
        )

    def inspect_without_execution(self):
        with ExitStack() as stack:
            for target in (
                "subprocess.run", "subprocess.Popen", "socket.create_connection",
                "socket.socket.connect",
            ):
                stack.enter_context(patch(target, side_effect=AssertionError(target)))
            return LocalSourceInstallationInspector(self.root).inspect("theharvester")

    def test_shared_processes_coexist_but_installer_waits_and_inode_persists(self):
        process = self.start_process(_HOLDER, self.tools, "shared")
        self.expect_ready(process, "locked")
        inode = self.lock_path.stat().st_ino
        with tool_installation_lock(self.tools, exclusive=False):
            self.assert_busy(exclusive=True)
        process.communicate(input="release", timeout=PROCESS_TIMEOUT_SECONDS)
        self.assertEqual(process.returncode, 0)
        with tool_installation_lock(self.tools, exclusive=True):
            self.assertEqual(self.lock_path.stat().st_ino, inode)
        self.assertEqual(self.lock_path.stat().st_ino, inode)

    def test_exclusive_process_blocks_workers_and_releases_on_process_death(self):
        process = self.start_process(_HOLDER, self.tools, "exclusive")
        self.expect_ready(process, "locked")
        inode = self.lock_path.stat().st_ino
        self.assert_busy(exclusive=False)
        self.assert_busy(exclusive=True)
        process.kill()
        process.communicate(timeout=PROCESS_TIMEOUT_SECONDS)
        with tool_installation_lock(self.tools, exclusive=True):
            self.assertEqual(self.lock_path.stat().st_ino, inode)

    def test_inherited_child_retains_lock_after_context_closes(self):
        with tool_installation_lock(self.tools, exclusive=True) as descriptor:
            process = self.start_process(
                _INHERITED_CHILD, descriptor, pass_fds=(descriptor,),
            )
            self.expect_ready(process, "inherited")
        self.assert_busy(exclusive=True)
        process.communicate(input="release", timeout=PROCESS_TIMEOUT_SECONDS)
        self.assertEqual(process.returncode, 0)
        with tool_installation_lock(self.tools, exclusive=True):
            pass

    def test_inherited_child_retains_lock_after_supervisor_is_killed(self):
        process = self.start_process(_SUPERVISOR, self.tools, _INHERITED_CHILD)
        self.expect_ready(process, "inherited")
        inode = self.lock_path.stat().st_ino
        process.kill()
        process.wait(timeout=PROCESS_TIMEOUT_SECONDS)
        self.assert_busy(exclusive=False)
        self.assert_busy(exclusive=True)
        # The supervisor is dead; its inherited pipe still reaches the child.
        process.communicate(input="release", timeout=PROCESS_TIMEOUT_SECONDS)
        with tool_installation_lock(self.tools, exclusive=True):
            self.assertEqual(self.lock_path.stat().st_ino, inode)

    def test_readonly_missing_lock_creates_nothing(self):
        before = self.snapshot()
        with tool_installation_lock(self.tools, exclusive=False, create=False) as descriptor:
            self.assertIsNone(descriptor)
        self.assertEqual(self.snapshot(), before)
        missing = self.root / "missing"
        with self.assertRaises(ToolInstallationError):
            with tool_installation_lock(missing, exclusive=False, create=False):
                pass
        self.assertFalse(missing.exists())

    def test_existing_lock_content_mode_and_inode_are_preserved(self):
        self.lock_path.write_bytes(b"existing lock metadata")
        self.lock_path.chmod(0o640)
        before = self.snapshot()
        for create in (False, True):
            with tool_installation_lock(self.tools, exclusive=False, create=create) as descriptor:
                self.assertIsInstance(descriptor, int)
        self.assertEqual(self.snapshot(), before)

    def test_body_oserror_is_not_relabelled_and_new_lock_is_private(self):
        failure = OSError("worker report unavailable")
        with self.assertRaises(OSError) as caught:
            with tool_installation_lock(self.tools, exclusive=True):
                self.assertEqual(stat.S_IMODE(self.lock_path.stat().st_mode), 0o600)
                raise failure
        self.assertIs(caught.exception, failure)
        with tool_installation_lock(self.tools, exclusive=True):
            pass

    def test_symlink_hardlink_fifo_and_directory_locks_are_refused(self):
        target = self.root / "keep"
        target.write_bytes(b"unrelated contents")
        target_before = target.stat()
        for kind in ("symlink", "dangling", "hardlink", "fifo", "directory"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    self.lock_path.symlink_to(target)
                elif kind == "dangling":
                    self.lock_path.symlink_to(self.root / "absent")
                elif kind == "hardlink":
                    os.link(target, self.lock_path)
                elif kind == "fifo":
                    os.mkfifo(self.lock_path)
                else:
                    self.lock_path.mkdir()
                before = self.snapshot()
                for create in (False, True):
                    with self.assertRaises(ToolInstallationError):
                        with tool_installation_lock(self.tools, exclusive=False, create=create):
                            pass
                self.assertEqual(self.snapshot(), before)
                if kind == "directory":
                    self.lock_path.rmdir()
                else:
                    self.lock_path.unlink()
        self.assertEqual(target.read_bytes(), b"unrelated contents")
        self.assertEqual(target.stat().st_ino, target_before.st_ino)
        self.assertEqual(target.stat().st_mtime_ns, target_before.st_mtime_ns)
        self.assertFalse((self.root / "absent").exists())

    def test_symlink_parent_is_refused_without_creating_a_lock(self):
        alias = self.root / "alias"
        alias.symlink_to(self.tools, target_is_directory=True)
        with self.assertRaises(ToolInstallationError):
            with tool_installation_lock(alias, exclusive=True):
                pass
        self.assertFalse(self.lock_path.exists())

    def test_pending_journal_including_dangling_link_blocks_runner(self):
        runner = Mock(side_effect=AssertionError("Pending install was executed"))
        source = self.installed_source(runner)
        self.assertFalse(pending_installation(self.tools))
        for kind in ("malformed", "dangling"):
            with self.subTest(kind=kind):
                if kind == "malformed":
                    self.journal_path.write_bytes(b"incomplete journal")
                else:
                    self.journal_path.symlink_to(self.root / "missing-journal")
                self.assertTrue(pending_installation(self.tools))
                with self.assertRaisesRegex(SourceError, "tamamlanmamış"):
                    source.search("%.example.com")
                runner.assert_not_called()
                self.journal_path.unlink()
        with tool_installation_lock(self.tools, exclusive=True):
            pass

    def test_runtime_holds_shared_lock_through_worker_and_report_parsing(self):
        stages = []

        def runner(command, **kwargs):
            stages.append("worker")
            descriptors = kwargs["pass_fds"]
            self.assertEqual(len(descriptors), 1)
            self.assertEqual(os.fstat(descriptors[0]).st_ino, self.lock_path.stat().st_ino)
            self.assert_busy(exclusive=True)
            with tool_installation_lock(self.tools, exclusive=False):
                pass
            Path(command[command.index("--report") + 1]).write_bytes(payload(report()))
            return subprocess.CompletedProcess(command, 0, "", "")

        def parse(*args, **kwargs):
            stages.append("parse")
            self.assert_busy(exclusive=True)
            return parse_theharvester_jsonl(*args, **kwargs)

        source = self.installed_source(runner)
        with patch("xti.adapters.theharvester_archive.parse_theharvester_jsonl", side_effect=parse):
            self.assertEqual(source.search("%.example.com").record_count, 2)
        self.assertEqual(stages, ["worker", "parse"])
        with tool_installation_lock(self.tools, exclusive=True):
            pass

    def test_runtime_busy_install_never_executes_worker(self):
        runner = Mock(side_effect=AssertionError("Worker ran during install"))
        source = self.installed_source(runner)
        with tool_installation_lock(self.tools, exclusive=True):
            with self.assertRaisesRegex(SourceError, "sürüyor"):
                source.search("%.example.com")
        runner.assert_not_called()

    def test_runtime_worker_failure_releases_shared_lock(self):
        source = self.installed_source(Mock(side_effect=OSError("missing worker")))
        with self.assertRaisesRegex(SourceError, "çalıştırılamadı"):
            source.search("%.example.com")
        with tool_installation_lock(self.tools, exclusive=True):
            pass

    def test_readiness_ready_does_not_create_lock_or_execute_code(self):
        self.installed_source(Mock())
        before = self.snapshot()
        self.assertEqual(self.inspect_without_execution(), ("ready", None))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.lock_path.exists())

    def test_readiness_busy_is_invalid_and_leaves_installation_untouched(self):
        self.installed_source(Mock())
        with tool_installation_lock(self.tools, exclusive=True):
            before = self.snapshot()
            status, reason = self.inspect_without_execution()
            self.assertEqual(status, "invalid")
            self.assertIn("sürüyor", reason)
            self.assertEqual(self.snapshot(), before)

    def test_readiness_pending_is_invalid_even_when_checkout_is_absent(self):
        self.journal_path.write_bytes(b"interrupted install")
        for installed in (False, True):
            with self.subTest(installed=installed):
                if installed:
                    self.installed_source(Mock())
                before = self.snapshot()
                status, reason = self.inspect_without_execution()
                self.assertEqual(status, "invalid")
                self.assertIn("--recover", reason)
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(self.lock_path.exists())


if __name__ == "__main__":
    unittest.main()

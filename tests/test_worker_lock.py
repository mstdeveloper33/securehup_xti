"""Real process exclusion and recovery for the local execution lock."""

import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from xti.adapters.sqlite import StorageError
from xti.adapters.worker_lock import LocalExecutionLock
from xti.ports.jobs import WorkerBusyError


# Interpreter/import startup can be delayed on a loaded host. This is a
# harness deadline, not a latency requirement for the nonblocking lock.
PROCESS_TIMEOUT_SECONDS = 30


_HOLD_LOCK = """
from pathlib import Path
import sys
from xti.adapters.worker_lock import LocalExecutionLock
with LocalExecutionLock(Path(sys.argv[1])).acquire():
    print('locked', flush=True)
    sys.stdin.read()
"""


class WorkerLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "xti.db"
        self.path = self.root / "xti.db.worker.lock"

    def start_holder(self):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        child = subprocess.Popen(
            [sys.executable, "-c", _HOLD_LOCK, str(self.database)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=environment,
        )
        def cleanup():
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=PROCESS_TIMEOUT_SECONDS)
        self.addCleanup(cleanup)
        # select keeps a broken worker implementation from hanging the test.
        import select
        ready, _, _ = select.select([child.stdout], [], [], PROCESS_TIMEOUT_SECONDS)
        self.assertTrue(
            ready,
            f"Worker did not signal readiness within {PROCESS_TIMEOUT_SECONDS}s "
            f"(exit status: {child.poll()!r})",
        )
        self.assertEqual(child.stdout.readline().strip(), "locked")
        return child

    def test_another_process_is_excluded_then_can_run_after_release(self):
        child = self.start_holder()
        inode = self.path.stat().st_ino
        with self.assertRaises(WorkerBusyError):
            with LocalExecutionLock(self.database).acquire():
                self.fail("A second worker entered the critical section")
        child.communicate(input="release", timeout=PROCESS_TIMEOUT_SECONDS)
        self.assertEqual(child.returncode, 0)
        with LocalExecutionLock(self.database).acquire():
            self.assertEqual(self.path.stat().st_ino, inode)
        self.assertEqual(self.path.stat().st_ino, inode)

    def test_process_death_releases_lock_without_deleting_its_inode(self):
        child = self.start_holder()
        inode = self.path.stat().st_ino
        child.kill()
        child.communicate(timeout=PROCESS_TIMEOUT_SECONDS)
        self.assertNotEqual(child.returncode, 0)
        with LocalExecutionLock(self.database).acquire():
            self.assertEqual(self.path.stat().st_ino, inode)
        self.assertTrue(self.path.is_file())

    def test_directory_alias_uses_the_same_lock(self):
        real = self.root / "real"
        real.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with LocalExecutionLock(real / "xti.db").acquire():
            with self.assertRaises(WorkerBusyError):
                with LocalExecutionLock(alias / "xti.db").acquire():
                    self.fail("Directory aliases bypassed execution lock")

    def test_existing_file_contents_permissions_and_inode_are_preserved(self):
        self.path.write_bytes(b"existing lock metadata")
        self.path.chmod(0o640)
        before = self.path.stat()
        for _ in range(2):
            with LocalExecutionLock(self.database).acquire():
                pass
        after = self.path.stat()
        self.assertEqual(after.st_ino, before.st_ino)
        self.assertEqual(stat.S_IMODE(after.st_mode), 0o640)
        self.assertEqual(self.path.read_bytes(), b"existing lock metadata")
        self.assertFalse(self.database.exists())

    def test_new_file_has_private_permissions_and_exception_releases_lock(self):
        with self.assertRaisesRegex(RuntimeError, "work failed"):
            with LocalExecutionLock(self.database).acquire():
                self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
                raise RuntimeError("work failed")
        with LocalExecutionLock(self.database).acquire():
            pass

    def test_symlink_lock_is_rejected_without_touching_target(self):
        target = self.root / "unrelated"
        target.write_bytes(b"keep me")
        self.path.symlink_to(target)
        before = target.stat()
        with self.assertRaises(StorageError):
            with LocalExecutionLock(self.database).acquire():
                self.fail("Followed a symbolic lock")
        self.assertEqual(target.read_bytes(), b"keep me")
        self.assertEqual(target.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertTrue(self.path.is_symlink())

    def test_fifo_and_directory_locks_are_rejected_without_blocking(self):
        self.path.mkdir()
        with self.assertRaises(StorageError):
            with LocalExecutionLock(self.database).acquire():
                pass
        self.path.rmdir()
        os.mkfifo(self.path)
        with self.assertRaises(StorageError):
            with LocalExecutionLock(self.database).acquire():
                pass
        self.assertTrue(stat.S_ISFIFO(self.path.stat().st_mode))

    def test_missing_parent_does_not_create_directories(self):
        missing = self.root / "absent"
        with self.assertRaises(StorageError):
            with LocalExecutionLock(missing / "xti.db").acquire():
                pass
        self.assertFalse(missing.exists())

    def test_symlink_database_is_rejected(self):
        target = self.root / "other.db"
        target.write_bytes(b"keep database")
        self.database.symlink_to(target)
        with self.assertRaises(StorageError):
            with LocalExecutionLock(self.database).acquire():
                pass
        self.assertEqual(target.read_bytes(), b"keep database")
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()

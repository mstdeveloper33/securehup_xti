import fcntl
import importlib.util
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]


def acceptance():
    spec = importlib.util.spec_from_file_location("linux_upgrade_acceptance", PROJECT / "scripts/check-linux-upgrade.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def proc_entry(root, pid, *, parent=1, group=None, start=100, state="S", arguments=("python",)):
    directory = root / str(pid)
    directory.mkdir(exist_ok=True)
    fields = [state, str(parent), str(group or pid)] + ["0"] * 16 + [str(start)]
    (directory / "stat").write_text(f"{pid} (tool ) name) " + " ".join(fields), encoding="ascii")
    (directory / "cmdline").write_bytes(b"\0".join(os.fsencode(value) for value in arguments) + b"\0")


class LinuxUpgradeAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.helper = acceptance()

    def test_wrong_host_refuses_before_creating_or_cloning_anything(self):
        with patch.object(self.helper.sys, "platform", "darwin"), \
                patch.object(self.helper, "disposable_clone") as clone, \
                patch.object(self.helper.COMMON, "summary"):
            self.assertEqual(self.helper.main(["--tool", "brand"]), 1)
            clone.assert_not_called()

    def test_process_identity_handles_parenthesized_names_and_rejects_invalid_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proc_entry(root, 123, parent=100, group=123, start=987,
                       arguments=("/path with spaces/python", "-m", "pip"))
            result = self.helper.process_identity(123, root)
            self.assertEqual((result.pid, result.parent, result.group, result.start), (123, 100, 123, 987))
            self.assertEqual(result.arguments[0], "/path with spaces/python")
            (root / "123/stat").write_text("123 broken")
            self.assertIsNone(self.helper.process_identity(123, root))
            self.assertIsNone(self.helper.process_identity(124, root))

    def test_descendant_tracking_survives_owner_death_but_rejects_pid_reuse(self):
        identity = self.helper.ProcessIdentity
        owner = identity(100, 1, 100, 50, "S", ("installer",))
        child = identity(200, 100, 200, 60, "S", ("pip",))
        grandchild = identity(201, 200, 200, 61, "S", ("git",))
        unrelated = identity(300, 1, 300, 70, "S", ("other",))
        current = {item.pid: item for item in (owner, child, grandchild, unrelated)}
        selected = self.helper.owned_processes(owner, table=current)
        self.assertEqual({item.pid for item in selected}, {100, 200, 201})
        # The recorded child remains ours after adoption by init.
        adopted = child._replace(parent=1)
        selected = self.helper.owned_processes(owner, selected, {200: adopted, 201: grandchild, 300: unrelated})
        self.assertEqual({item.pid for item in selected}, {200, 201})
        reused = adopted._replace(start=999)
        self.assertEqual(self.helper.owned_processes(owner, (child,), {200: reused}), ())

    def test_package_match_requires_real_canonical_command_and_direct_owned_session(self):
        identity = self.helper.ProcessIdentity
        owner = identity(100, 1, 100, 50, "S", ())
        canonical = Path("/tmp/disposable checkout/.venv")
        pip = identity(200, 100, 200, 60, "S", (str(canonical / "bin/python"), "-m", "pip", "--isolated", "install", "project[brand]"))
        self.assertTrue(self.helper.installer_child(pip, owner, canonical, "brand"))
        for changed in (pip._replace(parent=999), pip._replace(group=100), pip._replace(state="Z"),
                        pip._replace(arguments=("/other/python", "-m", "pip", "install")),
                        pip._replace(arguments=(str(canonical / "bin/python"), "-m", "pip", "check"))):
            self.assertFalse(self.helper.installer_child(changed, owner, canonical, "brand"))
        harvester = Path("/tmp/disposable checkout/.tools/theharvester")
        uv = pip._replace(arguments=("/tools/uv", "sync", "--frozen", "--no-dev", "--no-editable", "--project", str(harvester)))
        self.assertTrue(self.helper.installer_child(uv, owner, harvester, "harvester"))
        self.assertFalse(self.helper.installer_child(uv._replace(arguments=uv.arguments[:-1] + ("/other",)), owner, harvester, "harvester"))

    def test_signals_require_matching_identity_and_never_target_our_group(self):
        identity = self.helper.ProcessIdentity(200, 100, 200, 60, "S", ("pip",))
        with patch.object(self.helper, "process_identity", return_value=identity._replace(start=999)), \
                patch.object(self.helper.os, "killpg") as kill:
            self.helper.signal_owned_groups((identity,), signal.SIGKILL)
            kill.assert_not_called()
        ours = identity._replace(group=os.getpgrp())
        with patch.object(self.helper, "process_identity", return_value=ours), \
                patch.object(self.helper.os, "killpg") as kill:
            with self.assertRaisesRegex(RuntimeError, "acceptance process group"):
                self.helper.signal_owned_groups((ours,), signal.SIGKILL)
            kill.assert_not_called()

    def test_disposable_clone_rejects_existing_destination_before_git_runs(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(self.helper, "command") as command:
            root = Path(temporary)
            marker = root / "user-data"
            marker.write_bytes(b"preserved")
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                self.helper.disposable_clone(PROJECT, root, {})
            command.assert_not_called()
            self.assertEqual(marker.read_bytes(), b"preserved")
        for value in ("main", "--upload-pack=bad", "a" * 39, "A" * 40, "a" * 40 + "\n"):
            with self.assertRaises(RuntimeError):
                self.helper.checked_commit(value)
        self.assertEqual(self.helper.checked_commit("a" * 40), "a" * 40)

    def test_acceptance_environment_does_not_forward_secrets_or_user_config(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
                "GH_TOKEN": "test-secret", "PIP_INDEX_URL": "secret", "PYTHONPATH": "/untrusted",
                "UV_PROJECT": "/user-project", "XTI_DATA_DIR": "/user-data"}):
            root = Path(temporary)
            environment = self.helper.acceptance_environment(root)
            for key in ("GH_TOKEN", "PIP_INDEX_URL", "PYTHONPATH", "UV_PROJECT"):
                self.assertNotIn(key, environment)
            self.assertEqual(environment["XTI_DATA_DIR"], str(root / "data"))
            self.assertEqual(environment["HOME"], str(root / "home"))

    def test_lock_probe_does_not_unlock_another_open_description(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lock"
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertTrue(self.helper.lock_held(path))
                self.assertTrue(self.helper.lock_held(path))
            finally:
                os.close(descriptor)
            self.assertFalse(self.helper.lock_held(path))

    def test_unconfirmed_cleanup_retains_only_its_disposable_directory(self):
        retained = None
        try:
            with patch.object(self.helper.COMMON, "summary"):
                with self.assertRaises(self.helper.UnconfirmedCleanup):
                    with self.helper.disposable_workspace() as root:
                        retained = root
                        (root / "evidence").write_bytes(b"retained")
                        raise self.helper.UnconfirmedCleanup("writer still alive")
                self.assertEqual((retained / "evidence").read_bytes(), b"retained")
                with self.assertRaisesRegex(RuntimeError, "ordinary"):
                    with self.helper.disposable_workspace() as safe:
                        raise RuntimeError("ordinary checked failure")
                self.assertFalse(safe.exists())
        finally:
            if retained is not None:
                shutil.rmtree(retained)

    @unittest.skipUnless(sys.platform == "linux", "Requires real Linux /proc process ownership.")
    def test_command_captures_failure_and_times_out_owned_process(self):
        environment = dict(os.environ)
        text = self.helper.command([sys.executable, "-c", "print('ok')"], environment, cwd=PROJECT)
        self.assertEqual(text, "ok")
        self.assertEqual(self.helper.command([sys.executable, "-c", "print('expected'); raise SystemExit(2)"], environment,
                                            cwd=PROJECT, expected=None), "expected")
        with self.assertRaises(subprocess.TimeoutExpired):
            self.helper.command([sys.executable, "-c", "import time; time.sleep(60)"], environment, cwd=PROJECT, timeout=0.15)

    @unittest.skipUnless(sys.platform == "linux", "Requires real Linux /proc process ownership.")
    def test_timeout_stops_descendant_in_its_own_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "child.pid"
            code = (
                "import subprocess, sys, time; from pathlib import Path; "
                "child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True); "
                "Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(60)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                self.helper.command([sys.executable, "-c", code, str(marker)], dict(os.environ), cwd=PROJECT, timeout=0.75)
            self.assertTrue(marker.is_file())
            child = self.helper.process_identity(int(marker.read_text()))
            self.assertTrue(child is None or child.state == "Z")


if __name__ == "__main__":
    unittest.main()

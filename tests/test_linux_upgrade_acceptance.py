from contextlib import closing
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import signal
import shutil
import sqlite3
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

    def test_database_manifest_preserves_rowids_and_schema_and_never_creates_missing_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "xti.db"
            with self.assertRaisesRegex(RuntimeError, "missing"):
                self.helper.database_manifest(database)
            self.assertFalse(database.exists())
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute('CREATE TABLE "odd""name" (value TEXT)')
                connection.execute('INSERT INTO "odd""name" (rowid,value) VALUES (99,?)', ("preserved",))
                connection.execute("PRAGMA user_version=64")
            before = self.helper.database_manifest(database)
            self.assertEqual(before[0], 64)
            self.assertEqual(before[1]['odd"name'][1], [(99, "preserved")])
            self.helper.require_preserved_tables(before, before)
            with closing(sqlite3.connect(database)) as connection, connection:
                connection.execute('UPDATE "odd""name" SET value=?', ("changed",))
            after = self.helper.database_manifest(database)
            with self.assertRaisesRegex(RuntimeError, "pre-existing table"):
                self.helper.require_preserved_tables(before, after)
            linked = database.with_name("linked.db")
            linked.symlink_to(database)
            with self.assertRaisesRegex(RuntimeError, "linked"):
                self.helper.database_manifest(linked)

    def test_actual_cli_explicit_schema_upgrade_preserves_old_backup_and_evidence(self):
        from xti.adapters.sqlite import SQLiteAssetRepository
        from tests.global_saved_search_legacy_fixture import remove_global_saved_search_schema

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            environment = self.helper.acceptance_environment(root)
            data = Path(environment["XTI_DATA_DIR"])
            database = data / "xti.db"
            storage = SQLiteAssetRepository(database)
            storage.initialize()
            storage.add("example.com")
            with closing(sqlite3.connect(database)) as connection, connection:
                remove_global_saved_search_schema(connection)
                connection.execute("PRAGMA user_version=64")
            # CLI mutators use this existing ownership lock; include it in the manifest.
            (data / "xti.db.worker.lock").touch(mode=0o600)
            (data / "upgrade-evidence.bin").write_bytes(b"preserved external evidence")
            before_files = self.helper.COMMON.snapshot(data)
            before_database = self.helper.database_manifest(database)

            def portable_command(arguments, environment, *, expected=0, **kwargs):
                # Real CLI/SQLite migration, without Linux-only /proc process supervision.
                result = subprocess.run([str(value) for value in arguments], cwd=PROJECT,
                    env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=30)
                self.assertEqual(result.returncode, expected if expected is not None else 1,
                                 result.stdout + result.stderr)
                return (result.stdout + result.stderr).strip()

            with patch.object(self.helper, "command", side_effect=portable_command), \
                    patch.object(self.helper.COMMON, "summary"):
                backup, after_files = self.helper.migrate_acceptance_data(
                    environment, before_files, before_database,
                )
            self.assertEqual(self.helper.database_manifest(backup), before_database)
            self.assertEqual(self.helper.database_manifest(database)[0], 66)
            self.assertEqual(self.helper.COMMON.snapshot(data), after_files)
            self.assertEqual((data / "upgrade-evidence.bin").read_bytes(), b"preserved external evidence")

    def test_news_environment_upgrade_requires_one_exact_preserved_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            canonical = project / ".venv"
            canonical.mkdir()
            (canonical / "retained").write_bytes(b"old environment")
            original = self.helper.BRAND.environment_snapshot(canonical)
            existing = project / ".venv-backup-earlier"
            existing.mkdir()
            previous = {existing}
            with self.assertRaisesRegex(RuntimeError, "one unique"):
                self.helper.require_preserved_brand_backup(project, original, previous)
            retained = project / ".venv-backup-upgrade"
            canonical.rename(retained)
            canonical.mkdir()
            (canonical / "news-reader").write_bytes(b"new environment")
            self.assertEqual(self.helper.require_preserved_brand_backup(project, original, previous), retained)
            (retained / "retained").write_bytes(b"changed old environment")
            with self.assertRaisesRegex(RuntimeError, "retained previous"):
                self.helper.require_preserved_brand_backup(project, original, previous)
            (retained / "retained").write_bytes(b"old environment")
            (project / ".venv-backup-unexpected").mkdir()
            with self.assertRaisesRegex(RuntimeError, "one unique"):
                self.helper.require_preserved_brand_backup(project, original, previous)

    def test_unsupported_migration_target_stops_before_running_cli(self):
        with patch.object(self.helper, "command") as command:
            with self.assertRaisesRegex(RuntimeError, "Unsupported migration target"):
                self.helper.migrate_acceptance_data({}, {}, (64, {}), target_schema=67)
        command.assert_not_called()

    def test_schema_rollback_does_not_accept_an_unrelated_old_code_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "data"
            data.mkdir()
            (data / "xti.db").write_bytes(b"retained new-schema data")
            before = self.helper.COMMON.snapshot(data)
            with patch.object(self.helper, "command", return_value="An unrelated failure") as command:
                with self.assertRaisesRegex(RuntimeError, "unsupported new schema"):
                    self.helper.restore_baseline_data(
                        {"XTI_DATA_DIR": str(data)}, Path(temporary) / "backup.db", (64, {}), before,
                    )
            self.assertEqual(command.call_count, 1)
            self.assertEqual(self.helper.COMMON.snapshot(data), before)
            self.assertFalse((Path(temporary) / "rollback-restored").exists())

    def test_schema_rejection_decodes_pinned_baseline_unicode_json_error(self):
        # 9cdf32c report_error emits ensure_ascii=True, including the Turkish diagnosis.
        payload = {"ok": False, "error": {
            "code": "storage_error",
            "message": "Veritabanı sürümü bu uygulamayla uyumlu değil. "
                       "Dosya değiştirilmedi; uygun uygulama sürümünü kullanın.",
        }}
        escaped = json.dumps(payload, ensure_ascii=True)
        self.assertNotIn("uyumlu değil", escaped)
        self.helper.require_unsupported_schema_error(escaped)
        self.helper.require_unsupported_schema_error(json.dumps(payload, ensure_ascii=False))

    def test_schema_rejection_requires_failed_storage_error_and_exact_diagnosis(self):
        message = "Veritabanı sürümü bu uygulamayla uyumlu değil. " \
                  "Dosya değiştirilmedi; uygun uygulama sürümünü kullanın."
        for output in (
            "not JSON",
            "[]",
            "null",
            json.dumps({"ok": True, "error": {"code": "storage_error", "message": message}}),
            json.dumps({"ok": 0, "error": {"code": "storage_error", "message": message}}),
            json.dumps({"ok": False, "error": {"code": "filesystem_error", "message": message}}),
            json.dumps({"ok": False, "error": {"code": "storage_error", "message": "Other failure"}}),
            json.dumps({"ok": False, "error": {"code": "storage_error", "message": message + " Other failure"}}),
            json.dumps({"ok": False, "error": "storage_error"}),
        ):
            with self.subTest(output=output):
                with self.assertRaisesRegex(RuntimeError, "unsupported new schema"):
                    self.helper.require_unsupported_schema_error(output)

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

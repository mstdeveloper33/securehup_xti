"""File-only scheduling, explicit command boundaries and locked maintenance."""

import argparse
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.adapters.systemd_schedule import SystemdScheduleWriter, unit_argument
from xti.adapters.scheduled_backups import ScheduledBackupMaintenance
from xti.application.scheduling import SchedulingService
from xti.domain.assets import ValidationError
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.collection_history import CollectionFrozenPlan, CollectionFrozenUnit
from xti.domain.scheduling import ScheduleSpec, normalize_schedule
from xti.interfaces.scheduling import register_schedule_commands
from xti.ports.discovery import SourceError
from xti.ports.jobs import WorkerBusyError

NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


class SchedulingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project %i $HOME "quoted"'
        self.root.mkdir()
        self.launcher = self.root / "xti"
        self.launcher.write_text("#!/bin/sh\nexit 0\n"); self.launcher.chmod(0o700)
        self.database = self.root / 'data %n $USER "space"' / 'xti.db'
        self.storage = SQLiteAssetRepository(self.database); self.storage.initialize(); self.storage.add("example.com")
        self.profiles = SQLiteCollectionProfileRepository(self.database)
        self.definition = CollectionProfileDefinition("example.com", task_ids=("ioc-feodo",))
        self.profile = self.profiles.save('-Profile %n $HOME "name"', self.definition, recorded_at=NOW.isoformat()).profile
        self.history = SQLiteCollectionHistoryRepository(self.database)
        self.writer = SystemdScheduleWriter(self.launcher, self.database)
        self.backups = ScheduledBackupMaintenance(self.database)
        self.runner = Mock()
        self.factory = Mock(return_value=self.runner)
        self.lock = LocalExecutionLock(self.database)
        self.service = SchedulingService(self.profiles, self.factory, self.history, self.lock, self.writer, self.backups, clock=lambda: NOW)

    def generate(self, **options):
        return self.service.generate(self.profile.display_name, output=str(self.root / "units"), at="07:30", **options)

    def test_generation_is_network_free_and_database_readonly_with_distinct_profile_units(self):
        before = self.database.read_bytes()
        with patch("socket.socket.connect", side_effect=AssertionError("network")), patch("subprocess.run", side_effect=AssertionError("activation")):
            result = self.generate()
        self.assertEqual(self.database.read_bytes(), before)
        self.assertFalse(self.database.with_suffix(".db.worker.lock").exists())
        self.assertFalse(self.backups.directory.exists())
        self.runner.run.assert_not_called()
        self.assertEqual(result.unit_name, f"xti-collect-{self.profile.id}")
        other = self.profiles.save("Another profile", self.definition, recorded_at=NOW.isoformat()).profile
        second = self.service.generate(other.display_name, output=str(self.root / "other-units"), at="07:30")
        self.assertNotEqual(second.unit_name, result.unit_name)

    def test_unit_arguments_keep_literals_and_no_shell_or_success_remapping(self):
        result = self.generate(weekday="Mon", timezone="Europe/Istanbul", keep=3)
        service = Path(result.service_file).read_text(); timer = Path(result.timer_file).read_text()
        self.assertIn('%%n', service); self.assertIn('$HOME', service); self.assertIn('\\"name\\"', service)
        self.assertNotIn('$$HOME', service)
        self.assertIn('ExecStart=":/bin/sh" ', service); self.assertIn('ExecStartPre=":/bin/sh" ', service)
        self.assertIn('"--profile=-Profile %%n $HOME \\"name\\""', service)
        self.assertIn('"--keep" "3" "--" "-Profile', service)
        self.assertNotIn("WorkingDirectory=", service)
        self.assertIn("Type=oneshot\n", service); self.assertIn("Restart=no\n", service)
        self.assertNotIn("RemainAfterExit", service); self.assertNotIn("SuccessExitStatus", service)
        self.assertNotIn("/bin/sh -c", service)
        self.assertIn("OnCalendar=Mon *-*-* 07:30:00 Europe/Istanbul", timer)
        self.assertIn("Persistent=true", timer); self.assertIn("FixedRandomDelay=true", timer)
        instructions = Path(result.instructions_file).read_text()
        self.assertIn("systemctl --user link", instructions)
        self.assertIn(f"systemctl --user enable --now {result.unit_name}.timer", instructions)
        self.assertIn(f"systemctl --user disable {result.unit_name}.service", instructions)
        self.assertIn("profiles save yeterlidir", instructions)
        self.assertIn("Linux hizmet çalışmasını doğrulamaz", instructions)

    def test_invalid_injection_calendar_and_existing_output_never_overwrite(self):
        for spec in (ScheduleSpec("24:00"), ScheduleSpec("1:30"), ScheduleSpec("01:00", "UTC\nExecStart=bad"),
                     ScheduleSpec("01:00", weekday="Mon\n"), ScheduleSpec("01:00", keep=True)):
            with self.assertRaises(ValidationError): normalize_schedule(spec)
        for value in ("x\nExecStart=bad", "x\0", "x\x1b[31m"):
            with self.assertRaises(ValidationError): unit_argument(value)
        with self.assertRaises(ValidationError): self.generate(timezone="Missing/Timezone")
        self.assertFalse((self.root / "units").exists())
        result = self.generate(); before = {path.name: path.read_bytes() for path in Path(result.directory).iterdir()}
        with self.assertRaises(ValidationError): self.generate()
        self.assertEqual({path.name: path.read_bytes() for path in Path(result.directory).iterdir()}, before)
        link = self.root / "unit-link"; link.symlink_to(self.root / "units")
        with self.assertRaises(ValidationError):
            self.service.generate(self.profile.display_name, output=str(link), at="07:30")

    def test_profile_invalid_source_plan_busy_and_disk_low_fail_before_backup_or_recovery(self):
        with patch.object(self.history, "recover_interrupted", wraps=self.history.recover_interrupted) as recover, patch.object(self.backups, "backup_and_prune", wraps=self.backups.backup_and_prune) as backup:
            with self.assertRaises(ValidationError): self.service.prepare("Missing profile")
            self.runner.plan.side_effect = SourceError("Kaynak kurulumu eksik.")
            with self.assertRaises(SourceError): self.service.prepare(self.profile.display_name)
            self.runner.plan.side_effect = None
            with self.lock.acquire(), self.assertRaises(WorkerBusyError): self.service.prepare(self.profile.display_name)
            with patch("xti.adapters.scheduled_backups.shutil.disk_usage", return_value=Mock(free=0)), self.assertRaises(StorageError):
                self.service.prepare(self.profile.display_name)
            recover.assert_not_called(); backup.assert_not_called()
        self.assertFalse(self.backups.directory.exists())

    def test_prepare_recovers_under_shared_lock_and_backup_preserves_recovery_result(self):
        plan = CollectionFrozenPlan(self.definition, (CollectionFrozenUnit("ioc-feodo", "ioc", "feodo", "example.com", None, "feed-v1"),))
        session = self.history.begin(plan, started_at=NOW.isoformat())
        original = self.history.recover_interrupted
        def held_recovery(**options):
            with self.assertRaises(WorkerBusyError):
                with LocalExecutionLock(self.database).acquire(): pass
            return original(**options)
        with patch.object(self.history, "recover_interrupted", side_effect=held_recovery):
            report = self.service.prepare(self.profile.display_name, keep=1)
        self.assertEqual(report.recovered_sessions, (session.session.id,))
        self.assertTrue(report.backup.restore_verified)
        restored = self.root / "checked.db"
        SQLiteAssetRepository.restore(Path(report.backup.path), restored)
        self.assertEqual(SQLiteCollectionHistoryRepository(restored).get(session.session.id).session.status, "interrupted")
        self.runner.run.assert_not_called()

    def test_generated_prepare_arguments_parse_leading_hyphen_name(self):
        parser = argparse.ArgumentParser()
        register_schedule_commands(parser.add_subparsers(dest="command"))
        args = parser.parse_args(["schedule", "prepare", "--keep", "3", "--", self.profile.display_name])
        self.assertEqual((args.profile, args.keep), (self.profile.display_name, 3))

    def test_posix_launcher_keeps_literal_arguments_and_child_exit_codes(self):
        capture = self.root / "capture.py"
        self.launcher.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " " + shlex.quote(str(capture)) + ' "$@"\n')
        generated = self.generate()
        line = next(line for line in Path(generated.service_file).read_text().splitlines() if line.startswith("ExecStart="))
        # Lexical unquoting/specifier decoding only; actual Linux unit parsing is
        # covered separately when systemd-analyze is available.
        arguments = [item.replace("%%", "%") for item in shlex.split(line.split("=", 1)[1])]
        self.assertEqual(arguments[:2], [":/bin/sh", str(self.launcher.resolve())])
        self.assertNotIn("-c", arguments)
        arguments[0] = arguments[0][1:]
        for code in (3, 4):
            capture.write_text(f"import json,sys\nprint(json.dumps(sys.argv[1:]))\nraise SystemExit({code})\n")
            result = subprocess.run(arguments, capture_output=True, text=True, timeout=15, check=False)
            self.assertEqual(result.returncode, code)
            self.assertEqual(json.loads(result.stdout), ["--data-dir", str(self.database.parent.resolve()), "collect", "--profile=" + self.profile.display_name])

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("systemd-analyze"), "Linux systemd-analyze is not available; no Linux runtime claim.")
    def test_linux_systemd_parser_accepts_special_character_paths(self):
        generated = self.generate()
        checked = subprocess.run(["systemd-analyze", "verify", generated.service_file, generated.timer_file],
                                 capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()

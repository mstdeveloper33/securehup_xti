"""Budgeted group schedules preserve paths, credentials and explicit activation."""

from contextlib import closing
import json
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.systemd_mentions_schedule import SystemdMentionScheduleWriter
from xti.domain.assets import ValidationError
from xti.domain.mention_groups import MentionGroupDefinition
from xti.domain.scheduling import ScheduleSpec


class MentionScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project %n $HOME "quoted"'
        self.root.mkdir()
        self.launcher = self.root / "xti"
        self.launcher.write_text("#!/bin/sh\nexit 0\n")
        self.launcher.chmod(0o700)
        self.database = self.root / 'data %i $USER "space"' / "xti.db"
        self.database.parent.mkdir()
        # The file writer does not own schema validation; its caller supplies a
        # validated group. A real small SQLite file isolates the readonly test.
        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.execute("CREATE TABLE preserved_evidence(value TEXT)")
                connection.execute("INSERT INTO preserved_evidence VALUES ('keep')")
        self.group = SimpleNamespace(id=str(uuid4()), active=True,
            definition=MentionGroupDefinition(str(uuid4()), interval_hours=23))
        self.key = self.root / 'private %p $KEY "quoted".key'
        self.key.write_text("tvly-private-key-must-not-leak\n")
        self.key.chmod(0o600)
        self.writer = SystemdMentionScheduleWriter(self.launcher, self.database)

    def generate(self, *, output=None, spec=None, key=None):
        return self.writer.publish(self.group,
            output=str(output or self.root / "units"), spec=spec or ScheduleSpec("09:30"),
            api_key_file=self.key if key is None else key)

    def test_generation_does_not_read_key_access_network_or_modify_database(self):
        before = self.database.read_bytes()
        with patch("socket.socket.connect", side_effect=AssertionError("network")), \
                patch("subprocess.run", side_effect=AssertionError("activation")), \
                patch("xti.adapters.tavily_search.load_tavily_api_key", side_effect=AssertionError("read key")), \
                patch.dict(os.environ, {"TAVILY_API_KEY": "tvly-environment-secret"}):
            result = self.generate()
        self.assertEqual(self.database.read_bytes(), before)
        self.assertFalse(self.database.with_suffix(".db.worker.lock").exists())
        self.assertFalse((self.database.parent / "scheduled-backups").exists())
        self.assertEqual(result.unit_name, f"xti-mentions-{self.group.id}")
        for path in Path(result.directory).iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            content = path.read_text()
            self.assertNotIn("tvly-private-key-must-not-leak", content)
            self.assertNotIn("tvly-environment-secret", content)
        self.assertEqual(Path(result.directory).stat().st_mode & 0o777, 0o700)

    def test_fixed_commands_budget_owned_by_group_and_explicit_key_path(self):
        result = self.generate(spec=ScheduleSpec("08:15", "Europe/Istanbul", "Mon", 3))
        service = Path(result.service_file).read_text()
        timer = Path(result.timer_file).read_text()
        self.assertIn('ExecStart=":/bin/sh" ', service)
        self.assertIn('ExecStartPre=":/bin/sh" ', service)
        self.assertIn(f'"mentions" "groups" "run" "{self.group.id}"', service)
        self.assertIn(f'"prepare" "{self.group.id}" "--keep" "3" "--calendar-hours" "168"', service)
        self.assertIn('"--api-key-file"', service)
        self.assertIn("%%p", service)
        self.assertIn("$KEY", service)
        self.assertNotIn("$$KEY", service)
        self.assertNotIn("Environment=", service)
        self.assertNotIn("/bin/sh -c", service)
        self.assertNotIn("--force", service)
        self.assertNotIn("SuccessExitStatus=", service)
        self.assertIn("Restart=no\n", service)
        self.assertIn("OnCalendar=Mon *-*-* 08:15:00 Europe/Istanbul", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("FixedRandomDelay=true", timer)
        readme = Path(result.instructions_file).read_text()
        self.assertIn(f"systemctl --user enable --now {result.unit_name}.timer", readme)
        self.assertIn(f"systemctl --user disable {result.unit_name}.service", readme)
        self.assertIn("en az çalışma aralığı", readme)
        self.assertIn("son 3 yedek", readme)

    def test_default_key_location_is_frozen_as_path_without_reading_missing_file(self):
        key = self.root / "not-configured-yet.key"
        with patch("xti.adapters.systemd_mentions_schedule.default_tavily_key_path", return_value=key):
            result = self.writer.publish(self.group, output=self.root / "units", spec=ScheduleSpec("12:00"))
        self.assertFalse(key.exists())
        line = next(value for value in Path(result.service_file).read_text().splitlines() if value.startswith("ExecStart="))
        arguments = [value.replace("%%", "%") for value in shlex.split(line.split("=", 1)[1])]
        self.assertEqual(arguments[-2:], ["--api-key-file", str(key.absolute())])

    def test_existing_output_and_symlink_are_preserved(self):
        result = self.generate()
        before = {path.name: path.read_bytes() for path in Path(result.directory).iterdir()}
        with self.assertRaises(ValidationError):
            self.generate()
        self.assertEqual({path.name: path.read_bytes() for path in Path(result.directory).iterdir()}, before)
        alias = self.root / "alias"
        alias.symlink_to(result.directory)
        with self.assertRaises(ValidationError):
            self.generate(output=alias)

    def test_closed_group_invalid_uuid_calendar_or_path_stop_before_files(self):
        self.group.active = False
        with self.assertRaises(ValidationError):
            self.generate()
        self.group.active = True
        identifier, self.group.id = self.group.id, "bad\nExecStart=oops"
        with self.assertRaises(ValidationError):
            self.generate()
        self.group.id = identifier
        for spec in (ScheduleSpec("24:00"), ScheduleSpec("09:00", "Missing/Timezone"),
                     ScheduleSpec("09:00", weekday="Sun\n"), ScheduleSpec("09:00", keep=True)):
            with self.assertRaises(ValidationError):
                self.generate(spec=spec)
        with self.assertRaises(ValidationError):
            self.generate(key=self.root / "bad\nkey")
        with self.assertRaises(ValidationError):
            self.generate(output=self.root / "missing" / "units")
        self.assertFalse((self.root / "units").exists())

    def test_different_groups_have_distinct_units_and_changed_schedule_same_id(self):
        first = self.generate()
        changed = self.generate(output=self.root / "changed", spec=ScheduleSpec("10:00"))
        self.assertEqual(first.unit_name, changed.unit_name)
        self.assertNotEqual(first.calendar, changed.calendar)
        self.group.id = str(uuid4())
        other = self.generate(output=self.root / "other")
        self.assertNotEqual(first.unit_name, other.unit_name)

    def test_calendar_requires_shorter_group_guard_than_daily_or_weekly_period(self):
        from dataclasses import replace
        # Equality can skip the next calendar slot after a small runtime delay.
        daily = self.generate()
        self.assertIn('"--calendar-hours" "24"', Path(daily.service_file).read_text())
        for hours in (24, 25, 168):
            self.group.definition = replace(self.group.definition, interval_hours=hours)
            output = self.root / f"daily-rejected-{hours}"
            with self.assertRaisesRegex(ValidationError, "Takvim aralığından kısa"):
                self.generate(output=output)
            self.assertFalse(output.exists())
        self.group.definition = replace(self.group.definition, interval_hours=167)
        weekly = self.generate(output=self.root / "weekly", spec=ScheduleSpec("09:30", weekday="Mon"))
        self.assertEqual(weekly.calendar, "Mon *-*-* 09:30:00 UTC")
        self.assertIn('"--calendar-hours" "168"', Path(weekly.service_file).read_text())
        for hours in (168, 169):
            self.group.definition = replace(self.group.definition, interval_hours=hours)
            output = self.root / f"weekly-rejected-{hours}"
            with self.assertRaisesRegex(ValidationError, "Takvim aralığından kısa"):
                self.generate(output=output, spec=ScheduleSpec("09:30", weekday="Mon"))
            self.assertFalse(output.exists())

    def test_posix_launcher_keeps_literal_arguments_and_exit_status(self):
        capture = self.root / "capture.py"
        self.launcher.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " "
                                 + shlex.quote(str(capture)) + ' "$@"\n')
        generated = self.generate()
        line = next(value for value in Path(generated.service_file).read_text().splitlines() if value.startswith("ExecStart="))
        arguments = [value.replace("%%", "%") for value in shlex.split(line.split("=", 1)[1])]
        self.assertEqual(arguments[:2], [":/bin/sh", str(self.launcher.resolve())])
        self.assertNotIn("-c", arguments)
        arguments[0] = arguments[0][1:]
        for code in (3, 4):
            capture.write_text(f"import json,sys\nprint(json.dumps(sys.argv[1:]))\nraise SystemExit({code})\n")
            result = subprocess.run(arguments, capture_output=True, text=True, timeout=15, check=False)
            self.assertEqual(result.returncode, code)
            self.assertEqual(json.loads(result.stdout), ["--data-dir", str(self.database.parent.resolve()),
                "mentions", "groups", "run", self.group.id, "--api-key-file", str(self.key.absolute())])

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("systemd-analyze"),
                         "Linux systemd-analyze is unavailable; no Linux runtime claim.")
    def test_linux_systemd_accepts_special_character_paths(self):
        generated = self.generate()
        checked = subprocess.run(["systemd-analyze", "verify", generated.service_file, generated.timer_file],
                                 capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()

"""Real local watch commands retain complete evidence without collecting sources."""

from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.global_saved_searches import canonical_json
from xti.interfaces.cli import build_parser, main
from xti.interfaces.global_saved_searches import make_global_saved_search_service, run_lines


PROJECT = Path(__file__).resolve().parents[1]


class GlobalSavedSearchCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.database = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.database)
        self.storage.initialize()
        self.service = make_global_saved_search_service(self.database)
        self.addCleanup(patch.stopall)
        patch("socket.create_connection", side_effect=AssertionError("No source collection")).start()
        patch("socket.socket.connect", side_effect=AssertionError("No network")).start()
        patch("socket.getaddrinfo", side_effect=AssertionError("No DNS")).start()

    def invoke(self, *arguments, json_output=True, data=None):
        out, err = StringIO(), StringIO()
        prefix = ["--data-dir", str(data or self.data)]
        if json_output:
            prefix.append("--json")
        with redirect_stdout(out), redirect_stderr(err):
            code = main([*prefix, *arguments])
        return code, out.getvalue(), err.getvalue()

    def result(self, *arguments):
        code, out, err = self.invoke(*arguments)
        self.assertEqual((code, err), (0, ""), out + err)
        self.assertTrue(json.loads(out)["ok"])
        return json.loads(out)["data"]

    def files(self):
        return {path.relative_to(self.data).as_posix(): path.read_bytes()
                for path in self.data.rglob("*") if path.is_file()}

    def add(self, name="Example watch", query="example", *options):
        return self.result("search-watch", "add", name, query, *options)["saved_search"]["id"]

    def test_command_lifecycle_keeps_full_run_and_separate_pages(self):
        identifier = self.add("Example watch", "example", "--kind", "domain")
        for value in ("alpha.example", "beta.example", "gamma.example"):
            self.storage.add(value)
        first = self.result("search-watch", "run", identifier, "--limit", "1")
        self.assertEqual((first["run"]["total_count"], first["total_item_count"], len(first["items"])), (3, 3, 1))
        self.assertIsNone(first["notification_id"])
        self.assertTrue(first["has_more"])
        pages = [self.result("search-watch", "run-show", first["run"]["id"], "--offset", str(offset), "--limit", "1")
                 for offset in range(4)]
        self.assertEqual(len({page["items"][0]["key"] for page in pages[:3]}), 3)
        self.assertEqual(pages[-1]["items"], [])
        self.assertEqual([page["total_item_count"] for page in pages], [3] * 4)
        code, text, err = self.invoke("search-watch", "run-show", first["run"]["id"], "--limit", "1", json_output=False)
        self.assertEqual((code, err), (0, ""))
        next_command = next(line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("Sonraki kanıt sayfası:"))
        parsed = build_parser().parse_args(shlex.split(next_command)[1:])
        self.assertEqual((parsed.run_id, parsed.offset, parsed.limit), (first["run"]["id"], 1, 1))
        self.assertEqual(parsed.data_dir, str(self.data))
        self.assertIn("Önce:", text)
        self.assertIn("Sonra:", text)
        self.assertIn("sessiz başlangıç", text)

        self.storage.add("delta.example")
        changed = self.result("search-watch", "run", identifier)
        self.assertEqual(changed["run"]["added_count"], 1)
        self.assertIsNotNone(changed["notification_id"])
        self.result("search-watch", "disable", identifier, "--reason", "Şimdilik izlenmeyecek.")
        self.assertEqual(self.result("search-watch", "list")["total_count"], 0)
        self.assertEqual(self.result("search-watch", "list", "--all")["total_count"], 1)
        code, out, err = self.invoke("search-watch", "run", identifier)
        self.assertNotEqual(code, 0)
        self.assertIn("validation_error", err)
        self.assertEqual(self.result("search-watch", "show", identifier)["total_run_count"], 2)
        reactivated = self.result("search-watch", "add", "Example watch", "delta", "--kind", "domain")
        self.assertEqual(reactivated["saved_search"]["id"], identifier)
        reset = self.result("search-watch", "run", identifier)
        self.assertIsNone(reset["run"]["previous_run_id"])
        self.assertIsNone(reset["notification_id"])
        historical = self.result("search-watch", "run-show", changed["run"]["id"])
        self.assertEqual(historical["saved_search"]["query"], "example")

    def test_list_and_both_history_windows_keep_selectors_in_continuations(self):
        identifier = self.add("First watch")
        self.add("Second watch")
        self.add("Third watch")
        self.result("search-watch", "run", identifier)
        self.result("search-watch", "add", "First watch", "changed")
        self.result("search-watch", "run", identifier)
        parser = build_parser()
        _, text, _ = self.invoke("search-watch", "list", "--all", "--limit", "1", json_output=False)
        command = next(line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("Sonraki sayfa:"))
        parsed = parser.parse_args(shlex.split(command)[1:])
        self.assertTrue(parsed.include_disabled)
        self.assertEqual((parsed.offset, parsed.limit), (1, 1))
        self.assertEqual(parsed.data_dir, str(self.data))
        _, text, _ = self.invoke("search-watch", "show", identifier, "--event-limit", "1", "--run-limit", "1", json_output=False)
        commands = [line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("Sonraki ")]
        self.assertEqual(len(commands), 2)
        parsed = [parser.parse_args(shlex.split(command)[1:]) for command in commands]
        self.assertEqual({(arg.event_offset, arg.run_offset) for arg in parsed}, {(1, 0), (0, 1)})
        self.assertTrue(all(arg.event_limit == arg.run_limit == 1 and arg.search_id == identifier for arg in parsed))

    def test_read_commands_are_storage_preserving_and_do_not_lock_or_initialize(self):
        identifier = self.add()
        run = self.result("search-watch", "run", identifier)
        before = self.files()
        with (patch.object(SQLiteAssetRepository, "initialize", side_effect=AssertionError("No initialization")),
              patch.object(LocalExecutionLock, "acquire", side_effect=AssertionError("Read does not lock"))):
            self.result("search-watch", "list")
            self.result("search-watch", "show", identifier)
            self.result("search-watch", "run-show", run["run"]["id"])
            self.result("search", "example")
        self.assertEqual(self.files(), before)

    def test_missing_or_legacy_storage_never_auto_initializes_or_creates_lock(self):
        missing = self.root / "new-data"
        missing.mkdir()
        for command in (("list",), ("add", "Example watch", "example")):
            with self.subTest(command=command):
                code, out, err = self.invoke("search-watch", *command, data=missing)
                self.assertEqual(code, 1, out + err)
                self.assertIn("storage_error", err)
                self.assertEqual(list(missing.iterdir()), [])
        import sqlite3
        with closing(sqlite3.connect(self.database)) as connection:
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(connection)
            connection.execute("PRAGMA user_version=64")
            connection.commit()
        before = self.files()
        code, out, err = self.invoke("search-watch", "add", "New watch", "example")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(self.files(), before)

    def test_mutations_use_shared_lock_and_invalid_input_keeps_storage(self):
        identifier = self.add()
        before = self.files()
        with LocalExecutionLock(self.database).acquire():
            for command in (("add", "Other watch", "example"), ("run", identifier),
                            ("disable", identifier, "--reason", "İzleme durduruldu.")):
                code, out, err = self.invoke("search-watch", *command)
                self.assertNotEqual(code, 0, out + err)
                self.assertIn("worker_busy", err)
        self.assertEqual(self.files(), before)
        with patch.object(LocalExecutionLock, "acquire", side_effect=AssertionError("Invalid request must not lock")):
            for command in (("run", identifier, "--limit", "0"), ("add", "ok", "x"),
                            ("disable", identifier, "--reason", "x")):
                code, _, err = self.invoke("search-watch", *command)
                self.assertNotEqual(code, 0)
                self.assertIn("validation_error", err)

    def test_monitor_defaults_and_real_one_cycle_command(self):
        identifier = self.add()
        parsed = build_parser().parse_args(["search-watch", "monitor", identifier])
        self.assertEqual((parsed.cycles, parsed.interval, parsed.duration, parsed.limit), (2, 60, 600, 50))
        report = self.result("search-watch", "monitor", identifier, "--cycles", "1", "--duration", "5")
        self.assertEqual(report["completed_cycles"], 1)
        self.assertEqual(report["notification_count"], 0)
        self.assertEqual(self.result("search-watch", "show", identifier)["total_run_count"], 1)

    def test_terminal_renderer_escapes_external_details_and_semantic_values(self):
        identifier = self.add()
        self.storage.add("example.com")
        report = self.service.run(identifier)
        hostile = "value\x1b[31m\nforged"
        change = report.items[0]
        match = change.after
        result = replace(match.result, display_value=hostile, source=hostile, details=(hostile,))
        match = replace(match, result=result, semantic_json=canonical_json({"semantic": {"external": hostile}}))
        report = replace(report, items=(replace(change, after=match),))
        rendered = "\n".join(run_lines(report))
        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("\nforged", rendered)
        self.assertIn("forged", rendered)

    def test_real_cli_subprocess_reads_frozen_run_offline_without_changes(self):
        identifier = self.add()
        self.storage.add("example.com")
        report = self.service.run(identifier)
        before = self.files()
        injection = self.root / "offline"
        injection.mkdir()
        (injection / "sitecustomize.py").write_text(
            "import socket\ndef deny(*a, **k): raise AssertionError('Must remain offline')\n"
            "socket.create_connection=deny\nsocket.socket.connect=deny\nsocket.getaddrinfo=deny\n")
        environment = dict(os.environ, XTI_PYTHON=sys.executable,
                           PYTHONPATH=os.pathsep.join((str(injection), str(PROJECT / "src"))),
                           PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.run([str(PROJECT / "xti"), "--data-dir", str(self.data), "--json",
                                  "search-watch", "run-show", report.run.id], env=environment, cwd=PROJECT,
                                 capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual((process.returncode, process.stderr), (0, ""), process.stdout)
        self.assertEqual(json.loads(process.stdout)["data"]["run"]["total_count"], 1)
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()

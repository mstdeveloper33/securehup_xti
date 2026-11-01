"""Recorded status through the public command, with no live requests or writes."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import shlex
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.application.status import StatusService
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError
from tests.test_discovery import FakeSource, batch, document
from tests.test_multi_source import FakeUrlscanSource, scoped_batch, urlscan_document


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


class StatusCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "status data with spaces"
        self.database = self.data / "xti.db"
        self.crt = FakeSource({"%example%": batch(document("example-support.net"))})
        self.urlscan = FakeUrlscanSource({"example*": scoped_batch(urlscan_document())})

    def invoke(self, *arguments, as_json=True, now=NOW):
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("xti.interfaces.cli.CrtShSource", return_value=self.crt),
            patch("xti.interfaces.cli.UrlscanSource", return_value=self.urlscan),
            patch("xti.adapters.sqlite_jobs._now", return_value=NOW.isoformat()),
            patch("xti.interfaces.cli.StatusService", side_effect=lambda repo: StatusService(repo, clock=lambda: now)),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main(["--data-dir", str(self.data), *(["--json"] if as_json else []), *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def success(self, *arguments, **kwargs):
        code, stdout, stderr = self.invoke(*arguments, **kwargs)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        result = json.loads(stdout)
        self.assertTrue(result["ok"])
        return result["data"]

    def test_empty_view_is_read_only_and_does_not_create_worker_files(self):
        self.success("init")
        before = self.database.read_bytes()
        files = sorted(self.data.iterdir())
        data = self.success("status")
        self.assertEqual(data["assets"], [])
        self.assertEqual((data["asset_count"], data["notification_count"]), (0, 0))
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(sorted(self.data.iterdir()), files)
        self.assertEqual(sum(data["job_counts"].values()), 0)

    def test_real_discovery_flow_and_new_asset_have_distinct_coverage(self):
        self.success("scan", "example.com")
        self.success("assets", "add", "newbrand.com")
        before = self.database.read_bytes()
        self.crt.calls.clear()
        self.urlscan.calls.clear()
        with (
            patch("socket.socket", side_effect=AssertionError("Status must not open sockets")),
            patch("xti.interfaces.cli.make_jobs", side_effect=AssertionError("No discovery wiring on status")),
        ):
            report = self.success("status")
        self.assertEqual(report["asset_count"], 2)
        self.assertEqual(report["job_counts"]["complete"], 2)
        self.assertEqual(report["finding_counts"]["new"], 1)
        self.assertEqual(report["unread_notification_count"], 1)
        self.assertEqual({s["freshness"] for s in report["assets"][0]["sources"]}, {"current"})
        self.assertEqual({s["freshness"] for s in report["assets"][1]["sources"]}, {"never"})
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.crt.calls + self.urlscan.calls, [])

    def test_partial_latest_does_not_hide_previous_complete(self):
        self.success("scan", "example.com", "--source", "crt.sh")
        self.crt.responses["%example%"] = SourceError("Kontrollü kaynak hatası.")
        code, stdout, stderr = self.invoke("scan", "example.com", "--source", "crt.sh")
        self.assertEqual(code, 3, stderr)
        self.assertEqual(json.loads(stdout)["data"]["status"], "partial")
        report = self.success("status")
        source = report["assets"][0]["sources"][0]
        self.assertEqual(source["latest_attempt"]["status"], "partial")
        self.assertEqual(source["last_complete"]["status"], "complete")
        self.assertNotEqual(source["last_complete"]["id"], source["latest_attempt"]["id"])
        self.assertEqual(source["latest_attempt"]["failed_query_count"], 1)
        self.assertIn("Kontrollü", source["latest_attempt"]["error"])
        code, text, error = self.invoke("status", as_json=False)
        self.assertEqual(code, 0, error)
        self.assertIn("Kısmi sonuç", text)
        self.assertIn("Son tam arama", text)

    def test_age_threshold_changes_view_without_changing_data_or_schedule(self):
        self.success("scan", "example.com", "--source", "crt.sh")
        before = self.database.read_bytes()
        old = self.success("status", now=NOW + timedelta(hours=24))
        self.assertEqual(old["assets"][0]["sources"][0]["freshness"], "stale")
        expanded = self.success("status", "--stale-after-hours", "48", now=NOW + timedelta(hours=24))
        self.assertEqual(expanded["assets"][0]["sources"][0]["freshness"], "current")
        self.assertEqual(self.database.read_bytes(), before)

    def test_queue_and_running_records_are_reported_without_recovery(self):
        queued = self.success("scan", "example.com", "--queue")
        jobs = SQLiteJobRepository(self.database)
        jobs.start(queued["jobs"][0]["id"])
        before = self.database.read_bytes()
        data = self.success("status")
        self.assertEqual(data["job_counts"]["queued"], 1)
        self.assertEqual(data["job_counts"]["running"], 1)
        self.assertEqual(data["assets"][0]["sources"][0]["latest_attempt"]["status"], "running")
        self.assertEqual(data["assets"][0]["sources"][1]["queued_count"], 1)
        self.assertEqual(self.database.read_bytes(), before)
        code, output, error = self.invoke("status", as_json=False)
        self.assertEqual(code, 0, error)
        self.assertIn("Çalışıyor olarak kayıtlı", output)

    def test_filtered_and_limited_views_keep_global_counts_and_exact_commands(self):
        self.success("init")
        for domain in ("zebra.com", "example.com", "brand.com"):
            self.success("assets", "add", domain)
        limited = self.success("status", "--limit", "1", "--stale-after-hours", "48")
        self.assertTrue(limited["has_more_assets"])
        self.assertEqual(limited["displayed_asset_count"], 1)
        self.assertEqual(limited["assets"][0]["asset"]["value"], "brand.com")
        self.assertEqual(shlex.split(limited["commands"]["status_domain"])[-2:], ["--stale-after-hours", "48"])
        self.assertEqual(shlex.split(limited["commands"]["status_more"])[-2:], ["--stale-after-hours", "48"])
        one = self.success("status", "EXAMPLE.COM.")
        self.assertEqual(one["domain_filter"], "example.com")
        self.assertEqual(one["asset_count"], 3)
        self.assertFalse(one["has_more_assets"])
        self.assertEqual(shlex.split(one["commands"]["inbox"]), ["./xti", "--data-dir", str(self.data.resolve()), "inbox"])
        before = self.database.read_bytes()
        code, output, error = self.invoke("status", "missing.com")
        self.assertEqual(code, 2, error)
        self.assertEqual(output, "")
        self.assertEqual(self.database.read_bytes(), before)

    def test_missing_database_and_bad_options_do_not_create_files(self):
        for args, expected in (((), 1), (("--limit", "0"), 2), (("--limit", "101"), 2),
                               (("--stale-after-hours", "0"), 2), (("--stale-after-hours", "8761"), 2),
                               (("https://example.com",), 2)):
            with self.subTest(args=args):
                code, output, error = self.invoke("status", *args)
                self.assertEqual(code, expected, error)
                self.assertEqual(output, "")
                self.assertFalse(self.data.exists())

    def test_cooldowns_inbox_and_reviews_are_visible_but_unchanged(self):
        self.success("scan", "example.com")
        item = self.success("inbox")["items"][0]
        self.success("inbox", "read", item["notification"]["id"])
        self.success("findings", "review", item["finding"]["id"], "--decision", "dismissed", "--reason", "Test kararı.")
        SQLiteCooldownRepository(self.database).extend("crt.sh", (NOW + timedelta(seconds=90)).isoformat(), NOW.isoformat(), "retry_after")
        before = self.database.read_bytes()
        data = self.success("status")
        self.assertEqual(data["unread_notification_count"], 0)
        self.assertEqual(data["finding_counts"]["dismissed"], 1)
        self.assertTrue(data["cooldowns"][0]["active"])
        self.assertEqual(data["cooldowns"][0]["remaining_seconds"], 90)
        self.assertEqual(self.database.read_bytes(), before)

    def test_external_errors_and_paths_cannot_control_terminal(self):
        self.data = self.root / "status\x1b[31m data"
        self.database = self.data / "xti.db"
        self.success("scan", "example.com", "--queue", "--source", "crt.sh")
        jobs = SQLiteJobRepository(self.database)
        attempt = jobs.start()
        jobs.finish(attempt.id, "failed", error="source\x1b[2J\nforged")
        code, output, error = self.invoke("status", as_json=False)
        self.assertEqual(code, 0, error)
        self.assertNotIn("\x1b", output)
        self.assertIn(r"source\u001b[2J\u000aforged", output)
        self.assertIn(r"status\u001b[31m data", output)

    def test_current_schema_needs_no_migration_and_backup_preserves_status(self):
        self.success("scan", "example.com")
        before = self.success("status")
        snapshot = self.root / "backup.db"
        self.success("backup", "--output", str(snapshot))
        old_data = self.data
        self.data = self.root / "restored"
        self.database = self.data / "xti.db"
        self.success("restore", str(snapshot))
        after = self.success("status")
        for key in before.keys() - {"commands"}:
            self.assertEqual(after[key], before[key], key)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        self.assertTrue((old_data / "xti.db").is_file())


if __name__ == "__main__":
    unittest.main()

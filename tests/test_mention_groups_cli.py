"""Actual grouped CLI, scoped inbox, offline views and explicit source calls."""

from datetime import datetime, timedelta, timezone
from dataclasses import replace
import json
import shlex
from unittest.mock import patch
from uuid import uuid4
import unittest

from tests import test_mentions_cli as fixtures
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.application.mention_groups import MentionGroupService
from xti.interfaces.mention_groups import make_mention_group_service
from xti.interfaces.cli import build_parser
from xti.ports.discovery import SourceError


class MentionGroupCLITests(unittest.TestCase):
    setUp = fixtures.MentionCLITests.setUp
    invoke = fixtures.MentionCLITests.invoke
    result = fixtures.MentionCLITests.result
    fetch = fixtures.MentionCLITests.fetch

    def group(self, *, name="Firma ve tedarikçiler", supplier=True):
        organization = self.result("organizations", "add", "Example Company")["organization"]
        self.result("assets", "add", "example.com")
        self.result("organizations", "link", organization["id"], "--kind", "domain", "--value", "example.com")
        arguments = ["mentions", "groups", "save", name, "--organization", organization["id"],
                     "--interval-hours", "1", "--daily-queries", "4", "--run-queries", "2"]
        if supplier:
            record = self.result("suppliers", "add", "Example Supplier", "--domain", "supplier.example",
                                 "--relationship", "software", "--criticality", "medium", "--reason", "Test relationship")
            arguments.extend(("--supplier", record["supplier"]["id"]))
        self.now = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)
        patch.object(MentionGroupService, "_now", side_effect=lambda: self.now.isoformat()).start()
        return self.result(*arguments)

    def test_group_collects_both_targets_and_reuses_inbox_without_repeated_http(self):
        group = self.group()
        first = self.result("mentions", "groups", "run", group["id"])
        self.assertEqual(first["status"], "complete")
        self.assertEqual(len(self.calls), 2)
        self.assertEqual({request.target.kind for request in self.calls}, {"organization", "supplier"})
        self.assertEqual(SQLiteInboxRepository(self.storage.path).list().total_count, 0)
        duplicate = self.result("mentions", "groups", "run", group["id"], "--request-id", first["run"]["id"])
        self.assertEqual(duplicate["run"], first["run"])
        self.assertEqual(len(self.calls), 2)
        deferred = self.result("mentions", "groups", "run", group["id"])
        self.assertEqual(deferred["reason"], "not_due")
        self.now += timedelta(hours=2)
        self.hits = (replace(self.hits[0], title="Example Company corrected report"), self.hits[1])
        second = self.result("mentions", "groups", "run", group["id"])
        self.assertEqual((second["status"], second["daily_queries_used"], len(self.calls)), ("complete", 4, 4))
        inbox = SQLiteInboxRepository(self.storage.path).list()
        self.assertEqual(inbox.total_count, 2)
        self.assertTrue(all(item.global_search_change is not None for item in inbox.items))
        self.now += timedelta(hours=2)
        blocked = self.result("mentions", "groups", "run", group["id"])
        self.assertEqual(blocked["reason"], "daily_budget")
        self.assertEqual(len(self.calls), 4)

    def test_all_offline_views_and_navigation_preserve_database_and_need_no_key(self):
        group = self.group()
        first = self.result("mentions", "groups", "run", group["id"])
        before = self.storage.path.read_bytes()
        with patch.dict("os.environ", {"TAVILY_API_KEY": ""}):
            for arguments in (("list",), ("show", group["id"]), ("plan", group["id"]),
                              ("runs", group["id"]), ("run-show", first["run"]["id"], "--details")):
                self.result("mentions", "groups", *arguments)
            code, text, err = self.invoke("mentions", "groups", "run-show", first["run"]["id"],
                                          "--details", as_json=False)
            self.assertEqual((code, err), (0, ""))
            self.assertIn("Example Supplier", text)
            self.assertIn(self.hits[0].url, text)
            self.assertIn(self.hits[1].url, text)
            for line in text.splitlines():
                if ": ./xti " in line:
                    command = line.split(": ", 1)[1]
                    parsed = build_parser().parse_args(shlex.split(command)[1:])
                    self.assertEqual(parsed.data_dir, str(self.data))
        self.assertEqual(self.storage.path.read_bytes(), before)
        self.assertNotIn(fixtures.KEY.encode(), before)
        self.assertEqual(len(self.calls), 2)

    def test_source_error_stops_remaining_queries_preserves_failure_and_no_notice(self):
        group = self.group()
        self.error = SourceError("Tavily bağlantısı tamamlanamadı; otomatik tekrar yapılmadı.")
        code, output, error = self.invoke("mentions", "groups", "run", group["id"])
        self.assertEqual((code, error), (3, ""))
        data = json.loads(output)["data"]
        self.assertEqual([attempt["status"] for attempt in data["run"]["attempts"]], ["failed", "skipped"])
        self.assertEqual(data["daily_queries_used"], 1)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(SQLiteInboxRepository(self.storage.path).list().total_count, 0)
        self.result("mentions", "groups", "run-show", data["run"]["id"], "--details")

    def test_schedule_files_are_explicit_private_and_do_not_search_or_mutate_evidence(self):
        group = self.group(supplier=False)
        before = self.storage.path.read_bytes()
        output = self.root / "schedule with spaces"
        report = self.result("mentions", "groups", "schedule", group["id"], "--output", str(output),
                             "--at", "09:00", "--timezone", "Europe/Istanbul")
        self.assertTrue(output.is_dir())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.storage.path.read_bytes(), before)
        service = (output / (report["unit_name"] + ".service")).read_text()
        self.assertIn('"mentions" "groups" "run"', service)
        self.assertNotIn(fixtures.KEY, service)
        self.assertEqual((output.stat().st_mode & 0o777), 0o700)
        again, _, _ = self.invoke("mentions", "groups", "schedule", group["id"], "--output", str(output), "--at", "09:00")
        self.assertNotEqual(again, 0)

    def test_monitor_one_cycle_and_saved_group_pagination_are_real_cli(self):
        group = self.group(supplier=False)
        monitor = self.result("mentions", "groups", "monitor", group["id"], "--cycles", "1")
        self.assertEqual(monitor["completed_cycles"], 1)
        self.assertEqual(len(self.calls), 1)
        code, output, progress = self.invoke("mentions", "groups", "monitor", group["id"], "--cycles", "1", as_json=False)
        self.assertEqual(code, 0, output + progress)
        self.assertIn("izleme turu 1/1", progress)
        self.assertEqual(len(self.calls), 1)
        self.result("mentions", "groups", "save", "İkinci izleme", "--organization", group["definition"]["organization_id"])
        code, text, err = self.invoke("mentions", "groups", "list", "--limit", "1", as_json=False)
        self.assertEqual((code, err), (0, ""))
        command = next(line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("Sonraki sayfa:"))
        parsed = build_parser().parse_args(shlex.split(command)[1:])
        self.assertEqual((parsed.offset, parsed.limit, parsed.data_dir), (1, 1, str(self.data)))

    def test_invalid_scope_and_missing_key_leave_no_run_or_http(self):
        group = self.group()
        before = self.storage.path.read_bytes()
        with patch.dict("os.environ", {"TAVILY_API_KEY": ""}):
            code, _, _ = self.invoke("mentions", "groups", "run", group["id"])
            self.assertNotEqual(code, 0)
        self.assertEqual(self.storage.path.read_bytes(), before)
        code, _, _ = self.invoke("mentions", "groups", "save", "Unknown", "--organization", str(uuid4()))
        self.assertNotEqual(code, 0)
        self.assertEqual(self.storage.path.read_bytes(), before)
        self.assertEqual(self.calls, [])

    def test_reserved_and_unknown_run_details_do_not_link_nonexistent_source_results(self):
        group = self.group(supplier=False)
        service = make_mention_group_service(self.storage.path)
        requests = service.plan(group["id"])["requests"]
        run = service.repository.begin(group["id"], requests, started_at=self.now.isoformat())
        service.repository.reserve_attempt(run.id, 0, started_at=self.now.isoformat())
        with patch.dict("os.environ", {"TAVILY_API_KEY": ""}):
            reserved = self.result("mentions", "groups", "run-show", run.id, "--details")
            self.assertEqual(reserved["source_details"], [])
            code, output, _ = self.invoke("mentions", "groups", "resume", run.id)
            self.assertEqual(code, 3, output)
            unknown = self.result("mentions", "groups", "run-show", run.id, "--details")
            self.assertEqual(unknown["run"]["attempts"][0]["status"], "unknown")
            self.assertEqual(unknown["source_details"], [])
            code, text, error = self.invoke("mentions", "groups", "run-show", run.id, "--details", as_json=False)
            self.assertEqual((code, error), (0, ""))
            self.assertNotIn("Kaynak sonuçları:", text)
        self.assertEqual(self.calls, [])

    def test_prepare_verifies_backup_and_rejects_later_calendar_mismatch_before_backup(self):
        group = self.group(supplier=False)
        report = self.result("mentions", "groups", "prepare", group["id"], "--calendar-hours", "24")
        self.assertTrue(report["backup"]["restore_verified"])
        self.assertEqual(self.calls, [])
        self.result("mentions", "groups", "save", group["name"], "--organization",
                    group["definition"]["organization_id"], "--interval-hours", "24")
        with patch("xti.adapters.scheduled_backups.ScheduledBackupMaintenance.backup_and_prune",
                   side_effect=AssertionError("Incompatible calendar must not prepare backup")):
            code, _, _ = self.invoke("mentions", "groups", "prepare", group["id"], "--calendar-hours", "24")
            self.assertNotEqual(code, 0)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()

"""Offline user workflow from explicit organization scope to durable inbox."""

from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.public_notices import HIBP_ATTRIBUTION, HIBP_LICENSE
from xti.ports.discovery import SourceError
from tests import test_collection_watch_cli as fixtures
from tests.test_collection_public_notice_cli import public_catalog
from tests.test_public_notices import item


class PublicNoticeWatchCLITests(unittest.TestCase):
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files

    def setUp(self):
        fixtures.CollectionWatchCLITests.setUp(self)
        self.catalog = fixtures.ClaimSource(public_catalog(item()))
        self.factory = self.enterContext(patch("xti.interfaces.cli.HibpPublicNoticeSource", return_value=self.catalog))
        self.organization = self.result("organizations", "add", "Example group")["organization"]
        self.link = self.result("organizations", "link", self.organization["id"],
                                "--kind", "domain", "--value", "example.com")["link"]

    def enable(self, organization=None):
        return self.result("notices", "watch", "enable", (organization or self.organization)["id"])

    def show(self, organization=None):
        return self.result("notices", "watch", "show", (organization or self.organization)["id"])

    def refresh(self):
        return self.result("notices", "refresh")

    def collect(self):
        return self.result("collect", "example.com", "--task", "notices-hibp")

    def changed(self):
        self.enable()
        self.refresh()
        self.catalog.value = public_catalog(item(PwnCount=23456))
        self.refresh()
        return self.result("inbox", "list")["items"][0]

    def test_opt_in_configuration_and_planning_never_construct_or_fetch_source(self):
        self.assertEqual(self.result("notices", "watch", "list")["total_count"], 0)
        first = self.enable()
        self.assertTrue(first["watch"]["active"])
        self.assertEqual(self.show()["effective_domains"], ["example.com"])
        before = self.files()
        repeated = self.enable()
        self.assertEqual(repeated["action"], "unchanged")
        self.assertEqual(self.files(), before)
        self.result("profiles", "save", "notices", "example.com", "--task", "notices-hibp")
        self.result("collect", "--profile", "notices", "--plan")
        self.assertEqual(self.catalog.calls, 0)
        self.assertEqual(self.result("inbox", "list")["total_count"], 0)

    def test_baseline_collect_then_changed_refresh_has_exact_source_and_single_notice(self):
        self.enable()
        baseline = self.collect()["steps"][0]["public_notices"]["run"]
        self.assertEqual(self.result("inbox", "list")["total_count"], 0)
        self.assertEqual(self.show()["runs"][0]["baseline_count"], 1)
        self.catalog.value = public_catalog(item(PwnCount=23456), item("Unrelated", "other.example"))
        changed = self.refresh()["run"]
        notice, = self.result("inbox", "list")["items"]
        evidence = notice["public_notice_change"]
        self.assertEqual(evidence["organization_id"], self.organization["id"])
        self.assertEqual(evidence["source_run_id"], changed["id"])
        self.assertEqual(evidence["previous_source_run_id"], baseline["id"])
        self.assertEqual(evidence["items"][0]["before"]["pwn_count"], 12345)
        self.assertEqual(evidence["items"][0]["after"]["pwn_count"], 23456)
        self.assertEqual(evidence["updated_count"], 1)
        self.assertEqual(evidence["attribution"], HIBP_ATTRIBUTION)
        self.assertEqual(evidence["license"], HIBP_LICENSE)
        self.collect()
        self.assertEqual(self.result("inbox", "list")["total_count"], 1)

    def test_new_domain_baseline_does_not_silence_existing_domain_update(self):
        self.enable(); self.refresh()
        self.result("assets", "add", "new.example")
        self.result("organizations", "link", self.organization["id"], "--kind", "domain", "--value", "new.example")
        self.catalog.value = public_catalog(item(PwnCount=23456), item("OldHistory", "new.example"))
        self.refresh()
        latest = self.show()["runs"][0]
        self.assertEqual((latest["baseline_count"], latest["updated_count"]), (1, 1))
        report = self.result("notices", "watch-run-show", latest["id"])
        self.assertEqual(report["baseline_domains"], ["new.example"])
        self.assertEqual(report["continuing_domains"], ["example.com"])
        self.assertEqual({change["notice_id"]: change["action"] for change in report["items"]},
                         {"Example": "updated", "OldHistory": "baseline"})
        self.assertEqual(self.result("inbox", "list")["total_count"], 1)

    def test_same_domain_two_organizations_have_separate_historical_reports(self):
        other = self.result("organizations", "add", "Other group")["organization"]
        self.result("organizations", "link", other["id"], "--kind", "domain", "--value", "example.com")
        self.enable(); self.enable(other); self.refresh()
        self.catalog.value = public_catalog(item(PwnCount=23456)); self.refresh()
        items = self.result("inbox", "list")["items"]
        self.assertEqual(len(items), 2)
        by_org = {entry["public_notice_change"]["organization_id"]: entry for entry in items}
        self.assertEqual(set(by_org), {self.organization["id"], other["id"]})
        for organization in (self.organization, other):
            report = self.result("organizations", "report", organization["id"])
            watch = report["public_notice_watch"]
            self.assertEqual(watch["organization"]["id"], organization["id"])
            self.assertEqual(watch["runs"][0]["id"], by_org[organization["id"]]["public_notice_change"]["run_id"])
        self.result("organizations", "rename", self.organization["id"], "Renamed group", "--reason", "Yeni görünür isim.")
        self.result("organizations", "unlink", self.organization["id"], self.link["id"], "--reason", "Kapsamdan çıkarıldı.")
        history = self.result("inbox", "show", by_org[self.organization["id"]]["notification"]["id"])
        self.assertEqual(history["public_notice_change"]["organization_name"], "Example group")
        report = self.result("organizations", "report", self.organization["id"])
        self.assertEqual(report["targets"], [])
        self.assertEqual(report["public_notice_watch"]["runs"][0]["id"], history["public_notice_change"]["run_id"])

    def test_views_are_readonly_and_terminal_has_real_before_after_and_navigation(self):
        entry = self.changed()
        notification_id = entry["notification"]["id"]
        run_id = entry["public_notice_change"]["run_id"]
        before, calls = self.files(), self.catalog.calls
        with patch.object(LocalExecutionLock, "acquire", side_effect=AssertionError("Read must not acquire write lock")):
            for args in (("notices", "watch", "list"), ("notices", "watch", "show", self.organization["id"]),
                         ("notices", "watch-run-show", run_id), ("inbox", "show", notification_id),
                         ("organizations", "report", self.organization["id"])):
                self.result(*args)
                code, output, error = self.invoke(*args, as_json=False)
                self.assertEqual((code, error), (0, ""), output)
                self.assertIn(HIBP_ATTRIBUTION, output)
                self.assertIn(HIBP_LICENSE, output)
                if args[1] == "watch-run-show" or args[0] == "inbox":
                    self.assertIn("12345", output)
                    self.assertIn("23456", output)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.catalog.calls, calls)
        self.assertEqual(self.result("inbox", "list")["unread_count"], 1)
        self.result("inbox", "read", notification_id)
        self.assertEqual(self.result("inbox", "list")["unread_count"], 0)
        self.result("inbox", "unread", notification_id)
        self.assertEqual(self.result("inbox", "list")["unread_count"], 1)

    def test_failed_refresh_preserves_last_watch_and_next_success_retries_once(self):
        self.enable(); self.refresh()
        first = self.show()["runs"][0]
        self.catalog.value = SourceError("Katalog geçici olarak erişilemiyor.")
        self.result("notices", "refresh", expected_code=3)
        details = self.show()
        self.assertEqual(details["runs"][0], first)
        self.assertEqual(details["latest_source_run"]["status"], "failed")
        self.assertEqual(details["latest_complete_source_run"]["id"], first["source_run_id"])
        self.assertEqual(self.result("inbox", "list")["total_count"], 0)
        self.catalog.value = public_catalog(item(PwnCount=23456)); self.refresh()
        self.assertEqual(self.result("inbox", "list")["total_count"], 1)

    def test_source_commit_interrupt_keeps_notice_and_resume_does_not_duplicate(self):
        self.enable(); self.refresh()
        self.catalog.value = public_catalog(item(PwnCount=23456))
        original = SQLitePublicNoticeRepository.apply
        def interrupt_after_commit(repository, *arguments, **options):
            original(repository, *arguments, **options)
            raise KeyboardInterrupt()
        with patch.object(SQLitePublicNoticeRepository, "apply", interrupt_after_commit):
            code, _, _ = self.invoke("collect", "example.com", "--task", "notices-hibp")
        self.assertEqual(code, 130)
        session = self.result("collections", "list")["sessions"][0]
        before = self.result("inbox", "list")
        self.assertEqual(before["total_count"], 1)
        plan = self.result("collections", "resume", session["id"], "--plan")
        self.assertEqual(plan["units"], [])
        self.result("collections", "resume", session["id"])
        self.assertEqual(self.catalog.calls, 2)
        self.assertEqual(self.result("inbox", "list"), before)

    def test_invalid_selection_stops_without_source_or_data_change(self):
        self.enable()
        before = self.files()
        for args in (("enable", "not-a-uuid"), ("enable", str(uuid4())),
                     ("show", self.organization["id"], "--run-limit", "0"),
                     ("list", "--offset", "-1"), ("disable", self.organization["id"], "--reason", "x")):
            with self.subTest(args=args):
                code, _, _ = self.invoke("notices", "watch", *args)
                self.assertNotEqual(code, 0)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.catalog.calls, 0)

    def test_disabled_watch_and_reenable_are_explicit_with_silent_new_baseline(self):
        entry = self.changed()
        self.result("notices", "watch", "disable", self.organization["id"], "--reason", "İzleme duraklatıldı.")
        self.assertEqual(self.result("notices", "watch", "list")["total_count"], 0)
        self.assertEqual(self.result("notices", "watch", "list", "--all")["total_count"], 1)
        self.catalog.value = public_catalog(item(PwnCount=34567)); self.refresh()
        self.assertEqual(self.show()["total_run_count"], 2)
        self.enable(); self.refresh()
        run = self.show()["runs"][0]
        self.assertEqual((run["baseline_count"], run["updated_count"]), (1, 0))
        self.assertEqual(self.result("inbox", "list")["total_count"], 1)
        historical = self.result("inbox", "show", entry["notification"]["id"])
        self.assertEqual(historical["public_notice_change"]["items"][0]["after"]["pwn_count"], 23456)

    def test_corrupt_watch_stops_mixed_collection_before_any_source_or_write(self):
        watch = self.enable()["watch"]
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE public_notice_watches SET active=0 WHERE id=?", (watch["id"],))
        before = self.files()
        for extra in ((), ("--plan",)):
            code, _, _ = self.invoke("collect", "example.com", "--task", "scan-urlscan", "--task", "notices-hibp", *extra)
            self.assertNotEqual(code, 0)
        self.assertEqual(self.catalog.calls, 0)
        self.assertEqual(self.urlscan.calls, [])
        self.assertEqual(self.files(), before)

    def test_history_offsets_and_organization_report_reach_older_runs_and_events(self):
        self.changed(); self.refresh()
        self.result("notices", "watch", "disable", self.organization["id"], "--reason", "Geçici olarak kapalı.")
        self.enable()
        full = self.show()
        self.assertEqual((full["total_run_count"], full["total_event_count"]), (3, 3))
        before = self.files()
        for offset in (0, 1, 2, 3):
            page = self.result("notices", "watch", "show", self.organization["id"], "--run-limit", "1",
                               "--event-limit", "1", "--run-offset", str(offset), "--event-offset", str(offset))
            self.assertEqual(page["runs"], full["runs"][offset:offset + 1])
            self.assertEqual(page["events"], full["events"][offset:offset + 1])
            self.assertEqual((page["run_offset"], page["event_offset"]), (offset, offset))
            report = self.result("organizations", "report", self.organization["id"],
                                 "--item-limit", "1", "--item-offset", str(offset))
            self.assertEqual(report["public_notice_watch"]["runs"], page["runs"])
            self.assertEqual(report["public_notice_watch"]["events"], page["events"])
        code, output, error = self.invoke("notices", "watch", "show", self.organization["id"],
                                          "--run-limit", "1", "--run-offset", "1", as_json=False)
        self.assertEqual((code, error), (0, ""))
        self.assertNotIn("son değerlendirmesi en yeni başarılı kataloğa ait değil", output)
        self.assertIn("--run-offset 2", output)
        self.assertEqual(self.files(), before)

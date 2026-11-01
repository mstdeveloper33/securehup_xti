"""Local inbox behavior through discovery, explicit reading and recovery."""

from contextlib import closing, redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.interfaces.cli import main
from tests.test_discovery import FakeSource, batch, document
from tests.test_multi_source import FakeUrlscanSource, scoped_batch, urlscan_document


class InboxCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "local inbox with spaces"
        self.database = self.data / "xti.db"
        self.crt = FakeSource({"%example%": batch(document("example-support.net"))})
        self.urlscan = FakeUrlscanSource({"example*": scoped_batch(urlscan_document())})

    def invoke(self, *arguments, as_json=True, data_dir=None):
        argv = ["--data-dir", str(data_dir or self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("xti.interfaces.cli.CrtShSource", return_value=self.crt),
            patch("xti.interfaces.cli.UrlscanSource", return_value=self.urlscan),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def success(self, *arguments, **kwargs):
        code, stdout, stderr = self.invoke(*arguments, **kwargs)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        return payload["data"]

    def scan(self):
        self.success("scan", "example.com")
        return self.success("inbox")["items"][0]

    def test_both_sources_produce_one_notice_and_default_inbox_is_read_only(self):
        item = self.scan()
        notice = item["notification"]
        self.assertEqual(notice["origin"], "new")
        self.assertEqual(notice["event_type"], "finding_created")
        self.assertIsNone(notice["read_at"])
        before = self.database.read_bytes()
        self.crt.calls.clear()
        self.urlscan.calls.clear()
        page = self.success("inbox")
        self.assertEqual((page["total_count"], page["unread_count"], page["matching_count"]), (1, 1, 1))
        self.assertEqual(self.success("inbox", "list"), page)
        details = self.success("inbox", "show", notice["id"])
        self.assertEqual(details["notification"], notice)
        self.assertEqual(len(details["details"]["observations"]), 2)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.crt.calls + self.urlscan.calls, [])

    def test_read_is_idempotent_and_repeated_scans_do_not_reopen_notice(self):
        item = self.scan()
        identifier = item["notification"]["id"]
        first = self.success("inbox", "read", identifier)
        self.assertEqual(first["changed_count"], 1)
        self.assertIsNotNone(first["notifications"][0]["read_at"])
        self.assertEqual(self.success("inbox")["items"], [])
        second = self.success("inbox", "read", identifier, identifier)
        self.assertEqual(second["changed_count"], 0)
        self.assertEqual(second["notifications"], first["notifications"])
        self.success("scan", "example.com")
        self.assertEqual(self.success("inbox")["unread_count"], 0)
        shown = self.success("inbox", "show", identifier)
        self.assertEqual(shown["notification"], first["notifications"][0])
        self.assertEqual(shown["details"]["finding"]["status"], "new")

    def test_review_and_unread_are_separate_actions(self):
        item = self.scan()
        identifier = item["notification"]["id"]
        finding_id = item["finding"]["id"]
        self.success("findings", "review", finding_id, "--decision", "dismissed", "--reason", "İncelendi.")
        self.assertEqual(self.success("inbox")["unread_count"], 1)
        finding_before = self.success("findings", "show", finding_id)
        self.success("inbox", "read", identifier)
        read_page = self.success("inbox", "list", "--status", "read")
        self.assertEqual(read_page["items"][0]["finding"]["status"], "dismissed")
        marked = self.success("inbox", "unread", identifier)
        self.assertEqual(marked["changed_count"], 1)
        self.assertIsNone(marked["notifications"][0]["read_at"])
        self.assertEqual(self.success("findings", "show", finding_id), finding_before)

    def test_marking_unknown_id_rolls_back_the_whole_explicit_selection(self):
        item = self.scan()
        identifier = item["notification"]["id"]
        before = self.database.read_bytes()
        code, stdout, stderr = self.invoke("inbox", "read", identifier, "missing-notification")
        self.assertEqual(code, 2, stderr)
        self.assertEqual(stdout, "")
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.success("inbox")["unread_count"], 1)

    def test_paging_stays_bounded_when_new_notifications_arrive(self):
        domains = ["example-support.net", "example-login.net", "example-help.net"]
        self.crt = FakeSource({"%example%": batch(*(document(domain, number) for number, domain in enumerate(domains)))})
        self.success("scan", "example.com", "--source", "crt.sh")
        first = self.success("inbox", "list", "--limit", "2")
        self.assertEqual(len(first["items"]), 2)
        self.assertEqual(first["matching_count"], 3)
        cursor = first["next_before"]
        self.assertIsNotNone(cursor)
        self.assertIn("--before " + str(cursor), first["next_command"])
        self.crt = FakeSource({"%example%": batch(document("example-account.net", 40))})
        self.success("scan", "example.com", "--source", "crt.sh")
        second = self.success("inbox", "list", "--limit", "2", "--before", str(cursor))
        self.assertEqual(len(second["items"]), 1)
        self.assertIsNone(second["next_before"])
        first_ids = {item["notification"]["id"] for item in first["items"]}
        self.assertFalse(first_ids & {item["notification"]["id"] for item in second["items"]})
        self.assertEqual(self.success("inbox")["total_count"], 4)

    def test_invalid_arguments_and_missing_storage_never_create_data(self):
        for arguments in [
            ("inbox", "list", "--limit", "101"),
            ("inbox", "list", "--before", "0"),
            ("inbox", "list", "--before", str(2**63)),
            ("inbox", "show", "x" * 65),
            ("inbox", "read", *("id" for _ in range(101))),
            ("inbox", "unread", " "),
        ]:
            with self.subTest(arguments=arguments[:4]):
                code, stdout, stderr = self.invoke(*arguments)
                self.assertEqual(code, 2, stderr)
                self.assertEqual(stdout, "")
                self.assertFalse(self.data.exists())
        for arguments in [("inbox",), ("inbox", "show", "missing"), ("inbox", "read", "missing")]:
            code, stdout, stderr = self.invoke(*arguments)
            self.assertEqual(code, 1, stderr)
            self.assertFalse(self.data.exists())

    def test_notice_storage_failure_is_reported_without_partial_finding_or_observation(self):
        with patch.object(SQLiteFindingRepository, "_notify_new_finding", side_effect=sqlite3.OperationalError("disk full")):
            code, stdout, stderr = self.invoke("scan", "example.com", "--source", "crt.sh")
        self.assertEqual(code, 1, stderr)
        self.assertEqual(stdout, "")
        self.assertEqual(self.success("inbox")["total_count"], 0)
        state = self.success("doctor")
        self.assertEqual((state["finding_count"], state["observation_count"]), (0, 0))
        self.success("scan", "example.com", "--source", "crt.sh")
        self.assertEqual(self.success("inbox")["total_count"], 1)

    def test_queued_worker_creates_the_same_local_notification(self):
        self.success("scan", "example.com", "--source", "crt.sh", "--queue")
        self.assertEqual(self.success("inbox")["total_count"], 0)
        self.success("worker", "--once")
        page = self.success("inbox")
        self.assertEqual(page["total_count"], 1)
        self.assertEqual(page["items"][0]["notification"]["origin"], "new")

    def test_backup_restore_preserves_read_state_and_cleanup_protects_notice(self):
        item = self.scan()
        identifier = item["notification"]["id"]
        self.success("inbox", "read", identifier)
        before = self.success("inbox", "show", identifier)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE observations SET ingested_at = '2020-01-01T00:00:00+00:00'")
        plan = self.success("storage", "cleanup")["plan"]
        self.assertEqual(plan["selected_count"], 0)
        self.success("storage", "cleanup", "--apply", plan["token"])
        backup = self.root / "snapshot.db"
        self.success("backup", "--output", str(backup))
        restored = self.root / "restored"
        self.success("restore", str(backup), data_dir=restored)
        after = self.success("inbox", "show", identifier, data_dir=restored)
        self.assertEqual(after["notification"], before["notification"])
        self.assertEqual(after["details"]["finding"], before["details"]["finding"])
        self.assertEqual(len(after["details"]["observations"]), 2)
        self.assertEqual(self.success("inbox", data_dir=restored)["unread_count"], 0)

    def test_human_views_escape_external_text_and_do_not_mark_read(self):
        item = self.scan()
        identifier = item["notification"]["id"]
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE findings SET reasons = ?", (json.dumps(["Açıklama\x1b[31m\nmetni"]),))
        code, stdout, stderr = self.invoke("inbox", "show", identifier, as_json=False)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("\x1b", stdout + stderr)
        self.assertIn("okundu işaretlemez", stdout)
        self.assertEqual(self.success("inbox")["unread_count"], 1)


if __name__ == "__main__":
    unittest.main()

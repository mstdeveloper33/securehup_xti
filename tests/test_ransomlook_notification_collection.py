"""RansomLook notification and collection receipt share the real source transaction."""

from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.ports.discovery import SourceError
from tests import test_collection_watch_cli as fixtures


class RansomLookNotificationCollectionTests(unittest.TestCase):
    setUp = fixtures.CollectionWatchCLITests.setUp
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    add_rl = fixtures.CollectionWatchCLITests.add_rl

    def baseline(self):
        watch = self.add_rl()
        args = ("collect", "example.com", "--task", "scan-crtsh", "--ransomlook-watch", watch.id)
        self.result(*args)
        self.ransomlook.value = fixtures.ransomlook_feed([
            fixtures.post(), fixtures.post(group="second-group"),
        ])
        return watch, args

    def test_commit_survives_outer_interrupt_without_duplicate_notice_on_resume(self):
        watch, args = self.baseline()
        original = SQLiteRansomLookWatchRepository.run
        def interrupt_after_commit(repository, *arguments, **options):
            report = original(repository, *arguments, **options)
            self.assertIsNotNone(report.notification_id)
            raise KeyboardInterrupt()
        with patch.object(SQLiteRansomLookWatchRepository, "run", interrupt_after_commit):
            self.assertEqual(self.invoke(*args)[0], 130)
        latest = self.result("collections", "list")["sessions"][0]
        history = self.result("collections", "show", latest["id"])
        receipt = next(row for row in history["receipts"] if row["result_kind"] == "ransomlook_watch_run")
        inbox = SQLiteInboxRepository(self.database)
        notice, = inbox.list("all").items
        self.assertEqual(receipt["result_id"], notice.notification.ransomlook_run_id)
        source_calls = self.ransomlook.calls
        self.result("collections", "resume", latest["id"])
        self.assertEqual(self.ransomlook.calls, source_calls)
        self.assertEqual(inbox.list("all").total_count, 1)
        self.assertEqual(self.rl.show(watch.id).total_run_count, 2)

    def test_notification_insert_failure_keeps_run_and_receipt_absent_then_resume_records_once(self):
        watch, args = self.baseline()
        with patch.object(SQLiteRansomLookWatchRepository, "_notify", side_effect=sqlite3.OperationalError("controlled notice write failure")):
            self.assertNotEqual(self.invoke(*args)[0], 0)
        latest = self.result("collections", "list")["sessions"][0]
        history = self.result("collections", "show", latest["id"])
        self.assertFalse(any(row["result_kind"] == "ransomlook_watch_run" for row in history["receipts"]))
        self.assertEqual(self.rl.show(watch.id).total_run_count, 1)
        self.assertEqual(SQLiteInboxRepository(self.database).list("all").total_count, 0)
        resumed = self.result("collections", "resume", latest["id"])
        receipt = next(row for row in resumed["history"]["receipts"] if row["result_kind"] == "ransomlook_watch_run")
        notice, = SQLiteInboxRepository(self.database).list("all").items
        self.assertEqual(receipt["result_id"], notice.notification.ransomlook_run_id)

    def test_source_failure_cannot_alert_from_old_snapshot(self):
        watch, args = self.baseline()
        self.ransomlook.value = SourceError("Kaynak kapalı.")
        self.result(*args, expected_code=3)
        self.assertEqual(self.rl.show(watch.id).total_run_count, 1)
        self.assertEqual(SQLiteInboxRepository(self.database).list("all").total_count, 0)


if __name__ == "__main__":
    unittest.main()

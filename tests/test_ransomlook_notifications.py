"""Source-isolated local notices, durable evidence and atomic read state."""

from contextlib import closing, redirect_stdout, redirect_stderr
from dataclasses import replace
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.adapters.sqlite_webhooks import SQLiteWebhookRepository
from xti.application.webhooks import WebhookService
from xti.domain.assets import ValidationError
from xti.domain.findings import DomainInput, ImportDocument, MatchCandidate
from xti.interfaces.cli import main
from xti.interfaces.inbox import detail_lines, page_lines
from xti.interfaces.ransomlook_watches import run_lines
from tests.test_ransomlook_ransomware import post
from tests import test_ransomlook_watches as fixtures
from tests.test_webhooks import FakeSender

NOW = fixtures.NOW


class RansomLookNotificationTests(unittest.TestCase):
    setUp = fixtures.RansomLookWatchTests.setUp
    apply = fixtures.RansomLookWatchTests.apply
    service = fixtures.RansomLookWatchTests.service

    def baseline(self):
        self.apply([post("Example Holding")], minute=1)
        watch = self.service(minute=2).add("Example", "Example", kind="organization", match_mode="contains").watch
        baseline = self.service(minute=3).run(watch.id)
        return watch, baseline

    def changed(self):
        watch, baseline = self.baseline()
        self.apply([post("Example Holding"), post("Example Labs")], minute=4)
        return watch, baseline, self.service(minute=5).run(watch.id)

    def finding(self):
        asset, _ = SQLiteAssetRepository(self.path).add("example.com")
        domain = "example-support.net"
        SQLiteFindingRepository(self.path).save_import(
            ImportDocument("fixture:notice", "notice:fixture", (DomainInput(domain, domain, 1, None),)),
            (MatchCandidate(asset.id, asset.value, domain, "rules-v1", ("Test eşleşmesi",)),),
        )
        return next(item.notification for item in SQLiteInboxRepository(self.path).list("all", 100).items
                    if item.notification.finding_id is not None)

    def test_baseline_repeat_removal_changed_definition_and_source_failure_are_silent(self):
        watch, baseline = self.baseline()
        inbox = SQLiteInboxRepository(self.path)
        self.assertIsNone(baseline.notification_id)
        self.assertIsNone(self.service(minute=4).run(watch.id).notification_id)
        self.apply([], minute=5)
        removed = self.service(minute=6).run(watch.id)
        self.assertEqual(removed.run.removed_count, 1)
        self.assertIsNone(removed.notification_id)
        self.apply([post("Example Labs")], minute=7)
        self.service(minute=8).add("Example", "Example Labs", kind="organization", match_mode="exact")
        changed_definition = self.service(minute=9).run(watch.id)
        self.assertTrue(changed_definition.is_baseline)
        self.assertIsNone(changed_definition.notification_id)
        self.claims.record_failure(started_at=(NOW + timedelta(minutes=10)).isoformat(),
            finished_at=(NOW + timedelta(minutes=11)).isoformat(), error="Kaynak erişilemiyor.")
        self.assertEqual(inbox.list("all").total_count, 0)

    def test_new_match_produces_one_source_specific_notice_with_full_run_link(self):
        watch, baseline, changed = self.changed()
        inbox = SQLiteInboxRepository(self.path)
        notice, = inbox.list().items
        self.assertIsNotNone(changed.notification_id)
        self.assertEqual(notice.notification.id, changed.notification_id)
        self.assertEqual(notice.notification.event_type, "ransomlook_watch_changed")
        self.assertEqual(notice.notification.ransomlook_run_id, changed.run.id)
        self.assertIsNone(notice.notification.ransomware_run_id)
        self.assertIsNone(notice.ransomware_change)
        self.assertEqual(notice.ransomlook_change.source, "ransomlook")
        self.assertEqual(notice.ransomlook_change.source_run_id, changed.run.source_run_id)
        self.assertEqual(notice.ransomlook_change.definition_sha256, changed.run.definition_sha256)
        self.assertEqual(self.watches.run_details(changed.run.id, item_limit=1).notification_id, changed.notification_id)
        self.assertIsNone(self.service(minute=6).run(watch.id).notification_id)
        self.assertEqual(inbox.list("all").total_count, 1)
        self.assertEqual(inbox.get(changed.notification_id).ransomlook_change.added_count, 1)

    def test_notification_or_receipt_failure_rolls_back_run_items_and_notice(self):
        watch, baseline = self.baseline()
        self.apply([post("Example Labs")], minute=4)
        before = self.path.read_bytes()
        for target in ("_notify", "receipt"):
            with self.subTest(target=target):
                manager = (patch.object(self.watches, "_notify", side_effect=sqlite3.OperationalError("controlled notification failure"))
                           if target == "_notify" else patch("xti.adapters.sqlite_ransomlook_watches.record_collection_step_receipt",
                                side_effect=StorageError("controlled receipt failure")))
                with manager, self.assertRaises(StorageError):
                    self.service(minute=5).run(watch.id)
                self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.watches.details(watch.id, event_limit=10, run_limit=10).total_run_count, 1)

    def test_global_sequence_paging_and_explicit_read_state_survive_clock_regression(self):
        first = self.finding()
        _, _, changed = self.changed()
        inbox = SQLiteInboxRepository(self.path)
        newest = inbox.list("all", limit=1)
        self.assertEqual(newest.items[0].notification.id, changed.notification_id)
        self.assertGreater(newest.items[0].notification.sequence, first.sequence)
        self.assertLess(newest.items[0].notification.created_at, first.created_at)
        self.assertEqual(inbox.list("all", limit=1, before=newest.next_before).items[0].notification.id, first.id)
        before = self.path.read_bytes()
        inbox.list(); inbox.get(changed.notification_id)
        self.assertEqual(self.path.read_bytes(), before)
        now = (NOW - timedelta(days=1)).isoformat()
        marked = inbox.mark((changed.notification_id, first.id), True, now)
        self.assertEqual(marked.changed_count, 2)
        self.assertEqual(marked.notifications[0].read_at, now)
        self.assertEqual(inbox.mark((changed.notification_id,), True, NOW.isoformat()).changed_count, 0)
        self.assertEqual(inbox.get(changed.notification_id).notification.read_at, now)
        self.assertEqual(inbox.mark((changed.notification_id,), False, NOW.isoformat()).changed_count, 1)

    def test_mixed_batch_invalid_id_and_partial_write_failure_leave_every_notice_unread(self):
        first = self.finding(); _, _, changed = self.changed()
        inbox = SQLiteInboxRepository(self.path)
        ids = (first.id, changed.notification_id)
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError): inbox.mark((*ids, "missing"), True, NOW.isoformat())
        self.assertEqual(self.path.read_bytes(), before)
        def partial(connection, identifiers, read, now):
            connection.execute("UPDATE notifications SET read_at=? WHERE id=?", (now, first.id))
            raise sqlite3.OperationalError("controlled mark failure")
        with patch.object(inbox, "_mark_rows", side_effect=partial), self.assertRaises(StorageError):
            inbox.mark(ids, True, NOW.isoformat())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(inbox.list().unread_count, 2)

    def test_wrong_watch_or_baseline_run_or_global_sequence_collision_fail_closed(self):
        first = self.finding(); watch, baseline, changed = self.changed()
        other = self.service(minute=6).add("Other", "Other", kind="organization").watch
        mutations = (("watch_id", other.id), ("run_id", baseline.run.id), ("sequence", first.sequence))
        for column, value in mutations:
            with self.subTest(column=column):
                backup = Path(self.temp.name) / f"corrupt-{column}.db"
                SQLiteAssetRepository(self.path).backup(backup)
                with closing(sqlite3.connect(backup)) as connection, connection:
                    connection.execute(f"UPDATE ransomlook_watch_notifications SET {column}=?", (value,))
                before = backup.read_bytes(); inbox = SQLiteInboxRepository(backup)
                for operation in (lambda: inbox.list(), lambda: inbox.get(changed.notification_id),
                                  lambda: inbox.mark((changed.notification_id,), True, NOW.isoformat())):
                    with self.assertRaises(StorageError): operation()
                self.assertEqual(backup.read_bytes(), before)

    def test_current_label_is_explicit_and_historical_definition_and_counts_survive_changes(self):
        watch, _, changed = self.changed()
        inbox = SQLiteInboxRepository(self.path)
        prior = inbox.get(changed.notification_id).ransomlook_change
        self.service(minute=6).add("EXAMPLE", "Other", kind="organization", match_mode="exact")
        self.service(minute=7).revoke(watch.id, reason="Artık izlenmiyor.")
        after = inbox.get(changed.notification_id).ransomlook_change
        self.assertEqual(after.current_watch_name, "EXAMPLE")
        self.assertEqual(replace(after, current_watch_name=prior.current_watch_name), prior)

    def test_backup_restore_preserves_read_time_run_and_inspection_counts(self):
        _, _, changed = self.changed()
        inbox = SQLiteInboxRepository(self.path)
        inbox.mark((changed.notification_id,), True, NOW.isoformat())
        original = inbox.get(changed.notification_id)
        backup, restored = Path(self.temp.name)/"backup.db", Path(self.temp.name)/"restored.db"
        SQLiteAssetRepository(self.path).backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteInboxRepository(restored).get(changed.notification_id), original)
        counts = SQLiteAssetRepository(restored).inspect()
        self.assertEqual((counts["ransomlook_watch_notification_count"], counts["notification_count"],
                          counts["unread_ransomlook_watch_notification_count"], counts["unread_notification_count"]), (1, 1, 0, 0))

    def test_terminal_json_and_explicit_webhook_queue_preserve_source_without_sending(self):
        _, _, changed = self.changed()
        inbox = SQLiteInboxRepository(self.path)
        details = inbox.get(changed.notification_id)
        lines = "\n".join(detail_lines(details) + page_lines(inbox.list(), status="unread", next_command=None) + run_lines(changed))
        self.assertIn("RansomLook", lines)
        self.assertIn(f"watch-run-show {changed.run.id} --source ransomlook", lines)
        untrusted = replace(details, ransomlook_change=replace(details.ransomlook_change, current_watch_name="name\x1b[31m"))
        self.assertNotIn("\x1b", "\n".join(detail_lines(untrusted)))
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", self.temp.name, "--json", "inbox", "show", changed.notification_id])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        data = json.loads(stdout.getvalue())["data"]
        self.assertEqual(data["ransomlook_change"]["source"], "ransomlook")
        sender = FakeSender()
        repository = SQLiteWebhookRepository(self.path)
        service = WebhookService(repository, inbox, sender, clock=lambda: NOW)
        destination = service.add_destination("Local", "https://hooks.example.test/xti", b"s"*32).destination
        queued, created = service.queue(destination.id, changed.notification_id)
        self.assertTrue(created)
        payload = json.loads(repository.delivery_target(queued.id).payload)
        self.assertEqual(payload["data"]["ransomlook_change"]["source"], "ransomlook")
        self.assertIsNone(payload["data"]["ransomware_change"])
        self.assertEqual(sender.calls, [])


if __name__ == "__main__":
    unittest.main()

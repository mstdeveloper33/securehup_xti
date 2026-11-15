"""Frozen search changes join the inbox atomically and remain recoverable."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_status import SQLiteStatusRepository
from xti.adapters.sqlite_webhooks import SQLiteWebhookRepository
from xti.application.inbox import InboxService
from xti.application.webhooks import WebhookService
from xti.interfaces.inbox import detail_lines, page_lines
from xti.interfaces.cli import build_parser
from tests import test_global_saved_search_cli as fixtures
from tests.test_webhooks import FakeSender


class GlobalSavedSearchNotificationTests(unittest.TestCase):
    setUp = fixtures.GlobalSavedSearchCLITests.setUp
    invoke = fixtures.GlobalSavedSearchCLITests.invoke
    result = fixtures.GlobalSavedSearchCLITests.result
    files = fixtures.GlobalSavedSearchCLITests.files
    add = fixtures.GlobalSavedSearchCLITests.add

    def create_notice(self):
        identifier = self.add("Example watch", "example", "--kind", "domain")
        baseline = self.service.run(identifier)
        self.assertIsNone(baseline.notification_id)
        self.storage.add("example.com")
        changed = self.service.run(identifier)
        self.assertIsNotNone(changed.notification_id)
        return identifier, changed

    def test_notice_list_show_mark_and_all_status_counts_agree(self):
        identifier, changed = self.create_notice()
        inbox = InboxService(SQLiteInboxRepository(self.database))
        before = self.files()
        page = inbox.list(status="all")
        self.assertEqual((page.total_count, page.unread_count), (1, 1))
        item = page.items[0]
        self.assertEqual(item.notification.global_search_run_id, changed.run.id)
        self.assertEqual(item.notification.event_type, "global_saved_search_changed")
        self.assertEqual(item.global_search_change.run, changed.run)
        details = inbox.show(changed.notification_id)
        self.assertEqual(details.global_search_change, item.global_search_change)
        self.assertIn("Genel arama eşleşmeleri değişti", "\n".join(page_lines(page, status="all", next_command=None)))
        self.assertIn("search-watch run-show " + changed.run.id, "\n".join(detail_lines(details)))
        self.assertEqual(self.files(), before)
        snapshot = SQLiteStatusRepository(self.database).snapshot(("crtsh",), None, 10)
        self.assertEqual((snapshot.notification_count, snapshot.unread_notification_count), (1, 1))
        counts = self.storage.inspect()
        self.assertEqual(counts["global_saved_search_notification_count"], 1)
        self.assertEqual(counts["unread_global_saved_search_notification_count"], 1)
        marked = inbox.mark((changed.notification_id,), read=True)
        self.assertEqual(marked.changed_count, 1)
        self.assertEqual(inbox.mark((changed.notification_id,), read=True).changed_count, 0)
        self.assertEqual(inbox.list(status="unread").unread_count, 0)
        self.assertEqual(SQLiteStatusRepository(self.database).snapshot(("crtsh",), None, 10).unread_notification_count, 0)
        self.assertEqual(self.storage.inspect()["unread_global_saved_search_notification_count"], 0)
        self.assertEqual(inbox.mark((changed.notification_id,), read=False).changed_count, 1)
        self.assertEqual(self.service.show_run(changed.run.id).run, changed.run)

    def test_multiple_notices_are_batch_verified_and_paginated_in_global_sequence(self):
        identifier, first = self.create_notice()
        self.storage.add("second.example")
        second = self.service.run(identifier)
        self.storage.add("third.example")
        third = self.service.run(identifier)
        repository = SQLiteInboxRepository(self.database)
        method = SQLiteGlobalSavedSearchRepository.notification_evidences
        with patch.object(SQLiteGlobalSavedSearchRepository, "notification_evidences", wraps=method) as read:
            page = repository.list("all", 2)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(read.call_args.args[1], (third.notification_id, second.notification_id))
        self.assertEqual([item.notification.id for item in page.items], [third.notification_id, second.notification_id])
        last = repository.list("all", 2, page.next_before)
        self.assertEqual([item.notification.id for item in last.items], [first.notification_id])
        self.assertIsNone(last.next_before)
        self.assertEqual((last.total_count, last.matching_count), (3, 3))
        with patch.object(SQLiteGlobalSavedSearchRepository, "notification_evidences", wraps=method) as read:
            repository.mark((first.notification_id, second.notification_id), True, datetime.now(timezone.utc).isoformat())
        self.assertEqual(read.call_count, 1)

    def test_notification_keeps_historical_definition_and_evidence_after_update_or_disable(self):
        identifier, changed = self.create_notice()
        old = SQLiteInboxRepository(self.database).get(changed.notification_id).global_search_change
        self.service.add("Example watch", "changed", kinds=("cti",))
        self.service.disable(identifier, reason="Yeni tanım şimdilik durduruldu.")
        frozen = SQLiteInboxRepository(self.database).get(changed.notification_id).global_search_change
        self.assertEqual(frozen, old)
        self.assertEqual((frozen.saved_search.query, frozen.saved_search.kinds), ("example", ("domain",)))
        self.assertEqual(self.service.show(identifier).saved_search.query, "changed")

    def test_inbox_bounded_evidence_links_to_remaining_frozen_items_in_same_workspace(self):
        identifier = self.add("Example watch", "example", "--kind", "domain")
        self.service.run(identifier)
        for index in range(51):
            self.storage.add(f"item{index}.example")
        report = self.service.run(identifier)
        data = self.result("inbox", "show", report.notification_id)
        evidence = data["global_search_change"]
        self.assertEqual((evidence["total_item_count"], len(evidence["items"]), evidence["has_more"]), (51, 50, True))
        code, text, err = self.invoke("inbox", "show", report.notification_id, json_output=False)
        self.assertEqual((code, err), (0, ""))
        command = next(line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("Sonraki kanıt sayfası:"))
        parsed = build_parser().parse_args(shlex.split(command)[1:])
        self.assertEqual(Path(parsed.data_dir).resolve(), self.data.resolve())
        self.assertEqual((parsed.run_id, parsed.offset, parsed.limit), (report.run.id, 50, 50))
        remainder = self.result("search-watch", "run-show", report.run.id, "--offset", "50", "--limit", "50")
        self.assertEqual(len(remainder["items"]), 1)
        self.assertNotIn(remainder["items"][0]["key"], {item["key"] for item in evidence["items"]})

    def test_notification_failure_rolls_back_entire_run(self):
        identifier = self.add("Example watch", "example", "--kind", "domain")
        baseline = self.service.run(identifier)
        self.storage.add("example.com")
        before = self.files()
        with patch("xti.adapters.sqlite_global_saved_searches.next_notification_sequence", side_effect=StorageError("controlled notice failure")):
            with self.assertRaisesRegex(StorageError, "controlled"):
                self.service.run(identifier)
        self.assertEqual(self.files(), before)
        details = self.service.show(identifier)
        self.assertEqual((details.total_run_count, details.runs[0].id), (1, baseline.run.id))
        self.assertEqual(SQLiteInboxRepository(self.database).list("all").total_count, 0)

    def test_corrupt_notification_binding_prevents_show_list_and_mark_without_changes(self):
        _, changed = self.create_notice()
        other = self.add("Other watch", "other")
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE global_saved_search_notifications SET search_id=? WHERE id=?",
                               (other, changed.notification_id))
            connection.commit()
        before = self.files()
        repository = SQLiteInboxRepository(self.database)
        for action in (lambda: repository.get(changed.notification_id), lambda: repository.list("all"),
                       lambda: repository.mark((changed.notification_id,), True, datetime.now(timezone.utc).isoformat())):
            with self.assertRaises(StorageError):
                action()
        self.assertEqual(self.files(), before)

    def test_backup_restore_preserves_frozen_run_read_state_and_next_notification_order(self):
        identifier, changed = self.create_notice()
        inbox = InboxService(SQLiteInboxRepository(self.database))
        inbox.mark((changed.notification_id,), read=True)
        original = inbox.show(changed.notification_id)
        backup, restored = self.root / "backup.db", self.root / "restored.db"
        self.storage.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        restored_inbox = SQLiteInboxRepository(restored)
        self.assertEqual(restored_inbox.get(changed.notification_id), original)
        from xti.interfaces.global_saved_searches import make_global_saved_search_service
        service = make_global_saved_search_service(restored)
        SQLiteAssetRepository(restored).add("later.example")
        next_run = service.run(identifier)
        later = restored_inbox.get(next_run.notification_id)
        self.assertGreater(later.notification.sequence, original.notification.sequence)
        self.assertEqual(restored_inbox.get(changed.notification_id), original)
        self.assertEqual(self.service.show(identifier).total_run_count, 2)

    def test_manual_webhook_queue_preserves_new_notice_without_automatic_delivery(self):
        _, changed = self.create_notice()
        sender = FakeSender()
        webhook_repository = SQLiteWebhookRepository(self.database)
        webhooks = WebhookService(webhook_repository, SQLiteInboxRepository(self.database), sender)
        destination = webhooks.add_destination("Manual destination", "https://hooks.example.test/xti", b"s" * 32).destination
        self.assertEqual(webhooks.list_deliveries().total_count, 0)
        delivery, created = webhooks.queue(destination.id, changed.notification_id)
        self.assertTrue(created)
        self.assertEqual(delivery.event_type, "global_saved_search_changed")
        self.assertEqual(sender.calls, [])
        target = webhook_repository.delivery_target(delivery.id)
        payload = json.loads(target.payload)
        self.assertEqual(payload["data"]["notification"]["global_search_run_id"], changed.run.id)
        self.assertEqual(payload["data"]["global_search_change"]["run"]["id"], changed.run.id)
        repeated, recreated = webhooks.queue(destination.id, changed.notification_id)
        self.assertFalse(recreated)
        self.assertEqual(repeated.id, delivery.id)


if __name__ == "__main__":
    unittest.main()

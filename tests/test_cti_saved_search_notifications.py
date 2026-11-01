"""Meaningful saved CTI search changes create deduplicated local inbox notices."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_cti_saved_searches import SQLiteCtiSavedSearchRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.application.cti_saved_searches import CtiSavedSearchService
from xti.application.inbox import InboxService
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 30, 0, tzinfo=timezone.utc)


class CtiSavedSearchNotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.now = NOW
        self.saved = CtiSavedSearchService(
            SQLiteCtiSavedSearchRepository(self.path), clock=lambda: self.now,
        )
        self.knowledge = CtiKnowledgeService(
            SQLiteCtiKnowledgeRepository(self.path), clock=lambda: self.now,
        )
        self.inbox = InboxService(
            SQLiteInboxRepository(self.path), clock=lambda: self.now,
        )

    def advance(self):
        self.now += timedelta(minutes=1)

    def entity(self, name, source):
        return self.knowledge.add_entity(
            "malware", name, aliases=(), source_name=source,
            source_reference=f"local:{source}", confidence=70,
            description="CTI kayıtlı arama değişiklik bildirimi kabul kaydı.",
        )

    def test_baseline_is_silent_but_later_change_enters_inbox_and_can_be_read(self):
        watch = self.saved.add("Example watch", "Example", kind="entity")
        self.entity("Example One", "one")
        baseline = self.saved.run(watch.saved_search.id)
        self.assertIsNone(baseline.notification_id)
        self.assertEqual(self.inbox.list(status="all").total_count, 0)

        self.advance()
        added = self.entity("Example Two", "two")
        changed = self.saved.run(watch.saved_search.id)
        self.assertEqual((changed.run.added_count, changed.run.unchanged_count), (1, 1))
        self.assertIsNotNone(changed.notification_id)
        page = self.inbox.list(status="unread")
        self.assertEqual((page.total_count, page.unread_count), (1, 1))
        item = page.items[0]
        self.assertEqual(item.notification.event_type, "cti_saved_search_changed")
        self.assertEqual(item.notification.cti_run_id, changed.run.id)
        self.assertEqual(item.cti_change.run_id, changed.run.id)
        self.assertEqual(item.cti_change.added_count, 1)
        self.assertEqual(
            self.inbox.show(changed.notification_id).cti_change, item.cti_change,
        )
        marked = self.inbox.mark((changed.notification_id,), read=True)
        self.assertEqual(marked.changed_count, 1)
        self.assertEqual(self.inbox.list(status="unread").unread_count, 0)
        self.assertEqual(self.saved.show_run(changed.run.id).notification_id,
                         changed.notification_id)
        self.assertEqual(added.entity.display_name, "Example Two")

    def test_unchanged_and_new_definition_baselines_do_not_create_noise(self):
        watch = self.saved.add("Example watch", "Example", kind="entity")
        self.entity("Example One", "one")
        self.saved.run(watch.saved_search.id)
        self.advance()
        unchanged = self.saved.run(watch.saved_search.id)
        self.assertIsNone(unchanged.notification_id)
        self.advance()
        changed_definition = self.saved.add(
            "Example watch", "One", kind="entity",
        )
        reset = self.saved.run(changed_definition.saved_search.id)
        self.assertIsNone(reset.run.previous_run_id)
        self.assertIsNone(reset.notification_id)
        self.assertEqual(self.inbox.list(status="all").total_count, 0)

    def test_notification_failure_rolls_back_run_and_all_items(self):
        watch = self.saved.add("Example watch", "Example", kind="entity")
        self.entity("Example One", "one")
        baseline = self.saved.run(watch.saved_search.id)
        self.advance()
        self.entity("Example Two", "two")
        with patch(
            "xti.adapters.sqlite_cti_saved_searches.next_notification_sequence",
            side_effect=StorageError("controlled notification failure"),
        ):
            with self.assertRaisesRegex(StorageError, "controlled"):
                self.saved.run(watch.saved_search.id)
        details = self.saved.show(watch.saved_search.id)
        self.assertEqual((details.total_run_count, details.runs[0].id), (1, baseline.run.id))
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM cti_saved_search_notifications"
            ).fetchone()[0], 0)

    def test_misdirected_hidden_notification_fails_closed_everywhere(self):
        first = self.saved.add("Example watch", "Example", kind="entity")
        second = self.saved.add("Other watch", "Other", kind="entity")
        self.entity("Example One", "one")
        self.saved.run(first.saved_search.id)
        self.advance()
        self.entity("Example Two", "two")
        changed = self.saved.run(first.saved_search.id)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute(
                "UPDATE cti_saved_search_notifications SET saved_search_id=? WHERE id=?",
                (second.saved_search.id, changed.notification_id),
            )
        corrupt = self.path.read_bytes()
        for call in (
            lambda: self.saved.list(),
            lambda: self.inbox.list(status="all"),
            lambda: self.inbox.show(changed.notification_id),
        ):
            with self.assertRaises(StorageError):
                call()
        self.assertEqual(self.path.read_bytes(), corrupt)

    def call_cli(self, *arguments):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_run_reports_notice_and_unified_inbox_shows_cti_evidence(self):
        watch = self.saved.add("Example watch", "Example", kind="entity")
        self.entity("Example One", "one")
        self.saved.run(watch.saved_search.id)
        self.entity("Example Two", "two")
        code, output, error = self.call_cli("cti", "watch-run", watch.saved_search.id)
        self.assertEqual((code, error), (0, ""))
        notification_id = json.loads(output)["data"]["notification_id"]
        self.assertIsNotNone(notification_id)
        code, output, error = self.call_cli("inbox", "show", notification_id)
        self.assertEqual((code, error), (0, ""))
        data = json.loads(output)["data"]
        self.assertEqual(data["notification"]["event_type"], "cti_saved_search_changed")
        self.assertEqual(data["cti_change"]["added_count"], 1)


if __name__ == "__main__":
    unittest.main()

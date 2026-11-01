"""Durable organization/domain watches over stored public ransomware claims."""

from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.ransomware_watches import RansomwareWatchService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from tests.test_threatcluster_ransomware import claim, content


NOW = datetime(2026, 10, 30, 17, tzinfo=timezone.utc)


def snapshot(records, *, minute=0):
    return parse_threatcluster_ransomware_response(
        content(records), fetched_at=NOW + timedelta(minutes=minute),
    )


class RansomwareWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.claims = SQLiteRansomwareClaimRepository(self.path)
        self.watches = SQLiteRansomwareWatchRepository(self.path)

    def apply(self, records, *, minute):
        return self.claims.apply(
            snapshot(records, minute=minute),
            started_at=(NOW + timedelta(minutes=minute, seconds=1)).isoformat(),
            finished_at=(NOW + timedelta(minutes=minute, seconds=2)).isoformat(),
            item_limit=100,
        )

    def service(self, *, minute):
        return RansomwareWatchService(
            self.watches, self.claims,
            clock=lambda: NOW + timedelta(minutes=minute, seconds=3),
        )

    def test_first_run_is_silent_then_added_and_updated_enter_unified_inbox(self):
        self.apply([
            claim("Example Holding", website="www.example.com"),
            claim(
                "Other Company", group="other", website="other.example",
                discovered="2026-10-29T12:00:00Z",
            ),
        ], minute=1)
        watch = self.service(minute=2).add(
            "Example kuruluşu", "Example", kind="organization", match_mode="contains",
        ).watch
        baseline = self.service(minute=3).run(watch.id)
        self.assertTrue(baseline.is_baseline)
        self.assertEqual((baseline.run.total_count, baseline.notification_id), (1, None))
        self.assertEqual(SQLiteInboxRepository(self.path).list().total_count, 0)

        self.apply([
            claim("Example Holding", website="www.example.com", sector="Finance"),
            claim(
                "Example Labs", group="second", website="labs.example.com",
                discovered="2026-10-28T12:00:00Z",
            ),
        ], minute=4)
        changed = self.service(minute=5).run(watch.id)
        self.assertEqual(
            (changed.run.added_count, changed.run.updated_count,
             changed.run.unchanged_count, changed.run.removed_count),
            (1, 1, 0, 0),
        )
        self.assertIsNotNone(changed.notification_id)
        page = SQLiteInboxRepository(self.path).list()
        self.assertEqual((page.total_count, page.unread_count), (1, 1))
        self.assertEqual(page.items[0].ransomware_change.watch_id, watch.id)
        details = SQLiteInboxRepository(self.path).get(changed.notification_id)
        self.assertEqual(details.ransomware_change.run_id, changed.run.id)

    def test_domain_matches_exact_or_subdomain_and_removed_only_is_silent(self):
        self.apply([
            claim("Acme", website="https://portal.acme.example/path"),
            claim(
                "Wrong", group="wrong", website="notacme.example",
                discovered="2026-10-29T12:00:00Z",
            ),
        ], minute=1)
        watch = self.service(minute=2).add(
            "Acme domain", "acme.example", kind="domain",
        ).watch
        baseline = self.service(minute=3).run(watch.id)
        self.assertEqual(baseline.run.total_count, 1)
        self.assertEqual(baseline.items[0].match.match_type, "subdomain")

        self.apply([], minute=4)
        removed = self.service(minute=5).run(watch.id)
        self.assertEqual((removed.run.removed_count, removed.notification_id), (1, None))
        self.assertEqual(SQLiteInboxRepository(self.path).list().total_count, 0)

    def test_definition_change_creates_new_silent_baseline_and_validation_is_strict(self):
        self.apply([claim("Example Holding")], minute=1)
        watch = self.service(minute=2).add(
            "Kuruluş izlemesi", "Example Holding", kind="organization",
        ).watch
        first = self.service(minute=3).run(watch.id)
        updated = self.service(minute=4).add(
            "Kuruluş izlemesi", "Holding", kind="organization", match_mode="contains",
        )
        second = self.service(minute=5).run(updated.watch.id)
        self.assertTrue(first.is_baseline)
        self.assertTrue(second.is_baseline)
        self.assertIsNone(second.notification_id)
        with self.assertRaises(ValidationError):
            self.service(minute=6).add(
                "Hatalı domain", "example.com", kind="domain", match_mode="contains",
            )
        with self.assertRaises(ValidationError):
            self.service(minute=6).add(
                "Kısa contains", "abc", kind="organization", match_mode="contains",
            )

    def test_corrupt_notification_relation_fails_closed(self):
        self.apply([claim("Example Holding")], minute=1)
        watch = self.service(minute=2).add(
            "Example", "Example Holding", kind="organization",
        ).watch
        self.service(minute=3).run(watch.id)
        self.apply([
            claim("Example Holding", sector="Finance"),
        ], minute=4)
        changed = self.service(minute=5).run(watch.id)
        other = self.service(minute=6).add(
            "Başka izleme", "Other Company", kind="organization",
        ).watch
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ransomware_watch_notifications SET watch_id=? WHERE id=?",
                (other.id, changed.notification_id),
            )
        with self.assertRaises(StorageError):
            SQLiteInboxRepository(self.path).list()

    def test_cli_add_list_run_and_run_show_are_terminal_first(self):
        self.apply([claim("Example Holding")], minute=1)
        values = ["--data-dir", self.temp.name]
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                *values, "ransomware", "watch-add", "Example kuruluşu",
                "Example Holding", "--kind", "organization",
            ]), 0)
        watch_id = self.watches.list(active_only=True, limit=10)[0].watch.id
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                *values, "ransomware", "watch-run", watch_id,
            ]), 0)
        self.assertIn("sessiz başlangıç", output.getvalue())
        run_id = self.watches.list(active_only=True, limit=10)[0].last_run.id
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                *values, "ransomware", "watch-run-show", run_id,
            ]), 0)
        self.assertIn("doğrulanmış ihlal değildir", output.getvalue())


if __name__ == "__main__":
    unittest.main()

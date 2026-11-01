"""Atomic local notices, stable pages and explicit read state preserve evidence."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_assessments import SQLiteAssessmentRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.domain.assets import ValidationError
from xti.domain.findings import DomainInput, ImportDocument, MatchCandidate
from tests.test_assessments_storage import checked


NOW = "2026-10-29T08:00:00+00:00"
LATER = "2026-10-29T09:00:00+00:00"


class InboxStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.asset, _ = self.assets.add("example.com")
        self.findings = SQLiteFindingRepository(self.path)
        self.inbox = SQLiteInboxRepository(self.path)

    def create(self, domain="example-support.net", *, source="first", rule="rules-v1"):
        document = ImportDocument("fixture:" + source, source + ":" + domain, (
            DomainInput(domain, domain, 1, None),
        ))
        candidate = MatchCandidate(self.asset.id, self.asset.value, domain, rule, ("Test eşleşmesi",))
        self.findings.save_import(document, (candidate,))
        page = self.inbox.list("all", 100)
        return next(item for item in page.items if item.finding.domain == domain and item.finding.rule_version == rule)

    def dump(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return tuple(connection.iterdump())

    def test_new_finding_and_notice_are_saved_together(self):
        item = self.create()
        self.assertEqual(item.notification.finding_id, item.finding.id)
        self.assertEqual(item.notification.event_type, "finding_created")
        self.assertEqual(item.notification.origin, "new")
        self.assertIsNone(item.notification.read_at)
        self.assertEqual(item.notification.created_at, item.finding.created_at)
        details = self.inbox.get(item.notification.id)
        self.assertEqual(details.notification, item.notification)
        self.assertEqual(details.details.finding, item.finding)
        self.assertEqual(len(details.details.observations), 1)

    def test_ten_replays_new_source_review_and_check_do_not_duplicate_or_reset_notice(self):
        item = self.create()
        read = self.inbox.mark((item.notification.id,), True, NOW).notifications[0]
        for _ in range(10):
            self.create()
        self.create(source="second-source")
        self.findings.review_finding(item.finding.id, "dismissed", "Kullanıcı inceledi.")
        SQLiteAssessmentRepository(self.path).append(item.finding.id, checked())
        page = self.inbox.list("all")
        self.assertEqual(page.total_count, 1)
        self.assertEqual(page.unread_count, 0)
        self.assertEqual(page.items[0].notification, read)
        self.assertEqual(page.items[0].finding.status, "dismissed")
        self.assertEqual(len(self.inbox.get(item.notification.id).details.observations), 2)

    def test_rule_version_creates_distinct_finding_and_notice(self):
        first = self.create()
        second = self.create(rule="rules-v2")
        self.assertNotEqual(first.finding.id, second.finding.id)
        self.assertNotEqual(first.notification.id, second.notification.id)
        self.assertEqual(self.inbox.list().total_count, 2)

    def test_same_domain_for_different_assets_produces_separate_notices(self):
        first = self.create()
        other, _ = self.assets.add("example.net")
        self.findings.save_import(
            ImportDocument("fixture:first", "first:example-support.net", (
                DomainInput("example-support.net", "example-support.net", 1, None),
            )),
            (MatchCandidate(other.id, other.value, "example-support.net", "rules-v1", ("Test",)),),
        )
        items = self.inbox.list().items
        self.assertEqual(len(items), 2)
        self.assertEqual({item.finding.asset_value for item in items}, {"example.com", "example.net"})
        self.assertIn(first.notification, [item.notification for item in items])

    def test_notification_failure_rolls_back_observations_findings_and_links(self):
        self.create()
        before = self.dump()
        with patch.object(SQLiteFindingRepository, "_notify_new_finding", side_effect=sqlite3.OperationalError("disk failed")):
            with self.assertRaises(StorageError):
                self.create("example-login.net")
        self.assertEqual(self.dump(), before)

    def test_later_invalid_candidate_rolls_back_earlier_notice_in_same_import(self):
        before = self.dump()
        document = ImportDocument("fixture:atomic", "atomic", (
            DomainInput("example-login.net", "example-login.net", 1, None),
            DomainInput("example-support.net", "example-support.net", 2, None),
        ))
        candidates = (
            MatchCandidate(self.asset.id, self.asset.value, "example-login.net", "rules-v1", ("Test",)),
            MatchCandidate("missing-asset", "missing.com", "example-support.net", "rules-v1", ("Test",)),
        )
        with self.assertRaises(StorageError):
            self.findings.save_import(document, candidates)
        self.assertEqual(self.dump(), before)

    def test_list_and_details_are_read_only_and_do_not_mark_read(self):
        item = self.create()
        before = self.path.read_bytes()
        self.inbox.list()
        self.inbox.get(item.notification.id)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.inbox.list().unread_count, 1)

    def test_explicit_read_unread_is_idempotent_and_preserves_finding_decisions(self):
        item = self.create()
        self.findings.review_finding(item.finding.id, "suspicious", "İnceleme gerekiyor.")
        original = self.findings.get_finding(item.finding.id)
        marked = self.inbox.mark((item.notification.id,), True, NOW)
        self.assertEqual(marked.changed_count, 1)
        self.assertEqual(marked.notifications[0].read_at, NOW)
        before = self.path.read_bytes()
        repeated = self.inbox.mark((item.notification.id,), True, LATER)
        self.assertEqual(repeated.changed_count, 0)
        self.assertEqual(repeated.notifications, marked.notifications)
        self.assertEqual(self.path.read_bytes(), before)
        unread = self.inbox.mark((item.notification.id,), False, LATER)
        self.assertEqual(unread.changed_count, 1)
        self.assertIsNone(unread.notifications[0].read_at)
        before = self.path.read_bytes()
        self.assertEqual(self.inbox.mark((item.notification.id,), False, LATER).changed_count, 0)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.findings.get_finding(item.finding.id), original)

    def test_bulk_mark_deduplicates_in_input_order_and_validates_all_before_write(self):
        first = self.create("example-login.net")
        second = self.create("example-support.net")
        identifiers = (first.notification.id, second.notification.id)
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.inbox.mark((*identifiers, "missing"), True, NOW)
        self.assertEqual(self.path.read_bytes(), before)
        result = self.inbox.mark((identifiers[1], identifiers[0], identifiers[1]), True, NOW)
        self.assertEqual(result.changed_count, 2)
        self.assertEqual(tuple(item.id for item in result.notifications), (identifiers[1], identifiers[0]))

    def test_partial_mark_failure_or_interrupt_rolls_back_whole_batch(self):
        first = self.create("example-login.net")
        second = self.create("example-support.net")
        identifiers = (first.notification.id, second.notification.id)
        for failure in (sqlite3.OperationalError("failed"), KeyboardInterrupt()):
            before = self.path.read_bytes()

            def partial(connection, ids, read, now):
                connection.execute("UPDATE notifications SET read_at = ? WHERE id = ?", (now, ids[0]))
                raise failure

            expected = StorageError if isinstance(failure, sqlite3.Error) else KeyboardInterrupt
            with self.subTest(failure=type(failure).__name__):
                with patch.object(SQLiteInboxRepository, "_mark_rows", side_effect=partial):
                    with self.assertRaises(expected):
                        self.inbox.mark(identifiers, True, NOW)
                self.assertEqual(self.path.read_bytes(), before)

    def test_cursor_page_survives_new_arrivals_and_counts_are_overall_filter_totals(self):
        original = [self.create(f"example-name{i}.net") for i in range(5)]
        self.inbox.mark((original[1].notification.id,), True, NOW)
        first = self.inbox.list("unread", 2)
        self.assertEqual((first.total_count, first.unread_count, first.matching_count), (5, 4, 4))
        self.assertEqual([item.notification.id for item in first.items],
                         [original[4].notification.id, original[3].notification.id])
        self.assertEqual(first.next_before, original[3].notification.sequence)
        new = self.create("example-latest.net")
        second = self.inbox.list("unread", 2, first.next_before)
        self.assertEqual([item.notification.id for item in second.items],
                         [original[2].notification.id, original[0].notification.id])
        self.assertNotIn(new, second.items)
        self.assertIsNone(second.next_before)
        self.assertEqual((second.total_count, second.unread_count, second.matching_count), (6, 5, 5))
        read = self.inbox.list("read", 2)
        self.assertEqual(read.matching_count, 1)
        self.assertEqual(read.items[0].notification.id, original[1].notification.id)
        self.assertEqual(self.inbox.list("all", 100, 1).items, ())

    def test_sequence_order_survives_clock_regression_and_vacuum(self):
        first = self.create("example-first.net")
        second = self.create("example-second.net")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE notifications SET created_at = ? WHERE id = ?",
                               ("2000-01-01T00:00:00+00:00", second.notification.id))
        before = self.inbox.list("all")
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("VACUUM")
        after = self.inbox.list("all")
        self.assertEqual(before, after)
        self.assertEqual([item.notification.id for item in after.items], [second.notification.id, first.notification.id])

    def test_read_time_normalizes_offset_and_retains_clock_regression(self):
        item = self.create()
        result = self.inbox.mark((item.notification.id,), True, "2000-01-01T03:00:00+03:00")
        self.assertEqual(result.notifications[0].read_at, "2000-01-01T00:00:00+00:00")

    def test_backup_restore_preserves_identity_and_read_state(self):
        first = self.create("example-first.net")
        second = self.create("example-second.net")
        self.inbox.mark((first.notification.id,), True, NOW)
        expected = self.inbox.list("all")
        backup = self.path.parent / "backup.db"
        self.assets.backup(backup)
        self.inbox.mark((second.notification.id,), True, LATER)
        restored = self.path.parent / "restored.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteInboxRepository(restored).list("all"), expected)

    def test_missing_storage_and_invalid_parameters_never_create_data(self):
        missing = self.path.parent / "missing" / "xti.db"
        inbox = SQLiteInboxRepository(missing)
        for action in (lambda: inbox.list(), lambda: inbox.get("missing"),
                       lambda: inbox.mark(("missing",), True, NOW)):
            with self.assertRaises(StorageError):
                action()
            self.assertFalse(missing.parent.exists())
        for arguments in (("bad", 20, None), ("all", 0, None), ("all", 101, None),
                          ("all", True, None), ("all", 20, 0), ("all", 20, True),
                          ("all", 20, 2**63)):
            with self.subTest(arguments=arguments), self.assertRaises(ValidationError):
                inbox.list(*arguments)
        for ids, read, now in (((), True, NOW), (("x",) * 101, True, NOW), ("x", True, NOW),
                               (("bad\n",), True, NOW), (("x",), 1, NOW),
                               (("x",), True, "no-time"), (("x",), True, "2026-10-29T08:00:00")):
            with self.subTest(ids=ids, now=now), self.assertRaises(ValidationError):
                inbox.mark(ids, read, now)
        self.assertFalse(missing.parent.exists())

    def test_corrupt_notice_is_not_marked_or_silently_accepted(self):
        item = self.create()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE notifications SET created_at = 'not-a-time' WHERE id = ?",
                               (item.notification.id,))
        before = self.path.read_bytes()
        for action in (lambda: self.inbox.list(), lambda: self.inbox.get(item.notification.id),
                       lambda: self.inbox.mark((item.notification.id,), True, NOW)):
            with self.assertRaises(StorageError):
                action()
            self.assertEqual(self.path.read_bytes(), before)

    def test_details_are_one_snapshot_during_concurrent_finding_review(self):
        item = self.create()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        original = SQLiteInboxRepository._get
        reviewed = False

        def concurrent_review(connection, identifier):
            nonlocal reviewed
            notice = original(connection, identifier)
            if not reviewed:
                reviewed = True
                self.findings.review_finding(item.finding.id, "dismissed", "Concurrent decision")
            return notice

        with patch.object(SQLiteInboxRepository, "_get", side_effect=concurrent_review):
            details = self.inbox.get(item.notification.id)
        self.assertEqual(details.details.finding.status, "new")
        self.assertEqual(details.details.reviews, ())
        self.assertEqual(self.findings.get_finding(item.finding.id).finding.status, "dismissed")


if __name__ == "__main__":
    unittest.main()

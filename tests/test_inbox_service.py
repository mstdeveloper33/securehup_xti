"""Validate explicit inbox operations before crossing the persistence port."""

from datetime import datetime, timedelta, timezone, tzinfo
import unittest
from unittest.mock import Mock

from xti.application.inbox import InboxService
from xti.domain.assets import ValidationError
from xti.domain.inbox import InboxPage, MarkResult


class UnspecifiedTimezone(tzinfo):
    def utcoffset(self, value):
        return None


class InboxServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=["list", "get", "mark"])
        self.clock = Mock(return_value=datetime(2026, 10, 29, 3, 4, 5, tzinfo=timezone.utc))
        self.service = InboxService(self.repository, self.clock)

    def test_default_view_is_unread_and_never_reads_clock_or_marks(self):
        page = InboxPage((), None, 0, 0, 0)
        self.repository.list.return_value = page
        self.assertIs(self.service.list(), page)
        self.repository.list.assert_called_once_with("unread", 20, None)
        self.repository.mark.assert_not_called()
        self.clock.assert_not_called()

    def test_explicit_page_parameters_reach_the_repository_unchanged(self):
        for status in ("unread", "read", "all"):
            with self.subTest(status=status):
                self.service.list(status=status, limit=100, before=2**63 - 1)
                self.repository.list.assert_called_with(status, 100, 2**63 - 1)
        self.service.list(limit=1, before=1)
        self.repository.list.assert_called_with("unread", 1, 1)
        self.clock.assert_not_called()

    def test_invalid_status_does_not_access_storage(self):
        for status in (None, "", "new", "READ", [], True, 1):
            with self.subTest(status=status), self.assertRaises(ValidationError):
                self.service.list(status=status)
        self.assertEqual(self.repository.mock_calls, [])

    def test_invalid_limits_and_cursors_do_not_access_storage(self):
        for limit in (0, -1, 101, True, 1.0, "20", None):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                self.service.list(limit=limit)
        for before in (0, -1, 2**63, True, 1.0, "20", []):
            with self.subTest(before=before), self.assertRaises(ValidationError):
                self.service.list(before=before)
        self.assertEqual(self.repository.mock_calls, [])

    def test_show_does_not_mark_read_or_read_clock(self):
        details = object()
        self.repository.get.return_value = details
        self.assertIs(self.service.show("notification-1"), details)
        self.repository.get.assert_called_once_with("notification-1")
        self.repository.mark.assert_not_called()
        self.clock.assert_not_called()

    def test_invalid_notification_ids_are_rejected_before_storage(self):
        for notification_id in (None, 1, b"id", "", " ", "a" * 65, "bad\x1bid", "bad\nid", "bad\u202eid"):
            with self.subTest(notification_id=notification_id):
                with self.assertRaises(ValidationError):
                    self.service.show(notification_id)
                with self.assertRaises(ValidationError):
                    self.service.mark(["valid-id", notification_id])
        self.assertEqual(self.repository.mock_calls, [])
        self.clock.assert_not_called()

    def test_mark_deduplicates_ids_in_order_and_uses_one_timestamp(self):
        result = MarkResult((), 2)
        self.repository.mark.return_value = result
        self.assertIs(self.service.mark(["second", "first", "second"]), result)
        self.repository.mark.assert_called_once_with(
            ("second", "first"), True, "2026-10-29T03:04:05+00:00",
        )
        self.clock.assert_called_once_with()

    def test_unread_is_an_explicit_write_and_normalizes_offset_to_utc(self):
        self.clock.return_value = datetime(2026, 10, 29, 3, 4, 5, 123, tzinfo=timezone(timedelta(hours=3)))
        self.service.mark(("notice",), read=False)
        self.repository.mark.assert_called_once_with(
            ("notice",), False, "2026-10-29T00:04:05.000123+00:00",
        )

    def test_mark_list_bound_applies_before_deduplication(self):
        self.service.mark(["same"] * 100)
        self.repository.mark.assert_called_once()
        self.repository.reset_mock()
        self.clock.reset_mock()
        with self.assertRaises(ValidationError):
            self.service.mark(["same"] * 101)
        self.repository.mark.assert_not_called()
        self.clock.assert_not_called()

    def test_mark_rejects_non_sequences_and_empty_ids(self):
        for ids in (None, [], (), "notice", b"notice", {"notice"}, {"notice": 1}, iter(["notice"])):
            with self.subTest(ids=ids), self.assertRaises(ValidationError):
                self.service.mark(ids)
        self.assertEqual(self.repository.mock_calls, [])
        self.clock.assert_not_called()

    def test_mark_rejects_non_boolean_read_state(self):
        for read in (None, 0, 1, "read", "unread", []):
            with self.subTest(read=read), self.assertRaises(ValidationError):
                self.service.mark(["notice"], read=read)
        self.assertEqual(self.repository.mock_calls, [])
        self.clock.assert_not_called()

    def test_invalid_clock_never_mutates_storage(self):
        invalid_times = (
            None, "2026-10-29T03:04:05Z", datetime(2026, 10, 29),
            datetime(2026, 10, 29, tzinfo=UnspecifiedTimezone()),
            datetime.min.replace(tzinfo=timezone(timedelta(hours=1))),
            datetime.max.replace(tzinfo=timezone(timedelta(hours=-1))),
        )
        for now in invalid_times:
            with self.subTest(now=now), self.assertRaises(ValidationError):
                self.clock.return_value = now
                self.service.mark(["notice"])
        self.assertEqual(self.repository.mock_calls, [])

    def test_repository_failure_propagates_without_a_second_write(self):
        self.repository.mark.side_effect = ValidationError("Bildirim bulunamadı.")
        with self.assertRaisesRegex(ValidationError, "bulunamadı"):
            self.service.mark(["known", "missing"])
        self.assertEqual(self.repository.mark.call_count, 1)
        self.clock.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

"""Recorded monitoring recency stays separate from source availability and work state."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone, tzinfo
import unittest
from unittest.mock import Mock

from xti.application.status import DEFAULT_PROVIDERS, StatusService
from xti.domain.assets import Asset, ValidationError
from xti.domain.operations import SourceCooldown
from xti.domain.status import AssetHistory, SourceHistory, StatusAttempt, StatusSnapshot


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
ASSET = Asset("asset-1", "example.com", "2026-10-28T10:00:00+00:00")


def attempt(*, status="complete", age=timedelta(hours=1), identifier="attempt-1", **changes):
    finished = NOW - age
    record = StatusAttempt(
        id=identifier, job_id="job-1", number=1, status=status,
        started_at=(finished - timedelta(minutes=1)).isoformat(),
        finished_at=None if status == "running" else finished.isoformat(),
        query_count=2, failed_query_count=int(status == "failed"),
        partial_query_count=int(status == "partial"), error=None,
        rule_version="rule-v1", typos=False,
    )
    return replace(record, **changes)


def snapshot(*, histories=(), cooldowns=(), count=1):
    return StatusSnapshot(
        asset_count=count, observation_count=15,
        finding_counts={"new": 3, "suspicious": 1, "dismissed": 2, "uncertain": 0},
        job_counts={"queued": 2, "running": 0, "complete": 5, "partial": 1, "failed": 2, "interrupted": 1},
        notification_count=6, unread_notification_count=4,
        assets=tuple(histories), cooldowns=tuple(cooldowns),
    )


class UnspecifiedTimezone(tzinfo):
    def utcoffset(self, value):
        return None


class StatusServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = Mock(spec=["snapshot"])
        self.repository.snapshot.return_value = snapshot()
        self.clock = Mock(return_value=NOW)
        self.service = StatusService(self.repository, self.clock)

    def source(self, latest=None, completed=None, *, queued=0, hours=24):
        self.repository.snapshot.return_value = snapshot(histories=(
            AssetHistory(ASSET, (SourceHistory("crt.sh", latest, completed, queued),)),
        ))
        return self.service.show(freshness_hours=hours).assets[0].sources[0]

    def test_default_uses_one_clock_after_one_snapshot_and_preserves_global_counts(self):
        order = []
        self.clock.side_effect = lambda: order.append("clock") or NOW
        saved = snapshot()
        self.repository.snapshot.side_effect = lambda *args: order.append("snapshot") or saved
        report = self.service.show()
        self.assertEqual(order, ["snapshot", "clock"])
        self.repository.snapshot.assert_called_once_with(DEFAULT_PROVIDERS, None, 20)
        self.clock.assert_called_once_with()
        self.assertEqual(report.observed_at, NOW.isoformat())
        self.assertEqual(report.freshness_hours, 24)
        self.assertEqual(report.observation_count, 15)
        self.assertEqual(report.job_counts, saved.job_counts)
        self.assertEqual(report.finding_counts, saved.finding_counts)
        self.assertIsNot(report.job_counts, saved.job_counts)
        self.assertEqual((report.notification_count, report.unread_notification_count), (6, 4))

    def test_never_searched_source_is_distinct_from_recent_other_source(self):
        done = attempt()
        self.repository.snapshot.return_value = snapshot(histories=(
            AssetHistory(ASSET, (
                SourceHistory("crt.sh", done, done, 0),
                SourceHistory("urlscan", None, None, 0),
            )),
            AssetHistory(replace(ASSET, id="asset-2", value="different.com"), (
                SourceHistory("crt.sh", None, None, 0),
                SourceHistory("urlscan", None, None, 0),
            )),
        ), count=2)
        result = self.service.show()
        self.assertEqual([source.freshness for source in result.assets[0].sources], ["current", "never"])
        self.assertEqual([source.freshness for source in result.assets[1].sources], ["never", "never"])
        self.assertIsNone(result.assets[1].sources[0].age_seconds)

    def test_recent_complete_uses_finish_time_and_preserves_summary(self):
        done = attempt(age=timedelta(seconds=3600, microseconds=700000))
        result = self.source(done, done)
        self.assertEqual(result.freshness, "current")
        self.assertEqual(result.age_seconds, 3600)
        self.assertIs(result.latest_attempt, done)
        self.assertIs(result.last_complete, done)

    def test_exact_threshold_is_stale_and_one_microsecond_inside_is_current(self):
        for age, expected in (
            (timedelta(hours=24), "stale"),
            (timedelta(hours=24) - timedelta(microseconds=1), "current"),
            (timedelta(hours=25), "stale"),
        ):
            with self.subTest(age=age):
                done = attempt(age=age)
                self.assertEqual(self.source(done, done).freshness, expected)

    def test_explicit_threshold_is_applied_without_changing_history(self):
        done = attempt(age=timedelta(hours=2))
        self.assertEqual(self.source(done, done, hours=1).freshness, "stale")
        self.assertEqual(self.source(done, done, hours=3).freshness, "current")

    def test_later_failure_partial_or_interruption_does_not_renew_complete_time(self):
        done = attempt(age=timedelta(hours=26), identifier="older-complete")
        for status in ("failed", "partial", "interrupted"):
            with self.subTest(status=status):
                latest = attempt(status=status, age=timedelta(minutes=1), error="Son deneme hatası.")
                result = self.source(latest, done)
                self.assertEqual(result.freshness, "stale")
                self.assertEqual(result.age_seconds, 26 * 3600)
                self.assertIs(result.latest_attempt, latest)
                self.assertIs(result.last_complete, done)
                self.assertTrue(any("Son deneme" in reason for reason in result.reasons))

    def test_latest_failure_does_not_hide_recent_complete_or_failure(self):
        done, failed = attempt(), attempt(status="failed", age=timedelta(minutes=1))
        result = self.source(failed, done)
        self.assertEqual(result.freshness, "current")
        self.assertEqual(result.latest_attempt.status, "failed")
        self.assertTrue(any("başarısız" in reason for reason in result.reasons))

    def test_running_and_queued_are_not_success_or_live_process_proof(self):
        running = attempt(status="running")
        result = self.source(running, queued=3)
        self.assertEqual(result.freshness, "never")
        self.assertIsNone(result.age_seconds)
        self.assertEqual(result.queued_count, 3)
        self.assertTrue(any("kanıtlamaz" in reason for reason in result.reasons))
        self.assertTrue(any("3 iş sırada" in reason for reason in result.reasons))
        only_queued = self.source(queued=1)
        self.assertEqual(only_queued.freshness, "never")
        self.assertIsNone(only_queued.latest_attempt)

    def test_bad_latest_time_prevents_fresh_label_even_with_valid_complete(self):
        done = attempt()
        for changes in (
            {"started_at": "invalid"},
            {"finished_at": "2026-10-29T12:00:00"},
            {"started_at": (NOW + timedelta(seconds=1)).isoformat()},
            {"finished_at": (NOW + timedelta(seconds=1)).isoformat()},
            {"finished_at": "2026-10-27T12:00:00+00:00"},
            {"finished_at": None},
        ):
            with self.subTest(changes=changes):
                result = self.source(attempt(status="failed", **changes), done)
                self.assertEqual(result.freshness, "clock_error")
                self.assertIsNone(result.age_seconds)

    def test_bad_complete_time_never_falls_back_to_other_valid_attempt(self):
        done = attempt(finished_at="0001-01-01T00:00:00+01:00")
        result = self.source(attempt(status="failed"), done)
        self.assertEqual(result.freshness, "clock_error")
        self.assertIs(result.last_complete, done)
        self.assertIsNone(result.age_seconds)

    def test_running_time_requires_past_start_and_no_finish(self):
        for changes in (
            {"started_at": "invalid"},
            {"started_at": (NOW + timedelta(seconds=1)).isoformat()},
            {"finished_at": NOW.isoformat()},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.source(attempt(status="running", **changes)).freshness, "clock_error")

    def test_offsets_normalize_for_clock_and_attempt_age(self):
        offset = timezone(timedelta(hours=3))
        self.clock.return_value = NOW.astimezone(offset)
        done = attempt(
            started_at="2026-10-29T13:59:00+03:00", finished_at="2026-10-29T14:00:00+03:00",
        )
        self.assertEqual(self.source(done, done).age_seconds, 3600)
        self.assertEqual(self.service.show().observed_at, NOW.isoformat())

    def test_filter_normalizes_domain_and_keeps_global_counters(self):
        self.repository.snapshot.return_value = snapshot(histories=(AssetHistory(ASSET, ()),), count=5)
        result = self.service.show(" EXAMPLE.COM. ", limit=100, freshness_hours=8760)
        self.repository.snapshot.assert_called_once_with(DEFAULT_PROVIDERS, "example.com", 100)
        self.assertEqual(result.domain_filter, "example.com")
        self.assertEqual((result.asset_count, result.displayed_asset_count), (5, 1))
        self.assertFalse(result.has_more_assets)
        self.assertEqual(result.observation_count, 15)

    def test_limit_omission_is_visible_and_empty_workspace_is_not_paginated(self):
        self.repository.snapshot.return_value = snapshot(histories=(AssetHistory(ASSET, ()),), count=5)
        result = self.service.show(limit=1)
        self.assertTrue(result.has_more_assets)
        self.assertEqual(result.displayed_asset_count, 1)
        self.repository.snapshot.return_value = snapshot(count=0)
        empty = self.service.show()
        self.assertFalse(empty.has_more_assets)
        self.assertEqual(empty.assets, ())

    def test_invalid_threshold_or_limit_is_rejected_before_clock_and_storage(self):
        for value in (0, -1, 8761, None, "24", 1.0, True, []):
            with self.subTest(hours=value), self.assertRaises(ValidationError):
                self.service.show(freshness_hours=value)
        for value in (0, -1, 101, None, "20", 1.0, True, []):
            with self.subTest(limit=value), self.assertRaises(ValidationError):
                self.service.show(limit=value)
        self.clock.assert_not_called()
        self.repository.snapshot.assert_not_called()

    def test_invalid_domain_is_rejected_before_clock_and_storage(self):
        for value in ("", "https://example.com", "example.com\n", 1, [], "örnek.com"):
            with self.subTest(domain=value), self.assertRaises(ValidationError):
                self.service.show(value)
        self.clock.assert_not_called()
        self.repository.snapshot.assert_not_called()

    def test_invalid_clock_rejects_report_after_only_one_read(self):
        for value in (
            None, "2026-10-29T12:00:00Z", datetime(2026, 10, 29),
            datetime(2026, 10, 29, tzinfo=UnspecifiedTimezone()),
            datetime.min.replace(tzinfo=timezone(timedelta(hours=1))),
            datetime.max.replace(tzinfo=timezone(timedelta(hours=-1))),
        ):
            with self.subTest(clock=value), self.assertRaises(ValidationError):
                self.repository.reset_mock()
                self.clock.return_value = value
                self.service.show()
            self.repository.snapshot.assert_called_once_with(DEFAULT_PROVIDERS, None, 20)

    def test_cooldown_rounds_positive_fraction_up_and_preserves_expired_record(self):
        records = (
            SourceCooldown("crt.sh", (NOW + timedelta(microseconds=1)).isoformat(),
                           (NOW - timedelta(seconds=2)).isoformat(), "request_spacing"),
            SourceCooldown("urlscan", NOW.isoformat(),
                           (NOW - timedelta(seconds=2)).isoformat(), "rate_limit"),
        )
        self.repository.snapshot.return_value = snapshot(cooldowns=records)
        result = self.service.show()
        self.assertEqual([(c.active, c.remaining_seconds, c.clock_error) for c in result.cooldowns],
                         [(True, 1, False), (False, 0, False)])
        self.assertEqual(result.cooldowns[1].not_before, records[1].not_before)

    def test_invalid_or_future_cooldown_time_is_not_reported_as_known_expiry(self):
        records = (
            SourceCooldown("crt.sh", "invalid", NOW.isoformat(), "retry_after"),
            SourceCooldown("crt.sh", NOW.isoformat(), "invalid", "retry_after"),
            SourceCooldown("crt.sh", (NOW + timedelta(hours=2)).isoformat(),
                           (NOW + timedelta(hours=1)).isoformat(), "retry_after"),
            SourceCooldown("crt.sh", (NOW - timedelta(hours=2)).isoformat(),
                           (NOW - timedelta(hours=1)).isoformat(), "retry_after"),
        )
        for record in records:
            with self.subTest(record=record):
                self.repository.snapshot.return_value = snapshot(cooldowns=(record,))
                result = self.service.show().cooldowns[0]
                self.assertTrue(result.clock_error)
                self.assertEqual(result.remaining_seconds, 0)

    def test_notes_distinguish_threshold_and_recorded_history_from_monitoring_guarantees(self):
        report = self.service.show(freshness_hours=48)
        text = " ".join(report.notes)
        for fragment in ("48 saat", "takvimi değildir", "şu anki erişimi", "kısmi iş",
                         "bütün interneti", "canlı süreç", "güncel kesinti", "doctor"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, text)

    def test_repository_failure_propagates_without_retry(self):
        self.repository.snapshot.side_effect = ValidationError("Adres bulunamadı.")
        with self.assertRaisesRegex(ValidationError, "Adres bulunamadı"):
            self.service.show("unknown.com")
        self.clock.assert_not_called()
        self.repository.snapshot.assert_called_once_with(DEFAULT_PROVIDERS, "unknown.com", 20)


if __name__ == "__main__":
    unittest.main()

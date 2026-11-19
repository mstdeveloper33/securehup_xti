"""Lifecycle evidence semantics, replay integrity and deterministic review boundaries."""

from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.certpl_warning import parse_certpl_warning_response
from xti.adapters.feodo_tracker import parse_feodo_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_ioc_lifecycle import SQLiteIocLifecycleRepository
from xti.application.cti_indicators import CtiIndicatorService
from xti.application.ioc_lifecycle import IocLifecycleService
from xti.domain.assets import ValidationError
from xti.domain.cti_feeds import CERTPL_POLICY
from xti.domain.ioc_lifecycle import assess_lifecycle, lifecycle_parameters
from xti.domain.research import ResearchSnapshotChanged
from tests.test_certpl_warning import content
from tests.test_cti_feeds import raw


NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
VALUE = "192.0.2.10"


def feed_snapshot(*, last="2026-11-17", first="2026-11-01 10:00:00"):
    return parse_feodo_response(json.dumps([raw(VALUE, first_seen=first, last_online=last)]).encode())


class IocLifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "data" / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.reader = SQLiteIocLifecycleRepository(self.path)
        self.feed = SQLiteCtiFeedRepository(self.path)
        self.now = NOW + timedelta(minutes=1)
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("No network")))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("No network")))

    def apply(self, snapshot=None, *, at=NOW, repository=None):
        return (repository or self.feed).apply(snapshot if snapshot is not None else feed_snapshot(),
            started_at=at.isoformat(), finished_at=(at + timedelta(seconds=1)).isoformat())

    def show(self, kind="ipv4", value=VALUE, **parameters):
        return IocLifecycleService(self.reader, clock=lambda: self.now).show(indicator_type=kind, value=value, **parameters)

    def add(self, *, source="analyst", observed_at=None, valid_from=None, valid_until=None, confidence=80):
        return CtiIndicatorService(SQLiteCtiIndicatorRepository(self.path), clock=lambda: NOW).add(
            "ipv4", VALUE, source_name=source, source_reference="https://reports.example/" + source,
            confidence=confidence, description="Controlled evidence from analyst",
            observed_at=observed_at, valid_from=valid_from, valid_until=valid_until)

    def mutate(self, sql, values=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(sql, values)

    def test_repeated_collection_updates_receipt_but_never_refreshes_observation(self):
        first_run = self.apply()
        first = self.show()
        self.now += timedelta(days=10)
        second_run = self.apply(at=NOW + timedelta(days=10))
        before = self.path.read_bytes()
        second = self.show()
        old, new = first["assertions"][0], second["assertions"][0]
        self.assertEqual(old["reported_observation_at"], new["reported_observation_at"])
        self.assertEqual(old["observation_event_id"], new["observation_event_id"])
        self.assertEqual(new["currency"]["state"], "aging")
        self.assertEqual(new["collection"]["last_success"]["id"], second_run.id)
        self.assertNotEqual(first_run.id, second_run.id)
        self.assertEqual(new["confidence"], 50)
        self.assertEqual(second["assessment"], "needs_review")
        self.assertEqual(self.path.read_bytes(), before)

    def test_new_provider_observation_changes_evidence_and_not_confidence(self):
        self.apply()
        old = self.show()["assertions"][0]
        self.apply(feed_snapshot(last="2026-11-19"), at=NOW + timedelta(days=2))
        self.now += timedelta(days=2)
        new = self.show()["assertions"][0]
        self.assertGreater(new["reported_observation_at"], old["reported_observation_at"])
        self.assertNotEqual(new["observation_event_id"], old["observation_event_id"])
        self.assertEqual(new["assessment"], "current_context")
        self.assertEqual(new["confidence"], old["confidence"])

    def test_failure_keeps_success_and_active_claim_separate(self):
        good = self.apply()
        failure = self.feed.record_failure(started_at=(NOW + timedelta(seconds=10)).isoformat(),
            finished_at=(NOW + timedelta(seconds=20)).isoformat(), error="Provider timed out; evidence retained.")
        row = self.show()["assertions"][0]
        self.assertEqual((row["claim_state"], row["assessment"]), ("active", "needs_review"))
        self.assertEqual(row["collection"]["latest_attempt"]["id"], failure.id)
        self.assertEqual(row["collection"]["last_success"]["id"], good.id)
        self.assertTrue(row["collection"]["previous_success_preserved"])
        self.assertIn("latest_collection_failed", [item["code"] for item in row["reasons"]])

    def test_feed_absence_and_operator_revoke_are_distinct_and_preserved(self):
        self.apply()
        self.apply(parse_feodo_response(b"[]"), at=NOW + timedelta(seconds=10))
        withdrawn = self.show()["assertions"][0]
        self.assertEqual((withdrawn["claim_state"], withdrawn["revocation_basis"]), ("revoked", "feed_absence"))
        self.apply(at=NOW + timedelta(seconds=20))
        active = self.show()["assertions"][0]
        self.assertEqual(active["last_event"]["action"], "reactivated")
        CtiIndicatorService(SQLiteCtiIndicatorRepository(self.path), clock=lambda: NOW + timedelta(seconds=30)).revoke(
            active["assertion_id"], reason="Human decision; keep provider history")
        local = self.show()["assertions"][0]
        self.assertEqual(local["revocation_basis"], "local_decision")
        self.assertIn("Human decision", local["last_event"]["reason"])

    def test_certpl_list_version_is_not_an_event_time_even_after_new_header(self):
        repo = SQLiteCtiFeedRepository(self.path, CERTPL_POLICY)
        def cert(at):
            return parse_certpl_warning_response(content("example.test", version=at.strftime("%Y%m%d%H%M")), fetched_at=at)
        self.apply(cert(NOW), repository=repo)
        first = self.show("domain", "example.test")["assertions"][0]
        self.apply(cert(NOW + timedelta(days=1)), at=NOW + timedelta(days=1), repository=repo)
        self.now += timedelta(days=1)
        second = self.show("domain", "example.test")["assertions"][0]
        self.assertIsNone(second["reported_observation_at"])
        self.assertEqual(second["time_basis"], "provider_list_version")
        self.assertEqual(first["assertion_last_seen_at"], second["assertion_last_seen_at"])
        self.assertNotEqual(first["collection"]["last_success"]["id"], second["collection"]["last_success"]["id"])

    def test_legacy_manual_time_is_explicitly_unspecified_and_source_counts_do_not_add_confidence(self):
        self.add(source="one", confidence=80)
        self.add(source="two", confidence=90)
        result = self.show()
        self.assertEqual(result["source_count"], 2)
        self.assertEqual([row["confidence"] for row in result["assertions"]], [80, 90])
        self.assertTrue(all(row["reported_observation_at"] is None for row in result["assertions"]))
        self.assertTrue(all(row["time_basis"] == "unspecified_assertion_time" for row in result["assertions"]))

    def test_date_and_validity_boundaries_do_not_revoke_or_modify_records(self):
        self.apply()
        snapshot = self.reader.read("ipv4", VALUE)
        seen = datetime.fromisoformat(snapshot.details.assertions[0].last_seen_at)
        before = self.path.read_bytes()
        for days, seconds, expected in ((7, -1, "recent"), (7, 0, "aging"), (30, -1, "aging"), (30, 0, "stale")):
            with self.subTest(days=days, seconds=seconds):
                result = assess_lifecycle(snapshot, checked_at=(seen + timedelta(days=days, seconds=seconds)).isoformat(),
                    indicator_type="ipv4", value=VALUE)
                self.assertEqual(result["assertions"][0]["currency"]["state"], expected)
                self.assertEqual(result["assertions"][0]["claim_state"], "active")
        self.assertEqual(self.path.read_bytes(), before)

    def test_expiration_and_future_validity_are_distinct_from_age(self):
        self.add(source="expired", valid_from=(NOW - timedelta(days=1)).isoformat(), valid_until=NOW.isoformat())
        self.add(source="future", valid_from=(NOW + timedelta(days=1)).isoformat())
        self.add(source="active", valid_from=NOW.isoformat(), valid_until=(NOW + timedelta(days=1)).isoformat())
        result = {row["source_name"]: row for row in self.show()["assertions"]}
        self.assertEqual(result["expired"]["claim_state"], "expired")
        self.assertEqual(result["future"]["claim_state"], "not_yet_valid")
        self.assertEqual(result["active"]["claim_state"], "active")

    def test_future_collection_or_claim_clock_is_not_fresh_evidence(self):
        self.apply()
        self.now = NOW - timedelta(hours=2)
        row = self.show()["assertions"][0]
        self.assertEqual(row["assessment"], "needs_review")
        self.assertIn("clock_anomaly", [reason["code"] for reason in row["reasons"]])

    def test_policy_changes_are_explicit_and_do_not_touch_database(self):
        self.apply()
        before = self.path.read_bytes()
        result = self.show(fresh_days=1, stale_days=2, source_stale_hours=1)
        self.assertEqual(result["assertions"][0]["currency"]["state"], "aging")
        self.assertEqual(result["policy"]["fresh_days"], 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(lifecycle_parameters(indicator_type="sha256", value="a" * 64)["stale_days"], 180)

    def test_pagination_guard_accepts_elapsed_seconds_but_rejects_new_data_and_time_class(self):
        self.add(source="alpha")
        self.add(source="beta")
        first = self.show(limit=1)
        self.now += timedelta(seconds=2)
        second = self.show(offset=1, limit=1, expected_snapshot=first["snapshot_id"])
        self.assertEqual(second["total_count"], 2)
        self.assertNotEqual(second["assertions"][0]["assertion_id"], first["assertions"][0]["assertion_id"])
        self.now += timedelta(days=10)
        with self.assertRaises(ResearchSnapshotChanged):
            self.show(expected_snapshot=first["snapshot_id"])
        self.now = NOW + timedelta(minutes=1)
        self.add(source="gamma")
        with self.assertRaises(ResearchSnapshotChanged):
            self.show(expected_snapshot=first["snapshot_id"])

    def test_missing_record_is_not_safe_and_does_not_create_evidence(self):
        before = self.path.read_bytes()
        result = self.show()
        self.assertEqual((result["assessment"], result["assertions"], result["total_count"]), ("not_recorded", [], 0))
        self.assertIsNone(result["indicator_id"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_current_claim_fails_replay_before_assessment(self):
        self.add()
        self.mutate("UPDATE cti_indicator_assertions SET confidence=99")
        with self.assertRaises(StorageError):
            self.show()

    def test_missing_initial_receipt_is_not_accepted_as_provider_evidence(self):
        self.apply()
        self.mutate("DELETE FROM cti_feed_run_items")
        with self.assertRaises(StorageError):
            self.show()

    def test_changed_observation_requires_its_own_exact_receipt(self):
        self.apply()
        new = self.apply(feed_snapshot(last="2026-11-18"), at=NOW + timedelta(seconds=20))
        self.mutate("UPDATE cti_feed_run_items SET state_sha256=? WHERE run_id=?", ("0" * 64, new.id))
        with self.assertRaisesRegex(StorageError, "makbuzu"):
            self.show()

    def test_corrupt_feed_revocation_cannot_be_relabelled_as_an_operator_decision(self):
        self.apply()
        revoked = self.apply(parse_feodo_response(b"[]"), at=NOW + timedelta(seconds=10))
        self.mutate("UPDATE cti_feed_run_items SET state_sha256=? WHERE run_id=?", ("0" * 64, revoked.id))
        with self.assertRaises(StorageError):
            self.show()

    def test_repeated_feed_receipt_must_preserve_the_previous_evidence_state(self):
        self.apply()
        repeated = self.apply(at=NOW + timedelta(seconds=10))
        self.mutate("UPDATE cti_feed_run_items SET state_sha256=? WHERE run_id=?", ("0" * 64, repeated.id))
        with self.assertRaises(StorageError):
            self.show()

    def test_unchanged_collections_can_share_a_recording_timestamp(self):
        self.apply()
        repeated_at = NOW + timedelta(seconds=10)
        self.apply(at=repeated_at)
        last = self.apply(at=repeated_at)
        result = self.show()["assertions"][0]
        self.assertEqual(result["collection"]["last_success"]["id"], last.id)
        self.assertEqual(result["reported_observation_at"], "2026-11-17T00:00:00+00:00")

    def test_read_limits_are_preflighted_and_are_per_indicator_not_whole_catalog(self):
        self.add()
        for limit_name, limit in (("MAX_ASSERTIONS", 0), ("MAX_EVENTS", 0), ("MAX_READ_BYTES", 10)):
            with self.subTest(limit=limit_name), patch("xti.adapters.sqlite_ioc_lifecycle." + limit_name, limit):
                with self.assertRaisesRegex(StorageError, "okuma sınırını"):
                    self.show()
        self.assertEqual(self.show()["total_count"], 1)

    def test_excessive_receipts_are_bounded_before_loading(self):
        self.apply()
        with patch("xti.adapters.sqlite_ioc_lifecycle.MAX_RECEIPTS", 0):
            with self.assertRaises(StorageError):
                self.show()

    def test_unrelated_catalog_corruption_does_not_expand_the_selected_indicator_scope(self):
        self.add()
        unrelated = CtiIndicatorService(SQLiteCtiIndicatorRepository(self.path), clock=lambda: NOW).add(
            "domain", "unrelated.example", source_name="unrelated", source_reference="https://unrelated.example/report",
            confidence=50, description="Unrelated fixture evidence")
        self.mutate("UPDATE cti_indicator_assertions SET description=? WHERE id=?", ("x" * 100_000, unrelated.assertion.id))
        self.assertEqual(self.show()["total_count"], 1)
        with self.assertRaises(StorageError):
            self.show("domain", "unrelated.example")

    def test_invalid_parameters_fail_before_reading(self):
        for changes in ({"fresh_days": True}, {"stale_days": 7}, {"source_stale_hours": 0},
                        {"limit": 101}, {"offset": -1}, {"expected_snapshot": "bad"},
                        {"fresh_days": 0}, {"stale_days": "30"}):
            with self.subTest(changes=changes), patch.object(self.reader, "read", side_effect=AssertionError("Must validate first")):
                with self.assertRaises(ValidationError):
                    self.show(**changes)

    def test_partial_snapshot_cannot_be_mistaken_for_complete_assessment(self):
        self.add()
        snapshot = self.reader.read("ipv4", VALUE)
        broken = replace(snapshot, details=replace(snapshot.details, events=()))
        with self.assertRaises(ValidationError):
            assess_lifecycle(broken, checked_at=NOW.isoformat(), indicator_type="ipv4", value=VALUE)

    def test_concurrent_collection_does_not_mix_source_attempts_with_old_evidence(self):
        self.apply()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        original = self.reader.indicators._details
        def read_then_collect(*args, **kwargs):
            details = original(*args, **kwargs)
            self.feed.record_failure(started_at=(NOW + timedelta(seconds=10)).isoformat(),
                finished_at=(NOW + timedelta(seconds=11)).isoformat(), error="Concurrent provider timeout")
            return details
        with patch.object(self.reader.indicators, "_details", side_effect=read_then_collect):
            result = self.show()
        self.assertEqual(result["assertions"][0]["collection"]["status"], "complete")
        self.assertEqual(self.show()["assertions"][0]["collection"]["status"], "failed")

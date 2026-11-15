"""Grouped execution uses real receipts, budget history and notification storage."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
from xti.adapters.sqlite_mention_groups import SQLiteMentionGroupRepository
from xti.adapters.sqlite_mention_notifications import SQLiteMentionNotificationBridge, mention_watch_id
from xti.adapters.sqlite_mentions import SQLiteMentionRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.mention_groups import MentionGroupService
from xti.domain.assets import ValidationError
from xti.domain.mention_groups import MentionGroupDefinition
from xti.domain.mentions import MentionHit, MentionResponse, MentionTarget, build_query, request_key
from xti.ports.discovery import SourceError
from xti.ports.jobs import WorkerBusyError


NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
ORG = "11111111-1111-4111-8111-111111111111"
SUPPLIER = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"


class Targets:
    def __init__(self):
        self.values = {
            ("organization", ORG): MentionTarget("organization", ORG, "Example Company", ("example.com",)),
            ("supplier", SUPPLIER): MentionTarget("supplier", SUPPLIER, "Example Supplier", ("supplier.example",)),
            ("supplier", OTHER): MentionTarget("supplier", OTHER, "Other Supplier", ("other.example",)),
        }
        self.calls = []

    def resolve(self, kind, identifier):
        self.calls.append((kind, identifier))
        value = self.values.get((kind, identifier))
        if value is None:
            raise ValidationError("Target is missing or disabled")
        return value


class MentionGroupServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteMentionGroupRepository(self.path)
        self.mentions = SQLiteMentionRepository(self.path)
        self.notifications = SQLiteMentionNotificationBridge(self.path)
        self.targets = Targets()
        self.now = NOW
        self.source = Mock()
        self.source.fetch.side_effect = self.fetch
        self.factory = Mock(side_effect=self.make_source)
        self.service = MentionGroupService(self.repository, self.mentions, self.targets,
            LocalExecutionLock(self.path), notifications=self.notifications,
            source_factory=self.factory, clock=lambda: self.now)
        self.definition = MentionGroupDefinition(ORG, (SUPPLIER,), interval_hours=1,
            per_run_queries=2, daily_queries=4)
        self.group = self.service.save("My suppliers", self.definition)
        self.targets.calls.clear()
        self.addCleanup(patch.stopall)
        patch("socket.socket.connect", side_effect=AssertionError("No live internet in tests")).start()
        patch("socket.getaddrinfo", side_effect=AssertionError("No live DNS in tests")).start()

    def held(self):
        with self.assertRaises(WorkerBusyError):
            with LocalExecutionLock(self.path).acquire():
                pass

    def make_source(self):
        self.held()
        return self.source

    def fetch(self, request):
        self.held()
        hit = MentionHit(f"https://publisher.example/{request.target.id}",
            request.target.name + " announcement", "A public company announcement.", None, 0.8)
        return MentionResponse(build_query(request.target), "provider-request", (hit,), 1)

    def single_group(self):
        return self.service.save("Single company", replace(self.definition, supplier_ids=(),
            per_run_queries=1, daily_queries=2))

    def begin(self, group=None):
        group = group or self.group
        requests = self.service.plan(group.id)["requests"]
        return self.repository.begin(group.id, requests, started_at=self.now.isoformat())

    def test_success_reserves_each_request_and_links_complete_source_and_notice_receipts(self):
        result = self.service.run(self.group.id)
        run = result["run"]
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["daily_queries_used"], 2)
        self.assertEqual(self.source.fetch.call_count, 2)
        self.assertEqual([call.args[0].target.id for call in self.source.fetch.call_args_list], [ORG, SUPPLIER])
        self.assertTrue(all(attempt.status == "complete" and attempt.notification_run_id for attempt in run.attempts))
        self.assertEqual(len(self.mentions.catalog().runs), 2)
        self.assertTrue(all(self.mentions.run_show(attempt.result_run_id).status == "complete" for attempt in run.attempts))
        # The shared lock is released after the whole operation.
        with LocalExecutionLock(self.path).acquire():
            pass

    def test_daily_budget_insufficient_for_whole_group_stops_before_credentials_or_reservations(self):
        group = self.service.save("Insufficient budget", replace(self.definition, daily_queries=1))
        self.factory.reset_mock()
        result = self.service.run(group.id)
        self.assertEqual((result["status"], result["reason"]), ("skipped", "daily_budget"))
        self.factory.assert_not_called()
        self.source.fetch.assert_not_called()
        self.assertEqual(self.repository.runs(group.id), ())
        self.assertEqual(self.mentions.catalog().runs, ())

    def test_interval_and_latest_unfinished_work_stop_before_credentials(self):
        first = self.service.run(self.group.id)["run"]
        self.now += timedelta(hours=1)
        second = self.service.run(self.group.id)["run"]
        self.assertNotEqual(first.id, second.id)
        self.now += timedelta(minutes=30)
        self.factory.reset_mock()
        result = self.service.run(self.group.id)
        self.assertEqual(result["reason"], "not_due")
        self.assertEqual(self.service.show(self.group.id)["latest_run"].id, second.id)
        self.factory.assert_not_called()
        # On a fresh UTC day a deliberately unfinished newest run must win
        # over older completed history when deciding whether a new run is due.
        self.now += timedelta(days=1)
        unfinished = self.begin()
        self.now += timedelta(hours=2)
        result = self.service.run(self.group.id)
        self.assertEqual((result["reason"], result["unfinished_run_id"]), ("unfinished_run", unfinished.id))
        self.factory.assert_not_called()

    def test_invalid_later_target_blocks_entire_group_before_first_provider_call(self):
        del self.targets.values[("supplier", SUPPLIER)]
        with self.assertRaises(ValidationError):
            self.service.run(self.group.id)
        self.assertEqual(self.targets.calls, [("organization", ORG), ("supplier", SUPPLIER)])
        self.factory.assert_not_called()
        self.source.fetch.assert_not_called()
        self.assertEqual(self.repository.runs(self.group.id), ())

    def test_per_run_budget_rejected_before_credentials(self):
        # Persisted definitions may be deliberately tighter than their target
        # list; planning must surface that mismatch before constructing a key.
        group = self.repository.save("Too many targets", replace(self.definition, per_run_queries=1),
                                     recorded_at=self.now.isoformat())
        with self.assertRaises(ValidationError):
            self.service.run(group.id)
        self.factory.assert_not_called()
        self.source.fetch.assert_not_called()
        self.assertEqual(self.repository.runs(group.id), ())

    def test_missing_credentials_and_capacity_errors_leave_no_started_work(self):
        self.factory.side_effect = ValidationError("Missing key")
        with self.assertRaises(ValidationError):
            self.service.run(self.group.id)
        self.source.fetch.assert_not_called()
        self.assertEqual(self.repository.runs(self.group.id), ())
        self.factory.reset_mock()
        with patch.object(self.mentions, "validate", side_effect=StorageError("Capacity full")):
            with self.assertRaises(StorageError):
                self.service.run(self.group.id)
        self.factory.assert_not_called()
        self.assertEqual(self.repository.runs(self.group.id), ())

    def test_first_source_failure_spends_only_one_query_and_skips_remaining_targets(self):
        self.source.fetch.side_effect = SourceError("Tavily unavailable")
        result = self.service.run(self.group.id)
        self.assertEqual(result["status"], "failed")
        self.assertEqual([attempt.status for attempt in result["run"].attempts], ["failed", "skipped"])
        self.assertEqual(result["run"].attempts[1].error_code, "source_failed")
        self.assertEqual(result["daily_queries_used"], 1)
        self.assertEqual(self.source.fetch.call_count, 1)
        self.assertEqual([run.status for run in self.mentions.catalog().runs], ["failed"])

    def test_invalid_provider_response_is_failed_once_without_downstream_notice(self):
        other = self.targets.values[("supplier", OTHER)]
        self.source.fetch.return_value = None
        self.source.fetch.side_effect = lambda request: MentionResponse(build_query(other), "bad-scope", (), 1)
        with patch.object(self.notifications, "notify", wraps=self.notifications.notify) as notice:
            result = self.service.run(self.group.id)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.source.fetch.call_count, 1)
        notice.assert_not_called()

    def test_ambiguous_reserved_request_becomes_unknown_without_new_http(self):
        group = self.single_group()
        run = self.begin(group)
        self.repository.reserve_attempt(run.id, 0, started_at=self.now.isoformat())
        self.now += timedelta(seconds=1)
        result = self.service.resume(run.id)
        self.assertEqual((result["status"], result["run"].attempts[0].status), ("failed", "unknown"))
        self.assertEqual(result["daily_queries_used"], 1)
        self.factory.assert_not_called()
        self.source.fetch.assert_not_called()
        self.assertEqual(self.mentions.catalog().runs, ())
        repeated = self.service.resume(run.id)
        self.assertEqual(repeated["reason"], "replayed")
        self.source.fetch.assert_not_called()

    def test_resume_executes_only_never_attempted_target_after_unknown_reservation(self):
        run = self.begin()
        self.repository.reserve_attempt(run.id, 0, started_at=self.now.isoformat())
        self.now += timedelta(seconds=1)
        result = self.service.resume(run.id)
        self.assertEqual(result["status"], "partial")
        self.assertEqual([attempt.status for attempt in result["run"].attempts], ["unknown", "complete"])
        self.assertEqual([call.args[0].target.id for call in self.source.fetch.call_args_list], [SUPPLIER])
        self.assertEqual(result["daily_queries_used"], 2)

    def test_complete_source_notice_pending_resumes_without_key_or_network(self):
        group = self.single_group()
        with patch.object(self.notifications, "notify", side_effect=StorageError("Notice interrupted")):
            with self.assertRaises(StorageError):
                self.service.run(group.id)
        run = self.repository.runs(group.id)[-1]
        self.assertEqual((run.status, run.attempts[0].status), ("running", "complete"))
        self.assertIsNone(run.attempts[0].notification_run_id)
        old_sources = self.mentions.catalog().runs
        self.factory.reset_mock()
        self.factory.side_effect = AssertionError("No credential access during notice retry")
        self.source.fetch.reset_mock()
        self.source.fetch.side_effect = AssertionError("No HTTP during notice retry")
        self.now += timedelta(seconds=1)
        result = self.service.resume(run.id)
        self.assertEqual(result["status"], "complete")
        self.assertIsNotNone(result["run"].attempts[0].notification_run_id)
        self.assertEqual(self.mentions.catalog().runs, old_sources)
        self.factory.assert_not_called()
        self.source.fetch.assert_not_called()

    def test_notice_commit_before_group_receipt_is_reused_once_on_resume(self):
        group = self.single_group()
        with patch.object(self.repository, "record_notification", side_effect=StorageError("Receipt interrupted")):
            with self.assertRaises(StorageError):
                self.service.run(group.id)
        run = self.repository.runs(group.id)[-1]
        self.assertEqual(run.attempts[0].status, "complete")
        self.assertIsNone(run.attempts[0].notification_run_id)
        watches = SQLiteGlobalSavedSearchRepository(self.path)
        watch_id = mention_watch_id(group.id, request_key(run.attempts[0].request))
        before = watches.details(watch_id, event_offset=0, event_limit=5, run_offset=0, run_limit=5)
        self.assertEqual(before.total_run_count, 1)
        self.factory.reset_mock()
        self.factory.side_effect = AssertionError("Receipt retry must not load a key")
        self.source.fetch.reset_mock()
        self.now += timedelta(seconds=1)
        result = self.service.resume(run.id)
        after = watches.details(watch_id, event_offset=0, event_limit=5, run_offset=0, run_limit=5)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(after.runs, before.runs)
        self.assertEqual(after.total_run_count, 1)
        self.assertEqual(result["run"].attempts[0].notification_run_id, before.runs[0].id)
        self.factory.assert_not_called()
        self.source.fetch.assert_not_called()

    def test_disabled_or_renamed_target_skips_pending_frozen_requests(self):
        run = self.begin()
        del self.targets.values[("supplier", SUPPLIER)]
        self.now += timedelta(seconds=1)
        result = self.service.resume(run.id)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(all(attempt.status == "skipped" and attempt.error_code == "target_changed"
                            for attempt in result["run"].attempts))
        self.assertEqual(result["daily_queries_used"], 0)
        self.factory.assert_not_called()
        self.source.fetch.assert_not_called()

    def test_disabled_group_can_close_pending_run_without_new_collection(self):
        run = self.begin()
        self.now += timedelta(seconds=1)
        self.service.disable(self.group.id, reason="Stop group collection")
        result = self.service.resume(run.id)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(all(attempt.error_code == "group_disabled" for attempt in result["run"].attempts))
        self.source.fetch.assert_not_called()

    def test_explicit_request_id_replays_without_target_lookup_or_new_credits(self):
        identifier = str(uuid4())
        first = self.service.run(self.group.id, request_id=identifier)
        self.now += timedelta(days=1)
        self.factory.reset_mock()
        self.source.fetch.reset_mock()
        with patch.object(self.targets, "resolve", side_effect=AssertionError("Replay cannot resolve changed target")):
            result = self.service.run(self.group.id, request_id=identifier)
        self.assertEqual(result["reason"], "replayed")
        self.assertEqual(result["run"], first["run"])
        self.assertEqual(len(self.repository.runs(self.group.id)), 1)
        self.factory.assert_not_called()
        self.source.fetch.assert_not_called()
        other = self.service.save("Other group", self.definition)
        with self.assertRaises(ValidationError):
            self.service.run(other.id, request_id=identifier)
        self.source.fetch.assert_not_called()

    def test_daily_budget_uses_utc_date_and_preserves_previous_day_reservations(self):
        group = self.service.save("UTC budget", replace(self.definition, daily_queries=2))
        self.now = datetime(2026, 11, 15, 23, tzinfo=timezone.utc)
        first = self.service.run(group.id)
        self.now += timedelta(minutes=59)
        self.assertEqual(self.service.run(group.id)["reason"], "not_due")
        self.now += timedelta(minutes=1)
        second = self.service.run(group.id)
        self.assertEqual((first["status"], second["status"]), ("complete", "complete"))
        self.assertEqual((first["budget"].utc_day, second["budget"].utc_day), ("2026-11-15", "2026-11-16"))
        self.assertEqual((first["daily_queries_used"], second["daily_queries_used"]), (2, 2))
        self.assertEqual(self.source.fetch.call_count, 4)
        self.now += timedelta(hours=1)
        self.assertEqual(self.service.run(group.id)["reason"], "daily_budget")
        self.assertEqual(self.source.fetch.call_count, 4)

    def test_invalid_or_regressed_clock_blocks_new_provider_use(self):
        self.now = datetime(2026, 11, 15)
        with self.assertRaises(ValidationError):
            self.service.run(self.group.id)
        self.now = NOW - timedelta(seconds=1)
        with self.assertRaises(ValidationError):
            self.service.run(self.group.id)
        self.factory.assert_not_called()
        self.source.fetch.assert_not_called()
        self.assertEqual(self.repository.runs(self.group.id), ())
        self.now = NOW
        self.service.run(self.group.id)
        self.factory.reset_mock()
        self.source.fetch.reset_mock()
        self.now = NOW - timedelta(seconds=1)
        with self.assertRaises(ValidationError):
            self.service.plan(self.group.id)
        self.factory.assert_not_called()
        self.source.fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()

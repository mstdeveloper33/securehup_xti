"""Durable query budgets, frozen targets, atomic receipts and interruption recovery."""

from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_mention_groups import SQLiteMentionGroupRepository
from xti.adapters.sqlite_mention_notifications import SQLiteMentionNotificationBridge
from xti.adapters.sqlite_mentions import SQLiteMentionRepository, read_mentions_catalog
from xti.domain.assets import ValidationError
from xti.domain.mention_groups import MentionGroupDefinition, validate_definition
from xti.domain.mentions import MentionTarget, MentionRequest, MentionResponse, MentionHit, build_query

T0 = "2026-11-15T12:00:00+00:00"
T1 = "2026-11-15T12:00:01+00:00"
T2 = "2026-11-15T13:00:00+00:00"
T3 = "2026-11-16T13:00:00+00:00"


class MentionGroupStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.groups = SQLiteMentionGroupRepository(self.path)
        self.sources = SQLiteMentionRepository(self.path)
        self.org, self.supplier = str(uuid4()), str(uuid4())
        self.definition = MentionGroupDefinition(self.org, (self.supplier,), interval_hours=1, daily_queries=4)
        self.group = self.groups.save("Acme izleme", self.definition, recorded_at=T0)
        self.requests = (
            MentionRequest(MentionTarget("organization", self.org, "Acme", ("acme.test",)), "news", 10),
            MentionRequest(MentionTarget("supplier", self.supplier, "Supplier", ("supplier.test",)), "news", 10),
        )

    def begin(self, at=T0, request_id=None):
        return self.groups.begin(self.group.id, self.requests, started_at=at, request_id=request_id)

    def fail(self, run, index, at=T0):
        operation = self.groups.reserve_attempt(run.id, index, started_at=at)
        source = self.sources.record_failure(self.requests[index], error="Controlled source failure",
            started_at=at, finished_at=at, operation=operation)
        return operation, source

    def success(self, run, index, at=T0):
        operation = self.groups.reserve_attempt(run.id, index, started_at=at)
        request = self.requests[index]
        response = MentionResponse(build_query(request.target), None,
            (MentionHit("https://news.test/article", "Acme news", "Acme summary", None, .8),), 1)
        source = self.sources.apply(request, response, started_at=at, finished_at=at, operation=operation)
        return operation, source

    def test_group_definition_validation_rejects_ambiguous_or_unbounded_inputs(self):
        for bad in (replace(self.definition, daily_queries=True), replace(self.definition, interval_hours=0),
                    replace(self.definition, max_results=21), replace(self.definition, supplier_ids=(self.supplier,) * 2),
                    replace(self.definition, supplier_ids=("invalid",))):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                validate_definition(bad)
        same = self.groups.save("Acme izleme", self.definition, recorded_at=T1)
        self.assertEqual(same, self.group)
        self.assertEqual(self.groups.list(), (self.group,))

    def test_work_freezes_definition_and_rejects_changed_or_missing_target(self):
        with self.assertRaises(ValidationError):
            self.groups.begin(self.group.id, self.requests[:1], started_at=T0)
        wrong = replace(self.requests[1], target=replace(self.requests[1].target, id=str(uuid4())))
        with self.assertRaises(ValidationError):
            self.groups.begin(self.group.id, (self.requests[0], wrong), started_at=T0)
        run = self.begin()
        with self.assertRaisesRegex(ValidationError, "Tamamlanmamış"):
            self.groups.save(self.group.name, replace(self.definition, daily_queries=50), recorded_at=T1)
        self.assertEqual(tuple(a.request for a in self.groups.run_show(run.id).attempts), self.requests)

    def test_begin_rejects_insufficient_entire_run_budget_without_reservations(self):
        self.groups.save(self.group.name, replace(self.definition, daily_queries=1), recorded_at=T0)
        with self.assertRaisesRegex(ValidationError, "tüm hedefleri"):
            self.begin()
        self.assertEqual(self.groups.runs(self.group.id), ())
        self.assertEqual(self.groups.budget(self.group.id, at=T0).used_queries, 0)

    def test_per_run_limit_rejects_entire_group(self):
        self.groups.save(self.group.name, replace(self.definition, per_run_queries=1), recorded_at=T0)
        with self.assertRaisesRegex(ValidationError, "çalışma sorgu"):
            self.begin()
        self.assertEqual(self.groups.runs(self.group.id), ())

    def test_request_id_is_idempotent_and_rejects_conflicting_scope(self):
        request_id = str(uuid4())
        run = self.begin(request_id=request_id)
        self.assertEqual(self.begin(request_id=request_id), run)
        self.assertEqual(self.groups.find_run(request_id), run)
        self.assertIsNone(self.groups.find_run(str(uuid4())))
        changed = replace(self.requests[0], target=replace(self.requests[0].target, name="Acme new name"))
        with self.assertRaisesRegex(ValidationError, "farklı"):
            self.groups.begin(self.group.id, (changed, self.requests[1]), started_at=T0, request_id=request_id)
        with self.assertRaisesRegex(ValidationError, "tamamlanmamış"):
            self.begin()

    def test_reservation_survives_reopen_counts_budget_and_cannot_repeat(self):
        run = self.begin()
        operation = self.groups.reserve_attempt(run.id, 0, started_at=T0)
        fresh = SQLiteMentionGroupRepository(self.path)
        self.assertEqual(fresh.run_show(run.id).attempts[0].result_run_id, operation.result_run_id)
        self.assertEqual(fresh.budget(self.group.id, at=T0).used_queries, 1)
        with self.assertRaisesRegex(ValidationError, "yeniden sorgulanamaz"):
            fresh.reserve_attempt(run.id, 0, started_at=T1)

    def test_atomic_source_failure_receipt_retains_budget(self):
        run = self.begin()
        operation, result = self.fail(run, 0)
        attempt = self.groups.run_show(run.id).attempts[0]
        self.assertEqual((attempt.status, attempt.result_run_id), ("failed", result.id))
        self.assertEqual(result.id, operation.result_run_id)
        self.assertEqual(self.groups.budget(self.group.id, at=T0).used_queries, 1)
        with self.assertRaises(ValidationError):
            self.sources.record_failure(self.requests[0], error="Again", started_at=T1, finished_at=T1, operation=operation)
        self.assertEqual(len(self.sources.catalog().runs), 1)

    def test_receipt_failure_rolls_source_write_back_leaving_reserved_unknown(self):
        run = self.begin()
        operation = self.groups.reserve_attempt(run.id, 0, started_at=T0)
        with patch("xti.adapters.sqlite_mention_groups.record_group_result", side_effect=StorageError("Controlled receipt failure")):
            with self.assertRaises(StorageError):
                self.sources.record_failure(self.requests[0], error="Failure", started_at=T0, finished_at=T0, operation=operation)
        self.assertEqual(self.sources.catalog().runs, ())
        self.assertEqual(self.groups.run_show(run.id).attempts[0].status, "reserved")
        recovered = self.groups.recover(run.id, recorded_at=T1)
        self.assertEqual(tuple(a.status for a in recovered.attempts), ("unknown", "pending"))
        self.assertEqual(self.groups.budget(self.group.id, at=T1).used_queries, 1)
        with self.assertRaises(ValidationError):
            self.groups.reserve_attempt(run.id, 0, started_at=T1)
        self.fail(run, 1, T1)
        self.assertEqual(self.groups.finish(run.id, finished_at=T1).status, "failed")

    def test_atomic_receipt_rejects_wrong_request_or_source_start_time(self):
        run = self.begin()
        operation = self.groups.reserve_attempt(run.id, 0, started_at=T0)
        for request, started in ((self.requests[1], T0), (self.requests[0], T1)):
            with self.subTest(request=request, started=started), self.assertRaises(ValidationError):
                self.sources.record_failure(request, error="Failure", started_at=started, finished_at=T1, operation=operation)
        self.assertEqual(self.sources.catalog().runs, ())

    def test_due_and_budget_survive_revision_disable_reenable(self):
        run = self.begin()
        self.fail(run, 0); self.fail(run, 1)
        self.groups.finish(run.id, finished_at=T0)
        self.groups.disable(self.group.id, reason="Pause monitoring", recorded_at=T1)
        updated = self.groups.save(self.group.name, replace(self.definition, daily_queries=2), recorded_at=T1)
        self.assertEqual(updated.id, self.group.id)
        self.assertEqual(self.groups.budget(updated.id, at=T1).used_queries, 2)
        with self.assertRaisesRegex(ValidationError, "arama zamanı"):
            self.begin(T1)
        with self.assertRaisesRegex(ValidationError, "bütçesi"):
            self.begin(T2)
        self.assertEqual(len(self.begin(T3).attempts), 2)
        self.assertEqual(tuple(r.id for r in self.groups.runs(self.group.id))[0], run.id)

    def test_disabled_group_can_recover_and_skip_but_not_query(self):
        run = self.begin()
        self.groups.reserve_attempt(run.id, 0, started_at=T0)
        self.groups.disable(self.group.id, reason="Stop monitoring", recorded_at=T1)
        self.groups.recover(run.id, recorded_at=T1)
        with self.assertRaisesRegex(ValidationError, "etkin değil"):
            self.groups.reserve_attempt(run.id, 1, started_at=T1)
        self.groups.skip_pending(run.id, reason="Group disabled", recorded_at=T1)
        final = self.groups.finish(run.id, finished_at=T1)
        self.assertEqual(tuple(a.status for a in final.attempts), ("unknown", "skipped"))
        self.assertEqual(self.groups.list(), ())
        self.assertEqual(len(self.groups.list(active_only=False)), 1)

    def test_midnight_reservation_is_charged_to_actual_attempt_day(self):
        old = "2026-11-15T23:59:59+00:00"
        new = "2026-11-16T00:00:00+00:00"
        run = self.begin(old)
        self.fail(run, 0, old)
        self.fail(run, 1, new)
        self.assertEqual(self.groups.budget(self.group.id, at=old).used_queries, 1)
        self.assertEqual(self.groups.budget(self.group.id, at=new).used_queries, 1)

    def test_notifications_are_a_separate_recoverable_stage(self):
        run = self.begin()
        operation, source = self.success(run, 0)
        self.fail(run, 1)
        with self.assertRaisesRegex(ValidationError, "bildirim"):
            self.groups.finish(run.id, finished_at=T1)
        notice = SQLiteMentionNotificationBridge(self.path).notify(group_id=self.group.id,
            request=self.requests[0], mention_run_id=source.id, operation_id=operation.attempt_id, executed_at=T1)
        # A process can die here. Repeating the bridge and recording the receipt does not re-search.
        again = SQLiteMentionNotificationBridge(self.path).notify(group_id=self.group.id,
            request=self.requests[0], mention_run_id=source.id, operation_id=operation.attempt_id, executed_at=T1)
        self.assertEqual(again.run.id, notice.run.id)
        self.groups.record_notification(run.id, 0, notification_run_id=notice.run.id, recorded_at=T1)
        self.groups.record_notification(run.id, 0, notification_run_id=notice.run.id, recorded_at=T1)
        self.assertEqual(self.groups.finish(run.id, finished_at=T1).status, "partial")
        self.assertEqual(len(self.sources.catalog().runs), 2)
        self.assertEqual(self.groups.budget(self.group.id, at=T1).used_queries, 2)

    def test_deleted_tail_or_fabricated_metadata_is_detected(self):
        self.begin()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DELETE FROM mention_group_events WHERE sequence=(SELECT MAX(sequence) FROM mention_group_events)")
        with self.assertRaises(StorageError):
            self.groups.list()

    def test_event_metadata_is_bound_to_hashed_envelope(self):
        self.begin()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE mention_group_events SET recorded_at=?", (T1,))
        with self.assertRaises(StorageError):
            self.groups.list()

    def test_historical_source_slice_is_audited_and_does_not_include_later_hits(self):
        run = self.begin()
        _, first = self.success(run, 0)
        self.sources.apply(self.requests[0], MentionResponse(build_query(self.requests[0].target), None,
            (MentionHit("https://news.test/later", "Later", "Summary", None, .7),), 1), started_at=T1, finished_at=T1)
        with closing(sqlite3.connect(self.path)) as connection:
            old = read_mentions_catalog(connection, through_run_id=first.id)
            self.assertEqual(len(old.records), 1)
            self.assertEqual(old.records[0].hit.url, "https://news.test/article")
            with self.assertRaises(ValidationError):
                read_mentions_catalog(connection, through_run_id=str(uuid4()))

    def test_known_source_clock_regression_stops_before_query_reservation(self):
        request = self.requests[0]
        source = self.sources.apply(request, MentionResponse(build_query(request.target), None, (), 1),
            started_at=T3, finished_at=T3)
        run = self.begin(T0)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValidationError, "son kaynak çalışmasından eski"):
            self.groups.reserve_attempt(run.id, 0, started_at=T0)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.groups.budget(self.group.id, at=T0).used_queries, 0)
        self.assertEqual(tuple(a.status for a in self.groups.run_show(run.id).attempts), ("pending", "pending"))
        self.assertEqual(tuple(r.id for r in self.sources.catalog().runs), (source.id,))
        # Once the clock catches up, the same unattempted work can be reserved.
        operation = self.groups.reserve_attempt(run.id, 0, started_at=T3)
        self.assertEqual(self.groups.run_show(run.id).attempts[0].id, operation.attempt_id)

    def test_batch_capacity_preflight_rejects_whole_group(self):
        with patch("xti.adapters.sqlite_mentions.MAX_MENTION_RUNS", 1):
            with self.assertRaises(StorageError):
                self.sources.validate(max_results=10, pending_runs=2)
        with patch("xti.adapters.sqlite_mentions.MAX_MENTION_RECORDS", 15):
            with self.assertRaises(StorageError):
                self.sources.validate(max_results=10, pending_runs=2)
        self.assertEqual(self.sources.catalog().runs, ())


if __name__ == "__main__":
    unittest.main()

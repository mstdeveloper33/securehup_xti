"""Bounded monitoring ownership, timing and honest summaries over small ports."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from xti.application.monitoring import MonitorService
from xti.domain.assets import ValidationError
from xti.domain.findings import ImportSummary
from xti.domain.jobs import ScanJob
from xti.domain.monitoring import (
    MonitorAttempt, MonitorDetails, MonitorEntry, MonitorRun, MonitorSpec,
)
from xti.ports.jobs import WorkerBusyError
from tests.test_jobs import TrackingLock


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


class Time:
    def __init__(self):
        self.value = 100.0
        self.sleeps = []

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds


class Repository:
    def __init__(self, lock):
        self.lock = lock
        self.run = None
        self.entries = []
        self.calls = []

    def create(self, spec, now):
        assert self.lock.held
        self.calls.append("create")
        self.run = MonitorRun("monitor-1", spec, "running", now, None, None, None)
        return self.run

    def enqueue(self, run_id, cycle, provider, now):
        assert self.lock.held
        self.calls.append("enqueue")
        job = ScanJob(f"job-{len(self.entries) + 1}", self.run.spec.targets,
                      self.run.spec.typos, provider, self.run.spec.rule_version, "queued", now, now, 0)
        self.entries.append(MonitorEntry(cycle, provider, job, None))
        return job

    def finish(self, run_id, status, reason, now, elapsed_seconds):
        assert self.lock.held
        self.calls.append("finish")
        self.run = replace(self.run, status=status, stop_reason=reason,
                           finished_at=now, elapsed_seconds=elapsed_seconds)
        return self.run

    def recover(self, now):
        assert self.lock.held
        self.calls.append("recover")
        return 2

    def get(self, run_id):
        self.calls.append("get")
        return MonitorDetails(self.run, tuple(self.entries))

    def list(self, limit=20):
        self.calls.append(("list", limit))
        return (self.run,) if self.run is not None else ()


class Runner:
    def __init__(self, repository, timer, lock):
        self.repository = repository
        self.timer = timer
        self.lock = lock
        self.calls = []
        self.outcomes = []
        self.seconds_per_attempt = 0.0
        self.jobs = SimpleNamespace(recover_interrupted=Mock())
        self.discoveries = {
            provider: SimpleNamespace(
                matcher=SimpleNamespace(rule_version="rules-v1"),
                validate_targets=Mock(side_effect=lambda targets, typos=False: targets),
            ) for provider in ("crt.sh", "urlscan")
        }

    def run_owned(self, job_id, *, monitor_id=None, progress=None):
        assert self.lock.held
        self.calls.append((job_id, monitor_id))
        outcome = self.outcomes.pop(0) if self.outcomes else "complete"
        self.timer.value += self.seconds_per_attempt
        entry = next(item for item in self.repository.entries if item.job.id == job_id)
        failed = isinstance(outcome, BaseException)
        status = ("interrupted" if isinstance(outcome, (KeyboardInterrupt, SystemExit)) else "failed") if failed else outcome
        summary = None if failed else ImportSummary(2, 2, 0, 1, 0)
        attempt = MonitorAttempt(f"attempt-{job_id}", 1, status, NOW.isoformat(), NOW.isoformat(),
                                 None, 1, int(status == "failed"), int(status == "partial"), summary)
        index = self.repository.entries.index(entry)
        self.repository.entries[index] = replace(entry, attempt=attempt)
        if failed:
            raise outcome
        return attempt


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.lock = TrackingLock()
        self.timer = Time()
        self.repo = Repository(self.lock)
        self.jobs = Runner(self.repo, self.timer, self.lock)
        self.clock = Mock(return_value=NOW)
        self.service = MonitorService(self.repo, self.jobs, clock=self.clock,
                                      monotonic=self.timer.monotonic, sleeper=self.timer.sleep)
        self.spec = MonitorSpec(("example.com",), ("crt.sh", "urlscan"), False,
                                "rules-v1", 2, 300, 1000)

    def test_cycles_use_one_owner_and_gap_after_completed_cycle(self):
        self.jobs.seconds_per_attempt = 10
        report = self.service.start(self.spec)
        self.assertEqual(self.lock.acquisitions, 1)
        self.assertFalse(self.lock.held)
        self.assertEqual(len(self.jobs.calls), 4)
        self.assertTrue(all(identifier == "monitor-1" for _, identifier in self.jobs.calls))
        self.assertEqual(report.run.stop_reason, "cycles")
        self.assertEqual(report.run.elapsed_seconds, 340)
        self.assertEqual(sum(self.timer.sleeps), 300)
        self.assertTrue(all(0 < delay <= 1 for delay in self.timer.sleeps))
        self.assertEqual((report.completed_cycles, report.outcome), (2, "complete"))
        self.assertEqual(self.repo.calls[:2], ["recover", "create"])
        self.jobs.jobs.recover_interrupted.assert_called_once()

    def test_duration_between_sources_does_not_queue_or_start_next_source(self):
        self.jobs.seconds_per_attempt = 10
        report = self.service.start(replace(self.spec, max_duration_seconds=1))
        self.assertEqual(len(self.jobs.calls), 1)
        self.assertEqual(len(self.repo.entries), 1)
        self.assertEqual(report.run.stop_reason, "duration")
        self.assertEqual(report.run.elapsed_seconds, 10)
        self.assertEqual(report.completed_cycles, 0)
        self.assertEqual(report.sources[1].not_started, 2)
        self.assertEqual(report.sources[1].failed, 0)
        self.assertEqual(report.outcome, "complete")

    def test_duration_during_wait_stops_exactly_and_does_not_start_next_cycle(self):
        report = self.service.start(replace(self.spec, max_duration_seconds=12))
        self.assertEqual(len(self.jobs.calls), 2)
        self.assertEqual(sum(self.timer.sleeps), 12)
        self.assertEqual(report.run.elapsed_seconds, 12)
        self.assertEqual(report.run.stop_reason, "duration")
        self.assertEqual(report.completed_cycles, 1)

    def test_time_spent_persisting_or_printing_does_not_allow_late_network_start(self):
        def progress(message):
            if "kaynak:" in message:
                self.timer.value += 2

        report = self.service.start(replace(self.spec, max_duration_seconds=1), progress=progress)
        self.assertEqual(len(self.repo.entries), 1)
        self.assertEqual(self.jobs.calls, [])
        self.assertEqual(report.run.stop_reason, "duration")
        self.assertEqual(report.sources[0].scheduled_jobs, 1)
        self.assertEqual(report.sources[0].started_attempts, 0)
        self.assertEqual(report.sources[0].unknown_result_count, 0)

    def test_source_failures_continue_and_are_separate_from_session_completion(self):
        self.jobs.outcomes = ["failed", "partial", "complete", "complete"]
        report = self.service.start(self.spec)
        self.assertEqual(report.run.status, "completed")
        self.assertEqual(report.outcome, "partial")
        self.assertEqual(report.completed_cycles, 2)
        self.assertEqual((report.sources[0].failed, report.sources[1].partial), (1, 1))
        self.assertEqual(report.sources[0].unknown_result_count, 0)
        self.assertEqual(report.sources[0].query_count, 2)
        self.assertEqual(report.sources[0].failed_queries, 1)

    def test_interrupt_during_work_keeps_unknown_result_visible_and_rethrows(self):
        self.jobs.outcomes = [KeyboardInterrupt()]
        with self.assertRaises(KeyboardInterrupt):
            self.service.start(self.spec)
        report = self.service.show("monitor-1")
        self.assertEqual((report.run.status, report.run.stop_reason), ("interrupted", "cancelled"))
        self.assertEqual(report.sources[0].unknown_result_count, 1)
        self.assertEqual(report.sources[0].findings_created, 0)
        self.assertEqual(report.sources[0].query_count, 1)
        self.assertEqual(report.sources[1].started_attempts, 0)
        self.assertFalse(self.lock.held)

    def test_interrupt_during_wait_keeps_completed_source_results(self):
        self.service.sleeper = Mock(side_effect=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.service.start(self.spec)
        report = self.service.show("monitor-1")
        self.assertEqual(report.run.status, "interrupted")
        self.assertEqual(report.completed_cycles, 1)
        self.assertEqual([source.findings_created for source in report.sources], [1, 1])
        self.assertTrue(all(source.unknown_result_count == 0 for source in report.sources))

    def test_application_error_stops_other_sources_and_preserves_original_error(self):
        failure = RuntimeError("private error content")
        self.jobs.outcomes = [failure]
        with self.assertRaises(RuntimeError) as raised:
            self.service.start(self.spec)
        self.assertIs(raised.exception, failure)
        self.assertEqual(len(self.jobs.calls), 1)
        self.assertEqual((self.repo.run.status, self.repo.run.stop_reason), ("failed", "error"))
        self.assertFalse(self.lock.held)

    def test_error_while_closing_does_not_replace_original_failure(self):
        failure = RuntimeError("original")
        self.jobs.outcomes = [failure]
        self.repo.finish = Mock(side_effect=OSError("disk unavailable"))
        with self.assertRaises(RuntimeError) as raised:
            self.service.start(self.spec)
        self.assertIs(raised.exception, failure)
        self.assertEqual(self.repo.run.status, "running")
        self.assertFalse(self.lock.held)

    def test_created_identifier_is_reported_before_any_source_work(self):
        seen = []

        def progress(message):
            seen.append(message)
            if message.startswith("İzleme kimliği:"):
                self.assertEqual(self.jobs.calls, [])
                raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self.service.start(self.spec, progress=progress)
        self.assertEqual(seen, ["İzleme kimliği: monitor-1"])
        self.assertEqual(self.repo.run.status, "interrupted")

    def test_busy_owner_cannot_create_or_recover_session(self):
        self.lock.busy = True
        with self.assertRaises(WorkerBusyError):
            self.service.start(self.spec)
        self.assertEqual(self.repo.calls, [])
        self.assertEqual(self.jobs.calls, [])

    def test_invalid_specs_are_rejected_before_storage_or_ownership(self):
        for changes in (
            {"targets": ()}, {"targets": ("example.com", "EXAMPLE.COM.")},
            {"targets": ("https://example.com",)}, {"targets": ("example.com",) * 6},
            {"providers": ()}, {"providers": ("crt.sh", "crt.sh")}, {"providers": ("unknown",)},
            {"typos": 1}, {"rule_version": " "}, {"rule_version": "x\n"},
            {"rule_version": "x" * 513}, {"max_cycles": True}, {"max_cycles": 0},
            {"max_cycles": 1001}, {"interval_seconds": 299}, {"interval_seconds": 86401},
            {"max_duration_seconds": 0}, {"max_duration_seconds": 604801},
            {"max_duration_seconds": float("nan")},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.service.start(replace(self.spec, **changes))
        self.assertEqual(self.repo.calls, [])
        self.assertEqual(self.lock.acquisitions, 0)

    def test_missing_provider_or_wrong_rule_or_unregistered_target_fails_before_lock(self):
        self.jobs.discoveries["urlscan"].matcher.rule_version = "old-rule"
        with self.assertRaises(ValidationError):
            self.service.start(self.spec)
        self.jobs.discoveries["urlscan"].matcher.rule_version = "rules-v1"
        self.jobs.discoveries["crt.sh"].validate_targets.side_effect = ValidationError("Adres kayıtlı değil.")
        with self.assertRaises(ValidationError):
            self.service.start(self.spec)
        self.assertEqual(self.repo.calls, [])
        self.assertEqual(self.lock.acquisitions, 0)

    def test_normalized_targets_are_snapshotted_once(self):
        report = self.service.start(replace(self.spec, targets=("EXAMPLE.COM.",), max_cycles=1))
        self.assertEqual(report.run.spec.targets, ("example.com",))
        for discovery in self.jobs.discoveries.values():
            discovery.validate_targets.assert_called_once_with(("example.com",), typos=False)

    def test_bad_clocks_fail_before_creation(self):
        for value in (None, datetime(2026, 1, 1), "invalid"):
            self.clock.return_value = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.service.start(self.spec)
        self.clock.return_value = NOW
        for value in (True, float("nan"), float("inf"), 10**1000):
            self.service.monotonic = lambda value=value: value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.service.start(self.spec)
        self.assertEqual(self.repo.calls, [])
        self.assertEqual(self.lock.acquisitions, 0)

    def test_backward_monotonic_during_work_stops_session(self):
        self.jobs.seconds_per_attempt = -1
        with self.assertRaises(ValidationError):
            self.service.start(self.spec)
        self.assertEqual(self.repo.run.status, "failed")
        self.assertIsNone(self.repo.run.elapsed_seconds)
        self.assertEqual(len(self.jobs.calls), 1)

    def test_wall_clock_rollback_does_not_extend_monotonic_budget(self):
        self.clock.side_effect = lambda: NOW - timedelta(seconds=self.timer.value)
        report = self.service.start(replace(self.spec, max_duration_seconds=5))
        self.assertEqual(report.run.elapsed_seconds, 5)
        self.assertEqual(report.run.stop_reason, "duration")
        self.assertEqual(len(self.jobs.calls), 2)

    def test_reads_need_no_runner_clock_or_lock_and_show_uses_one_snapshot(self):
        self.service.start(replace(self.spec, max_cycles=1))
        self.repo.calls.clear()
        read = MonitorService(self.repo, clock=Mock(side_effect=AssertionError("No clock on read")))
        self.assertEqual(read.show("monitor-1").outcome, "complete")
        self.assertEqual(self.repo.calls, ["get"])
        self.assertEqual(read.list(), (self.repo.run,))
        self.assertEqual(self.lock.acquisitions, 1)
        with self.assertRaises(ValidationError):
            read.start(self.spec)
        with self.assertRaises(ValidationError):
            read.recover()

    def test_read_validation_and_explicit_recovery(self):
        for identifier in ("", " ", "x\n", "x" * 65):
            with self.subTest(identifier=identifier), self.assertRaises(ValidationError):
                self.service.show(identifier)
        for limit in (0, 101, True, "1"):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                self.service.list(limit)
        self.assertEqual(self.repo.calls, [])
        self.assertEqual(self.service.recover(), 2)
        self.assertEqual(self.repo.calls, ["recover"])
        self.jobs.jobs.recover_interrupted.assert_not_called()

    def test_summary_attributes_known_results_and_counts_unknown_attempts(self):
        self.service.start(replace(self.spec, max_cycles=1))
        first, second = self.repo.entries
        first = replace(first, attempt=replace(first.attempt, summary=ImportSummary(9, 3, 6, 2, 5)))
        second = replace(second, attempt=replace(second.attempt, status="interrupted", summary=None))
        details = MonitorDetails(replace(self.repo.run, status="interrupted"), (first, second))
        report = MonitorService.summarize(details)
        self.assertEqual(report.completed_cycles, 1)
        self.assertEqual((report.sources[0].observations_created, report.sources[0].findings_created), (3, 2))
        self.assertEqual(report.sources[1].unknown_result_count, 1)
        self.assertEqual(report.sources[1].findings_created, 0)
        self.assertEqual(report.outcome, "interrupted")

    def test_retired_unstarted_job_does_not_change_successful_started_work_outcome(self):
        self.service.start(replace(self.spec, max_cycles=1))
        first, second = self.repo.entries
        run = replace(self.repo.run, stop_reason="duration")
        unstarted = replace(second, attempt=None, job=replace(second.job, status="interrupted"))
        queued_report = MonitorService.summarize(MonitorDetails(run, (first, unstarted)))
        unscheduled_report = MonitorService.summarize(MonitorDetails(run, (first,)))
        self.assertEqual(queued_report.outcome, "complete")
        self.assertEqual(queued_report.outcome, unscheduled_report.outcome)
        self.assertEqual(queued_report.completed_cycles, 0)
        self.assertEqual(queued_report.sources[1].scheduled_jobs, 1)
        self.assertEqual(queued_report.sources[1].started_attempts, 0)
        self.assertEqual(queued_report.sources[1].not_started, 1)
        self.assertEqual(queued_report.sources[1].unknown_result_count, 0)


if __name__ == "__main__":
    unittest.main()

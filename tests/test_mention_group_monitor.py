"""Foreground polling cannot bypass persistent group budget/interval decisions."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from uuid import uuid4

from xti.application.mention_group_monitor import MentionGroupMonitor
from xti.domain.assets import ValidationError


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = []

    def now(self):
        return datetime(2026, 11, 15, tzinfo=timezone.utc) + timedelta(seconds=self.value)

    def sleep(self, amount):
        self.sleeps.append(amount)
        self.value += amount


class MentionGroupMonitorTests(unittest.TestCase):
    def setUp(self):
        self.identifier = str(uuid4())
        self.clock = FakeClock()
        self.service = Mock()
        self.monitor = MentionGroupMonitor(self.service, clock=self.clock.now,
            monotonic=lambda: self.clock.value, sleeper=self.clock.sleep)

    @staticmethod
    def result(*, status="complete", reason=None, run=True, used=1):
        return {"status": status, "reason": reason, "run": SimpleNamespace(id=str(uuid4())) if run else None,
                "next_due_at": "2026-11-15T01:00:00+00:00", "daily_queries_used": used}

    def test_normal_runs_pass_only_group_id_and_do_not_override_budgets(self):
        self.service.run.side_effect = [self.result(), self.result(status="partial", used=2)]
        progress = []
        result = self.monitor.run(self.identifier, cycles=2, interval_seconds=60, progress=progress.append)
        self.assertEqual((result.completed_cycles, result.stop_reason, result.elapsed_seconds), (2, "cycles", 60))
        self.assertEqual([cycle.status for cycle in result.cycles], ["complete", "partial"])
        self.assertEqual([cycle.cycle for cycle in result.cycles], [1, 2])
        self.assertTrue(all(call.args == (self.identifier,) and not call.kwargs for call in self.service.run.call_args_list))
        self.assertEqual(sum(self.clock.sleeps), 60)
        self.assertLessEqual(max(self.clock.sleeps), 1)
        self.assertEqual(len(progress), 4)

    def test_not_due_waits_then_uses_service_decision(self):
        self.service.run.side_effect = [self.result(status="skipped", reason="not_due", run=False, used=0), self.result()]
        result = self.monitor.run(self.identifier)
        self.assertIsNone(result.cycles[0].run_id)
        self.assertEqual(result.cycles[0].reason, "not_due")
        self.assertIsNotNone(result.cycles[1].run_id)
        self.assertEqual(self.service.run.call_count, 2)

    def test_daily_budget_stops_without_polling_or_new_request(self):
        self.service.run.return_value = self.result(status="skipped", reason="daily_budget", run=False, used=5)
        result = self.monitor.run(self.identifier, cycles=10)
        self.assertEqual((result.completed_cycles, result.stop_reason), (1, "daily_budget"))
        self.assertEqual(self.service.run.call_count, 1)
        self.assertEqual(self.clock.sleeps, [])

    def test_duration_prevents_next_collection_after_long_run(self):
        def run(_):
            self.clock.value += 40
            return self.result()
        self.service.run.side_effect = run
        result = self.monitor.run(self.identifier, duration_seconds=61)
        self.assertEqual((result.completed_cycles, result.stop_reason, result.elapsed_seconds), (1, "duration", 61))
        self.assertEqual(self.service.run.call_count, 1)

    def test_keyboard_interrupt_does_not_retry_possible_metered_request(self):
        self.service.run.side_effect = [self.result(), KeyboardInterrupt()]
        result = self.monitor.run(self.identifier, cycles=3)
        self.assertEqual((result.completed_cycles, result.stop_reason), (1, "interrupted"))
        self.assertEqual(self.service.run.call_count, 2)
        self.assertEqual([call[0] for call in self.service.method_calls], ["run", "run"])

    def test_keyboard_interrupt_during_wait_preserves_completed_run(self):
        self.service.run.return_value = self.result()
        self.monitor.sleeper = Mock(side_effect=KeyboardInterrupt())
        result = self.monitor.run(self.identifier)
        self.assertEqual((result.completed_cycles, result.stop_reason), (1, "interrupted"))
        self.assertIsNotNone(result.cycles[0].run_id)
        self.assertEqual(self.service.run.call_count, 1)

    def test_validation_and_storage_failures_are_not_retried(self):
        self.service.run.side_effect = ValidationError("Closed group")
        with self.assertRaises(ValidationError):
            self.monitor.run(self.identifier)
        self.assertEqual(self.service.run.call_count, 1)
        self.assertEqual(self.clock.sleeps, [])

    def test_invalid_limits_or_identifier_stop_before_service(self):
        for options in ({"cycles": 0}, {"cycles": True}, {"cycles": 101},
                        {"interval_seconds": 59}, {"interval_seconds": 86401},
                        {"duration_seconds": 0}, {"duration_seconds": 604801}):
            with self.assertRaises(ValidationError):
                self.monitor.run(self.identifier, **options)
        with self.assertRaises(ValidationError):
            self.monitor.run("bad-id")
        self.service.run.assert_not_called()

    def test_invalid_clock_fails_before_first_request(self):
        for value in (True, float("nan"), float("inf"), "0"):
            self.monitor.monotonic = lambda: value
            with self.assertRaises(ValidationError):
                self.monitor.run(self.identifier)
        self.monitor.monotonic = Mock(side_effect=[0, -1])
        with self.assertRaises(ValidationError):
            self.monitor.run(self.identifier)
        self.monitor.monotonic = lambda: 0
        self.monitor.clock = lambda: datetime(2026, 11, 15)
        with self.assertRaises(ValidationError):
            self.monitor.run(self.identifier)
        self.service.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

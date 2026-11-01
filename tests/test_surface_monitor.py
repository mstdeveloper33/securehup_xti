"""Bounded foreground orchestration for selected surface checks."""

from datetime import datetime, timezone
import unittest

from xti.application.surface_monitor import SurfaceMonitorService
from xti.domain.assets import ValidationError
from xti.domain.surface import SurfaceMonitorOutcome


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


class Timer:
    def __init__(self, *, interrupt: bool = False) -> None:
        self.value = 100.0
        self.sleeps = []
        self.interrupt = interrupt

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        if self.interrupt:
            raise KeyboardInterrupt()
        self.sleeps.append(seconds)
        self.value += seconds


class FakeRunner:
    def __init__(self, name, timer, outcomes, *, duration=0.0, prepared="example.com"):
        self.name = name
        self.timer = timer
        self.outcomes = list(outcomes)
        self.duration = duration
        self.prepared = prepared
        self.prepare_calls = []
        self.check_calls = []

    def prepare(self, asset_value):
        self.prepare_calls.append(asset_value)
        return self.prepared

    def check(self, asset_value):
        self.check_calls.append(asset_value)
        self.timer.value += self.duration
        status, change = self.outcomes.pop(0)
        return SurfaceMonitorOutcome(
            self.name, status, f"{self.name}-{len(self.check_calls)}", change,
            NOW.isoformat(),
        )


class SurfaceMonitorTests(unittest.TestCase):
    def service(self, runners, timer):
        return SurfaceMonitorService(
            runners, clock=lambda: NOW,
            monotonic=timer.monotonic, sleeper=timer.sleep,
        )

    def test_selected_checks_repeat_in_order_and_summarize_changes(self):
        timer = Timer()
        web = FakeRunner(
            "web", timer, (("complete", "baseline"), ("complete", "changed")),
        )
        mail = FakeRunner(
            "mail", timer, (("partial", "baseline"), ("complete", "unchanged")),
        )
        report = self.service((web, mail), timer).run(
            "EXAMPLE.COM", max_cycles=2, interval_seconds=300,
            max_duration_seconds=1000,
        )
        self.assertEqual(report.asset_value, "example.com")
        self.assertEqual(report.checks, ("web", "mail"))
        self.assertEqual((report.completed_cycles, report.completed_checks), (2, 4))
        self.assertEqual(
            (report.complete_checks, report.partial_checks, report.failed_checks),
            (3, 1, 0),
        )
        self.assertEqual(report.notifications_created, 1)
        self.assertEqual(
            [(step.cycle, step.check_type) for step in report.steps],
            [(1, "web"), (1, "mail"), (2, "web"), (2, "mail")],
        )
        self.assertEqual(sum(timer.sleeps), 300)

    def test_duration_stops_before_next_check_and_keeps_completed_step(self):
        timer = Timer()
        web = FakeRunner("web", timer, (("complete", "changed"),), duration=2.0)
        mail = FakeRunner("mail", timer, (("complete", "baseline"),))
        report = self.service((web, mail), timer).run(
            "example.com", max_cycles=2, interval_seconds=300,
            max_duration_seconds=1,
        )
        self.assertEqual(report.stop_reason, "duration")
        self.assertEqual((report.completed_cycles, report.completed_checks), (0, 1))
        self.assertEqual(report.notifications_created, 1)
        self.assertEqual(web.check_calls, ["example.com"])
        self.assertEqual(mail.check_calls, [])

    def test_duplicate_or_mismatched_runners_fail_before_any_check(self):
        timer = Timer()
        first = FakeRunner("web", timer, (("complete", "baseline"),))
        duplicate = FakeRunner("web", timer, (("complete", "baseline"),))
        with self.assertRaisesRegex(ValidationError, "tekrarlı"):
            self.service((first, duplicate), timer).run("example.com")
        self.assertEqual((first.prepare_calls, duplicate.prepare_calls), ([], []))
        self.assertEqual((first.check_calls, duplicate.check_calls), ([], []))

        mismatch = FakeRunner(
            "mail", timer, (("complete", "baseline"),), prepared="other.example",
        )
        with self.assertRaisesRegex(ValidationError, "aynı kök"):
            self.service((mismatch,), timer).run("example.com")
        self.assertEqual(mismatch.check_calls, [])

    def test_invalid_outcome_is_rejected_after_runner_returns(self):
        timer = Timer()
        runner = FakeRunner("web", timer, (("unknown", "baseline"),))
        with self.assertRaisesRegex(ValidationError, "geçersiz sonuç"):
            self.service((runner,), timer).run("example.com")

    def test_ctrl_c_during_wait_propagates_after_completed_cycle(self):
        timer = Timer(interrupt=True)
        runner = FakeRunner(
            "web", timer, (("complete", "baseline"), ("complete", "unchanged")),
        )
        with self.assertRaises(KeyboardInterrupt):
            self.service((runner,), timer).run(
                "example.com", max_cycles=2, interval_seconds=300,
                max_duration_seconds=1000,
            )
        self.assertEqual(runner.check_calls, ["example.com"])

    def test_invalid_limits_fail_before_prepare(self):
        timer = Timer()
        runner = FakeRunner("web", timer, (("complete", "baseline"),))
        with self.assertRaisesRegex(ValidationError, "tur sayısı"):
            self.service((runner,), timer).run("example.com", max_cycles=0)
        self.assertEqual(runner.prepare_calls, [])


if __name__ == "__main__":
    unittest.main()

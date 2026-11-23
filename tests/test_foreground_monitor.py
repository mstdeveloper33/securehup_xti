"""Shared foreground clock guards keep every monitor fail-closed."""

from datetime import datetime, timezone
import unittest

from xti.application.foreground_monitor import (
    MonotonicBudget, monotonic_value, utc_now,
)
from xti.domain.assets import ValidationError


class ForegroundMonitorTests(unittest.TestCase):
    def test_utc_now_normalizes_and_rejects_naive_or_invalid_values(self):
        value = utc_now(
            lambda: datetime(2026, 11, 23, 3, tzinfo=timezone.utc),
            error_message="bad wall clock",
        )
        self.assertEqual(value, "2026-11-23T03:00:00+00:00")
        for invalid in (datetime(2026, 11, 23), None, "now"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValidationError, "bad wall clock"):
                    utc_now(lambda invalid=invalid: invalid, error_message="bad wall clock")

    def test_monotonic_value_rejects_boolean_nan_and_non_numeric_values(self):
        self.assertEqual(monotonic_value(lambda: 2, error_message="bad timer"), 2.0)
        for invalid in (True, float("nan"), float("inf"), None, "2"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValidationError, "bad timer"):
                    monotonic_value(
                        lambda invalid=invalid: invalid,
                        error_message="bad timer",
                    )

    def test_budget_measures_elapsed_and_rejects_rollback(self):
        values = iter((10, 12, 11))
        budget = MonotonicBudget(
            lambda: next(values), invalid_message="bad timer",
            rollback_message="timer moved backwards",
        )
        self.assertEqual(budget.start(), 10)
        self.assertEqual(budget.elapsed(), 2)
        with self.assertRaisesRegex(ValidationError, "timer moved backwards"):
            budget.elapsed()

    def test_budget_requires_explicit_start(self):
        budget = MonotonicBudget(
            lambda: 1, invalid_message="bad timer",
            rollback_message="timer moved backwards",
        )
        with self.assertRaises(RuntimeError):
            budget.elapsed()


if __name__ == "__main__":
    unittest.main()

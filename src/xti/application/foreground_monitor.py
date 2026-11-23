"""Shared clock guards for bounded foreground monitoring loops."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import math

from xti.domain.assets import ValidationError


def utc_now(clock: Callable[[], datetime], *, error_message: str) -> str:
    """Return a timezone-aware UTC timestamp or fail before durable work starts."""
    try:
        value = clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError("timezone required")
        return value.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError(error_message) from error


def monotonic_value(
    monotonic: Callable[[], float], *, error_message: str,
) -> float:
    """Read a finite, non-boolean monotonic value with a stable public error."""
    try:
        value = monotonic()
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("invalid monotonic clock")
        return float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError(error_message) from error


class MonotonicBudget:
    """Measure one foreground session and reject rollback or invalid clocks."""

    def __init__(
        self, monotonic: Callable[[], float], *,
        invalid_message: str, rollback_message: str,
    ) -> None:
        self.monotonic = monotonic
        self.invalid_message = invalid_message
        self.rollback_message = rollback_message
        self._started: float | None = None
        self._previous: float | None = None

    def start(self) -> float:
        value = monotonic_value(
            self.monotonic, error_message=self.invalid_message,
        )
        self._started = self._previous = value
        return value

    def elapsed(self) -> float:
        if self._started is None or self._previous is None:
            raise RuntimeError("MonotonicBudget.start() must be called first.")
        current = monotonic_value(
            self.monotonic, error_message=self.invalid_message,
        )
        if (
            current < self._previous
            or not math.isfinite(current - self._started)
        ):
            raise ValidationError(self.rollback_message)
        self._previous = current
        return current - self._started

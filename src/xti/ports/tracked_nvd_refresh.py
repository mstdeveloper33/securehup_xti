"""Persistence boundary for exposure-scoped official NVD refresh planning."""

from typing import Protocol

from xti.domain.tracked_nvd_refresh import TrackedNvdRefreshPlan


class TrackedNvdRefreshPlanRepository(Protocol):
    def plan(
        self, *, stale_after_hours: int, include_closed: bool,
        include_suppressed: bool, limit: int, checked_at: str,
    ) -> TrackedNvdRefreshPlan:
        ...

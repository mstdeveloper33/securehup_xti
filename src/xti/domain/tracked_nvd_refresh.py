"""Exposure-scoped planning and execution results for official NVD refreshes."""

from dataclasses import dataclass

from xti.domain.vulnerability import VulnerabilitySourceRun


TRACKED_NVD_FRESHNESS = {"stale", "clock_error"}


@dataclass(frozen=True, slots=True)
class TrackedNvdRefreshCandidate:
    cve_id: str
    exposure_count: int
    open_exposure_count: int
    closed_exposure_count: int
    last_success_at: str
    age_seconds: int
    freshness: str


@dataclass(frozen=True, slots=True)
class TrackedNvdRefreshPlan:
    stale_after_hours: int
    include_closed: bool
    include_suppressed: bool
    examined_exposure_count: int
    tracked_cve_count: int
    current_cve_count: int
    refresh_due_count: int
    clock_error_count: int
    attention_count: int
    items: tuple[TrackedNvdRefreshCandidate, ...]
    truncated: bool
    checked_at: str
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrackedNvdRefreshResult:
    status: str
    stale_after_hours: int
    include_closed: bool
    include_suppressed: bool
    limit: int
    minimum_interval_seconds: str
    plan_attention_count: int
    plan_refresh_due_count: int
    planned_candidates: tuple[TrackedNvdRefreshCandidate, ...]
    runs: tuple[VulnerabilitySourceRun, ...]
    notes: tuple[str, ...]

"""Read-only interpretation of the latest passive surface discovery run."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SurfaceDiscoveryStatusReport:
    asset_id: str
    asset_value: str
    observed_at: str
    freshness_hours: int
    provider: str | None
    source_status: str
    result_status: str
    outcome: str
    coverage_complete: bool
    empty_result_confirmed: bool
    freshness: str
    age_seconds: int | None
    run_id: str | None
    run_status: str | None
    started_at: str | None
    finished_at: str | None
    record_count: int | None
    candidate_count: int | None
    skipped_names: int | None
    ignored_names: int | None
    warnings: tuple[str, ...]
    error: str | None
    next_step: str
    reasons: tuple[str, ...]
    notes: tuple[str, ...]

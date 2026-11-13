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


@dataclass(frozen=True, slots=True)
class SurfaceDiscoveryHealthReport:
    asset_id: str
    asset_value: str
    observed_at: str
    freshness_hours: int
    provider_count: int
    complete_count: int
    partial_count: int
    failed_count: int
    never_run_count: int
    current_record_count: int
    stale_record_count: int
    clock_error_count: int
    attention_count: int
    sources: tuple[SurfaceDiscoveryStatusReport, ...]
    notes: tuple[str, ...]

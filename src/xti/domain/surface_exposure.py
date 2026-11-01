"""Explainable candidates derived from stored, approved surface evidence."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SurfaceExposureCandidate:
    candidate_type: str
    category: str
    title: str
    summary: str
    evidence_level: str
    evidence_freshness: str
    evidence_id: str
    recorded_at: str
    facts: tuple[str, ...]
    limitations: tuple[str, ...]
    next_step: str


@dataclass(frozen=True, slots=True)
class SurfaceExposureCoverage:
    check_type: str
    status: str
    evidence_id: str | None
    recorded_at: str | None
    reason: str
    next_command: str | None = None


@dataclass(frozen=True, slots=True)
class SurfaceExposureReport:
    asset_id: str
    asset_value: str
    observed_at: str
    stale_after_hours: int
    scope_status: str
    candidate_count: int
    stale_candidate_count: int
    clock_error_candidate_count: int
    categories: tuple[str, ...]
    candidates: tuple[SurfaceExposureCandidate, ...]
    coverage: tuple[SurfaceExposureCoverage, ...]
    notes: tuple[str, ...]
    current_coverage_count: int = 0
    attention_coverage_count: int = 0
    unsupported_coverage_count: int = 0
    scope_next_command: str | None = None

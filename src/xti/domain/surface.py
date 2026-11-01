"""Owned-scope attack-surface baselines and append-only check evidence."""

from dataclasses import dataclass

from xti.domain.enrichment import ProbeResult


@dataclass(frozen=True, slots=True)
class SurfaceScope:
    asset_id: str
    asset_value: str
    active: bool
    reason: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class SurfaceScopeEvent:
    id: str
    asset_id: str
    action: str
    reason: str
    created_at: str


@dataclass(frozen=True, slots=True)
class SurfaceChange:
    kind: str
    added_addresses: tuple[str, ...]
    removed_addresses: tuple[str, ...]
    changed_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SurfaceCheck:
    id: str
    asset_id: str
    asset_value: str
    result: ProbeResult
    state_sha256: str
    change: SurfaceChange
    recorded_at: str


@dataclass(frozen=True, slots=True)
class SurfaceSummary:
    scope: SurfaceScope
    latest_check: SurfaceCheck | None
    check_count: int


@dataclass(frozen=True, slots=True)
class SurfaceDetails:
    scope: SurfaceScope
    events: tuple[SurfaceScopeEvent, ...]
    checks: tuple[SurfaceCheck, ...]
    total_check_count: int


@dataclass(frozen=True, slots=True)
class SurfaceCandidateEvidence:
    domain: str
    provider: str
    source_name: str
    source_sha256: str
    raw_domain: str
    observed_at: str | None


@dataclass(frozen=True, slots=True)
class SurfaceCandidate:
    id: str
    asset_id: str
    asset_value: str
    domain: str
    status: str
    reason: str
    first_seen_at: str
    last_seen_at: str
    created_at: str
    updated_at: str
    source_count: int


@dataclass(frozen=True, slots=True)
class SurfaceCandidateSource:
    id: str
    candidate_id: str
    provider: str
    source_name: str
    source_sha256: str
    raw_domain: str
    observed_at: str | None
    recorded_at: str


@dataclass(frozen=True, slots=True)
class SurfaceCandidateEvent:
    id: str
    candidate_id: str
    action: str
    status: str
    reason: str
    created_at: str


@dataclass(frozen=True, slots=True)
class SurfaceCandidateDetails:
    candidate: SurfaceCandidate
    sources: tuple[SurfaceCandidateSource, ...]
    events: tuple[SurfaceCandidateEvent, ...]
    total_source_count: int


@dataclass(frozen=True, slots=True)
class SurfaceCandidateSaveSummary:
    candidates_created: int
    candidates_existing: int
    evidence_created: int
    evidence_existing: int


@dataclass(frozen=True, slots=True)
class SurfaceDiscoveryResult:
    asset_value: str
    started_at: str
    finished_at: str
    status: str
    source_url: str
    record_count: int
    skipped_names: int
    ignored_names: int
    warnings: tuple[str, ...]
    candidates_created: int
    candidates_existing: int
    evidence_created: int
    evidence_existing: int
    candidate_domains: tuple[str, ...]
    error: str | None
    run_id: str | None = None
    provider: str = "crt.sh"


@dataclass(frozen=True, slots=True)
class SurfaceDiscoveryRunRequest:
    status: str
    source_url: str
    started_at: str
    finished_at: str
    record_count: int
    skipped_names: int
    ignored_names: int
    warnings: tuple[str, ...]
    candidate_count: int
    error: str | None
    provider: str = "crt.sh"


@dataclass(frozen=True, slots=True)
class SurfaceDiscoveryRun:
    sequence: int
    id: str
    asset_id: str
    asset_value: str
    provider: str
    status: str
    source_url: str
    started_at: str
    finished_at: str
    record_count: int
    skipped_names: int
    ignored_names: int
    warnings: tuple[str, ...]
    candidate_count: int
    candidates_created: int
    candidates_existing: int
    evidence_created: int
    evidence_existing: int
    error: str | None


@dataclass(frozen=True, slots=True)
class SurfaceWatchCycle:
    cycle: int
    run_id: str | None
    status: str
    started_at: str
    finished_at: str
    candidate_count: int
    candidates_created: int
    evidence_created: int
    error: str | None


@dataclass(frozen=True, slots=True)
class SurfaceWatchReport:
    asset_value: str
    planned_cycles: int
    completed_cycles: int
    complete: int
    partial: int
    failed: int
    candidates_created: int
    evidence_created: int
    started_at: str
    finished_at: str
    elapsed_seconds: float
    stop_reason: str
    cycles: tuple[SurfaceWatchCycle, ...]
    notes: tuple[str, ...]
    provider: str = "crt.sh"


@dataclass(frozen=True, slots=True)
class SurfaceMonitorOutcome:
    check_type: str
    status: str
    evidence_id: str
    change_kind: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class SurfaceMonitorStep:
    cycle: int
    check_type: str
    status: str
    evidence_id: str
    change_kind: str
    notification_created: bool
    recorded_at: str


@dataclass(frozen=True, slots=True)
class SurfaceMonitorReport:
    asset_value: str
    checks: tuple[str, ...]
    planned_cycles: int
    completed_cycles: int
    completed_checks: int
    complete_checks: int
    partial_checks: int
    failed_checks: int
    notifications_created: int
    started_at: str
    finished_at: str
    elapsed_seconds: float
    stop_reason: str
    steps: tuple[SurfaceMonitorStep, ...]
    notes: tuple[str, ...]



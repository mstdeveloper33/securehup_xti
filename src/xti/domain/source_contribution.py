"""Explicit provider membership, retained attempt outcomes and local set comparisons."""
from dataclasses import dataclass
FAMILIES = frozenset({'all', 'surface', 'brand'})
PROVIDERS = {'surface': ('crt.sh', 'theharvester'), 'brand': ('crt.sh', 'urlscan')}


@dataclass(frozen=True, slots=True)
class SurfaceContributionEvidence:
    provider: str
    domain: str
    candidate_id: str
    review_status: str
    evidence_id: str
    source_name: str
    recorded_at: str
    observed_at: str | None


@dataclass(frozen=True, slots=True)
class ContributionAttempt:
    id: str
    family: str
    provider: str
    status: str
    started_at: str
    finished_at: str | None
    targets: tuple[str, ...]
    rule_version: str | None =  None
    typos: bool | None =  None
    job_id: str | None =  None
    result_available: bool =  False
    candidate_domains: tuple[str, ...] =  ()
    warnings: tuple[str, ...] =  ()
    reported_candidate_count: int | None =  None


@dataclass(frozen=True, slots=True)
class ContributionQueuedJob:
    id: str
    provider: str
    targets: tuple[str, ...]
    rule_version: str
    typos: bool


@dataclass(frozen=True, slots=True)
class SourceContributionSnapshot:
    asset_id: str
    asset_value: str
    surface_evidence: tuple[SurfaceContributionEvidence, ...]
    attempts: tuple[ContributionAttempt, ...]
    queued_jobs: tuple[ContributionQueuedJob, ...]
    schema_version: int


@dataclass(frozen=True, slots=True)
class ContributionDomain:
    domain: str
    providers: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    record_ids: tuple[str, ...]
    source_names: tuple[str, ...]
    review_statuses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContributionDomainPage:
    items: tuple[ContributionDomain, ...]
    offset: int
    limit: int
    total_count: int
    shown_count: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class ContributionOutcomeCounts:
    complete: int
    partial: int
    failed: int
    interrupted: int
    running: int
    completion_numerator: int
    completion_denominator: int
    completion_rate: float | None


@dataclass(frozen=True, slots=True)
class ProviderContribution:
    provider: str
    all_domains: ContributionDomainPage
    shared_domains: ContributionDomainPage
    exclusive_domains: ContributionDomainPage
    outcomes: ContributionOutcomeCounts
    excluded_multi_target_outcomes: ContributionOutcomeCounts
    excluded_multi_target_attempt_count: int
    resultless_attempt_count: int
    complete_empty_attempt_count: int
    queued_job_count: int
    excluded_multi_target_queued_job_count: int
    first_evidence_recorded_at: str | None
    last_evidence_recorded_at: str | None
    first_attempt_at: str | None
    last_attempt_at: str | None
    current_review_counts: tuple[tuple[str, int], ...]
    attempt_ids: tuple[str, ...]
    excluded_multi_target_attempt_ids: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContributionPairOverlap:
    first_provider: str
    second_provider: str
    domains: ContributionDomainPage


@dataclass(frozen=True, slots=True)
class ContributionGroup:
    family: str
    rule_version: str | None
    typos: bool | None
    sources: tuple[ProviderContribution, ...]
    union_domains: ContributionDomainPage
    overlaps: tuple[ContributionPairOverlap, ...]
    comparison_state: str
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceContributionReport:
    asset_id: str
    asset_value: str
    family: str
    groups: tuple[ContributionGroup, ...]
    schema_version: int
    notes: tuple[str, ...]
    provider_evaluation: str


def outcome_counts(attempts: tuple[ContributionAttempt, ...]) -> ContributionOutcomeCounts:
    counts = {status: sum((attempt.status == status for attempt in attempts)) for status in (
        'complete',
        'partial',
        'failed',
        'interrupted',
        'running',
    )}
    denominator = sum((counts[status] for status in ('complete', 'partial', 'failed', 'interrupted')))
    return ContributionOutcomeCounts(
        counts['complete'],
        counts['partial'],
        counts['failed'],
        counts['interrupted'],
        counts['running'],
        counts['complete'],
        denominator,
        counts['complete'] / denominator if denominator else None,
    )

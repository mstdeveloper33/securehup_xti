"""Source-qualified, derived event candidates; never persisted incident verdicts."""

from dataclasses import dataclass

from xti.domain.public_notices import PublicNotice, PublicNoticeRun
from xti.domain.ransomlook_ransomware import RansomLookClaim, RansomLookClaimRun
from xti.domain.ransomware_claims import RansomwareClaim, RansomwareClaimRun
from xti.domain.ransomware_source_comparison import RansomwareSourceReviewState


EVENT_CANDIDATE_RULE_VERSION = "event-candidates-v1"
EVENT_SOURCE_KEYS = ("threatcluster", "ransomlook", "hibp")
MAX_EVENT_RECORDS = 50_000
MAX_EVENT_PAIR_REFERENCES = 100_000
MAX_EVENT_CANDIDATES = 50_000

EventRecord = RansomwareClaim | RansomLookClaim | PublicNotice
EventRun = RansomwareClaimRun | RansomLookClaimRun | PublicNoticeRun


@dataclass(frozen=True, slots=True)
class EventSourceSnapshot:
    source_key: str
    latest_run: EventRun | None
    successful_run: EventRun | None
    records: tuple[EventRecord, ...]


@dataclass(frozen=True, slots=True)
class EventLegacyReview:
    state: RansomwareSourceReviewState
    threatcluster_state_sha256: str
    ransomlook_state_sha256: str


@dataclass(frozen=True, slots=True)
class EventCandidateSnapshot:
    sources: tuple[EventSourceSnapshot, ...]
    legacy_reviews: tuple[EventLegacyReview, ...] = ()


@dataclass(frozen=True, slots=True)
class EventDate:
    field: str
    meaning: str
    value: str


@dataclass(frozen=True, slots=True)
class EventEvidence:
    source_key: str
    record_type: str
    record_id: str
    source_run_id: str
    state_sha256: str
    title: str
    domain: str | None
    group: str | None
    dates: tuple[EventDate, ...]
    source_url: str
    record: EventRecord


@dataclass(frozen=True, slots=True)
class EventReviewContext:
    comparison_id: str
    decision: str
    reason: str
    reviewed_at: str
    evidence_matches: bool


@dataclass(frozen=True, slots=True)
class EventCandidate:
    id: str
    evidence_sha256: str
    kind: str
    basis: str
    reasons: tuple[str, ...]
    cautions: tuple[str, ...]
    left: EventEvidence
    right: EventEvidence
    discovery_gap_hours: float | None = None
    legacy_comparison_id: str | None = None
    legacy_review: EventReviewContext | None = None


@dataclass(frozen=True, slots=True)
class EventSourceCoverage:
    source_key: str
    source_name: str
    source_url: str
    license: str
    latest_run_id: str | None
    latest_run_status: str | None
    latest_run_at: str | None
    latest_success_run_id: str | None
    latest_success_at: str | None
    status: str
    freshness: str
    record_count: int
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EventCandidateReport:
    rule_version: str
    checked_at: str
    domain_filter: str | None
    stale_after_hours: int
    total_candidate_count: int
    possible_same_event_count: int
    organization_context_count: int
    offset: int
    limit: int
    has_more: bool
    candidates: tuple[EventCandidate, ...]
    coverage: tuple[EventSourceCoverage, ...]
    notes: tuple[str, ...]

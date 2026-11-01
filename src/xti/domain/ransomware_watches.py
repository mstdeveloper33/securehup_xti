"""Conservative organization/domain watches over public ransomware claims."""

from dataclasses import dataclass
import hashlib
import json
from urllib.parse import urlsplit
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.ransomware_claims import (
    RansomwareClaim,
    RansomwareClaimRunReport,
    ransomware_claim_state_sha256,
)


RANSOMWARE_WATCH_KINDS = frozenset({"organization", "domain"})
RANSOMWARE_WATCH_MATCH_MODES = frozenset({"exact", "contains"})
RANSOMWARE_WATCH_ACTIONS = frozenset({"added", "updated", "reactivated", "revoked"})
RANSOMWARE_WATCH_ITEM_ACTIONS = frozenset({"added", "updated", "unchanged", "removed"})
RANSOMWARE_MONITOR_SESSION_STATUSES = frozenset({
    "running", "complete", "partial", "interrupted", "failed",
})
RANSOMWARE_MONITOR_STOP_REASONS = frozenset({
    "", "cycles", "duration", "interrupted", "error",
})
RANSOMWARE_TIMELINE_ACTIONS = frozenset({
    "first_seen", "updated", "match_started", "match_ended",
    "removed", "reappeared",
})
RANSOMWARE_IDENTITY_REVIEW_DECISIONS = frozenset({
    "possible_same", "different", "uncertain",
})


def _visible_text(value: str, *, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} gerekli.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if (
        not minimum <= len(normalized) <= maximum
        or any(not character.isprintable() for character in normalized)
    ):
        raise ValidationError(
            f"{field} {minimum}–{maximum} görünür karakter arasında olmalı."
        )
    return normalized


def normalize_ransomware_watch_name(value: str) -> str:
    return _visible_text(value, field="İzleme adı", minimum=2, maximum=100)


def ransomware_watch_name_key(value: str) -> str:
    return normalize_ransomware_watch_name(value).casefold()


def normalize_ransomware_watch_query(value: str, *, kind: str, match_mode: str) -> str:
    if kind not in RANSOMWARE_WATCH_KINDS:
        raise ValidationError("İzleme türü organization veya domain olmalı.")
    if match_mode not in RANSOMWARE_WATCH_MATCH_MODES:
        raise ValidationError("Eşleşme biçimi exact veya contains olmalı.")
    if kind == "domain":
        if match_mode != "exact":
            raise ValidationError("Domain izlemede yalnız exact eşleşme kullanılabilir.")
        return normalize_domain(value)
    query = _visible_text(value, field="Kuruluş ifadesi", minimum=2, maximum=200)
    if match_mode == "contains" and len(query) < 5:
        raise ValidationError("Contains kuruluş izlemesi için en az 5 karakter gerekli.")
    return query


def ransomware_watch_query_key(value: str, *, kind: str) -> str:
    return value if kind == "domain" else value.casefold()


def ransomware_watch_definition_sha256(
    *, query: str, query_key: str, kind: str, match_mode: str,
) -> str:
    canonical = json.dumps(
        {
            "kind": kind,
            "match_mode": match_mode,
            "query": query,
            "query_key": query_key,
        },
        ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ransomware_claim_website_host(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate if "://" in candidate else "//" + candidate)
        host = parsed.hostname
        return normalize_domain(host) if host else None
    except (TypeError, ValueError, ValidationError):
        return None


@dataclass(frozen=True, slots=True)
class RansomwareWatchMatch:
    claim: RansomwareClaim
    matched_field: str
    matched_value: str
    match_type: str


def match_ransomware_claim(
    claim: RansomwareClaim, *, kind: str, query_key: str, match_mode: str,
) -> RansomwareWatchMatch | None:
    """Match only the victim label or normalized first-party website host."""
    if kind == "organization":
        victim_key = unicodedata.normalize("NFKC", claim.victim).casefold()
        matched = victim_key == query_key if match_mode == "exact" else query_key in victim_key
        if matched:
            return RansomwareWatchMatch(
                claim, "victim", claim.victim,
                "exact" if victim_key == query_key else "contains",
            )
        return None
    host = ransomware_claim_website_host(claim.website)
    if host is not None and (host == query_key or host.endswith("." + query_key)):
        return RansomwareWatchMatch(
            claim, "website", host, "exact" if host == query_key else "subdomain",
        )
    return None


def ransomware_watch_match_state_sha256(match: RansomwareWatchMatch) -> str:
    canonical = json.dumps(
        {
            "claim_state": ransomware_claim_state_sha256(match.claim),
            "match_type": match.match_type,
            "matched_field": match.matched_field,
            "matched_value": match.matched_value,
        },
        ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RansomwareWatch:
    id: str
    name_key: str
    display_name: str
    kind: str
    query: str
    query_key: str
    match_mode: str
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class RansomwareWatchEvent:
    id: str
    watch_id: str
    action: str
    definition_sha256: str
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class RansomwareWatchMutation:
    action: str
    watch: RansomwareWatch


@dataclass(frozen=True, slots=True)
class RansomwareWatchRun:
    sequence: int
    id: str
    watch_id: str
    source_run_id: str
    definition_sha256: str
    previous_run_id: str | None
    executed_at: str
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    result_sha256: str


@dataclass(frozen=True, slots=True)
class RansomwareWatchRunItem:
    id: str
    run_id: str
    match: RansomwareWatchMatch
    action: str
    state_sha256: str


@dataclass(frozen=True, slots=True)
class RansomwareWatchSummary:
    watch: RansomwareWatch
    run_count: int
    last_run: RansomwareWatchRun | None


@dataclass(frozen=True, slots=True)
class RansomwareWatchDetails:
    watch: RansomwareWatch
    events: tuple[RansomwareWatchEvent, ...]
    runs: tuple[RansomwareWatchRun, ...]
    total_event_count: int
    total_run_count: int


@dataclass(frozen=True, slots=True)
class RansomwareWatchRunReport:
    watch: RansomwareWatch
    run: RansomwareWatchRun
    items: tuple[RansomwareWatchRunItem, ...]
    total_item_count: int
    notification_id: str | None
    is_baseline: bool


@dataclass(frozen=True, slots=True)
class RansomwareWatchRefreshItem:
    position: int
    watch_id: str
    display_name: str
    run_id: str
    source_run_id: str
    executed_at: str
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    notification_id: str | None
    is_baseline: bool


@dataclass(frozen=True, slots=True)
class RansomwareWatchRefreshReport:
    refresh: RansomwareClaimRunReport
    planned_watch_count: int
    completed_watch_count: int
    baseline_watch_count: int
    started_at: str
    finished_at: str
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    notification_count: int
    items: tuple[RansomwareWatchRefreshItem, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RansomwareWatchMonitorCycle:
    cycle: int
    source_run_id: str
    source_status: str
    source_finished_at: str
    source_record_count: int
    planned_watch_count: int
    completed_watch_count: int
    baseline_watch_count: int
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    notification_count: int
    source_error: str | None
    watch_run_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RansomwareWatchMonitorReport:
    planned_cycles: int
    completed_cycles: int
    successful_cycles: int
    failed_cycles: int
    completed_watch_runs: int
    baseline_watch_runs: int
    started_at: str
    finished_at: str
    elapsed_seconds: float
    stop_reason: str
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    notification_count: int
    cycles: tuple[RansomwareWatchMonitorCycle, ...]
    notes: tuple[str, ...]
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class RansomwareMonitorSession:
    sequence: int
    id: str
    status: str
    started_at: str
    finished_at: str | None
    stop_reason: str
    planned_cycles: int
    interval_seconds: int
    max_duration_seconds: int
    max_watches: int
    source_item_limit: int
    watch_item_limit: int
    error: str
    completed_cycles: int
    successful_cycles: int
    failed_cycles: int
    completed_watch_runs: int
    baseline_watch_runs: int
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    notification_count: int


@dataclass(frozen=True, slots=True)
class RansomwareMonitorSessionDetails:
    session: RansomwareMonitorSession
    cycles: tuple[RansomwareWatchMonitorCycle, ...]
    total_cycle_count: int


@dataclass(frozen=True, slots=True)
class RansomwareWatchTimelineEvent:
    source_sequence: int
    source_run_id: str
    observed_at: str
    action: str
    claim: RansomwareClaim
    matched_field: str
    matched_value: str
    match_type: str


@dataclass(frozen=True, slots=True)
class RansomwareWatchTimelineReport:
    watch: RansomwareWatch
    complete_source_run_count: int
    failed_source_run_count: int
    first_complete_at: str | None
    last_complete_at: str | None
    distinct_claim_count: int
    active_claim_count: int
    repeat_observation_count: int
    reappearance_count: int
    total_event_count: int
    events: tuple[RansomwareWatchTimelineEvent, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RansomwareIdentityReviewState:
    candidate_id: str
    decision: str
    reason: str
    reviewed_at: str
    event_count: int


@dataclass(frozen=True, slots=True)
class RansomwareWatchIdentityCandidate:
    id: str
    older_claim: RansomwareClaim
    newer_claim: RansomwareClaim
    transition_source_sequence: int
    transition_source_run_id: str
    transition_observed_at: str
    successful_snapshot_gap: int
    older_matches_watch: bool
    newer_matches_watch: bool
    common_evidence: tuple[str, ...]
    changed_identity_fields: tuple[str, ...]
    current_review: RansomwareIdentityReviewState | None = None


@dataclass(frozen=True, slots=True)
class RansomwareWatchIdentityCandidateReport:
    watch: RansomwareWatch
    complete_source_run_count: int
    failed_source_run_count: int
    transition_pair_count: int
    total_candidate_count: int
    candidates: tuple[RansomwareWatchIdentityCandidate, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RansomwareIdentityReviewEvent:
    sequence: int
    id: str
    candidate_id: str
    decision: str
    reason: str
    recorded_at: str
    previous_event_id: str | None
    candidate_sha256: str


@dataclass(frozen=True, slots=True)
class RansomwareIdentityReviewDetails:
    candidate: RansomwareWatchIdentityCandidate
    current: RansomwareIdentityReviewState
    events: tuple[RansomwareIdentityReviewEvent, ...]
    total_event_count: int


@dataclass(frozen=True, slots=True)
class RansomwareIdentityReviewMutation:
    action: str
    details: RansomwareIdentityReviewDetails


def normalize_ransomware_identity_review_decision(value: str) -> str:
    if not isinstance(value, str) or value not in RANSOMWARE_IDENTITY_REVIEW_DECISIONS:
        raise ValidationError(
            "Kimlik adayı kararı possible_same, different veya uncertain olmalı."
        )
    return value


def normalize_ransomware_identity_review_reason(value: str) -> str:
    return _visible_text(value, field="Kimlik adayı karar gerekçesi", minimum=2, maximum=500)


def ransomware_identity_candidate_id(
    *, watch_id: str, older_claim_id: str, newer_claim_id: str,
    transition_source_run_id: str,
) -> str:
    canonical = json.dumps(
        [watch_id, older_claim_id, newer_claim_id, transition_source_run_id],
        ensure_ascii=True, separators=(",", ":"),
    )
    return str(uuid5(NAMESPACE_URL, "xti:ransomware-identity-candidate:" + canonical))


def ransomware_identity_candidate_json(
    candidate: RansomwareWatchIdentityCandidate,
) -> str:
    def claim(value: RansomwareClaim) -> dict[str, object]:
        return {
            "country": value.country,
            "delisted_at": value.delisted_at,
            "discovered_at": value.discovered_at,
            "first_party": value.first_party,
            "group": value.group,
            "id": value.id,
            "last_seen_at": value.last_seen_at,
            "sector": value.sector,
            "source_post_available": value.source_post_available,
            "status": value.status,
            "victim": value.victim,
            "website": value.website,
        }

    payload = {
        "changed_identity_fields": candidate.changed_identity_fields,
        "common_evidence": candidate.common_evidence,
        "id": candidate.id,
        "newer_claim": claim(candidate.newer_claim),
        "newer_matches_watch": candidate.newer_matches_watch,
        "older_claim": claim(candidate.older_claim),
        "older_matches_watch": candidate.older_matches_watch,
        "successful_snapshot_gap": candidate.successful_snapshot_gap,
        "transition_observed_at": candidate.transition_observed_at,
        "transition_source_run_id": candidate.transition_source_run_id,
        "transition_source_sequence": candidate.transition_source_sequence,
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def ransomware_identity_candidate_sha256(
    candidate: RansomwareWatchIdentityCandidate,
) -> str:
    return hashlib.sha256(
        ransomware_identity_candidate_json(candidate).encode("ascii")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class RansomwareWatchChangeEvidence:
    watch_id: str
    display_name: str
    kind: str
    query: str
    run_id: str
    source_run_id: str
    executed_at: str
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int

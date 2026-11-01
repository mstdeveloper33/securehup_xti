"""Source-isolated organization watches over stored RansomLook claims."""

from dataclasses import dataclass
import hashlib
import json
import unicodedata

from xti.domain.ransomlook_ransomware import (
    RansomLookClaim,
    ransomlook_claim_state_sha256,
)
from xti.domain.ransomware_watches import (
    normalize_ransomware_watch_name,
    normalize_ransomware_watch_query,
    ransomware_watch_name_key,
    ransomware_watch_query_key,
)


RANSOMLOOK_WATCH_ACTIONS = frozenset({"added", "updated", "reactivated", "revoked"})
RANSOMLOOK_WATCH_ITEM_ACTIONS = frozenset({"added", "updated", "unchanged", "removed"})
RANSOMLOOK_WATCH_MATCH_MODES = frozenset({"exact", "contains"})


def normalize_ransomlook_watch_name(value: str) -> str:
    return normalize_ransomware_watch_name(value)


def ransomlook_watch_name_key(value: str) -> str:
    return ransomware_watch_name_key(value)


def normalize_ransomlook_watch_query(value: str, *, match_mode: str) -> str:
    return normalize_ransomware_watch_query(
        value, kind="organization", match_mode=match_mode,
    )


def ransomlook_watch_query_key(value: str) -> str:
    return ransomware_watch_query_key(value, kind="organization")


def ransomlook_watch_definition_sha256(
    *, query: str, query_key: str, match_mode: str,
) -> str:
    canonical = json.dumps(
        {"match_mode": match_mode, "query": query, "query_key": query_key},
        ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class RansomLookWatchMatch:
    claim: RansomLookClaim
    matched_value: str
    match_type: str


def match_ransomlook_claim(
    claim: RansomLookClaim, *, query_key: str, match_mode: str,
) -> RansomLookWatchMatch | None:
    """Match only the source-provided post/victim title."""
    victim_key = unicodedata.normalize("NFKC", claim.victim).casefold()
    matched = victim_key == query_key if match_mode == "exact" else query_key in victim_key
    if not matched:
        return None
    return RansomLookWatchMatch(
        claim=claim, matched_value=claim.victim,
        match_type="exact" if victim_key == query_key else "contains",
    )


def ransomlook_watch_match_state_sha256(match: RansomLookWatchMatch) -> str:
    canonical = json.dumps(
        {
            "claim_state": ransomlook_claim_state_sha256(match.claim),
            "match_type": match.match_type,
            "matched_field": "victim",
            "matched_value": match.matched_value,
        },
        ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class RansomLookWatch:
    id: str
    name_key: str
    display_name: str
    query: str
    query_key: str
    match_mode: str
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class RansomLookWatchEvent:
    id: str
    watch_id: str
    action: str
    definition_sha256: str
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class RansomLookWatchMutation:
    action: str
    watch: RansomLookWatch


@dataclass(frozen=True, slots=True)
class RansomLookWatchRun:
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
class RansomLookWatchRunItem:
    id: str
    run_id: str
    match: RansomLookWatchMatch
    action: str
    state_sha256: str


@dataclass(frozen=True, slots=True)
class RansomLookWatchSummary:
    watch: RansomLookWatch
    run_count: int
    last_run: RansomLookWatchRun | None


@dataclass(frozen=True, slots=True)
class RansomLookWatchDetails:
    watch: RansomLookWatch
    events: tuple[RansomLookWatchEvent, ...]
    runs: tuple[RansomLookWatchRun, ...]
    total_event_count: int
    total_run_count: int


@dataclass(frozen=True, slots=True)
class RansomLookWatchRunReport:
    watch: RansomLookWatch
    run: RansomLookWatchRun
    items: tuple[RansomLookWatchRunItem, ...]
    total_item_count: int
    attention_count: int
    is_baseline: bool


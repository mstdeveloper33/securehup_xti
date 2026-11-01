"""Minimal RansomLook post claims without leak-site content or verdicts."""

from dataclasses import dataclass
import hashlib
import json


RANSOMLOOK_SOURCE_NAME = "RansomLook public ransomware posts"
RANSOMLOOK_SOURCE_URL = "https://www.ransomlook.io/api/posts?days=7"
RANSOMLOOK_SOURCE_LICENSE = (
    "CC BY 4.0 — attribution: RansomLook (https://www.ransomlook.io)"
)
RANSOMLOOK_RUN_STATUSES = frozenset({"complete", "failed"})
RANSOMLOOK_ITEM_ACTIONS = frozenset({"added", "updated", "unchanged", "removed"})


@dataclass(frozen=True, slots=True)
class RansomLookClaim:
    id: str
    group: str
    victim: str
    discovered_at: str


def ransomlook_claim_state_sha256(claim: RansomLookClaim) -> str:
    canonical = json.dumps(
        {
            "discovered_at": claim.discovered_at,
            "group": claim.group,
            "id": claim.id,
            "victim": claim.victim,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class RansomLookClaimFeed:
    source_name: str
    source_url: str
    fetched_at: str
    window_days: int
    source_record_count: int
    content_sha256: str
    license: str
    source_note: str
    claims: tuple[RansomLookClaim, ...]


@dataclass(frozen=True, slots=True)
class RansomLookClaimReport:
    source_name: str
    source_url: str
    fetched_at: str
    window_days: int
    source_record_count: int
    content_sha256: str
    license: str
    query: str | None
    matched_count: int
    displayed_count: int
    has_more: bool
    claims: tuple[RansomLookClaim, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RansomLookClaimRunItem:
    id: str
    run_id: str
    claim: RansomLookClaim
    action: str
    state_sha256: str


@dataclass(frozen=True, slots=True)
class RansomLookClaimRun:
    sequence: int
    id: str
    source_name: str
    status: str
    source_url: str
    content_sha256: str | None
    started_at: str
    finished_at: str
    fetched_at: str | None
    window_days: int | None
    source_record_count: int
    claim_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    error: str | None


@dataclass(frozen=True, slots=True)
class RansomLookClaimRunReport:
    run: RansomLookClaimRun
    items: tuple[RansomLookClaimRunItem, ...]
    total_item_count: int
    is_baseline: bool


@dataclass(frozen=True, slots=True)
class RansomLookClaimHistoryStatus:
    latest_run: RansomLookClaimRun | None
    latest_complete_run: RansomLookClaimRun | None
    recent_runs: tuple[RansomLookClaimRun, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RansomLookClaimSnapshot:
    run: RansomLookClaimRun
    claims: tuple[RansomLookClaim, ...]


@dataclass(frozen=True, slots=True)
class RansomLookClaimHistoryEvidence:
    runs: tuple[RansomLookClaimRun, ...]
    items: tuple[RansomLookClaimRunItem, ...]

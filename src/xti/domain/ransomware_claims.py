"""Source-labelled ransomware leak-site claims without breach conclusions."""

from dataclasses import dataclass
import hashlib
import json


RANSOMWARE_SOURCE_NAME = "ThreatCluster public ransomware claims"
RANSOMWARE_SOURCE_URL = "https://threatcluster.io/api/darkweb/public/victims.json"
RANSOMWARE_SOURCE_LICENSE = (
    "CC-BY 4.0 — attribution: ThreatCluster (https://threatcluster.io)"
)
RANSOMWARE_RUN_STATUSES = frozenset({"complete", "failed"})
RANSOMWARE_ITEM_ACTIONS = frozenset({"added", "updated", "unchanged", "removed"})


@dataclass(frozen=True, slots=True)
class RansomwareClaim:
    id: str
    group: str
    victim: str
    country: str | None
    sector: str | None
    discovered_at: str
    status: str
    website: str | None
    last_seen_at: str | None
    delisted_at: str | None
    first_party: bool | None
    source_post_available: bool


def ransomware_claim_state_sha256(claim: RansomwareClaim) -> str:
    """Hash the safe normalized claim fields; leak-site URLs are never present."""
    canonical = json.dumps(
        {
            "country": claim.country,
            "delisted_at": claim.delisted_at,
            "discovered_at": claim.discovered_at,
            "first_party": claim.first_party,
            "group": claim.group,
            "id": claim.id,
            "last_seen_at": claim.last_seen_at,
            "sector": claim.sector,
            "source_post_available": claim.source_post_available,
            "status": claim.status,
            "victim": claim.victim,
            "website": claim.website,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class RansomwareClaimFeed:
    source_name: str
    source_url: str
    fetched_at: str
    generated_at: str
    window_days: int
    source_record_count: int
    content_sha256: str
    license: str
    source_note: str
    claims: tuple[RansomwareClaim, ...]


@dataclass(frozen=True, slots=True)
class RansomwareClaimReport:
    source_name: str
    source_url: str
    fetched_at: str
    generated_at: str
    window_days: int
    source_record_count: int
    content_sha256: str
    license: str
    query: str | None
    status_filter: str
    matched_count: int
    displayed_count: int
    has_more: bool
    claims: tuple[RansomwareClaim, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RansomwareClaimRunItem:
    id: str
    run_id: str
    claim: RansomwareClaim
    action: str
    state_sha256: str


@dataclass(frozen=True, slots=True)
class RansomwareClaimRun:
    sequence: int
    id: str
    source_name: str
    status: str
    source_url: str
    content_sha256: str | None
    started_at: str
    finished_at: str
    fetched_at: str | None
    generated_at: str | None
    window_days: int | None
    source_record_count: int
    claim_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    error: str | None


@dataclass(frozen=True, slots=True)
class RansomwareClaimRunReport:
    run: RansomwareClaimRun
    items: tuple[RansomwareClaimRunItem, ...]
    total_item_count: int
    is_baseline: bool


@dataclass(frozen=True, slots=True)
class RansomwareClaimHistoryStatus:
    latest_run: RansomwareClaimRun | None
    latest_complete_run: RansomwareClaimRun | None
    recent_runs: tuple[RansomwareClaimRun, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RansomwareClaimSnapshot:
    """Latest complete local source state used by offline watch evaluation."""

    run: RansomwareClaimRun
    claims: tuple[RansomwareClaim, ...]


@dataclass(frozen=True, slots=True)
class RansomwareClaimHistoryEvidence:
    """Complete audited local differences used by offline historical views."""

    runs: tuple[RansomwareClaimRun, ...]
    items: tuple[RansomwareClaimRunItem, ...]

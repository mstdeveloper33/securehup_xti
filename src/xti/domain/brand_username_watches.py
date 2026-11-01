"""Durable, conservative watches over bounded social username previews."""

from dataclasses import dataclass
import hashlib
import json
import unicodedata

from xti.domain.assets import ValidationError
from xti.domain.brand_username import BrandUsernamePreview
from xti.domain.brand_username_reviews import BrandUsernameReviewState


WATCH_ACTIONS = frozenset({"added", "updated", "reactivated", "revoked"})
RUN_STATUSES = frozenset({"complete", "failed"})
ITEM_STATUSES = frozenset({"found_unverified", "unreported"})
ITEM_ACTIONS = frozenset({
    "baseline_found",
    "baseline_unreported",
    "newly_found",
    "changed",
    "unchanged_found",
    "no_longer_reported",
    "unchanged_unreported",
})


def normalize_brand_watch_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("İzleme adı gerekli.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if (
        not 2 <= len(normalized) <= 100
        or any(not character.isprintable() for character in normalized)
    ):
        raise ValidationError("İzleme adı 2–100 görünür karakter arasında olmalı.")
    return normalized


def brand_watch_name_key(value: str) -> str:
    return normalize_brand_watch_name(value).casefold()


def brand_watch_definition_sha256(
    *, username: str, platforms: tuple[str, ...],
) -> str:
    canonical = json.dumps(
        {"platforms": list(platforms), "username": username},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def brand_watch_item_state_sha256(
    *, platform: str, status: str, profile_url: str | None,
) -> str:
    canonical = json.dumps(
        {"platform": platform, "profile_url": profile_url, "status": status},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class BrandUsernameWatch:
    id: str
    name_key: str
    display_name: str
    username: str
    platforms: tuple[str, ...]
    source_key: str
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class BrandUsernameWatchEvent:
    id: str
    watch_id: str
    action: str
    definition_sha256: str
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class BrandUsernameWatchMutation:
    action: str
    watch: BrandUsernameWatch


@dataclass(frozen=True, slots=True)
class BrandUsernameWatchRun:
    sequence: int
    id: str
    watch_id: str
    status: str
    source_name: str
    source_version: str
    integration_profile: str
    username: str
    platforms: tuple[str, ...]
    definition_sha256: str
    previous_complete_run_id: str | None
    checked_at: str | None
    recorded_at: str
    platform_count: int
    found_count: int
    newly_found_count: int
    changed_count: int
    unchanged_found_count: int
    no_longer_reported_count: int
    unreported_count: int
    result_sha256: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class BrandUsernameWatchRunItem:
    id: str
    run_id: str
    platform: str
    profile_url: str | None
    status: str
    action: str
    state_sha256: str
    current_review: BrandUsernameReviewState | None = None


@dataclass(frozen=True, slots=True)
class BrandUsernameWatchSummary:
    watch: BrandUsernameWatch
    run_count: int
    last_run: BrandUsernameWatchRun | None


@dataclass(frozen=True, slots=True)
class BrandUsernameWatchDetails:
    watch: BrandUsernameWatch
    events: tuple[BrandUsernameWatchEvent, ...]
    runs: tuple[BrandUsernameWatchRun, ...]
    total_event_count: int
    total_run_count: int


@dataclass(frozen=True, slots=True)
class BrandUsernameWatchRunReport:
    watch: BrandUsernameWatch
    run: BrandUsernameWatchRun
    items: tuple[BrandUsernameWatchRunItem, ...]
    total_item_count: int
    attention_count: int
    is_baseline: bool
    preview: BrandUsernamePreview | None = None


@dataclass(frozen=True, slots=True)
class BrandUsernameWatchBatchItem:
    position: int
    watch_id: str
    display_name: str
    source_key: str
    run_id: str
    status: str
    recorded_at: str
    platform_count: int
    found_count: int
    newly_found_count: int
    changed_count: int
    unchanged_found_count: int
    no_longer_reported_count: int
    unreported_count: int
    attention_count: int
    error: str | None


@dataclass(frozen=True, slots=True)
class BrandUsernameWatchBatchReport:
    planned_watch_count: int
    completed_watch_count: int
    successful_watch_count: int
    failed_watch_count: int
    started_at: str
    finished_at: str
    platform_count: int
    found_count: int
    newly_found_count: int
    changed_count: int
    no_longer_reported_count: int
    attention_count: int
    items: tuple[BrandUsernameWatchBatchItem, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BrandUsernameWatchMonitorCycle:
    cycle: int
    run_id: str
    status: str
    recorded_at: str
    platform_count: int
    found_count: int
    newly_found_count: int
    changed_count: int
    no_longer_reported_count: int
    attention_count: int
    error: str | None


@dataclass(frozen=True, slots=True)
class BrandUsernameWatchMonitorReport:
    watch: BrandUsernameWatch
    planned_cycles: int
    completed_cycles: int
    successful_cycles: int
    failed_cycles: int
    started_at: str
    finished_at: str
    elapsed_seconds: float
    stop_reason: str
    found_count: int
    newly_found_count: int
    changed_count: int
    no_longer_reported_count: int
    attention_count: int
    cycles: tuple[BrandUsernameWatchMonitorCycle, ...]
    notes: tuple[str, ...]

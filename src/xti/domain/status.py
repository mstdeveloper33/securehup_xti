"""Recorded monitoring coverage; freshness never implies current source availability."""

from dataclasses import dataclass

from xti.domain.assets import Asset
from xti.domain.operations import SourceCooldown


@dataclass(frozen=True, slots=True)
class StatusAttempt:
    id: str
    job_id: str
    number: int
    status: str
    started_at: str
    finished_at: str | None
    query_count: int
    failed_query_count: int
    partial_query_count: int
    error: str | None
    rule_version: str
    typos: bool


@dataclass(frozen=True, slots=True)
class SourceHistory:
    provider: str
    latest_attempt: StatusAttempt | None
    last_complete: StatusAttempt | None
    queued_count: int


@dataclass(frozen=True, slots=True)
class AssetHistory:
    asset: Asset
    sources: tuple[SourceHistory, ...]


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    asset_count: int
    observation_count: int
    finding_counts: dict[str, int]
    job_counts: dict[str, int]
    notification_count: int
    unread_notification_count: int
    assets: tuple[AssetHistory, ...]
    cooldowns: tuple[SourceCooldown, ...]


@dataclass(frozen=True, slots=True)
class SourceStatus:
    provider: str
    latest_attempt: StatusAttempt | None
    last_complete: StatusAttempt | None
    queued_count: int
    freshness: str
    age_seconds: int | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AssetStatus:
    asset: Asset
    sources: tuple[SourceStatus, ...]


@dataclass(frozen=True, slots=True)
class CooldownStatus:
    provider: str
    not_before: str
    recorded_at: str
    reason: str
    active: bool
    remaining_seconds: int
    clock_error: bool


@dataclass(frozen=True, slots=True)
class StatusReport:
    observed_at: str
    freshness_hours: int
    domain_filter: str | None
    asset_count: int
    displayed_asset_count: int
    has_more_assets: bool
    observation_count: int
    finding_counts: dict[str, int]
    job_counts: dict[str, int]
    notification_count: int
    unread_notification_count: int
    assets: tuple[AssetStatus, ...]
    cooldowns: tuple[CooldownStatus, ...]
    notes: tuple[str, ...]

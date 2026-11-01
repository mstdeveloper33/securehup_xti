"""Portable records for provider waits and conservative local maintenance."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceCooldown:
    provider: str
    not_before: str
    recorded_at: str
    reason: str


@dataclass(frozen=True, slots=True)
class StorageUsage:
    database_bytes: int
    wal_bytes: int
    journal_bytes: int
    logical_bytes: int
    reusable_bytes: int
    observation_count: int
    linked_observation_count: int


@dataclass(frozen=True, slots=True)
class CleanupPlan:
    policy_version: str
    cutoff: str
    older_than_days: int
    limit: int
    eligible_count: int
    selected_count: int
    remaining_count: int
    protected_count: int
    invalid_time_count: int
    token: str


@dataclass(frozen=True, slots=True)
class CleanupRun:
    id: str
    created_at: str
    cutoff: str
    deleted_count: int
    token: str
    backup: str


@dataclass(frozen=True, slots=True)
class CleanupResult:
    plan: CleanupPlan
    deleted_count: int
    backup: str | None
    run: CleanupRun | None

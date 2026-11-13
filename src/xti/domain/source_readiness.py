"""Stored evidence and local installation facts for source readiness."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceReadinessEvidence:
    identifier: str
    label: str
    scope: str
    installation: str
    latest_status: str
    last_attempt_at: str | None
    last_success_at: str | None
    error: str | None
    next_command: str
    notes: tuple[str, ...]
    record_count: int | None = None
    cooldown_until: str | None = None


@dataclass(frozen=True, slots=True)
class SourceReadinessSnapshot:
    storage_state: str
    sources: tuple[SourceReadinessEvidence, ...]

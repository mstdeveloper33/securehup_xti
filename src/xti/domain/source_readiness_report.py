"""Local source readiness views; no claim of live availability."""

from dataclasses import dataclass

from xti.domain.source_readiness import SourceReadinessEvidence


@dataclass(frozen=True, slots=True)
class SourceReadinessRow:
    evidence: SourceReadinessEvidence
    freshness: str
    success_age_seconds: int | None
    cooldown_active: bool
    cooldown_seconds: int
    needs_attention: bool
    next_command: str


@dataclass(frozen=True, slots=True)
class SourceReadinessReport:
    observed_at: str
    domain: str | None
    storage_state: str
    stale_after_hours: int
    sources: tuple[SourceReadinessRow, ...]
    attention_count: int
    notes: tuple[str, ...]

"""Immutable records shared by offline collection, analysis and persistence."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DomainInput:
    domain: str
    raw_domain: str
    source_line: int
    observed_at: str | None


@dataclass(frozen=True, slots=True)
class ImportDocument:
    source_name: str
    sha256: str
    records: tuple[DomainInput, ...]


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    asset_id: str
    asset_value: str
    domain: str
    rule_version: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Observation:
    id: str
    domain: str
    raw_domain: str
    source_name: str
    source_sha256: str
    source_line: int
    observed_at: str | None
    ingested_at: str


@dataclass(frozen=True, slots=True)
class Finding:
    id: str
    asset_id: str
    asset_value: str
    domain: str
    rule_version: str
    reasons: tuple[str, ...]
    status: str
    created_at: str
    last_seen_at: str


@dataclass(frozen=True, slots=True)
class Review:
    id: str
    finding_id: str
    decision: str
    reason: str
    created_at: str


@dataclass(frozen=True, slots=True)
class FindingDetails:
    finding: Finding
    observations: tuple[Observation, ...]
    reviews: tuple[Review, ...]


@dataclass(frozen=True, slots=True)
class ImportSummary:
    total_records: int
    observations_created: int
    observations_existing: int
    findings_created: int
    findings_existing: int
    findings_suppressed: int = 0


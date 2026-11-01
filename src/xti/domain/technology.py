"""Conservative technology hints derived from stored service evidence."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TechnologyHint:
    endpoint: str
    port: int
    transport: str
    usage_hint: str
    confidence: str
    vendor: None
    product: None
    version: None
    detection_method: str
    cve_match_eligible: bool
    evidence_freshness: str
    evidence_id: str
    recorded_at: str
    limitations: tuple[str, ...]
    next_step: str


@dataclass(frozen=True, slots=True)
class TechnologyEvidenceCoverage:
    status: str
    evidence_id: str | None
    recorded_at: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class TechnologyReport:
    asset_id: str
    asset_value: str
    observed_at: str
    stale_after_hours: int
    scope_status: str
    checked_address: str | None
    hint_count: int
    cve_match_eligible_count: int
    coverage: TechnologyEvidenceCoverage
    hints: tuple[TechnologyHint, ...]
    notes: tuple[str, ...]

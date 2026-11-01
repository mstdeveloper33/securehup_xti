"""Versioned evidence for choosing an additional ransomware claim source."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RansomwareSourceCriterion:
    key: str
    label: str
    required: bool
    passed: bool
    evidence: str


@dataclass(frozen=True, slots=True)
class RansomwareSourceCandidate:
    identifier: str
    label: str
    decision: str
    data_format: str
    access: str
    collection: str
    maintenance_risk: str
    criteria: tuple[RansomwareSourceCriterion, ...]
    blockers: tuple[str, ...]
    reference_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RansomwareSourceEvaluationReport:
    profile_version: str
    evaluated_at: str
    required_criteria: tuple[str, ...]
    selected_identifier: str
    selected_next_step: str
    candidates: tuple[RansomwareSourceCandidate, ...]
    notes: tuple[str, ...]

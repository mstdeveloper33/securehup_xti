"""Versioned evidence for choosing optional brand-OSINT tool integrations."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BrandSourceCriterion:
    key: str
    label: str
    required: bool
    passed: bool
    evidence: str


@dataclass(frozen=True, slots=True)
class BrandSourceCandidate:
    identifier: str
    label: str
    decision: str
    purpose: str
    integration_mode: str
    maintenance_risk: str
    criteria: tuple[BrandSourceCriterion, ...]
    blockers: tuple[str, ...]
    reference_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BrandSourceEvaluationReport:
    profile_version: str
    evaluated_at: str
    required_criteria: tuple[str, ...]
    selected_identifier: str
    selected_next_step: str
    candidates: tuple[BrandSourceCandidate, ...]
    notes: tuple[str, ...]

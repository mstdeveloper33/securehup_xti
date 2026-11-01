"""Versioned evidence for choosing the next official vulnerability source."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VendorSourceCriterion:
    key: str
    label: str
    required: bool
    passed: bool
    evidence: str


@dataclass(frozen=True, slots=True)
class VendorSourceCandidate:
    identifier: str
    label: str
    decision: str
    data_format: str
    access: str
    granularity: str
    maintenance_risk: str
    criteria: tuple[VendorSourceCriterion, ...]
    blockers: tuple[str, ...]
    reference_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VendorSourceEvaluationReport:
    profile_version: str
    evaluated_at: str
    required_criteria: tuple[str, ...]
    selected_identifier: str
    selected_next_step: str
    candidates: tuple[VendorSourceCandidate, ...]
    notes: tuple[str, ...]

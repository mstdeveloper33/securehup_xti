"""Versioned evidence for accepting passive surface-discovery adapters."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SurfaceSourceCriterion:
    key: str
    label: str
    required: bool
    passed: bool
    evidence: str


@dataclass(frozen=True, slots=True)
class SurfaceSourceCandidate:
    identifier: str
    label: str
    decision: str
    purpose: str
    integration_mode: str
    upstream_version: str
    maintenance_risk: str
    criteria: tuple[SurfaceSourceCriterion, ...]
    blockers: tuple[str, ...]
    reference_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SurfaceSourceEvaluationReport:
    profile_version: str
    evaluated_at: str
    required_criteria: tuple[str, ...]
    active_identifiers: tuple[str, ...]
    next_step: str
    candidates: tuple[SurfaceSourceCandidate, ...]
    notes: tuple[str, ...]

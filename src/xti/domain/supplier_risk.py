"""Explainable supplier review cards built only from explicit local evidence."""

from dataclasses import dataclass

from xti.domain.supplier_candidates import SupplierCandidate
from xti.domain.supplier_threat_events import (
    SupplierThreatEvent,
    SupplierThreatSourceCoverage,
)
from xti.domain.suppliers import Supplier


SUPPLIER_ATTENTION_LEVELS = frozenset({
    "priority_review",
    "review",
    "identity_review",
    "insufficient_data",
    "no_current_match",
})


@dataclass(frozen=True, slots=True)
class SupplierRiskCard:
    supplier: Supplier
    attention: str
    current_dependency_count: int
    claim_candidate_count: int
    matched_source_count: int
    domain_evidence_count: int
    name_only_evidence_count: int
    ambiguous_name_count: int
    available_source_count: int
    degraded_source_count: int
    missing_source_count: int
    newest_claim_at: str | None
    newest_snapshot_at: str | None
    event_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    missing_data: tuple[str, ...]
    next_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SupplierRiskReport:
    total_supplier_count: int
    displayed_count: int
    has_more: bool
    priority_review_count: int
    review_count: int
    identity_review_count: int
    insufficient_data_count: int
    no_current_match_count: int
    coverage: tuple[SupplierThreatSourceCoverage, ...]
    cards: tuple[SupplierRiskCard, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SupplierRiskCardDetails:
    card: SupplierRiskCard
    coverage: tuple[SupplierThreatSourceCoverage, ...]
    dependencies: tuple[SupplierCandidate, ...]
    events: tuple[SupplierThreatEvent, ...]
    notes: tuple[str, ...]

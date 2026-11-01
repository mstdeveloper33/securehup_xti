"""Boundaries for stored dependency evidence and supplier-candidate decisions."""

from typing import Protocol

from xti.domain.supplier_candidates import (
    SupplierCandidate,
    SupplierCandidateDetails,
    SupplierCandidateMutation,
    SupplierCandidateProposal,
    SupplierCandidateRefresh,
    SupplierDependencyObservation,
)


class SupplierDependencySource(Protocol):
    def latest(self, *, limit: int) -> tuple[SupplierDependencyObservation, ...]:
        ...


class SupplierCandidateRepository(Protocol):
    def refresh(
        self, proposals: tuple[SupplierCandidateProposal, ...], *,
        observation_count: int, recorded_at: str,
    ) -> SupplierCandidateRefresh:
        ...

    def list(
        self, *, status: str | None, current_only: bool, limit: int,
    ) -> tuple[SupplierCandidate, ...]:
        ...

    def show(
        self, candidate_id: str, *, evidence_limit: int, resolution_limit: int,
    ) -> SupplierCandidateDetails:
        ...

    def review(
        self, candidate_id: str, *, decision: str, supplier_id: str | None,
        reason: str, recorded_at: str,
    ) -> SupplierCandidateMutation:
        ...

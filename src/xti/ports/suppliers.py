"""Persistence boundary for the human-approved supplier inventory."""

from typing import Protocol

from xti.domain.suppliers import Supplier, SupplierDetails, SupplierMutation


class SupplierRepository(Protocol):
    def add(
        self, *, name_key: str, display_name: str, primary_domain: str,
        relationship_type: str, criticality: str, reason: str, recorded_at: str,
    ) -> SupplierMutation:
        ...

    def update(
        self, supplier_id: str, *, display_name: str | None,
        relationship_type: str | None, criticality: str | None,
        reason: str, recorded_at: str,
    ) -> SupplierMutation:
        ...

    def revoke(
        self, supplier_id: str, *, reason: str, recorded_at: str,
    ) -> SupplierMutation:
        ...

    def list(self, *, active_only: bool, limit: int) -> tuple[Supplier, ...]:
        ...

    def show(self, supplier_id: str, *, event_limit: int) -> SupplierDetails:
        ...

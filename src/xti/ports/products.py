"""Persistence boundary for verified asset product evidence."""

from typing import Protocol

from xti.domain.products import (
    AssetProductDetails,
    AssetProductEvidence,
    AssetProductMutation,
)


class AssetProductRepository(Protocol):
    def add(
        self, *, asset_value: str, part: str, vendor: str, product: str, version: str,
        evidence_type: str, evidence: str, recorded_at: str,
    ) -> AssetProductMutation:
        ...

    def revoke(
        self, product_id: str, *, evidence_type: str, evidence: str, recorded_at: str,
    ) -> AssetProductMutation:
        ...

    def list(
        self, *, asset_value: str | None, active_only: bool, limit: int,
    ) -> tuple[AssetProductEvidence, ...]:
        ...

    def details(self, product_id: str, *, event_limit: int) -> AssetProductDetails:
        ...

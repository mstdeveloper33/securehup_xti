"""User-confirmed product evidence lifecycle."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.products import (
    AssetProductDetails,
    AssetProductEvidence,
    AssetProductMutation,
    normalize_cpe_token,
    normalize_product_evidence,
    normalize_product_id,
    normalize_product_part,
    normalize_product_version,
)
from xti.ports.products import AssetProductRepository


class AssetProductService:
    def __init__(
        self, repository: AssetProductRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Ürün kanıtı zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def add(
        self, asset_value: str, *, part: str, vendor: str, product: str,
        version: str, evidence: str,
    ) -> AssetProductMutation:
        return self.repository.add(
            asset_value=normalize_domain(asset_value),
            part=normalize_product_part(part),
            vendor=normalize_cpe_token(vendor, field="Üretici"),
            product=normalize_cpe_token(product, field="Ürün"),
            version=normalize_product_version(version),
            evidence_type="user_verified",
            evidence=normalize_product_evidence(evidence),
            recorded_at=self._now(),
        )

    def revoke(self, product_id: str, *, reason: str) -> AssetProductMutation:
        return self.repository.revoke(
            normalize_product_id(product_id), evidence_type="user_verified",
            evidence=normalize_product_evidence(reason), recorded_at=self._now(),
        )

    def list(
        self, *, asset_value: str | None = None, active_only: bool = True, limit: int = 50,
    ) -> tuple[AssetProductEvidence, ...]:
        if type(active_only) is not bool:
            raise ValidationError("Ürün etkinlik filtresi geçersiz.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Ürün liste sınırı 1–500 arasında olmalı.")
        normalized_asset = normalize_domain(asset_value) if asset_value is not None else None
        return self.repository.list(
            asset_value=normalized_asset, active_only=active_only, limit=limit,
        )

    def show(self, product_id: str, *, event_limit: int = 50) -> AssetProductDetails:
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("Ürün kanıt geçmişi sınırı 1–100 arasında olmalı.")
        return self.repository.details(
            normalize_product_id(product_id), event_limit=event_limit,
        )

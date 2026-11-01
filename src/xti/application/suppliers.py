"""Use cases for a local, explicitly approved supplier inventory."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.suppliers import (
    Supplier,
    SupplierDetails,
    SupplierMutation,
    normalize_supplier_criticality,
    normalize_supplier_id,
    normalize_supplier_name,
    normalize_supplier_reason,
    normalize_supplier_relationship,
)
from xti.ports.suppliers import SupplierRepository


class SupplierService:
    def __init__(
        self, repository: SupplierRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Tedarikçi kayıt zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def add(
        self, name: str, *, domain: str, relationship_type: str,
        criticality: str, reason: str,
    ) -> SupplierMutation:
        name_key, display_name = normalize_supplier_name(name)
        return self.repository.add(
            name_key=name_key,
            display_name=display_name,
            primary_domain=normalize_domain(domain),
            relationship_type=normalize_supplier_relationship(relationship_type),
            criticality=normalize_supplier_criticality(criticality),
            reason=normalize_supplier_reason(reason),
            recorded_at=self._now(),
        )

    def update(
        self, supplier_id: str, *, name: str | None = None,
        relationship_type: str | None = None, criticality: str | None = None,
        reason: str,
    ) -> SupplierMutation:
        if name is None and relationship_type is None and criticality is None:
            raise ValidationError(
                "Güncelleme için --name, --relationship veya --criticality gerekli."
            )
        display_name = None
        if name is not None:
            _, display_name = normalize_supplier_name(name)
        return self.repository.update(
            normalize_supplier_id(supplier_id),
            display_name=display_name,
            relationship_type=(
                normalize_supplier_relationship(relationship_type)
                if relationship_type is not None else None
            ),
            criticality=(
                normalize_supplier_criticality(criticality)
                if criticality is not None else None
            ),
            reason=normalize_supplier_reason(reason),
            recorded_at=self._now(),
        )

    def revoke(self, supplier_id: str, *, reason: str) -> SupplierMutation:
        return self.repository.revoke(
            normalize_supplier_id(supplier_id),
            reason=normalize_supplier_reason(reason),
            recorded_at=self._now(),
        )

    def list(self, *, active_only: bool = True, limit: int = 100) -> tuple[Supplier, ...]:
        if type(active_only) is not bool:
            raise ValidationError("Tedarikçi liste filtresi geçersiz.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Tedarikçi liste sınırı 1–500 arasında olmalı.")
        return self.repository.list(active_only=active_only, limit=limit)

    def show(self, supplier_id: str, *, event_limit: int = 50) -> SupplierDetails:
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("Tedarikçi geçmiş sınırı 1–100 arasında olmalı.")
        return self.repository.show(
            normalize_supplier_id(supplier_id), event_limit=event_limit,
        )

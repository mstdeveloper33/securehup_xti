"""Explain discovery, user ownership choice, registration and active scope separately."""

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.surface_inventory import (
    SurfaceInventoryItem,
    SurfaceInventoryReport,
    SurfaceInventorySnapshot,
)
from xti.ports.assets import AssetRepository
from xti.ports.surface_inventory import SurfaceInventoryRepository


INVENTORY_STATUSES = frozenset({"pending", "owned", "rejected", "all"})


class SurfaceInventoryService:
    def __init__(
        self, assets: AssetRepository, repository: SurfaceInventoryRepository,
    ) -> None:
        self.assets = assets
        self.repository = repository

    def _asset(self, value: str) -> Asset:
        normalized = normalize_domain(value)
        for asset in self.assets.list():
            if asset.value == normalized:
                return asset
        raise ValidationError("Adres kayıtlı değil. Önce './xti assets add' kullan.")

    @staticmethod
    def _scope_status(scope, *, registered: bool) -> str:
        if not registered:
            return "not_applicable"
        if scope is None:
            return "not_approved"
        return "active" if scope.active else "revoked"

    @classmethod
    def _item(cls, record) -> SurfaceInventoryItem:
        candidate = record.candidate
        registered = record.registered_asset is not None
        scope_status = cls._scope_status(record.scope, registered=registered)
        if candidate.status == "pending":
            next_step = "review_candidate"
        elif candidate.status == "rejected":
            next_step = "none"
        elif not registered:
            next_step = "register_asset"
        elif scope_status != "active":
            next_step = "approve_scope"
        else:
            next_step = "monitor"
        return SurfaceInventoryItem(
            candidate_id=candidate.id, domain=candidate.domain,
            candidate_status=candidate.status, decision_reason=candidate.reason,
            first_seen_at=candidate.first_seen_at, last_seen_at=candidate.last_seen_at,
            source_count=candidate.source_count,
            registered_asset_id=(
                None if record.registered_asset is None else record.registered_asset.id
            ),
            registration_status="registered" if registered else "unregistered",
            scope_status=scope_status,
            active_check_authorized=scope_status == "active",
            next_step=next_step,
        )

    def show(
        self, root_asset_value: str, *, status: str = "all", limit: int = 100,
    ) -> SurfaceInventoryReport:
        if status not in INVENTORY_STATUSES:
            raise ValidationError("Envanter durumu pending, owned, rejected veya all olmalı.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Dış yüzey envanter sınırı 1–500 arasında olmalı.")
        root = self._asset(root_asset_value)
        selected_status = None if status == "all" else status
        snapshot = self.repository.snapshot(
            root.id, root.value, status=selected_status, limit=limit,
        )
        if not isinstance(snapshot, SurfaceInventorySnapshot):
            raise ValidationError("Dış yüzey envanteri beklenen biçimde değil.")
        if (
            snapshot.matching_count < len(snapshot.records)
            or snapshot.registered_count > snapshot.candidate_counts.total
            or snapshot.active_scope_count > snapshot.registered_count
        ):
            raise ValidationError("Dış yüzey envanter sayaçları tutarsız.")
        items = tuple(self._item(record) for record in snapshot.records)
        root_scope_status = (
            "not_approved" if snapshot.root_scope is None
            else "active" if snapshot.root_scope.active else "revoked"
        )
        return SurfaceInventoryReport(
            root_asset_id=root.id, root_asset_value=root.value,
            root_scope_status=root_scope_status, status_filter=status,
            candidate_counts=snapshot.candidate_counts,
            matching_count=snapshot.matching_count, displayed_count=len(items),
            has_more=snapshot.matching_count > len(items),
            registered_count=snapshot.registered_count,
            active_scope_count=snapshot.active_scope_count,
            items=items,
            notes=(
                "Pasif aday, kullanıcının bana ait kararı, varlık kaydı ve aktif kapsam ayrı katmanlardır.",
                "Bana ait kararı otomatik varlık kaydı veya bağlantı yetkisi oluşturmaz.",
                "Aktif kapsam kullanıcı yetki beyanıdır; teknik sahiplik doğrulaması değildir.",
                "Bu görünüm internete bağlanmaz, karar vermez ve kayıt değiştirmez.",
            ),
        )

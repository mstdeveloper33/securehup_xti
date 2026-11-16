"""Use cases for authorized Nmap target scopes and dry-run plans."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.nmap_management import (
    ManagedNmapPlan,
    ManagedNmapPlanMutation,
    NmapTargetScope,
    NmapTargetScopeDetails,
    NmapTargetScopeMutation,
    build_managed_plan_definition,
    build_target_definition,
    normalize_authorization_reason,
    normalize_lifecycle_reason,
    normalize_target_name,
)
from xti.ports.assets import AssetRepository
from xti.ports.jobs import ExecutionLock
from xti.ports.nmap_management import NmapManagementRepository
from xti.ports.surface import SurfaceRepository


class NmapManagementService:
    def __init__(
        self,
        assets: AssetRepository,
        surfaces: SurfaceRepository,
        repository: NmapManagementRepository,
        lock: ExecutionLock,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.assets = assets
        self.surfaces = surfaces
        self.repository = repository
        self.lock = lock
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Nmap yönetim kayıt zamanı saat dilimi bilgili olmalı.")
        return value.astimezone(timezone.utc).isoformat()

    def _asset(self, value: str) -> Asset:
        normalized = normalize_domain(value)
        for asset in self.assets.list():
            if asset.value == normalized:
                return asset
        raise ValidationError("Adres kayıtlı değil. Önce './xti assets add' kullan.")

    def _scope(self, asset: Asset, *, require_active: bool):
        scope = self.surfaces.details(asset.id, history_limit=1).scope
        if require_active and not scope.active:
            raise ValidationError(
                "Bu adresin dış yüzey kapsamı etkin değil. Önce 'surface approve' kullan."
            )
        return scope

    @staticmethod
    def _limit(value: int, maximum: int = 500) -> int:
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValidationError(f"Nmap sonuç sınırı 1–{maximum} arasında olmalı.")
        return value

    def save_target(
        self,
        asset_value: str,
        name: str,
        network: str,
        exclusions: tuple[str, ...],
        authorization_reason: str,
    ) -> NmapTargetScopeMutation:
        asset = self._asset(asset_value)
        self._scope(asset, require_active=True)
        name = normalize_target_name(name)
        definition = build_target_definition(network, exclusions)
        reason = normalize_authorization_reason(authorization_reason)
        # Validate existing history before acquiring the writer lock.
        self.repository.list_targets(asset.id, active_only=False, limit=1)
        with self.lock.acquire():
            scope = self._scope(asset, require_active=True)
            return self.repository.save_target(
                scope.asset_id, scope.asset_value, name, definition, reason,
                recorded_at=self._now(),
            )

    def revoke_target(
        self, asset_value: str, name: str, reason: str,
    ) -> NmapTargetScopeMutation:
        asset = self._asset(asset_value)
        self._scope(asset, require_active=False)
        name = normalize_target_name(name)
        reason = normalize_lifecycle_reason(reason)
        self.repository.get_target(asset.id, name)
        with self.lock.acquire():
            return self.repository.revoke_target(
                asset.id, name, reason=reason, recorded_at=self._now(),
            )

    def list_targets(
        self, asset_value: str, *, active_only: bool = True, limit: int = 100,
    ) -> tuple[NmapTargetScope, ...]:
        asset = self._asset(asset_value)
        self._scope(asset, require_active=False)
        return self.repository.list_targets(
            asset.id, active_only=active_only, limit=self._limit(limit),
        )

    def show_target(
        self, asset_value: str, name: str, *, event_limit: int = 50,
    ) -> NmapTargetScopeDetails:
        asset = self._asset(asset_value)
        self._scope(asset, require_active=False)
        return self.repository.target_details(
            asset.id, normalize_target_name(name), event_limit=self._limit(event_limit),
        )

    def create_plan(
        self,
        asset_value: str,
        target_name: str,
        **options,
    ) -> ManagedNmapPlanMutation:
        asset = self._asset(asset_value)
        self._scope(asset, require_active=True)
        target_name = normalize_target_name(target_name)
        target = self.repository.get_target(asset.id, target_name)
        definition = build_managed_plan_definition(target, **options)
        with self.lock.acquire():
            scope = self._scope(asset, require_active=True)
            current = self.repository.get_target(asset.id, target_name)
            if current != target:
                raise ValidationError(
                    "Nmap hedef kapsamı değişti; güncel kapsamı inceleyip planı yeniden oluşturun."
                )
            return self.repository.save_plan(
                scope.asset_id, scope.asset_value, definition, recorded_at=self._now(),
            )

    def list_plans(
        self, asset_value: str, *, limit: int = 100,
    ) -> tuple[ManagedNmapPlan, ...]:
        asset = self._asset(asset_value)
        self._scope(asset, require_active=False)
        return self.repository.list_plans(asset.id, limit=self._limit(limit))

    def show_plan(self, asset_value: str, plan_id: str) -> ManagedNmapPlan:
        asset = self._asset(asset_value)
        self._scope(asset, require_active=False)
        return self.repository.get_plan(asset.id, plan_id)

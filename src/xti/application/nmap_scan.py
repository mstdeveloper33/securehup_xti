"""Authorized Nmap orchestration without storage or subprocess dependencies."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.nmap_scan import (
    NmapScanCheck,
    NmapScanDetails,
    NmapScanPlan,
    validate_nmap_scan_plan,
    validate_nmap_scan_result,
)
from xti.domain.services import normalize_public_address
from xti.ports.assets import AssetRepository
from xti.ports.nmap_scan import NmapProbe, NmapScanRepository
from xti.ports.surface import SurfaceRepository


class NmapSurfaceScanService:
    def __init__(
        self,
        assets: AssetRepository,
        scopes: SurfaceRepository,
        repository: NmapScanRepository,
        probe: NmapProbe | None = None,
        *,
        id_factory: Callable[[], object] = uuid4,
    ) -> None:
        self.assets = assets
        self.scopes = scopes
        self.repository = repository
        self.probe = probe
        self.id_factory = id_factory

    def _asset(self, value: str) -> Asset:
        normalized = normalize_domain(value)
        for asset in self.assets.list():
            if asset.value == normalized:
                return asset
        raise ValidationError("Adres kayıtlı değil. Önce './xti assets add' kullan.")

    def _scope(self, asset: Asset, *, require_active: bool):
        details = self.scopes.details(asset.id, history_limit=1)
        if require_active and not details.scope.active:
            raise ValidationError(
                "Bu adresin dış yüzey kapsamı etkin değil. Önce 'surface approve' kullan."
            )
        return details.scope

    @staticmethod
    def _reason(value: str) -> str:
        if (
            not isinstance(value, str) or value != value.strip()
            or not 1 <= len(value) <= 1000 or not value.isprintable()
        ):
            raise ValidationError("IP kontrol gerekçesi 1–1000 görünür karakter olmalı.")
        return value

    def prepare(
        self,
        asset_value: str,
        requested_addresses: tuple[str, ...],
        authorization_reason: str,
        plan: NmapScanPlan,
    ):
        if not isinstance(requested_addresses, tuple) or not requested_addresses:
            raise ValidationError("En az bir kesin genel IP adresi gerekli.")
        addresses = tuple(normalize_public_address(item) for item in requested_addresses)
        if len(set(addresses)) != len(addresses):
            raise ValidationError("Nmap hedef IP listesi yinelenen adres taşıyamaz.")
        plan = validate_nmap_scan_plan(plan)
        if len(addresses) != plan.target_count:
            raise ValidationError("Nmap hedef sayısı tarama planıyla uyuşmuyor.")
        reason = self._reason(authorization_reason)
        asset = self._asset(asset_value)
        scope = self._scope(asset, require_active=True)
        return scope, addresses, reason, plan

    def check(
        self,
        asset_value: str,
        requested_addresses: tuple[str, ...],
        authorization_reason: str,
        plan: NmapScanPlan,
    ) -> tuple[NmapScanCheck, ...]:
        scope, addresses, reason, plan = self.prepare(
            asset_value, requested_addresses, authorization_reason, plan,
        )
        if self.probe is None:
            raise ValidationError("Nmap kontrolü bu çalışma yolunda yapılandırılmadı.")
        # Tool compatibility is checked before the first DNS or target connection.
        self.probe.readiness()
        execution_id = str(self.id_factory())
        if not 1 <= len(execution_id) <= 64 or not execution_id.isprintable():
            raise ValidationError("Nmap çalışma kimliği üretilemedi.")
        checks: list[NmapScanCheck] = []
        for address in addresses:
            result = validate_nmap_scan_result(
                self.probe.check(scope.asset_value, address, plan, execution_id)
            )
            if (
                result.domain != scope.asset_value
                or result.requested_address != address
                or result.execution_id != execution_id
                or result.plan != plan
            ):
                raise ValidationError(
                    "Nmap sonucu istenen domain, IP, plan veya çalışmayla eşleşmiyor."
                )
            checks.append(self.repository.append_check(scope.asset_id, reason, result))
        return tuple(checks)

    def show(self, asset_value: str, *, history_limit: int = 20) -> NmapScanDetails:
        if type(history_limit) is not int or not 1 <= history_limit <= 100:
            raise ValidationError("Nmap geçmiş sınırı 1–100 arasında olmalı.")
        asset = self._asset(asset_value)
        self._scope(asset, require_active=False)
        return self.repository.details(asset.id, history_limit=history_limit)

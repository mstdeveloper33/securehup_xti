"""Explicit-scope service inventory without storage or transport dependencies."""

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.services import (
    ServiceScanCheck,
    ServiceScanDetails,
    normalize_public_address,
    validate_service_scan_result,
)
from xti.domain.surface import SurfaceScope
from xti.ports.assets import AssetRepository
from xti.ports.services import ServicePortProbe, SurfaceServiceScanRepository
from xti.ports.surface import SurfaceRepository


class SurfaceServiceScanService:
    def __init__(
        self, assets: AssetRepository, scopes: SurfaceRepository,
        repository: SurfaceServiceScanRepository, probe: ServicePortProbe | None = None,
    ) -> None:
        self.assets = assets
        self.scopes = scopes
        self.repository = repository
        self.probe = probe

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

    def check(
        self, asset_value: str, requested_address: str, authorization_reason: str,
    ) -> ServiceScanCheck:
        scope, address, reason = self.prepare(
            asset_value, requested_address, authorization_reason,
        )
        if self.probe is None:
            raise ValidationError("Servis kontrolü bu çalışma yolunda yapılandırılmadı.")
        result = validate_service_scan_result(self.probe.check(scope.asset_value, address))
        if result.domain != scope.asset_value or result.requested_address != address:
            raise ValidationError("Servis sonucu istenen domain ve IP ile eşleşmiyor.")
        return self.repository.append_check(scope.asset_id, reason, result)

    def prepare(
        self, asset_value: str, requested_address: str, authorization_reason: str,
    ) -> tuple[SurfaceScope, str, str]:
        """Validate the exact target and active scope before a lock or network call."""
        address = normalize_public_address(requested_address)
        reason = self._reason(authorization_reason)
        asset = self._asset(asset_value)
        scope = self._scope(asset, require_active=True)
        return scope, address, reason

    def show(self, asset_value: str, *, history_limit: int = 20) -> ServiceScanDetails:
        if type(history_limit) is not int or not 1 <= history_limit <= 100:
            raise ValidationError("Servis geçmiş sınırı 1–100 arasında olmalı.")
        asset = self._asset(asset_value)
        self._scope(asset, require_active=False)
        return self.repository.details(asset.id, history_limit=history_limit)

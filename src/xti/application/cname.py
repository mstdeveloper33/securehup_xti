"""Approved exact-domain CNAME checks without concrete transport or storage."""

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.cname import CnameDnsCheck, CnameDnsDetails, validate_cname_dns_result
from xti.domain.surface import SurfaceScope
from xti.ports.assets import AssetRepository
from xti.ports.cname import CnameDnsProbe, SurfaceCnameRepository
from xti.ports.surface import SurfaceRepository


class SurfaceCnameService:
    def __init__(
        self, assets: AssetRepository, scopes: SurfaceRepository,
        repository: SurfaceCnameRepository, probe: CnameDnsProbe | None = None,
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

    def _scope(self, asset: Asset, *, require_active: bool) -> SurfaceScope:
        details = self.scopes.details(asset.id, history_limit=1)
        if require_active and not details.scope.active:
            raise ValidationError(
                "Bu adresin dış yüzey kapsamı etkin değil. Önce 'surface approve' kullan."
            )
        return details.scope

    def prepare(self, asset_value: str) -> SurfaceScope:
        return self._scope(self._asset(asset_value), require_active=True)

    def check(self, asset_value: str) -> CnameDnsCheck:
        scope = self.prepare(asset_value)
        if self.probe is None:
            raise ValidationError("CNAME kontrolü bu çalışma yolunda yapılandırılmadı.")
        result = validate_cname_dns_result(self.probe.check(scope.asset_value))
        if result.domain != scope.asset_value:
            raise ValidationError("CNAME sonucu istenen tam adresle eşleşmiyor.")
        return self.repository.append_check(scope.asset_id, result)

    def show(self, asset_value: str, *, history_limit: int = 20) -> CnameDnsDetails:
        if type(history_limit) is not int or not 1 <= history_limit <= 100:
            raise ValidationError("CNAME geçmiş sınırı 1–100 arasında olmalı.")
        asset = self._asset(asset_value)
        self._scope(asset, require_active=False)
        return self.repository.details(asset.id, history_limit=history_limit)

"""Approved mail-DNS baselines without storage or transport dependencies."""

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.mail import MailDnsCheck, MailDnsDetails, validate_mail_dns_result
from xti.domain.surface import SurfaceScope
from xti.ports.assets import AssetRepository
from xti.ports.mail import MailDnsProbe, SurfaceMailRepository
from xti.ports.surface import SurfaceRepository


class SurfaceMailService:
    def __init__(
        self, assets: AssetRepository, scopes: SurfaceRepository,
        repository: SurfaceMailRepository, probe: MailDnsProbe | None = None,
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

    def check(self, asset_value: str) -> MailDnsCheck:
        scope = self.prepare(asset_value)
        if self.probe is None:
            raise ValidationError("E-posta DNS kontrolü bu çalışma yolunda yapılandırılmadı.")
        result = validate_mail_dns_result(self.probe.check(scope.asset_value))
        if result.domain != scope.asset_value:
            raise ValidationError("E-posta DNS sonucu istenen kök adresle eşleşmiyor.")
        return self.repository.append_check(scope.asset_id, result)

    def prepare(self, asset_value: str) -> SurfaceScope:
        """Validate the active root and exact DMARC name before lock or network access."""
        asset = self._asset(asset_value)
        scope = self._scope(asset, require_active=True)
        if len(f"_dmarc.{scope.asset_value}") > 253:
            raise ValidationError("Kök adres _dmarc DNS sorgusu oluşturmak için çok uzun.")
        return scope

    def show(self, asset_value: str, *, history_limit: int = 20) -> MailDnsDetails:
        if type(history_limit) is not int or not 1 <= history_limit <= 100:
            raise ValidationError("E-posta DNS geçmiş sınırı 1–100 arasında olmalı.")
        asset = self._asset(asset_value)
        self._scope(asset, require_active=False)
        return self.repository.details(asset.id, history_limit=history_limit)

"""User-facing exact-domain policy without storage or terminal dependencies."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from xti.domain.allowlist import AllowlistDetails, AllowlistEntry
from xti.domain.assets import Asset, ValidationError
from xti.domain.matching import DomainMatcher, normalize_for_matching
from xti.ports.allowlist import AllowlistRepository
from xti.ports.assets import AssetRepository


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AllowlistService:
    def __init__(
        self, assets: AssetRepository, repository: AllowlistRepository,
        matcher: DomainMatcher, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.assets = assets
        self.repository = repository
        self.matcher = matcher
        self.clock = clock or _utc_now

    @staticmethod
    def _reason(value: str) -> str:
        if not isinstance(value, str):
            raise ValidationError("İstisna için açıklama gerekli.")
        value = value.strip()
        if not 1 <= len(value) <= 1000 or not value.isprintable():
            raise ValidationError("İstisna açıklaması 1–1000 görünür karakter içermeli.")
        return value

    @staticmethod
    def _id(value: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 64 or not value.isprintable():
            raise ValidationError("Geçerli bir istisna kimliği gerekli.")
        return value

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("İstisna zamanı saat dilimi bilgili olmalı.")
        return value.astimezone(timezone.utc).isoformat()

    def _asset(self, value: str) -> Asset:
        normalized = normalize_for_matching(value)
        for asset in self.assets.list():
            if asset.value == normalized:
                return asset
        raise ValidationError("İzlenen adres kayıtlı değil. Önce './xti assets add' kullan.")

    def _candidate(self, value: str) -> str:
        security = self.matcher.unicode_security
        if security is not None:
            return security.to_ascii(value)
        return normalize_for_matching(value)

    @staticmethod
    def _expiration(now: datetime, expires_in_days: int | None) -> str | None:
        if expires_in_days is None:
            return None
        if type(expires_in_days) is not int or not 1 <= expires_in_days <= 3650:
            raise ValidationError("İstisna süresi 1–3650 gün arasında olmalı.")
        return (now + timedelta(days=expires_in_days)).isoformat()

    def add(
        self, asset_value: str, domain: str, reason: str,
        expires_in_days: int | None = None,
    ) -> tuple[AllowlistEntry, bool]:
        asset = self._asset(asset_value)
        candidate = self._candidate(domain)
        if self.matcher.match(asset, candidate) is None:
            raise ValidationError(
                "Bu adres seçilen izlenen adres için mevcut kurallarda aday değil; "
                "geniş veya ilgisiz istisna kaydedilmedi."
            )
        now = datetime.fromisoformat(self._now())
        return self.repository.activate(
            asset.id, asset.value, candidate, self._reason(reason), now.isoformat(),
            self._expiration(now, expires_in_days),
        )

    def revoke(self, entry_id: str, reason: str) -> AllowlistEntry:
        return self.repository.revoke(self._id(entry_id), self._reason(reason), self._now())

    def list(
        self, *, active_only: bool = True, asset_value: str | None = None, limit: int = 100,
    ) -> tuple[AllowlistEntry, ...]:
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("İstisna listesi sınırı 1–500 arasında olmalı.")
        asset_id = self._asset(asset_value).id if asset_value is not None else None
        return self.repository.list(active_only=active_only, asset_id=asset_id, limit=limit)

    def show(self, entry_id: str) -> AllowlistDetails:
        return self.repository.get(self._id(entry_id))

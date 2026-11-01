"""Describe stored surface evidence age without starting network work."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import math

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.priority import parse_timestamp
from xti.domain.surface_freshness import (
    SurfaceFreshnessItem,
    SurfaceFreshnessReport,
    SurfaceFreshnessSnapshot,
)
from xti.ports.assets import AssetRepository
from xti.ports.surface_freshness import SurfaceFreshnessRepository


SURFACE_FRESHNESS_TYPES = ("web", "mail", "services")


class SurfaceFreshnessService:
    def __init__(
        self, assets: AssetRepository, repository: SurfaceFreshnessRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.assets = assets
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _asset(self, value: str) -> Asset:
        normalized = normalize_domain(value)
        for asset in self.assets.list():
            if asset.value == normalized:
                return asset
        raise ValidationError("Adres kayıtlı değil. Önce './xti assets add' kullan.")

    def _now(self) -> datetime:
        value = self.clock()
        try:
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("timezone required")
            return value.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Dış yüzey güncellik zamanı geçersiz.") from error

    @staticmethod
    def _result_status(check_type: str, check) -> str:
        if check_type == "web":
            if check.result.dns_status in {"failed", "blocked"}:
                return "failed"
            return "partial" if check.result.errors else "complete"
        if check_type == "mail":
            statuses = (
                check.result.mx_status,
                check.result.spf_status,
                check.result.dmarc_status,
            )
            if all(item == "failed" for item in statuses):
                return "failed"
            return "partial" if check.result.errors else "complete"
        if check.result.dns_status != "resolved":
            return "failed"
        return (
            "partial"
            if any(item.state == "unknown" for item in check.result.ports)
            else "complete"
        )

    @classmethod
    def _item(
        cls, check_type: str, check, now: datetime, freshness_hours: int,
    ) -> SurfaceFreshnessItem:
        if check is None:
            return SurfaceFreshnessItem(
                check_type=check_type, freshness="never", age_seconds=None,
                evidence_id=None, recorded_at=None, result_status="not_checked",
                change_kind=None,
                reasons=("Bu kontrol türü için henüz kalıcı kanıt yok.",),
            )

        recorded = parse_timestamp(check.recorded_at)
        if recorded is None or recorded > now:
            return SurfaceFreshnessItem(
                check_type=check_type, freshness="clock_error", age_seconds=None,
                evidence_id=check.id, recorded_at=check.recorded_at,
                result_status=cls._result_status(check_type, check),
                change_kind=check.change.kind,
                reasons=(
                    "Kanıt zamanı okunamıyor veya gelecekte; güncellik belirlenemedi.",
                ),
            )

        elapsed = now - recorded
        age_seconds = math.floor(elapsed.total_seconds())
        freshness = (
            "current" if elapsed < timedelta(hours=freshness_hours) else "stale"
        )
        reasons = [
            (
                f"Son kanıt seçilen {freshness_hours} saatlik aralıkta."
                if freshness == "current"
                else f"Son kanıt en az {freshness_hours} saat önce kaydedilmiş."
            )
        ]
        result_status = cls._result_status(check_type, check)
        if result_status == "partial":
            reasons.append("Son kontrol kısmi kanıt taşıyor; eksik bölüm tamamlanmış sayılmaz.")
        elif result_status == "failed":
            reasons.append("Son kontrol başarısız; bu, varlığın artık bulunmadığını kanıtlamaz.")
        return SurfaceFreshnessItem(
            check_type=check_type, freshness=freshness, age_seconds=age_seconds,
            evidence_id=check.id, recorded_at=check.recorded_at,
            result_status=result_status, change_kind=check.change.kind,
            reasons=tuple(reasons),
        )

    def show(
        self, asset_value: str, *, freshness_hours: int = 24,
    ) -> SurfaceFreshnessReport:
        if type(freshness_hours) is not int or not 1 <= freshness_hours <= 8760:
            raise ValidationError("Dış yüzey güncellik eşiği 1–8760 saat arasında olmalı.")
        asset = self._asset(asset_value)
        snapshot = self.repository.snapshot(asset.id, asset.value)
        if not isinstance(snapshot, SurfaceFreshnessSnapshot):
            raise ValidationError("Dış yüzey güncellik görünümü beklenen biçimde değil.")
        if snapshot.asset_id != asset.id or snapshot.asset_value != asset.value:
            raise ValidationError("Dış yüzey güncellik görünümü kayıtlı adresle uyuşmuyor.")
        now = self._now()
        checks = {
            "web": snapshot.latest_check,
            "mail": snapshot.latest_mail_check,
            "services": snapshot.latest_service_check,
        }
        items = tuple(
            self._item(check_type, checks[check_type], now, freshness_hours)
            for check_type in SURFACE_FRESHNESS_TYPES
        )
        scope_status = (
            "missing" if snapshot.scope is None
            else "active" if snapshot.scope.active else "revoked"
        )
        return SurfaceFreshnessReport(
            asset_id=asset.id, asset_value=asset.value,
            observed_at=now.isoformat(), freshness_hours=freshness_hours,
            scope_status=scope_status,
            current_count=sum(item.freshness == "current" for item in items),
            stale_count=sum(item.freshness == "stale" for item in items),
            never_count=sum(item.freshness == "never" for item in items),
            clock_error_count=sum(item.freshness == "clock_error" for item in items),
            items=items,
            notes=(
                "Güncellik eşiği yalnız bu görünüm içindir; otomatik kontrol takvimi değildir.",
                "Bu komut yalnız kayıtlı kanıtı okur; internete bağlanmaz ve kayıt değiştirmez.",
                "Eski veya bulunmayan kanıt tek başına risk, kesinti ya da güvenlik kararı değildir.",
                "Sonucun kısmi veya başarısız olması kanıt yaşından ayrı gösterilir.",
            ),
        )

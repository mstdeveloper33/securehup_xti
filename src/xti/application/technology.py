"""Expose port-based usage hints without inventing products or versions."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.priority import parse_timestamp
from xti.domain.surface_freshness import SurfaceFreshnessSnapshot
from xti.domain.technology import (
    TechnologyEvidenceCoverage,
    TechnologyHint,
    TechnologyReport,
)
from xti.ports.assets import AssetRepository
from xti.ports.surface_freshness import SurfaceFreshnessRepository


class TechnologyService:
    """Build a read-only technology boundary from the latest TCP evidence."""

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
            raise ValidationError("Teknoloji değerlendirme zamanı geçersiz.") from error

    @staticmethod
    def _freshness(recorded_at: str, now: datetime, stale_after_hours: int) -> str:
        recorded = parse_timestamp(recorded_at)
        if recorded is None or recorded > now:
            return "clock_error"
        return (
            "current"
            if now - recorded < timedelta(hours=stale_after_hours)
            else "stale"
        )

    @classmethod
    def _coverage(
        cls, check, now: datetime, stale_after_hours: int,
    ) -> TechnologyEvidenceCoverage:
        if check is None:
            return TechnologyEvidenceCoverage(
                "not_checked", None, None,
                "Sınırlı TCP servis kanıtı yok; teknoloji ipucu üretilemedi.",
            )
        freshness = cls._freshness(check.recorded_at, now, stale_after_hours)
        if freshness == "clock_error":
            return TechnologyEvidenceCoverage(
                "clock_error", check.id, check.recorded_at,
                "Kanıt zamanı okunamıyor veya gelecekte; güncellik güvenle belirlenemedi.",
            )
        if check.result.dns_status != "resolved":
            return TechnologyEvidenceCoverage(
                "failed", check.id, check.recorded_at,
                "Son servis kontrolü DNS doğrulamasını tamamlamadı; port sonucu yok.",
            )
        if any(item.state == "unknown" for item in check.result.ports):
            return TechnologyEvidenceCoverage(
                "partial", check.id, check.recorded_at,
                "Son servis kanıtında belirsiz portlar var; görülen açık portlar korunur.",
            )
        return TechnologyEvidenceCoverage(
            freshness, check.id, check.recorded_at,
            (
                f"Son servis kanıtı {stale_after_hours} saatlik aralıkta."
                if freshness == "current"
                else f"Son servis kanıtı en az {stale_after_hours} saat önce kaydedilmiş."
            ),
        )

    def show(
        self, asset_value: str, *, stale_after_hours: int = 24,
    ) -> TechnologyReport:
        if type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760:
            raise ValidationError("Teknoloji güncellik eşiği 1–8760 saat arasında olmalı.")
        asset = self._asset(asset_value)
        snapshot = self.repository.snapshot(asset.id, asset.value)
        if not isinstance(snapshot, SurfaceFreshnessSnapshot):
            raise ValidationError("Teknoloji görünümü beklenen biçimde değil.")
        if snapshot.asset_id != asset.id or snapshot.asset_value != asset.value:
            raise ValidationError("Teknoloji görünümü kayıtlı adresle uyuşmuyor.")
        now = self._now()
        check = snapshot.latest_service_check
        coverage = self._coverage(check, now, stale_after_hours)
        hints: list[TechnologyHint] = []
        if check is not None and check.result.dns_status == "resolved":
            freshness = self._freshness(check.recorded_at, now, stale_after_hours)
            for item in check.result.ports:
                if item.state != "open":
                    continue
                hints.append(TechnologyHint(
                    endpoint=f"{check.result.checked_address}:{item.port}/tcp",
                    port=item.port,
                    transport="tcp",
                    usage_hint=item.service_hint,
                    confidence="hint",
                    vendor=None,
                    product=None,
                    version=None,
                    detection_method="tcp_connect_only",
                    cve_match_eligible=False,
                    evidence_freshness=freshness,
                    evidence_id=check.id,
                    recorded_at=check.recorded_at,
                    limitations=(
                        "Port numarası yalnız yaygın kullanım ipucudur; çalışan ürünü doğrulamaz.",
                        "Banner, protokol cevabı, ürün adı veya sürüm alınmadı.",
                        "Bu ipucu CVE eşleştirmesine uygun değildir.",
                    ),
                    next_step=(
                        "Hizmet sahibinden ürün ve sürüm bilgisini doğrulanabilir kaynakla al; "
                        "CVE değerlendirmesini ancak bundan sonra yap."
                    ),
                ))
        scope_status = (
            "missing" if snapshot.scope is None
            else "active" if snapshot.scope.active else "revoked"
        )
        return TechnologyReport(
            asset_id=asset.id,
            asset_value=asset.value,
            observed_at=now.isoformat(),
            stale_after_hours=stale_after_hours,
            scope_status=scope_status,
            checked_address=(
                check.result.checked_address
                if check is not None and check.result.dns_status == "resolved"
                else None
            ),
            hint_count=len(hints),
            cve_match_eligible_count=sum(item.cve_match_eligible for item in hints),
            coverage=coverage,
            hints=tuple(hints),
            notes=(
                "Servis ipucu doğrulanmış teknoloji, ürün, sürüm veya zafiyet değildir.",
                "Ürün ve sürüm kanıtı bulunmadığı için bu kayıtlar CVE ile eşleştirilmez.",
                "Bu komut yalnız son kayıtlı servis kanıtını okur; internete bağlanmaz ve kayıt değiştirmez.",
                "Kapalı veya belirsiz porttan teknoloji yokluğu sonucu çıkarılmaz.",
            ),
        )

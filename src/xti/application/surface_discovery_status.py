"""Separate a valid empty passive result from incomplete or failed collection."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import math

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.priority import parse_timestamp
from xti.domain.surface import SurfaceDiscoveryRun
from xti.domain.surface_discovery_status import SurfaceDiscoveryStatusReport
from xti.ports.assets import AssetRepository
from xti.ports.surface import SurfaceCandidateRepository


class SurfaceDiscoveryStatusService:
    def __init__(
        self, assets: AssetRepository, repository: SurfaceCandidateRepository, *,
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
            raise ValidationError("Pasif keşif durum zamanı geçersiz.") from error

    @staticmethod
    def _freshness(
        run: SurfaceDiscoveryRun, now: datetime, freshness_hours: int,
    ) -> tuple[str, int | None]:
        finished = parse_timestamp(run.finished_at)
        if finished is None or finished > now:
            return "clock_error", None
        elapsed = now - finished
        return (
            "current" if elapsed < timedelta(hours=freshness_hours) else "stale",
            math.floor(elapsed.total_seconds()),
        )

    @staticmethod
    def _classification(run: SurfaceDiscoveryRun):
        found = run.candidate_count > 0
        if run.status == "complete":
            return (
                "available", "candidates_observed" if found else "none_observed",
                "complete_found" if found else "complete_empty", True, not found,
                "none",
                (
                    "Kaynak sorgusu tamamlandı ve aday bulundu."
                    if found else
                    "Kaynak sorgusu tamamlandı; bu kaynağın yanıtında aday bulunmadı."
                ),
            )
        if run.status == "partial":
            return (
                "incomplete", "candidates_observed" if found else "none_observed",
                "partial_found" if found else "partial_empty", False, False,
                "review_and_retry",
                (
                    "Kısmi yanıtta aday bulundu; fakat daha fazla sonuç eksik olabilir."
                    if found else
                    "Aday görülmedi; fakat kaynak sonucu eksik olduğu için boş sonuç doğrulanmış sayılmaz."
                ),
            )
        return (
            "unavailable", "unknown", "failed", False, False, "retry_discovery",
            "Kaynak çalışması tamamlanamadı; aday varlığı hakkında sonuç çıkarılamaz.",
        )

    def show(
        self, asset_value: str, *, freshness_hours: int = 24,
    ) -> SurfaceDiscoveryStatusReport:
        if type(freshness_hours) is not int or not 1 <= freshness_hours <= 8760:
            raise ValidationError("Pasif keşif güncellik eşiği 1–8760 saat arasında olmalı.")
        asset = self._asset(asset_value)
        runs = self.repository.list_discovery_runs(asset.id, limit=1)
        now = self._now()
        notes = (
            "Tamamlanmış boş sonuç yalnız bu kaynak sorgusunda aday görülmediğini anlatır.",
            "Boş sonuç internette hiç alt alan adı veya risk bulunmadığını kanıtlamaz.",
            "Kısmi ya da başarısız çalışma boş sonuç sayılmaz; durum bilinmiyor kalır.",
            "Bu görünüm yalnız kayıtlı geçmişi okur; internete bağlanmaz ve kayıt değiştirmez.",
        )
        if not runs:
            return SurfaceDiscoveryStatusReport(
                asset.id, asset.value, now.isoformat(), freshness_hours,
                None, "never", "unknown", "never", False, False, "never", None,
                None, None, None, None, None, None, None, None, (), None,
                "run_discovery",
                ("Bu kök için henüz kayıtlı pasif keşif çalışması yok.",), notes,
            )
        if len(runs) != 1 or not isinstance(runs[0], SurfaceDiscoveryRun):
            raise ValidationError("Pasif keşif durum görünümü beklenen biçimde değil.")
        run = runs[0]
        if run.asset_id != asset.id or run.asset_value != asset.value:
            raise ValidationError("Pasif keşif çalışma kaydı kök adresle uyuşmuyor.")
        (
            source_status, result_status, outcome, coverage_complete,
            empty_result_confirmed, next_step, reason,
        ) = self._classification(run)
        freshness, age_seconds = self._freshness(run, now, freshness_hours)
        reasons = [reason]
        if freshness == "stale":
            reasons.append(
                f"Son çalışma en az {freshness_hours} saat önce bitti; yeni durum bilinmiyor."
            )
            if next_step == "none":
                next_step = "run_discovery"
        elif freshness == "clock_error":
            reasons.append("Çalışma zamanı okunamıyor veya gelecekte; güncellik belirlenemedi.")
            if next_step == "none":
                next_step = "run_discovery"
        return SurfaceDiscoveryStatusReport(
            asset.id, asset.value, now.isoformat(), freshness_hours,
            run.provider,
            source_status, result_status, outcome, coverage_complete,
            empty_result_confirmed, freshness, age_seconds,
            run.id, run.status, run.started_at, run.finished_at,
            run.record_count, run.candidate_count, run.skipped_names,
            run.ignored_names, run.warnings, run.error, next_step,
            tuple(reasons), notes,
        )

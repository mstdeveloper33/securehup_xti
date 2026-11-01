"""Describe recorded monitoring coverage without starting work or changing records."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import math

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.operations import SourceCooldown
from xti.domain.priority import parse_timestamp
from xti.domain.status import (
    AssetStatus, CooldownStatus, SourceHistory, SourceStatus, StatusAttempt, StatusReport,
)
from xti.ports.status import StatusRepository


DEFAULT_PROVIDERS = ("crt.sh", "urlscan")


def _valid_times(attempt: StatusAttempt, now: datetime) -> bool:
    started = parse_timestamp(attempt.started_at)
    if started is None or started > now:
        return False
    if attempt.status == "running":
        return attempt.finished_at is None
    finished = parse_timestamp(attempt.finished_at)
    return finished is not None and started <= finished <= now


def _source_status(history: SourceHistory, now: datetime, hours: int) -> SourceStatus:
    latest, completed = history.latest_attempt, history.last_complete
    reasons: list[str] = []
    age: int | None = None
    invalid_time = any(
        attempt is not None and not _valid_times(attempt, now)
        for attempt in (latest, completed)
    )
    if invalid_time:
        freshness = "clock_error"
        reasons.append("Arama zamanı okunamıyor, gelecekte veya tutarsız; güncellik belirlenemedi.")
    elif completed is None:
        freshness = "never"
        reasons.append("Bu adres ve kaynak için tamamlanmış arama kaydı yok.")
    else:
        finished = parse_timestamp(completed.finished_at)
        # A complete record must have a finish even if a replacement port is faulty.
        if completed.status != "complete" or finished is None:
            freshness = "clock_error"
            reasons.append("Tamamlanmış aramanın zaman kaydı tutarsız; güncellik belirlenemedi.")
        else:
            elapsed = now - finished
            age = math.floor(elapsed.total_seconds())
            freshness = "current" if elapsed < timedelta(hours=hours) else "stale"
            reasons.append(
                f"Son tamamlanan arama seçilen {hours} saatlik aralıkta."
                if freshness == "current" else
                f"Son tamamlanan arama en az {hours} saat önce yapılmış."
            )

    if latest is None:
        reasons.append("Bu adres ve kaynak için henüz deneme kaydı yok.")
    elif latest.status == "running":
        reasons.append("Son deneme çalışıyor olarak kayıtlı; bu, çalıştırıcının hâlâ açık olduğunu kanıtlamaz.")
    elif latest.status == "failed":
        reasons.append("Son deneme başarısız; bu kayıt kaynağın şu an kapalı olduğunu göstermez.")
    elif latest.status == "partial":
        reasons.append("Son deneme kısmi kaldı; tamamlanmış arama zamanını yenilemez.")
    elif latest.status == "interrupted":
        reasons.append("Son deneme yarıda kaldı; tamamlanmış arama zamanını yenilemez.")
    if history.queued_count:
        reasons.append(f"Bu adres ve kaynak için {history.queued_count} iş sırada; henüz arama yapılmış sayılmaz.")
    return SourceStatus(
        provider=history.provider, latest_attempt=latest, last_complete=completed,
        queued_count=history.queued_count, freshness=freshness, age_seconds=age,
        reasons=tuple(reasons),
    )


def _cooldown_status(record: SourceCooldown, now: datetime) -> CooldownStatus:
    deadline = parse_timestamp(record.not_before)
    recorded = parse_timestamp(record.recorded_at)
    clock_error = (
        deadline is None or recorded is None
        or recorded > now or deadline < recorded
    )
    # These numeric fields are meaningful only when clock_error is false.
    remaining = 0 if clock_error else max(0, math.ceil((deadline - now).total_seconds()))
    return CooldownStatus(
        provider=record.provider, not_before=record.not_before,
        recorded_at=record.recorded_at, reason=record.reason,
        active=remaining > 0, remaining_seconds=remaining, clock_error=clock_error,
    )


class StatusService:
    def __init__(
        self, repository: StatusRepository, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        now = self.clock()
        try:
            if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
                raise ValidationError("Durum özeti için saat dilimi belli bir zaman gerekli.")
            return now.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Durum özeti zamanı geçersiz veya desteklenen aralığın dışında.") from error

    def show(
        self, domain: str | None = None, *, freshness_hours: int = 24, limit: int = 20,
    ) -> StatusReport:
        if type(freshness_hours) is not int or not 1 <= freshness_hours <= 8760:
            raise ValidationError("Güncellik eşiği 1–8760 saat arasında olmalı.")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Durum özeti adres sınırı 1–100 arasında olmalı.")
        selected_domain = normalize_domain(domain) if domain is not None else None
        snapshot = self.repository.snapshot(DEFAULT_PROVIDERS, selected_domain, limit)
        now = self._now()
        assets = tuple(
            AssetStatus(
                asset=history.asset,
                sources=tuple(_source_status(source, now, freshness_hours) for source in history.sources),
            )
            for history in snapshot.assets
        )
        return StatusReport(
            observed_at=now.isoformat(), freshness_hours=freshness_hours,
            domain_filter=selected_domain, asset_count=snapshot.asset_count,
            displayed_asset_count=len(assets),
            has_more_assets=selected_domain is None and snapshot.asset_count > len(assets),
            observation_count=snapshot.observation_count,
            finding_counts=dict(snapshot.finding_counts), job_counts=dict(snapshot.job_counts),
            notification_count=snapshot.notification_count,
            unread_notification_count=snapshot.unread_notification_count,
            assets=assets,
            cooldowns=tuple(_cooldown_status(item, now) for item in snapshot.cooldowns),
            notes=(
                f"{freshness_hours} saat yalnız bu görünümün güncellik eşiğidir; otomatik çalışma takvimi değildir.",
                "Güncellik adres ve kaynak başına son tamamlanan aramaya aittir; kaynağın şu anki erişimi ölçülmez.",
                "Birden fazla adresli kısmi iş, hiçbir adres için tamamlanmış arama sayılmaz.",
                "Arşivlerin tarih, indeks ve sayfa sınırları vardır; tamamlanan arama bütün interneti kapsamaz.",
                "Çalışıyor kaydı canlı süreç kanıtı değildir; bu görünüm iş başlatmaz veya yarım işi kurtarmaz.",
                "İş durum sayıları geçmiş dahil bütün kayıtlar içindir; başarısız iş sayısı güncel kesinti sayısı değildir.",
                "Adres filtresi yalnız ayrıntıyı daraltır; genel sayaçlar ve kaynak beklemeleri tüm kayıt alanına aittir.",
                "Bu özet kayıtları okur; tam veritabanı bütünlük kontrolü için doctor kullanılır.",
            ),
        )

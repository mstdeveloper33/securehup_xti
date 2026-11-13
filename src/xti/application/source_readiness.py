"""Explain installation, recorded outcomes and age without refreshing sources."""

from collections.abc import Callable
from datetime import datetime, timezone
import math

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.priority import parse_timestamp
from xti.domain.source_readiness_report import SourceReadinessReport, SourceReadinessRow
from xti.ports.source_readiness import SourceReadinessRepository


class SourceReadinessService:
    def __init__(
        self, repository: SourceReadinessRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def show(
        self, *, domain: str | None = None, stale_after_hours: int = 24,
    ) -> SourceReadinessReport:
        if type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760:
            raise ValidationError("Kaynak güncellik eşiği 1–8760 saat arasında olmalı.")
        domain = normalize_domain(domain) if domain is not None else None
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Kaynak durumu için saat dilimli zaman gerekiyor.")
        now = now.astimezone(timezone.utc)
        snapshot = self.repository.snapshot(domain=domain)
        rows = []
        identifiers = set()
        for item in snapshot.sources:
            if item.identifier in identifiers:
                raise ValidationError("Kaynak durumunda yinelenen kaynak kimliği var.")
            identifiers.add(item.identifier)
            if item.installation not in {"builtin", "ready", "missing", "invalid"}:
                raise ValidationError("Kaynak kurulum durumu geçersiz.")
            if item.latest_status not in {
                "never", "complete", "partial", "failed", "running", "unknown", "interrupted",
            }:
                raise ValidationError("Kaynak çalışma durumu geçersiz.")
            age = None
            freshness = "never"
            invalid_time = False
            for value in (item.last_attempt_at, item.last_success_at, item.cooldown_until):
                if value is not None and parse_timestamp(value) is None:
                    invalid_time = True
            attempt = parse_timestamp(item.last_attempt_at)
            success = parse_timestamp(item.last_success_at)
            if invalid_time or (attempt is not None and attempt > now) or (
                success is not None and success > now
            ):
                freshness = "clock_error"
            elif success is not None:
                age = math.floor((now - success).total_seconds())
                freshness = "current" if age < stale_after_hours * 3600 else "stale"
            deadline = parse_timestamp(item.cooldown_until)
            remaining = max(0, math.ceil((deadline - now).total_seconds())) if deadline else 0
            attention = (
                snapshot.storage_state != "ready"
                or item.installation in {"missing", "invalid"}
                or item.latest_status not in {"complete", "unknown"}
                or freshness != "current" or remaining > 0
            )
            command = item.next_command
            if snapshot.storage_state == "not_initialized":
                command = "./setup"
            rows.append(SourceReadinessRow(
                evidence=item, freshness=freshness, success_age_seconds=age,
                cooldown_active=remaining > 0, cooldown_seconds=remaining,
                needs_attention=attention, next_command=command,
            ))
        return SourceReadinessReport(
            observed_at=now.isoformat(), domain=domain,
            storage_state=snapshot.storage_state, stale_after_hours=stale_after_hours,
            sources=tuple(rows), attention_count=sum(row.needs_attention for row in rows),
            notes=(
                "Bu ekran kurulum ve kayıtlı geçmişi okur; internet isteği veya veri yazımı yapmaz.",
                "Her satır kendi kapsamındaki son kaydı gösterir; bütün varlıkların kontrol edildiği anlamına gelmez.",
                "Güncellik, son başarılı yerel kaydın yaşıdır; kaynağın şu an erişilebilir olduğunu ölçmez.",
                "Domain filtresi tarama ve alt alan adı keşfine uygulanır; sosyal izlemeler ve genel beslemeler ayrıca gösterilir.",
                "Önerilen komutlar otomatik çalıştırılmaz. Bekleme varsa bitmesini bekle.",
            ),
        )

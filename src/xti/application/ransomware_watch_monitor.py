"""Bounded foreground repetition of explicit ransomware refresh-all cycles."""

from collections.abc import Callable
from datetime import datetime, timezone
import time

from xti.application.foreground_monitor import MonotonicBudget, utc_now
from xti.application.ransomware_watch_refresh import RansomwareWatchRefreshService
from xti.domain.assets import ValidationError
from xti.domain.ransomware_watches import (
    RansomwareWatchMonitorCycle,
    RansomwareWatchMonitorReport,
)


class RansomwareWatchMonitorService:
    def __init__(
        self, refresh_all: RansomwareWatchRefreshService, *,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.refresh_all = refresh_all
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.sleeper = sleeper

    @staticmethod
    def validate_limits(
        max_cycles: int, interval_seconds: int, max_duration_seconds: int,
    ) -> None:
        for value, minimum, maximum, message in (
            (max_cycles, 1, 1000,
             "Ransomware izleme tur sayısı 1–1000 arasında olmalı."),
            (interval_seconds, 300, 86400,
             "Ransomware izleme aralığı 300–86400 saniye arasında olmalı."),
            (max_duration_seconds, 1, 604800,
             "Ransomware izleme süresi 1–604800 saniye arasında olmalı."),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValidationError(message)

    def _now(self) -> str:
        return utc_now(self.clock, error_message="Ransomware izleme zamanı geçersiz.")

    def run(
        self, *, max_cycles: int = 3, interval_seconds: int = 3600,
        max_duration_seconds: int = 86400, max_watches: int = 50,
        source_item_limit: int = 100, watch_item_limit: int = 100,
        progress: Callable[[str], None] | None = None,
        on_cycle: Callable[[RansomwareWatchMonitorCycle], None] | None = None,
    ) -> RansomwareWatchMonitorReport:
        self.validate_limits(max_cycles, interval_seconds, max_duration_seconds)
        self.refresh_all.validate_limits(
            max_watches, source_item_limit, watch_item_limit,
        )
        if on_cycle is not None and not callable(on_cycle):
            raise ValidationError("Ransomware izleme tur kayıt işlevi geçersiz.")
        # Validate the complete active window before time starts or any source call.
        self.refresh_all.preflight(max_watches=max_watches)
        started_at = self._now()
        budget = MonotonicBudget(
            self.monotonic,
            invalid_message="Ransomware izleme süresini ölçen saat geçersiz.",
            rollback_message=(
                "Ransomware izleme süresini ölçen saat geriye gitti; "
                "izleme durduruldu."
            ),
        )
        budget.start()
        cycles: list[RansomwareWatchMonitorCycle] = []
        elapsed = budget.elapsed

        stop_reason = "cycles"
        for cycle in range(1, max_cycles + 1):
            if elapsed() >= max_duration_seconds:
                stop_reason = "duration"
                break
            if progress:
                progress(f"Ransomware izleme turu {cycle}/{max_cycles} başlıyor.")
            report = self.refresh_all.run(
                max_watches=max_watches,
                source_item_limit=source_item_limit,
                watch_item_limit=watch_item_limit,
                progress=progress,
            )
            source = report.refresh.run
            completed_cycle = RansomwareWatchMonitorCycle(
                cycle=cycle, source_run_id=source.id,
                source_status=source.status,
                source_finished_at=source.finished_at,
                source_record_count=source.source_record_count,
                planned_watch_count=report.planned_watch_count,
                completed_watch_count=report.completed_watch_count,
                baseline_watch_count=report.baseline_watch_count,
                total_count=report.total_count,
                added_count=report.added_count,
                updated_count=report.updated_count,
                unchanged_count=report.unchanged_count,
                removed_count=report.removed_count,
                notification_count=report.notification_count,
                source_error=source.error,
                watch_run_ids=tuple(item.run_id for item in report.items),
            )
            if on_cycle is not None:
                on_cycle(completed_cycle)
            cycles.append(completed_cycle)
            if progress:
                progress(
                    f"Ransomware izleme turu {cycle}/{max_cycles} tamamlandı; "
                    f"kaynak durumu: {source.status}."
                )
            if cycle == max_cycles:
                break
            wait_started = elapsed()
            if wait_started >= max_duration_seconds:
                stop_reason = "duration"
                break
            wait_until = min(wait_started + interval_seconds, max_duration_seconds)
            if progress:
                progress("Sonraki ransomware turu bekleniyor. Durdurmak için Ctrl+C.")
            while True:
                remaining = wait_until - elapsed()
                if remaining <= 0:
                    break
                self.sleeper(min(1.0, remaining))
            if elapsed() >= max_duration_seconds:
                stop_reason = "duration"
                break

        duration = elapsed()
        statuses = tuple(item.source_status for item in cycles)
        return RansomwareWatchMonitorReport(
            planned_cycles=max_cycles, completed_cycles=len(cycles),
            successful_cycles=statuses.count("complete"),
            failed_cycles=statuses.count("failed"),
            completed_watch_runs=sum(item.completed_watch_count for item in cycles),
            baseline_watch_runs=sum(item.baseline_watch_count for item in cycles),
            started_at=started_at, finished_at=self._now(),
            elapsed_seconds=duration, stop_reason=stop_reason,
            total_count=sum(item.total_count for item in cycles),
            added_count=sum(item.added_count for item in cycles),
            updated_count=sum(item.updated_count for item in cycles),
            unchanged_count=sum(item.unchanged_count for item in cycles),
            removed_count=sum(item.removed_count for item in cycles),
            notification_count=sum(item.notification_count for item in cycles),
            cycles=tuple(cycles),
            notes=(
                "Her tur ayrı kaynak çalışmasıdır; başarılı turdaki her izleme ayrı atomik kayıttır.",
                "Kaynak hatası boş sonuç sayılmaz ve o turda eski snapshot üzerinde izleme yapılmaz.",
                "Süre sınırı yeni tur başlatmayı durdurur; başlamış kaynak isteği tamamlanabilir.",
                "Bu komut yalnız terminal açıkken çalışır; arka plan servisi veya zamanlayıcı kurmaz.",
                "Toplam eşleşme ve fark sayaçları tur bazlıdır; aynı kayıt farklı turlarda yeniden sayılabilir.",
            ),
        )

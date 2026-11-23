"""Bounded foreground scheduling for one durable local CTI search."""

from collections.abc import Callable
from datetime import datetime, timezone
import time

from xti.application.foreground_monitor import MonotonicBudget, utc_now
from xti.application.cti_saved_searches import CtiSavedSearchService
from xti.domain.assets import ValidationError
from xti.domain.cti_saved_searches import (
    CtiSavedSearchMonitorCycle,
    CtiSavedSearchMonitorReport,
)


class CtiSavedSearchMonitorService:
    def __init__(
        self, saved_searches: CtiSavedSearchService, *,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.saved_searches = saved_searches
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.sleeper = sleeper

    @staticmethod
    def validate_limits(
        max_cycles: int, interval_seconds: int, max_duration_seconds: int,
    ) -> None:
        for value, minimum, maximum, message in (
            (max_cycles, 1, 1000, "CTI izleme tur sayısı 1–1000 arasında olmalı."),
            (interval_seconds, 300, 86400,
             "CTI izleme aralığı 300–86400 saniye arasında olmalı."),
            (max_duration_seconds, 1, 604800,
             "CTI izleme süresi 1–604800 saniye arasında olmalı."),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValidationError(message)

    def _now(self) -> str:
        return utc_now(self.clock, error_message="CTI izleme zamanı geçersiz.")

    def run(
        self, saved_search_id: str, *, max_cycles: int = 3,
        interval_seconds: int = 3600, max_duration_seconds: int = 86400,
        item_limit: int = 100, progress: Callable[[str], None] | None = None,
    ) -> CtiSavedSearchMonitorReport:
        self.validate_limits(max_cycles, interval_seconds, max_duration_seconds)
        if type(item_limit) is not int or not 1 <= item_limit <= 500:
            raise ValidationError("CTI izleme sonuç sınırı 1–500 arasında olmalı.")
        details = self.saved_searches.show(saved_search_id, event_limit=1, run_limit=1)
        if not details.saved_search.active:
            raise ValidationError("Geri çekilmiş kayıtlı CTI araması izlenemez.")
        started_at = self._now()
        budget = MonotonicBudget(
            self.monotonic,
            invalid_message="CTI izleme süresini ölçen saat geçersiz.",
            rollback_message=(
                "CTI izleme süresini ölçen saat geriye gitti; izleme durduruldu."
            ),
        )
        budget.start()
        cycles: list[CtiSavedSearchMonitorCycle] = []
        elapsed = budget.elapsed

        stop_reason = "cycles"
        for cycle in range(1, max_cycles + 1):
            if elapsed() >= max_duration_seconds:
                stop_reason = "duration"
                break
            if progress:
                progress(
                    f"CTI arama turu {cycle}/{max_cycles}: "
                    f"{details.saved_search.display_name}"
                )
            report = self.saved_searches.run(saved_search_id, item_limit=item_limit)
            run = report.run
            cycles.append(CtiSavedSearchMonitorCycle(
                cycle=cycle, run_id=run.id, executed_at=run.executed_at,
                total_count=run.total_count, added_count=run.added_count,
                updated_count=run.updated_count, unchanged_count=run.unchanged_count,
                removed_count=run.removed_count,
                notification_id=report.notification_id,
            ))
            if progress:
                progress(f"CTI arama turu {cycle}/{max_cycles} tamamlandı.")
            if cycle == max_cycles:
                break
            wait_started = elapsed()
            if wait_started >= max_duration_seconds:
                stop_reason = "duration"
                break
            wait_until = min(wait_started + interval_seconds, max_duration_seconds)
            if progress:
                progress("Sonraki CTI arama turu bekleniyor. Durdurmak için Ctrl+C.")
            while True:
                remaining = wait_until - elapsed()
                if remaining <= 0:
                    break
                self.sleeper(min(1.0, remaining))
            if elapsed() >= max_duration_seconds:
                stop_reason = "duration"
                break

        duration = elapsed()
        return CtiSavedSearchMonitorReport(
            saved_search=details.saved_search, planned_cycles=max_cycles,
            completed_cycles=len(cycles), started_at=started_at,
            finished_at=self._now(), elapsed_seconds=duration,
            stop_reason=stop_reason,
            added_count=sum(value.added_count for value in cycles),
            updated_count=sum(value.updated_count for value in cycles),
            removed_count=sum(value.removed_count for value in cycles),
            notification_count=sum(value.notification_id is not None for value in cycles),
            cycles=tuple(cycles),
            notes=(
                "Her tamamlanan tur ayrı ve tam bir kayıtlı CTI arama çalışmasıdır.",
                "İlk çalışma veya yeni tanım başlangıcı sessizdir; anlamlı sonraki fark yerel kutuya düşer.",
                "Süre sınırı yeni tur başlatmayı durdurur; otomatik arka plan servisi kurulmaz.",
            ),
        )

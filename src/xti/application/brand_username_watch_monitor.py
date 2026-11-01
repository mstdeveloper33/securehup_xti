"""Bounded foreground repetition for one durable social username watch."""

from collections.abc import Callable
from datetime import datetime, timezone
import math
import time

from xti.application.brand_username import validate_brand_request_timeout
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.domain.assets import ValidationError
from xti.domain.brand_username_watches import (
    BrandUsernameWatchMonitorCycle,
    BrandUsernameWatchMonitorReport,
)


class BrandUsernameWatchMonitorService:
    def __init__(
        self,
        watches: BrandUsernameWatchService,
        *,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.watches = watches
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.sleeper = sleeper

    @staticmethod
    def validate_limits(
        max_cycles: int,
        interval_seconds: int,
        max_duration_seconds: int,
        request_timeout: int,
    ) -> None:
        for value, minimum, maximum, message in (
            (
                max_cycles,
                1,
                1000,
                "Sosyal izleme tur sayısı 1–1000 arasında olmalı.",
            ),
            (
                interval_seconds,
                300,
                86400,
                "Sosyal izleme aralığı 300–86400 saniye arasında olmalı.",
            ),
            (
                max_duration_seconds,
                1,
                604800,
                "Sosyal izleme süresi 1–604800 saniye arasında olmalı.",
            ),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValidationError(message)
        validate_brand_request_timeout(request_timeout)

    def _now(self) -> str:
        value = self.clock()
        try:
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValueError("timezone required")
            return value.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Sosyal izleme zamanı geçersiz.") from error

    def _tick(self) -> float:
        value = self.monotonic()
        try:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("invalid monotonic clock")
            return float(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError(
                "Sosyal izleme süresini ölçen saat geçersiz."
            ) from error

    def run(
        self,
        watch_id: str,
        *,
        max_cycles: int = 3,
        interval_seconds: int = 3600,
        max_duration_seconds: int = 86400,
        request_timeout: int = 10,
        progress: Callable[[str], None] | None = None,
    ) -> BrandUsernameWatchMonitorReport:
        self.validate_limits(
            max_cycles,
            interval_seconds,
            max_duration_seconds,
            request_timeout,
        )
        details = self.watches.show(watch_id, event_limit=1, run_limit=1)
        if not details.watch.active:
            raise ValidationError(
                "Geri çekilmiş sosyal kullanıcı adı izlemesi izlenemez."
            )

        started_at = self._now()
        started = self._tick()
        previous = started
        cycles: list[BrandUsernameWatchMonitorCycle] = []

        def elapsed() -> float:
            nonlocal previous
            current = self._tick()
            if current < previous or not math.isfinite(current - started):
                raise ValidationError(
                    "Sosyal izleme süresini ölçen saat geriye gitti; "
                    "izleme durduruldu."
                )
            previous = current
            return current - started

        stop_reason = "cycles"
        for cycle in range(1, max_cycles + 1):
            if elapsed() >= max_duration_seconds:
                stop_reason = "duration"
                break
            if progress:
                progress(
                    f"Sosyal izleme turu {cycle}/{max_cycles}: "
                    f"{details.watch.display_name}"
                )
            report = self.watches.run(
                details.watch.id,
                request_timeout=request_timeout,
                item_limit=10,
            )
            run = report.run
            cycles.append(BrandUsernameWatchMonitorCycle(
                cycle=cycle,
                run_id=run.id,
                status=run.status,
                recorded_at=run.recorded_at,
                platform_count=run.platform_count,
                found_count=run.found_count,
                newly_found_count=run.newly_found_count,
                changed_count=run.changed_count,
                no_longer_reported_count=run.no_longer_reported_count,
                attention_count=report.attention_count,
                error=run.error,
            ))
            if progress:
                progress(
                    f"Sosyal izleme turu {cycle}/{max_cycles} tamamlandı; "
                    f"kaynak durumu: {run.status}."
                )
            if cycle == max_cycles:
                break

            wait_started = elapsed()
            if wait_started >= max_duration_seconds:
                stop_reason = "duration"
                break
            wait_until = min(
                wait_started + interval_seconds,
                max_duration_seconds,
            )
            if progress:
                progress(
                    "Sonraki sosyal izleme turu bekleniyor. Durdurmak için Ctrl+C."
                )
            while True:
                remaining = wait_until - elapsed()
                if remaining <= 0:
                    break
                self.sleeper(min(1.0, remaining))
            if elapsed() >= max_duration_seconds:
                stop_reason = "duration"
                break

        duration = elapsed()
        statuses = tuple(item.status for item in cycles)
        return BrandUsernameWatchMonitorReport(
            watch=details.watch,
            planned_cycles=max_cycles,
            completed_cycles=len(cycles),
            successful_cycles=statuses.count("complete"),
            failed_cycles=statuses.count("failed"),
            started_at=started_at,
            finished_at=self._now(),
            elapsed_seconds=duration,
            stop_reason=stop_reason,
            found_count=sum(item.found_count for item in cycles),
            newly_found_count=sum(item.newly_found_count for item in cycles),
            changed_count=sum(item.changed_count for item in cycles),
            no_longer_reported_count=sum(
                item.no_longer_reported_count for item in cycles
            ),
            attention_count=sum(item.attention_count for item in cycles),
            cycles=tuple(cycles),
            notes=(
                "Her tamamlanan tur ayrı ve atomik izleme çalışmasıdır.",
                "Kaynak hatası hesap yokluğu sayılmaz; sonraki tur denenebilir.",
                "Süre sınırı yeni turu durdurur; başlamış kaynak işi tamamlanabilir.",
                "Komut yalnız terminal açıkken çalışır; arka plan servisi kurmaz.",
                "Bulunan profil otomatik taklit kararı veya bildirim değildir.",
            ),
        )

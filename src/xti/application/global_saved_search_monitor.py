"""Bounded foreground monitoring; each cycle releases the shared writer lock."""

import math
import time

from xti.application.global_saved_searches import GlobalSavedSearchService
from xti.domain.assets import ValidationError
from xti.domain.global_saved_searches import (
    GlobalSavedSearchMonitorCycle, GlobalSavedSearchMonitorReport, watch_id,
)


class GlobalSavedSearchMonitor:
    def __init__(self, service: GlobalSavedSearchService, *, monotonic=time.monotonic,
                 sleeper=time.sleep):
        self.service, self.monotonic, self.sleeper = service, monotonic, sleeper

    def _tick(self):
        value = self.monotonic()
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValidationError("İzleme süresini ölçen saat geçersiz.")
        return float(value)

    def run(self, search_id, *, cycles=2, interval_seconds=60, duration_seconds=600,
            limit=50, progress=None):
        search_id = watch_id(search_id)
        for value, minimum, maximum, label in (
            (cycles, 1, 1000, "Tur sayısı"), (interval_seconds, 1, 86400, "Tur aralığı"),
            (duration_seconds, 1, 604800, "İzleme süresi"), (limit, 1, 500, "Görünüm sınırı"),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValidationError(f"{label} {minimum}–{maximum} arasında olmalı.")
        definition = self.service.show(search_id, event_limit=1, run_limit=1)
        if not definition.saved_search.active:
            raise ValidationError("Kapalı kayıtlı arama izlenemez.")
        started_at, started = self.service._now(), self._tick()
        previous, results, stop_reason = started, [], "cycles"

        def elapsed():
            nonlocal previous
            value = self._tick()
            if value < previous or not math.isfinite(value - started):
                raise ValidationError("İzleme saati geriye gitti; işlem durduruldu.")
            previous = value
            return value - started

        for cycle in range(cycles):
            if elapsed() >= duration_seconds:
                stop_reason = "duration"
                break
            if progress:
                progress(f"Genel arama turu {cycle + 1}/{cycles}.")
            report = self.service.run(search_id, limit=limit)
            results.append(GlobalSavedSearchMonitorCycle(report.run, report.notification_id))
            if progress:
                progress(f"Tur tamamlandı: {report.run.total_count} eşleşme; "
                         f"{report.run.added_count} yeni, {report.run.updated_count} değişen.")
            if cycle + 1 == cycles:
                break
            wait_until = min(elapsed() + interval_seconds, duration_seconds)
            while True:
                remaining = wait_until - elapsed()
                if remaining <= 0:
                    break
                self.sleeper(min(1.0, remaining))
            if elapsed() >= duration_seconds:
                stop_reason = "duration"
                break
        return GlobalSavedSearchMonitorReport(search_id, cycles, len(results), started_at,
            self.service._now(), elapsed(), stop_reason, tuple(results),
            sum(result.notification_id is not None for result in results))

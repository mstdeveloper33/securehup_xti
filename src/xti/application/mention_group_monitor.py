"""Finite foreground collection; no detached worker or scheduling side effect."""

from datetime import datetime, timezone
import time

from xti.application.foreground_monitor import MonotonicBudget, utc_now
from xti.domain.assets import ValidationError
from xti.domain.mention_group_monitor import MentionGroupMonitorCycle, MentionGroupMonitorReport
from xti.domain.mentions import mention_uuid
from xti.ports.mention_group_monitor import MentionGroupRunner


class MentionGroupMonitor:
    def __init__(self, service: MentionGroupRunner, *, clock=None,
                 monotonic=time.monotonic, sleeper=time.sleep):
        self.service = service
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic, self.sleeper = monotonic, sleeper

    def _now(self):
        return utc_now(
            self.clock,
            error_message="Grup izleme zamanı saat dilimi bilgili olmalı.",
        )

    def run(self, group_id, *, cycles=2, interval_seconds=60, duration_seconds=600,
            progress=None):
        group_id = mention_uuid(group_id)
        for value, minimum, maximum, label in (
            (cycles, 1, 100, "Tur sayısı"),
            (interval_seconds, 60, 86400, "Kontrol aralığı"),
            (duration_seconds, 1, 604800, "İzleme süresi"),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValidationError(f"{label} {minimum}–{maximum} arasında olmalı.")
        started_at = self._now()
        budget = MonotonicBudget(
            self.monotonic,
            invalid_message="Grup izleme süresini ölçen saat geçersiz.",
            rollback_message="Grup izleme saati geriye gitti; işlem durduruldu.",
        )
        budget.start()
        elapsed = budget.elapsed
        results, stop_reason = [], "cycles"

        try:
            for index in range(cycles):
                if elapsed() >= duration_seconds:
                    stop_reason = "duration"
                    break
                if progress:
                    progress(f"Firma içerik izleme turu {index + 1}/{cycles}.")
                result = self.service.run(group_id)
                run = result.get("run")
                cycle = MentionGroupMonitorCycle(
                    index + 1, result["status"], result.get("reason"),
                    run.id if run is not None else None,
                    result["daily_queries_used"], result.get("next_due_at"),
                )
                results.append(cycle)
                if progress:
                    progress(f"Tur tamamlandı: {cycle.status}; günlük sorgu sayısı {cycle.daily_queries_used}.")
                if cycle.reason == "daily_budget":
                    stop_reason = "daily_budget"
                    break
                if index + 1 == cycles:
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
        except KeyboardInterrupt:
            # The group service owns durable progress. Do not retry a possibly
            # charged request or alter evidence when the foreground is stopped.
            stop_reason = "interrupted"
        return MentionGroupMonitorReport(
            group_id, cycles, len(results), started_at, self._now(), elapsed(),
            stop_reason, tuple(results),
        )

"""Durable lifecycle around bounded foreground ransomware monitoring."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from xti.application.ransomware_watch_monitor import RansomwareWatchMonitorService
from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.ransomware_watches import (
    RansomwareMonitorSession,
    RansomwareMonitorSessionDetails,
    RansomwareWatchMonitorReport,
)
from xti.ports.ransomware_monitor_sessions import RansomwareMonitorSessionRepository


class RansomwareMonitorSessionService:
    def __init__(
        self, repository: RansomwareMonitorSessionRepository,
        monitor: RansomwareWatchMonitorService, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.monitor = monitor
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        try:
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("timezone required")
            return value.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Ransomware monitor oturum zamanı geçersiz.") from error

    @staticmethod
    def _limit(value: int, *, field: str) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError(f"{field} 1–500 arasında olmalı.")
        return value

    def run(
        self, *, max_cycles: int = 3, interval_seconds: int = 3600,
        max_duration_seconds: int = 86400, max_watches: int = 50,
        source_item_limit: int = 100, watch_item_limit: int = 100,
        progress: Callable[[str], None] | None = None,
    ) -> RansomwareWatchMonitorReport:
        self.monitor.validate_limits(
            max_cycles, interval_seconds, max_duration_seconds,
        )
        self.monitor.refresh_all.validate_limits(
            max_watches, source_item_limit, watch_item_limit,
        )
        self.monitor.refresh_all.preflight(max_watches=max_watches)
        session = self.repository.start(
            started_at=self._now(), planned_cycles=max_cycles,
            interval_seconds=interval_seconds,
            max_duration_seconds=max_duration_seconds,
            max_watches=max_watches, source_item_limit=source_item_limit,
            watch_item_limit=watch_item_limit,
        )
        try:
            report = self.monitor.run(
                max_cycles=max_cycles, interval_seconds=interval_seconds,
                max_duration_seconds=max_duration_seconds,
                max_watches=max_watches, source_item_limit=source_item_limit,
                watch_item_limit=watch_item_limit, progress=progress,
                on_cycle=lambda cycle: self.repository.record_cycle(session.id, cycle),
            )
        except KeyboardInterrupt:
            self.repository.finish(
                session.id, status="interrupted", stop_reason="interrupted",
                finished_at=self._now(), error="",
            )
            raise
        except Exception as error:
            message = (
                str(error) if isinstance(error, ValidationError)
                else "İzleme kalıcı kayıt veya çalışma hatası nedeniyle durdu."
            )
            self.repository.finish(
                session.id, status="failed", stop_reason="error",
                finished_at=self._now(), error=message,
            )
            raise
        status = (
            "complete"
            if report.completed_cycles > 0 and report.failed_cycles == 0
            else "partial"
        )
        self.repository.finish(
            session.id, status=status, stop_reason=report.stop_reason,
            finished_at=self._now(), error="",
        )
        return replace(report, session_id=session.id)

    def list(self, *, limit: int = 20) -> tuple[RansomwareMonitorSession, ...]:
        return self.repository.list(limit=self._limit(limit, field="Oturum sınırı"))

    def show(
        self, session_id: str, *, cycle_limit: int = 100,
    ) -> RansomwareMonitorSessionDetails:
        return self.repository.details(
            normalize_knowledge_id(session_id, field="ransomware monitor oturum kimliği"),
            cycle_limit=self._limit(cycle_limit, field="Tur sınırı"),
        )

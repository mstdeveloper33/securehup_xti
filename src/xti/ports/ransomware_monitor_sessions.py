"""Persistence boundary for foreground ransomware monitor sessions."""

from typing import Protocol

from xti.domain.ransomware_watches import (
    RansomwareMonitorSession,
    RansomwareMonitorSessionDetails,
    RansomwareWatchMonitorCycle,
)


class RansomwareMonitorSessionRepository(Protocol):
    def start(self, **values) -> RansomwareMonitorSession: ...

    def record_cycle(
        self, session_id: str, cycle: RansomwareWatchMonitorCycle,
    ) -> RansomwareMonitorSession: ...

    def finish(
        self, session_id: str, *, status: str, stop_reason: str,
        finished_at: str, error: str,
    ) -> RansomwareMonitorSession: ...

    def list(self, *, limit: int) -> tuple[RansomwareMonitorSession, ...]: ...

    def details(
        self, session_id: str, *, cycle_limit: int,
    ) -> RansomwareMonitorSessionDetails: ...

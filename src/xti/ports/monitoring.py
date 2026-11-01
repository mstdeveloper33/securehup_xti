"""Persistence boundary for grouped, bounded monitoring work."""

from typing import Protocol

from xti.domain.jobs import ScanJob
from xti.domain.monitoring import MonitorDetails, MonitorRun, MonitorSpec


class MonitorRepository(Protocol):
    def create(self, spec: MonitorSpec, now: str) -> MonitorRun:
        """Caller holds the local execution lock throughout the session."""
        ...

    def enqueue(self, run_id: str, cycle: int, provider: str, now: str) -> ScanJob:
        """Create the job and its session link in the same transaction."""
        ...

    def finish(
        self, run_id: str, status: str, reason: str, now: str,
        elapsed_seconds: float | None,
    ) -> MonitorRun:
        """Close a session; retire linked unstarted work without inventing attempts."""
        ...

    def recover(self, now: str) -> int:
        """Under execution lock, close interrupted sessions and their pending work.

        Elapsed monotonic duration cannot be reconstructed after process death.
        """
        ...

    def list(self, limit: int = 20) -> tuple[MonitorRun, ...]:
        ...

    def get(self, run_id: str) -> MonitorDetails:
        """One read transaction; only the attributed first attempt per linked job."""
        ...

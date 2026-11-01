"""Storage boundaries for conservative provider pacing and maintenance."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from xti.domain.operations import CleanupPlan, CleanupResult, CleanupRun, SourceCooldown, StorageUsage


class CooldownRepository(Protocol):
    def get(self, provider: str) -> SourceCooldown | None:
        ...

    def list(self) -> tuple[SourceCooldown, ...]:
        ...

    def extend(
        self, provider: str, not_before: str, recorded_at: str, reason: str,
    ) -> SourceCooldown:
        """Atomically preserve the later deadline; never shorten a recorded wait."""
        ...


class MaintenanceRepository(Protocol):
    def usage(self) -> StorageUsage:
        ...

    def preview(self, older_than_days: int, limit: int, now: datetime) -> CleanupPlan:
        ...

    def apply(
        self, older_than_days: int, limit: int, now: datetime, token: str,
    ) -> CleanupResult:
        """Recheck preview, back up, then atomically delete and record the action."""
        ...

    def history(self, limit: int) -> tuple[CleanupRun, ...]:
        ...

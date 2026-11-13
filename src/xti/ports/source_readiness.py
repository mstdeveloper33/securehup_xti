"""Read-only boundary for source history and local tool installation."""

from typing import Protocol

from xti.domain.source_readiness import SourceReadinessSnapshot


class SourceReadinessRepository(Protocol):
    def snapshot(self, *, domain: str | None = None) -> SourceReadinessSnapshot: ...

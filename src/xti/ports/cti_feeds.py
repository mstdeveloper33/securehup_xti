"""Application boundaries for bounded complete-snapshot CTI feeds."""

from typing import Protocol

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.cti_feeds import CtiFeedRun, CtiFeedSnapshot, CtiFeedStatus


class CtiFeedSource(Protocol):
    def fetch(self) -> CtiFeedSnapshot:
        ...


class CtiFeedRepository(Protocol):
    def apply(
        self, snapshot: CtiFeedSnapshot, *, started_at: str, finished_at: str,
        operation: CollectionOperationToken | None = None,
    ) -> CtiFeedRun:
        ...

    def record_failure(
        self, *, started_at: str, finished_at: str, error: str,
        operation: CollectionOperationToken | None = None,
    ) -> CtiFeedRun:
        ...

    def status(self, *, run_limit: int) -> CtiFeedStatus:
        ...


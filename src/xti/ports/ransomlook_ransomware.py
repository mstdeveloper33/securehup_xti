"""Boundary for the public RansomLook recent-post source."""

from typing import Protocol

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.ransomlook_ransomware import (
    RansomLookClaimFeed,
    RansomLookClaimHistoryEvidence,
    RansomLookClaimHistoryStatus,
    RansomLookClaimRun,
    RansomLookClaimRunReport,
    RansomLookClaimSnapshot,
)


class RansomLookClaimSource(Protocol):
    def fetch(self) -> RansomLookClaimFeed:
        """Return one completely validated recent-post snapshot."""


class RansomLookClaimRepository(Protocol):
    def apply(
        self, feed: RansomLookClaimFeed, *, started_at: str, finished_at: str,
        item_limit: int, operation: CollectionOperationToken | None = None,
    ) -> RansomLookClaimRunReport:
        ...

    def record_failure(
        self, *, started_at: str, finished_at: str, error: str,
        operation: CollectionOperationToken | None = None,
    ) -> RansomLookClaimRun:
        ...

    def status(self, *, run_limit: int) -> RansomLookClaimHistoryStatus:
        ...

    def latest_snapshot(self) -> RansomLookClaimSnapshot:
        ...

    def history(self) -> RansomLookClaimHistoryEvidence:
        ...

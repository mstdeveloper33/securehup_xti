"""Boundary for the public RansomLook recent-post source."""

from typing import Protocol

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
        item_limit: int,
    ) -> RansomLookClaimRunReport:
        ...

    def record_failure(
        self, *, started_at: str, finished_at: str, error: str,
    ) -> RansomLookClaimRun:
        ...

    def status(self, *, run_limit: int) -> RansomLookClaimHistoryStatus:
        ...

    def latest_snapshot(self) -> RansomLookClaimSnapshot:
        ...

    def history(self) -> RansomLookClaimHistoryEvidence:
        ...

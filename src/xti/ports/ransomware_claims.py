"""Boundary for public ransomware claim feeds."""

from typing import Protocol

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.ransomware_claims import (
    RansomwareClaimFeed,
    RansomwareClaimHistoryStatus,
    RansomwareClaimHistoryEvidence,
    RansomwareClaimRun,
    RansomwareClaimRunReport,
    RansomwareClaimSnapshot,
)


class RansomwareClaimSource(Protocol):
    def fetch(self) -> RansomwareClaimFeed:
        """Return one completely validated public source snapshot."""


class RansomwareClaimRepository(Protocol):
    def apply(
        self, feed: RansomwareClaimFeed, *, started_at: str, finished_at: str,
        item_limit: int, operation: CollectionOperationToken | None = None,
    ) -> RansomwareClaimRunReport:
        ...

    def record_failure(
        self, *, started_at: str, finished_at: str, error: str,
        operation: CollectionOperationToken | None = None,
    ) -> RansomwareClaimRun:
        ...

    def status(self, *, run_limit: int) -> RansomwareClaimHistoryStatus:
        ...

    def latest_snapshot(self) -> RansomwareClaimSnapshot:
        """Return the latest complete locally stored source state."""
        ...

    def history(self) -> RansomwareClaimHistoryEvidence:
        """Return the fully audited compact local source history."""
        ...


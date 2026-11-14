"""Persistence boundary for local ransomware claim watches."""

from typing import Protocol

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.ransomware_claims import RansomwareClaimSnapshot
from xti.domain.ransomware_watches import (
    RansomwareWatchDetails,
    RansomwareWatchMutation,
    RansomwareWatchRunReport,
    RansomwareWatchSummary,
)


class RansomwareWatchRepository(Protocol):
    def upsert(self, **values) -> RansomwareWatchMutation: ...

    def revoke(
        self, watch_id: str, *, reason: str, recorded_at: str,
    ) -> RansomwareWatchMutation: ...

    def list(
        self, *, active_only: bool, limit: int,
    ) -> tuple[RansomwareWatchSummary, ...]: ...

    def details(
        self, watch_id: str, *, event_limit: int, run_limit: int,
    ) -> RansomwareWatchDetails: ...

    def run(
        self, watch_id: str, snapshot: RansomwareClaimSnapshot, *,
        executed_at: str, item_limit: int,
        operation: CollectionOperationToken | None = None,
    ) -> RansomwareWatchRunReport: ...

    def run_details(
        self, run_id: str, *, item_limit: int,
    ) -> RansomwareWatchRunReport: ...

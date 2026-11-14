"""Persistence boundary for RansomLook organization watches."""

from typing import Protocol

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.ransomlook_ransomware import RansomLookClaimSnapshot
from xti.domain.ransomlook_watches import (
    RansomLookWatchDetails,
    RansomLookWatchMutation,
    RansomLookWatchRunReport,
    RansomLookWatchSummary,
)


class RansomLookWatchRepository(Protocol):
    def upsert(self, **values) -> RansomLookWatchMutation: ...

    def revoke(
        self, watch_id: str, *, reason: str, recorded_at: str,
    ) -> RansomLookWatchMutation: ...

    def list(
        self, *, active_only: bool, limit: int,
    ) -> tuple[RansomLookWatchSummary, ...]: ...

    def details(
        self, watch_id: str, *, event_limit: int, run_limit: int,
    ) -> RansomLookWatchDetails: ...

    def run(
        self, watch_id: str, snapshot: RansomLookClaimSnapshot, *,
        executed_at: str, item_limit: int,
        operation: CollectionOperationToken | None = None,
    ) -> RansomLookWatchRunReport: ...

    def run_details(
        self, run_id: str, *, item_limit: int,
    ) -> RansomLookWatchRunReport: ...


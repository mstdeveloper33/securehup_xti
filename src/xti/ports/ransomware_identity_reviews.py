"""Persistence boundary for human ransomware identity-candidate decisions."""

from typing import Protocol

from xti.domain.ransomware_watches import (
    RansomwareIdentityReviewDetails,
    RansomwareIdentityReviewMutation,
    RansomwareIdentityReviewState,
    RansomwareWatchIdentityCandidate,
)


class RansomwareIdentityReviewRepository(Protocol):
    def record(
        self, candidate: RansomwareWatchIdentityCandidate, *, decision: str,
        reason: str, recorded_at: str,
    ) -> RansomwareIdentityReviewMutation: ...

    def details(
        self, candidate_id: str, *, event_limit: int,
    ) -> RansomwareIdentityReviewDetails: ...

    def states(self, watch_id: str) -> tuple[RansomwareIdentityReviewState, ...]: ...

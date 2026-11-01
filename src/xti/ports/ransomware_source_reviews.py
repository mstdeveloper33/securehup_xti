"""Persistence boundary for cross-source ransomware human decisions."""

from typing import Protocol

from xti.domain.ransomware_source_comparison import (
    RansomwareSourceComparisonEvidence,
    RansomwareSourceReviewDetails,
    RansomwareSourceReviewMutation,
    RansomwareSourceReviewState,
)


class RansomwareSourceReviewRepository(Protocol):
    def record(
        self, evidence: RansomwareSourceComparisonEvidence, *, decision: str,
        reason: str, recorded_at: str,
    ) -> RansomwareSourceReviewMutation: ...

    def details(
        self, comparison_id: str, *, event_limit: int,
    ) -> RansomwareSourceReviewDetails: ...

    def states(self) -> tuple[RansomwareSourceReviewState, ...]: ...

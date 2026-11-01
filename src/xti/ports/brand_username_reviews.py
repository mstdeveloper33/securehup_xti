"""Persistence boundary for exact social-profile human decisions."""

from typing import Protocol

from xti.domain.brand_username_reviews import (
    BrandUsernameReviewCandidate,
    BrandUsernameReviewDetails,
    BrandUsernameReviewMutation,
    BrandUsernameReviewState,
)


class BrandUsernameReviewRepository(Protocol):
    def current_candidate(
        self, watch_id: str, platform: str,
    ) -> BrandUsernameReviewCandidate: ...

    def record(
        self, candidate: BrandUsernameReviewCandidate, *, decision: str,
        reason: str, recorded_at: str,
    ) -> BrandUsernameReviewMutation: ...

    def details(
        self, candidate_id: str, *, event_limit: int,
    ) -> BrandUsernameReviewDetails: ...

    def states(self, watch_id: str) -> tuple[BrandUsernameReviewState, ...]: ...

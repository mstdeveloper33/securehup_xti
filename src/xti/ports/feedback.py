"""Persistence boundary for a consistent, read-only review summary."""

from typing import Protocol

from xti.domain.feedback import FeedbackSnapshot


class FeedbackRepository(Protocol):
    def snapshot(self) -> FeedbackSnapshot:
        """Read current findings and review history in one transaction.

        This operation must not initialize, migrate, repair or otherwise change
        storage, and must not infer ground truth from a human decision.
        """
        ...

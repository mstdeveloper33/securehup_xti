"""Bounded local inbox persistence; no external delivery is implied."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from xti.domain.inbox import InboxDetails, InboxPage, MarkResult


class NotificationRepository(Protocol):
    def list(
        self, status: str = "unread", limit: int = 20, before: int | None = None,
    ) -> InboxPage:
        """Read counts and a stable sequence page from one snapshot."""
        ...

    def get(self, notification_id: str) -> InboxDetails:
        """Read a notice and its finding evidence without marking it read."""
        ...

    def mark(self, ids: Sequence[str], read: bool, now: str) -> MarkResult:
        """Update only explicit IDs, all-or-nothing; preserve repeat read time."""
        ...

"""Idempotent hand-off from a completed source attempt to the existing inbox."""

from typing import Protocol

from xti.domain.global_saved_searches import GlobalSavedSearchRunReport
from xti.domain.mentions import MentionRequest


class MentionNotificationBridge(Protocol):
    def validate(self, *, group_id: str, requests: tuple[MentionRequest, ...]) -> None:
        """Read-only preflight for known scope/capacity failures before metered HTTP."""
        ...

    def notify(self, *, group_id: str, request: MentionRequest, mention_run_id: str,
               operation_id: str, executed_at: str) -> GlobalSavedSearchRunReport:
        """Caller owns the workspace writer lock; this call never uses the network."""
        ...

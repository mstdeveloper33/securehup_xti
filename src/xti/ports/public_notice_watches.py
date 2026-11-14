"""Configuration and immutable evidence for explicit public catalog watches."""
from typing import Protocol
from xti.domain.public_notice_watches import (
    PublicNoticeWatchDetails, PublicNoticeWatchMutation, PublicNoticeWatchPage,
    PublicNoticeWatchRunReport,
)


class PublicNoticeWatchRepository(Protocol):
    def configure(self, organization_id: str, *, enabled: bool, reason: str,
                  recorded_at: str) -> PublicNoticeWatchMutation: ...
    def list(self, *, active_only: bool, offset: int, limit: int) -> PublicNoticeWatchPage: ...
    def show(self, organization_id: str, *, event_limit: int, run_limit: int, run_offset: int = 0, event_offset: int = 0) -> PublicNoticeWatchDetails: ...
    def run_show(self, run_id: str, *, item_limit: int, offset: int) -> PublicNoticeWatchRunReport: ...

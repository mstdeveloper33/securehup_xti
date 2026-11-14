"""Boundaries for the public incident catalog and its local complete snapshots."""

from typing import Protocol

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.public_notices import (
    PublicNoticeFeed, PublicNoticeRefreshReport, PublicNoticeRun,
    PublicNoticeSnapshot, PublicNoticeStatus,
)


class PublicNoticeSource(Protocol):
    def fetch(self) -> PublicNoticeFeed:
        ...


class PublicNoticeRepository(Protocol):
    def validate(self, *, operation: CollectionOperationToken | None = None) -> None:
        ...

    def apply(self, feed: PublicNoticeFeed, *, started_at: str, finished_at: str,
              item_limit: int, operation: CollectionOperationToken | None = None) -> PublicNoticeRefreshReport:
        ...

    def record_failure(self, *, started_at: str, finished_at: str, error: str,
                       operation: CollectionOperationToken | None = None) -> PublicNoticeRun:
        ...

    def status(self, *, run_limit: int, offset: int = 0) -> PublicNoticeStatus:
        ...

    def latest_snapshot(self) -> PublicNoticeSnapshot:
        ...

    def run_show(self, identifier: str, *, item_limit: int, offset: int = 0) -> PublicNoticeRefreshReport:
        ...

"""Persistence boundary for durable local CTI search watches."""

from typing import Protocol

from xti.domain.cti_saved_searches import (
    CtiSavedSearchDetails,
    CtiSavedSearchMutation,
    CtiSavedSearchRunReport,
    CtiSavedSearchSummary,
)


class CtiSavedSearchRepository(Protocol):
    def upsert(self, **values) -> CtiSavedSearchMutation:
        ...

    def revoke(
        self, saved_search_id: str, *, reason: str, recorded_at: str,
    ) -> CtiSavedSearchMutation:
        ...

    def list(
        self, *, active_only: bool, limit: int,
    ) -> tuple[CtiSavedSearchSummary, ...]:
        ...

    def details(
        self, saved_search_id: str, *, event_limit: int, run_limit: int,
    ) -> CtiSavedSearchDetails:
        ...

    def run(
        self, saved_search_id: str, *, executed_at: str, item_limit: int,
    ) -> CtiSavedSearchRunReport:
        ...

    def run_details(
        self, run_id: str, *, item_limit: int,
    ) -> CtiSavedSearchRunReport:
        ...

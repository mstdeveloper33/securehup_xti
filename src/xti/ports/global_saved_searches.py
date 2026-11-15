"""Atomic persistence boundary for saved searches and local change notices."""

from typing import Protocol

from xti.domain.global_saved_searches import (
    GlobalSavedSearchDetails, GlobalSavedSearchMutation, GlobalSavedSearchPage,
    GlobalSavedSearchRunReport,
)


class GlobalSavedSearchRepository(Protocol):
    def upsert(self, *, name_key: str, display_name: str, query: str,
               kinds: tuple[str, ...], include_inactive: bool,
               recorded_at: str, mention_request_key: str | None = None) -> GlobalSavedSearchMutation: ...

    def disable(self, search_id: str, *, reason: str,
                recorded_at: str) -> GlobalSavedSearchMutation: ...

    def list(self, *, active_only: bool, offset: int, limit: int) -> GlobalSavedSearchPage: ...

    def details(self, search_id: str, *, event_offset: int, event_limit: int,
                run_offset: int, run_limit: int) -> GlobalSavedSearchDetails: ...

    def run(self, search_id: str, *, executed_at: str, offset: int,
            limit: int, run_id: str | None = None) -> GlobalSavedSearchRunReport: ...

    def run_details(self, run_id: str, *, offset: int,
                    limit: int) -> GlobalSavedSearchRunReport: ...

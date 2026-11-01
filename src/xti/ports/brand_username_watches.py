"""Persistence boundary for durable social username watches."""

from typing import Protocol

from xti.domain.brand_username import BrandUsernamePreview
from xti.domain.brand_username_watches import (
    BrandUsernameWatch,
    BrandUsernameWatchDetails,
    BrandUsernameWatchMutation,
    BrandUsernameWatchRunReport,
    BrandUsernameWatchSummary,
)


class BrandUsernameWatchRepository(Protocol):
    def upsert(self, **values) -> BrandUsernameWatchMutation: ...

    def revoke(
        self, watch_id: str, *, reason: str, recorded_at: str,
    ) -> BrandUsernameWatchMutation: ...

    def get(self, watch_id: str) -> BrandUsernameWatch: ...

    def list(
        self, *, active_only: bool, limit: int,
    ) -> tuple[BrandUsernameWatchSummary, ...]: ...

    def details(
        self, watch_id: str, *, event_limit: int, run_limit: int,
    ) -> BrandUsernameWatchDetails: ...

    def record_preview(
        self,
        watch_id: str,
        *,
        expected_definition_sha256: str,
        preview: BrandUsernamePreview,
        recorded_at: str,
        item_limit: int,
    ) -> BrandUsernameWatchRunReport: ...

    def record_failure(
        self,
        watch_id: str,
        *,
        expected_definition_sha256: str,
        source_name: str,
        source_version: str,
        integration_profile: str,
        error: str,
        recorded_at: str,
    ) -> BrandUsernameWatchRunReport: ...

    def run_details(
        self, run_id: str, *, item_limit: int,
    ) -> BrandUsernameWatchRunReport: ...

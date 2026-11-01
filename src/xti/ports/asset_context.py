"""Persistence boundary for human-managed asset business criticality."""

from typing import Protocol

from xti.domain.asset_context import (
    AssetCriticality,
    AssetCriticalityDetails,
    AssetCriticalityMutation,
)


class AssetCriticalityRepository(Protocol):
    def set(
        self, asset_value: str, *, level: str, reason: str, recorded_at: str,
    ) -> AssetCriticalityMutation:
        ...

    def clear(
        self, asset_value: str, *, reason: str, recorded_at: str,
    ) -> AssetCriticalityMutation:
        ...

    def show(self, asset_value: str, *, event_limit: int) -> AssetCriticalityDetails:
        ...

    def active_for_assets(self, asset_ids: tuple[str, ...]) -> dict[str, AssetCriticality]:
        ...

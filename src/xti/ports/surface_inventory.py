"""Storage boundary for layered surface inventory classification."""

from typing import Protocol

from xti.domain.surface_inventory import SurfaceInventorySnapshot


class SurfaceInventoryRepository(Protocol):
    def snapshot(
        self, root_asset_id: str, root_asset_value: str, *,
        status: str | None, limit: int,
    ) -> SurfaceInventorySnapshot:
        ...

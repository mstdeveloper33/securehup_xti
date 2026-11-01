"""Storage boundary for one read-only surface freshness snapshot."""

from typing import Protocol

from xti.domain.surface_freshness import SurfaceFreshnessSnapshot


class SurfaceFreshnessRepository(Protocol):
    def snapshot(self, asset_id: str, asset_value: str) -> SurfaceFreshnessSnapshot:
        ...

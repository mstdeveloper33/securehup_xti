"""Persistence contract for already normalized domain assets."""

from typing import Protocol

from xti.domain.assets import Asset


class AssetRepository(Protocol):
    """A storage boundary; domain rules are owned by the application."""

    def add(self, domain: str) -> tuple[Asset, bool]:
        """Return the saved asset and whether this call created it."""
        ...

    def list(self) -> list[Asset]:
        """Return assets in stable value order."""
        ...

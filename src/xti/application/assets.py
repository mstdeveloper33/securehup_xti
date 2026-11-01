"""Asset use cases shared by the CLI and any future interface."""

from xti.domain.assets import Asset, normalize_domain
from xti.ports.assets import AssetRepository


class AssetService:
    """Apply domain validation before invoking the persistence contract."""

    def __init__(self, repository: AssetRepository) -> None:
        self.repository = repository

    def add(self, value: str) -> tuple[Asset, bool]:
        return self.repository.add(normalize_domain(value))

    def list(self) -> list[Asset]:
        return self.repository.list()

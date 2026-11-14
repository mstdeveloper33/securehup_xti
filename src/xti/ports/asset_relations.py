"""Read all stored evidence for one exact registered domain."""
from typing import Protocol
from xti.domain.asset_relations import AssetRelationsSnapshot


class AssetRelationsRepository(Protocol):
    def read(self, domain: str) -> AssetRelationsSnapshot: ...

"""Read-only boundary for the source-identified ATT&CK catalog."""

from typing import Protocol

from xti.domain.attack_catalog import AttackCatalogDetails, AttackCatalogPage, AttackCatalogStatus


class AttackCatalogRepository(Protocol):
    def status(self, *, run_limit: int = 20) -> AttackCatalogStatus:
        ...

    def search(
        self, query: str, *, kind: str | None = None, active_only: bool = True,
        limit: int = 50, offset: int = 0,
    ) -> AttackCatalogPage:
        ...

    def get(
        self, identifier: str, *, relationship_limit: int = 100,
        relationship_offset: int = 0, event_limit: int = 20,
    ) -> AttackCatalogDetails:
        ...

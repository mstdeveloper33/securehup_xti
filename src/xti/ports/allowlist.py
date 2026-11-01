"""Persistence boundary for exact-domain false-positive policy."""

from typing import Protocol, Sequence

from xti.domain.allowlist import AllowlistDetails, AllowlistEntry


class AllowlistRepository(Protocol):
    def activate(
        self, asset_id: str, asset_value: str, domain: str, reason: str,
        created_at: str, expires_at: str | None,
    ) -> tuple[AllowlistEntry, bool]:
        ...

    def revoke(self, entry_id: str, reason: str, created_at: str) -> AllowlistEntry:
        ...

    def list(
        self, *, active_only: bool = True, asset_id: str | None = None, limit: int = 100,
    ) -> tuple[AllowlistEntry, ...]:
        ...

    def get(self, entry_id: str) -> AllowlistDetails:
        ...

    def active_pairs(
        self, asset_ids: Sequence[str], at: str | None = None,
    ) -> frozenset[tuple[str, str]]:
        ...

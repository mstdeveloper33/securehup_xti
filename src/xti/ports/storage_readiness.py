"""Filesystem boundary for local storage readiness inspection."""

from typing import Protocol

from xti.domain.storage_readiness import StorageReadinessSnapshot


class StorageReadinessRepository(Protocol):
    def snapshot(self) -> StorageReadinessSnapshot:
        ...

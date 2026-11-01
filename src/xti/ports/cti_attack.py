"""Boundaries for the pinned MITRE ATT&CK source and atomic local sync."""

from typing import Protocol

from xti.domain.cti_attack import AttackSnapshot, AttackSyncResult


class AttackSource(Protocol):
    def fetch(self) -> AttackSnapshot:
        ...


class AttackSyncRepository(Protocol):
    def validate_attack_source(self) -> None:
        ...

    def sync_attack_snapshot(
        self, snapshot: AttackSnapshot, *, recorded_at: str,
    ) -> AttackSyncResult:
        ...

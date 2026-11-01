"""Explicit, bounded MITRE ATT&CK Enterprise synchronization."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.cti_attack import AttackSyncResult, validate_attack_snapshot
from xti.ports.cti_attack import AttackSource, AttackSyncRepository


class AttackSyncService:
    def __init__(
        self, repository: AttackSyncRepository, source: AttackSource, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("MITRE ATT&CK senkron zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def sync(self) -> AttackSyncResult:
        # Corrupt managed history must stop the network request, not get overwritten.
        self.repository.validate_attack_source()
        recorded_at = self._now()
        snapshot = validate_attack_snapshot(self.source.fetch())
        return self.repository.sync_attack_snapshot(
            snapshot, recorded_at=recorded_at,
        )

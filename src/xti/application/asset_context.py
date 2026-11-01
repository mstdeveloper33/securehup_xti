"""Use cases for explicit, human-owned asset business criticality."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.asset_context import (
    AssetCriticalityDetails,
    AssetCriticalityMutation,
    normalize_criticality_level,
    normalize_criticality_reason,
)
from xti.domain.assets import ValidationError, normalize_domain
from xti.ports.asset_context import AssetCriticalityRepository


class AssetCriticalityService:
    def __init__(
        self, repository: AssetCriticalityRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Varlık önemi kayıt zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def set(
        self, asset_value: str, *, level: str, reason: str,
    ) -> AssetCriticalityMutation:
        return self.repository.set(
            normalize_domain(asset_value), level=normalize_criticality_level(level),
            reason=normalize_criticality_reason(reason), recorded_at=self._now(),
        )

    def clear(self, asset_value: str, *, reason: str) -> AssetCriticalityMutation:
        return self.repository.clear(
            normalize_domain(asset_value), reason=normalize_criticality_reason(reason),
            recorded_at=self._now(),
        )

    def show(self, asset_value: str, *, event_limit: int = 50) -> AssetCriticalityDetails:
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("Varlık önemi geçmiş sınırı 1–100 arasında olmalı.")
        return self.repository.show(normalize_domain(asset_value), event_limit=event_limit)

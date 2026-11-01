"""Validated local IOC lifecycle; source claims never become automatic verdicts."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.cti_feeds import CERTPL_SOURCE, FEODO_SOURCE
from xti.domain.cti_indicators import (
    CtiIndicatorDetails,
    CtiIndicatorMutation,
    CtiIndicatorSummary,
    normalize_assertion_id,
    normalize_assertion_reason,
    normalize_confidence,
    normalize_cti_timestamp,
    normalize_indicator_description,
    normalize_indicator_id,
    normalize_indicator_type,
    normalize_indicator_value,
    normalize_source_name,
    normalize_source_reference,
    validate_validity_window,
)
from xti.ports.cti_indicators import CtiIndicatorRepository


_MANAGED_SOURCE_NAMES = {FEODO_SOURCE, CERTPL_SOURCE}


class CtiIndicatorService:
    def __init__(
        self, repository: CtiIndicatorRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("IOC kayıt zamanı geçersiz.")
        return value.astimezone(timezone.utc)

    def add(
        self, indicator_type: str, value: str, *, source_name: str,
        source_reference: str, confidence: int | str, description: str,
        valid_from: str | None = None, valid_until: str | None = None,
        observed_at: str | None = None,
    ) -> CtiIndicatorMutation:
        indicator_type = normalize_indicator_type(indicator_type)
        value = normalize_indicator_value(indicator_type, value)
        valid_from, valid_until = validate_validity_window(valid_from, valid_until)
        now = self._now()
        observed = (
            now.isoformat() if observed_at is None else
            normalize_cti_timestamp(observed_at, field="IOC gözlem zamanı")
        )
        if datetime.fromisoformat(observed) > now:
            raise ValidationError("IOC gözlem zamanı sistem saatinden ileride olamaz.")
        source_name = normalize_source_name(source_name)
        if source_name in _MANAGED_SOURCE_NAMES:
            raise ValidationError(
                "Bu IOC kaynak adı otomatik besleme tarafından yönetilir; "
                "elle kayıt için farklı bir kaynak adı kullanın."
            )
        return self.repository.add_assertion(
            indicator_type=indicator_type, value=value,
            source_name=source_name,
            source_reference=normalize_source_reference(source_reference),
            confidence=normalize_confidence(confidence), valid_from=valid_from,
            valid_until=valid_until,
            description=normalize_indicator_description(description),
            observed_at=observed, recorded_at=now.isoformat(),
        )

    def revoke(self, assertion_id: str, *, reason: str) -> CtiIndicatorMutation:
        return self.repository.revoke_assertion(
            normalize_assertion_id(assertion_id),
            reason=normalize_assertion_reason(reason),
            recorded_at=self._now().isoformat(),
        )

    def list(
        self, *, indicator_type: str | None = None, active_only: bool = True,
        limit: int = 50,
    ) -> tuple[CtiIndicatorSummary, ...]:
        if type(active_only) is not bool:
            raise ValidationError("IOC etkinlik filtresi geçersiz.")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("IOC liste sınırı 1–500 arasında olmalı.")
        return self.repository.list(
            indicator_type=(
                normalize_indicator_type(indicator_type)
                if indicator_type is not None else None
            ),
            active_only=active_only, checked_at=self._now().isoformat(), limit=limit,
        )

    @staticmethod
    def _limits(assertion_limit: int, event_limit: int) -> tuple[int, int]:
        if type(assertion_limit) is not int or not 1 <= assertion_limit <= 500:
            raise ValidationError("IOC kaynak iddiası görünüm sınırı 1–500 arasında olmalı.")
        if type(event_limit) is not int or not 1 <= event_limit <= 500:
            raise ValidationError("IOC geçmiş görünüm sınırı 1–500 arasında olmalı.")
        return assertion_limit, event_limit

    def show(
        self, indicator_id: str, *, assertion_limit: int = 50,
        event_limit: int = 100,
    ) -> CtiIndicatorDetails:
        assertion_limit, event_limit = self._limits(assertion_limit, event_limit)
        return self.repository.details(
            normalize_indicator_id(indicator_id), assertion_limit=assertion_limit,
            event_limit=event_limit,
        )

    def lookup(
        self, indicator_type: str, value: str, *, assertion_limit: int = 50,
        event_limit: int = 100,
    ) -> CtiIndicatorDetails:
        assertion_limit, event_limit = self._limits(assertion_limit, event_limit)
        indicator_type = normalize_indicator_type(indicator_type)
        return self.repository.lookup(
            indicator_type, normalize_indicator_value(indicator_type, value),
            assertion_limit=assertion_limit, event_limit=event_limit,
        )

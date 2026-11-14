"""Resolve explicit CTI context without collecting or creating relationships."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.cti_context import CtiContextReport, context_query
from xti.ports.cti_context import CtiContextRepository


class CtiContextService:
    def __init__(
        self, repository: CtiContextRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def show(
        self, *, indicator_type: str | None = None, value: str | None = None,
        entity_id: str | None = None, include_inactive: bool = False,
        offset: int = 0, limit: int = 50,
        source_offset: int = 0, source_limit: int = 20,
    ) -> CtiContextReport:
        query = context_query(
            indicator_type=indicator_type, value=value, entity_id=entity_id,
            include_inactive=include_inactive,
        )
        for start in (offset, source_offset):
            if type(start) is not int or not 0 <= start <= 1_000_000:
                raise ValidationError("CTI bağlamı sayfa başlangıcı 0–1000000 arasında olmalı.")
        for count in (limit, source_limit):
            if type(count) is not int or not 1 <= count <= 500:
                raise ValidationError("CTI bağlamı görünüm sınırı 1–500 arasında olmalı.")
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("CTI bağlamı zamanı saat dilimi bilgili olmalı.")
        return self.repository.read(
            query, checked_at=now.astimezone(timezone.utc).isoformat(),
            offset=offset, limit=limit, source_offset=source_offset, source_limit=source_limit,
        )

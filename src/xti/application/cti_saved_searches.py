"""Validated use cases for saved local CTI searches and explicit difference runs."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import (
    normalize_assertion_reason,
    normalize_indicator_type,
)
from xti.domain.cti_knowledge import (
    normalize_entity_type,
    normalize_search_kind,
    normalize_search_query,
    search_query_key,
)
from xti.domain.cti_saved_searches import (
    CtiSavedSearchDetails,
    CtiSavedSearchMutation,
    CtiSavedSearchRunReport,
    CtiSavedSearchSummary,
    normalize_saved_search_id,
    normalize_saved_search_name,
    saved_search_name_key,
)
from xti.ports.cti_saved_searches import CtiSavedSearchRepository


class CtiSavedSearchService:
    def __init__(
        self, repository: CtiSavedSearchRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Kayıtlı CTI arama zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int, *, field: str) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError(f"{field} 1–500 arasında olmalı.")
        return value

    def add(
        self, name: str, query: str, *, kind: str = "all",
        entity_type: str | None = None, indicator_type: str | None = None,
        active_only: bool = True,
    ) -> CtiSavedSearchMutation:
        name = normalize_saved_search_name(name)
        query = normalize_search_query(query)
        kind = normalize_search_kind(kind)
        if type(active_only) is not bool:
            raise ValidationError("Kayıtlı CTI arama geçmiş filtresi geçersiz.")
        if kind == "entity" and indicator_type is not None:
            raise ValidationError("Entity aramasında IOC türü filtresi kullanılamaz.")
        if kind == "indicator" and entity_type is not None:
            raise ValidationError("IOC aramasında CTI varlık türü filtresi kullanılamaz.")
        entity_type = normalize_entity_type(entity_type) if entity_type else None
        indicator_type = normalize_indicator_type(indicator_type) if indicator_type else None
        return self.repository.upsert(
            name_key=saved_search_name_key(name), display_name=name,
            query=query, query_key=search_query_key(query), kind=kind,
            entity_type=entity_type, indicator_type=indicator_type,
            active_only=active_only, recorded_at=self._now(),
        )

    def revoke(self, saved_search_id: str, *, reason: str) -> CtiSavedSearchMutation:
        return self.repository.revoke(
            normalize_saved_search_id(saved_search_id),
            reason=normalize_assertion_reason(reason), recorded_at=self._now(),
        )

    def list(
        self, *, active_only: bool = True, limit: int = 50,
    ) -> tuple[CtiSavedSearchSummary, ...]:
        if type(active_only) is not bool:
            raise ValidationError("Kayıtlı CTI arama etkinlik filtresi geçersiz.")
        return self.repository.list(
            active_only=active_only, limit=self._limit(limit, field="Liste sınırı"),
        )

    def list_window(
        self, *, active_only: bool = True, limit: int = 50,
    ) -> tuple[tuple[CtiSavedSearchSummary, ...], bool]:
        """Return a bounded deterministic window and explicit overflow signal."""
        if type(active_only) is not bool:
            raise ValidationError("Kayıtlı CTI arama etkinlik filtresi geçersiz.")
        limit = self._limit(limit, field="Liste sınırı")
        records = self.repository.list(active_only=active_only, limit=limit + 1)
        return records[:limit], len(records) > limit

    def show(
        self, saved_search_id: str, *, event_limit: int = 50, run_limit: int = 20,
    ) -> CtiSavedSearchDetails:
        return self.repository.details(
            normalize_saved_search_id(saved_search_id),
            event_limit=self._limit(event_limit, field="Olay sınırı"),
            run_limit=self._limit(run_limit, field="Çalışma sınırı"),
        )

    def run(
        self, saved_search_id: str, *, item_limit: int = 100,
    ) -> CtiSavedSearchRunReport:
        return self.repository.run(
            normalize_saved_search_id(saved_search_id), executed_at=self._now(),
            item_limit=self._limit(item_limit, field="Sonuç sınırı"),
        )

    def show_run(
        self, run_id: str, *, item_limit: int = 100,
    ) -> CtiSavedSearchRunReport:
        return self.repository.run_details(
            normalize_saved_search_id(run_id, field="CTI arama çalışma kimliği"),
            item_limit=self._limit(item_limit, field="Sonuç sınırı"),
        )

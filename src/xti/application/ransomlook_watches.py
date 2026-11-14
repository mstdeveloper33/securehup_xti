"""Validated local organization watches over stored RansomLook snapshots."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_assertion_reason
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.ransomlook_watches import (
    RansomLookWatchDetails,
    RansomLookWatchMutation,
    RansomLookWatchRunReport,
    RansomLookWatchSummary,
    normalize_ransomlook_watch_name,
    normalize_ransomlook_watch_query,
    ransomlook_watch_name_key,
    ransomlook_watch_query_key,
)
from xti.ports.ransomlook_ransomware import RansomLookClaimRepository
from xti.ports.ransomlook_watches import RansomLookWatchRepository


class RansomLookWatchService:
    def __init__(
        self, repository: RansomLookWatchRepository,
        claim_repository: RansomLookClaimRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.claim_repository = claim_repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("RansomLook izleme zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int, *, field: str) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError(f"{field} 1–500 arasında olmalı.")
        return value

    def add(
        self, name: str, query: str, *, kind: str,
        match_mode: str = "exact",
    ) -> RansomLookWatchMutation:
        if kind != "organization":
            raise ValidationError(
                "RansomLook domain bilgisi sağlamaz; yalnız organization izlenebilir."
            )
        name = normalize_ransomlook_watch_name(name)
        query = normalize_ransomlook_watch_query(query, match_mode=match_mode)
        return self.repository.upsert(
            name_key=ransomlook_watch_name_key(name), display_name=name,
            query=query, query_key=ransomlook_watch_query_key(query),
            match_mode=match_mode, recorded_at=self._now(),
        )

    def revoke(self, watch_id: str, *, reason: str) -> RansomLookWatchMutation:
        return self.repository.revoke(
            normalize_knowledge_id(watch_id, field="RansomLook izleme kimliği"),
            reason=normalize_assertion_reason(reason), recorded_at=self._now(),
        )

    def list(
        self, *, active_only: bool = True, limit: int = 50,
    ) -> tuple[RansomLookWatchSummary, ...]:
        if type(active_only) is not bool:
            raise ValidationError("RansomLook izleme etkinlik filtresi geçersiz.")
        return self.repository.list(
            active_only=active_only, limit=self._limit(limit, field="Liste sınırı"),
        )

    def show(
        self, watch_id: str, *, event_limit: int = 50, run_limit: int = 20,
    ) -> RansomLookWatchDetails:
        return self.repository.details(
            normalize_knowledge_id(watch_id, field="RansomLook izleme kimliği"),
            event_limit=self._limit(event_limit, field="Olay sınırı"),
            run_limit=self._limit(run_limit, field="Çalışma sınırı"),
        )

    def run(
        self, watch_id: str, *, item_limit: int = 100,
        expected_source_run_id: str | None = None,
        operation: CollectionOperationToken | None = None,
    ) -> RansomLookWatchRunReport:
        watch_id = normalize_knowledge_id(watch_id, field="RansomLook izleme kimliği")
        item_limit = self._limit(item_limit, field="Sonuç sınırı")
        expected = (
            normalize_knowledge_id(
                expected_source_run_id, field="beklenen RansomLook kaynak çalışma kimliği",
            )
            if expected_source_run_id is not None else None
        )
        snapshot = self.claim_repository.latest_snapshot()
        if expected is not None and snapshot.run.id != expected:
            raise ValidationError(
                "Son başarılı RansomLook kaynak snapshot'ı beklenen yenilemeyle "
                "eşleşmiyor; izleme çalıştırılmadı."
            )
        return self.repository.run(
            watch_id, snapshot,
            executed_at=self._now(), item_limit=item_limit,
            **({"operation": operation} if operation is not None else {}),
        )

    def show_run(
        self, run_id: str, *, item_limit: int = 100,
    ) -> RansomLookWatchRunReport:
        return self.repository.run_details(
            normalize_knowledge_id(run_id, field="RansomLook izleme çalışma kimliği"),
            item_limit=self._limit(item_limit, field="Sonuç sınırı"),
        )


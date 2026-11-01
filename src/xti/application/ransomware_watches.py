"""Validated local organization/domain watches over stored public claims."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_assertion_reason
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.ransomware_watches import (
    RansomwareWatchDetails,
    RansomwareWatchMutation,
    RansomwareWatchRunReport,
    RansomwareWatchSummary,
    normalize_ransomware_watch_name,
    normalize_ransomware_watch_query,
    ransomware_watch_name_key,
    ransomware_watch_query_key,
)
from xti.ports.ransomware_claims import RansomwareClaimRepository
from xti.ports.ransomware_watches import RansomwareWatchRepository


class RansomwareWatchService:
    def __init__(
        self, repository: RansomwareWatchRepository,
        claim_repository: RansomwareClaimRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.claim_repository = claim_repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Ransomware izleme zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int, *, field: str) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError(f"{field} 1–500 arasında olmalı.")
        return value

    def add(
        self, name: str, query: str, *, kind: str,
        match_mode: str = "exact",
    ) -> RansomwareWatchMutation:
        name = normalize_ransomware_watch_name(name)
        query = normalize_ransomware_watch_query(
            query, kind=kind, match_mode=match_mode,
        )
        return self.repository.upsert(
            name_key=ransomware_watch_name_key(name), display_name=name,
            kind=kind, query=query,
            query_key=ransomware_watch_query_key(query, kind=kind),
            match_mode=match_mode, recorded_at=self._now(),
        )

    def revoke(self, watch_id: str, *, reason: str) -> RansomwareWatchMutation:
        return self.repository.revoke(
            normalize_knowledge_id(watch_id, field="ransomware izleme kimliği"),
            reason=normalize_assertion_reason(reason), recorded_at=self._now(),
        )

    def list(
        self, *, active_only: bool = True, limit: int = 50,
    ) -> tuple[RansomwareWatchSummary, ...]:
        if type(active_only) is not bool:
            raise ValidationError("Ransomware izleme etkinlik filtresi geçersiz.")
        return self.repository.list(
            active_only=active_only, limit=self._limit(limit, field="Liste sınırı"),
        )

    def list_window(
        self, *, active_only: bool = True, limit: int = 50,
    ) -> tuple[tuple[RansomwareWatchSummary, ...], bool]:
        """Return a stable bounded window and signal any hidden active watch."""
        if type(active_only) is not bool:
            raise ValidationError("Ransomware izleme etkinlik filtresi geçersiz.")
        limit = self._limit(limit, field="Liste sınırı")
        records = self.repository.list(active_only=active_only, limit=limit + 1)
        return records[:limit], len(records) > limit

    def show(
        self, watch_id: str, *, event_limit: int = 50, run_limit: int = 20,
    ) -> RansomwareWatchDetails:
        return self.repository.details(
            normalize_knowledge_id(watch_id, field="ransomware izleme kimliği"),
            event_limit=self._limit(event_limit, field="Olay sınırı"),
            run_limit=self._limit(run_limit, field="Çalışma sınırı"),
        )

    def run(
        self, watch_id: str, *, item_limit: int = 100,
        expected_source_run_id: str | None = None,
    ) -> RansomwareWatchRunReport:
        watch_id = normalize_knowledge_id(
            watch_id, field="ransomware izleme kimliği",
        )
        item_limit = self._limit(item_limit, field="Sonuç sınırı")
        expected = (
            normalize_knowledge_id(
                expected_source_run_id,
                field="beklenen ransomware kaynak çalışma kimliği",
            )
            if expected_source_run_id is not None else None
        )
        snapshot = self.claim_repository.latest_snapshot()
        if expected is not None and snapshot.run.id != expected:
            raise ValidationError(
                "Son başarılı ransomware kaynak snapshot'ı beklenen yenilemeyle "
                "eşleşmiyor; izleme çalıştırılmadı."
            )
        return self.repository.run(
            watch_id, snapshot, executed_at=self._now(), item_limit=item_limit,
        )

    def show_run(self, run_id: str, *, item_limit: int = 100) -> RansomwareWatchRunReport:
        return self.repository.run_details(
            normalize_knowledge_id(run_id, field="ransomware izleme çalışma kimliği"),
            item_limit=self._limit(item_limit, field="Sonuç sınırı"),
        )

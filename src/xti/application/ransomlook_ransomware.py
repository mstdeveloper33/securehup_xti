"""Read and locally filter one bounded RansomLook recent-post snapshot."""

import unicodedata
from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.assets import ValidationError
from xti.domain.ransomlook_ransomware import (
    RansomLookClaim,
    RansomLookClaimHistoryStatus,
    RansomLookClaimReport,
    RansomLookClaimRunReport,
)
from xti.ports.discovery import SourceError
from xti.ports.ransomlook_ransomware import (
    RansomLookClaimRepository,
    RansomLookClaimSource,
)


def _query(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("Arama ifadesi metin olmalı.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if not 1 <= len(normalized) <= 200 or not all(char.isprintable() for char in normalized):
        raise ValidationError("Arama ifadesi 1–200 görünür karakter olmalı.")
    return normalized


def _rank(claim: RansomLookClaim, needle: str) -> int | None:
    values = (claim.victim.casefold(), claim.group.casefold())
    if any(value == needle for value in values):
        return 0
    if any(value.startswith(needle) for value in values):
        return 1
    if any(needle in value for value in values):
        return 2
    return None


class RansomLookClaimService:
    def __init__(self, source: RansomLookClaimSource) -> None:
        self._source = source

    def recent(self, query: str | None = None, *, limit: int = 20) -> RansomLookClaimReport:
        query = _query(query)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Ransomware iddiası görünüm sınırı 1–100 olmalı.")
        feed = self._source.fetch()
        needle = query.casefold() if query is not None else None
        ranked: list[tuple[int, int, RansomLookClaim]] = []
        for source_order, claim in enumerate(feed.claims):
            rank = 0 if needle is None else _rank(claim, needle)
            if rank is not None:
                ranked.append((rank, source_order, claim))
        ranked.sort(key=lambda item: (item[0], item[1]))
        ordered = [claim for _, _, claim in ranked]
        selected = tuple(ordered[:limit])
        return RansomLookClaimReport(
            source_name=feed.source_name,
            source_url=feed.source_url,
            fetched_at=feed.fetched_at,
            window_days=feed.window_days,
            source_record_count=feed.source_record_count,
            content_sha256=feed.content_sha256,
            license=feed.license,
            query=query,
            matched_count=len(ordered),
            displayed_count=len(selected),
            has_more=len(ordered) > len(selected),
            claims=selected,
            notes=(
                "Kayıtlar ransomware gruplarının yayımladığı doğrulanmamış iddialardır.",
                "Kaynak güncel/kaldırılmış üyelik durumu, ülke, sektör veya domain sağlamaz; XTI bunları uydurmaz.",
                "XTI yalnız RansomLook HTTPS API'sine bağlanır; Tor veya leak-site adresi açmaz.",
                "Bu önizleme veritabanına yazmaz ve mevcut ThreatCluster geçmişiyle kayıt birleştirmez.",
            ),
        )


class RansomLookClaimHistoryService:
    """Explicitly refresh and inspect source-isolated RansomLook history."""

    def __init__(
        self, repository: RansomLookClaimRepository,
        source: RansomLookClaimSource | None = None, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValidationError("RansomLook çalışma zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int, *, maximum: int, field: str) -> int:
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValidationError(f"{field} 1–{maximum} arasında olmalı.")
        return value

    def refresh(
        self, *, item_limit: int = 100, operation: CollectionOperationToken | None = None,
    ) -> RansomLookClaimRunReport:
        item_limit = self._limit(item_limit, maximum=500, field="Değişiklik görünüm sınırı")
        if self.source is None:
            raise ValidationError("RansomLook kaynağı yapılandırılmamış.")
        started_at = self._now()
        try:
            feed = self.source.fetch()
        except SourceError as error:
            run = self.repository.record_failure(
                started_at=started_at, finished_at=self._now(), error=str(error),
                **({"operation": operation} if operation is not None else {}),
            )
            return RansomLookClaimRunReport(
                run=run, items=(), total_item_count=0, is_baseline=False,
            )
        return self.repository.apply(
            feed, started_at=started_at, finished_at=self._now(),
            item_limit=item_limit,
            **({"operation": operation} if operation is not None else {}),
        )

    def status(self, *, run_limit: int = 10) -> RansomLookClaimHistoryStatus:
        run_limit = self._limit(run_limit, maximum=100, field="Geçmiş sınırı")
        return self.repository.status(run_limit=run_limit)

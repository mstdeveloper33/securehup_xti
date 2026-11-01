"""Read and locally filter one bounded ransomware claim snapshot."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.ransomware_claims import (
    RansomwareClaim,
    RansomwareClaimHistoryStatus,
    RansomwareClaimReport,
    RansomwareClaimRunReport,
)
from xti.ports.discovery import SourceError
from xti.ports.ransomware_claims import (
    RansomwareClaimRepository,
    RansomwareClaimSource,
)


_STATUSES = {"all", "listed", "delisted"}


def _query(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError("Arama ifadesi metin olmalı.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if not 1 <= len(normalized) <= 200 or not all(char.isprintable() for char in normalized):
        raise ValidationError("Arama ifadesi 1–200 görünür karakter olmalı.")
    return normalized


def _search_values(claim: RansomwareClaim) -> tuple[str, ...]:
    return tuple(
        value.casefold()
        for value in (
            claim.victim,
            claim.website,
            claim.group,
            claim.country,
            claim.sector,
        )
        if value
    )


def _rank(claim: RansomwareClaim, needle: str) -> int | None:
    values = _search_values(claim)
    if any(value == needle for value in values):
        return 0
    if any(value.startswith(needle) for value in values):
        return 1
    if any(needle in value for value in values):
        return 2
    return None


class RansomwareClaimService:
    def __init__(self, source: RansomwareClaimSource) -> None:
        self._source = source

    def recent(
        self, query: str | None = None, *, status: str = "all", limit: int = 20,
    ) -> RansomwareClaimReport:
        query = _query(query)
        if not isinstance(status, str) or status not in _STATUSES:
            raise ValidationError("Ransomware iddiası durum filtresi geçersiz.")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Ransomware iddiası görünüm sınırı 1–100 olmalı.")

        feed = self._source.fetch()
        needle = query.casefold() if query is not None else None
        ranked: list[tuple[int, int, RansomwareClaim]] = []
        for source_order, claim in enumerate(feed.claims):
            if status != "all" and claim.status != status:
                continue
            rank = 0 if needle is None else _rank(claim, needle)
            if rank is not None:
                ranked.append((rank, source_order, claim))
        ranked.sort(key=lambda item: (item[0], item[1]))
        ordered = [claim for _, _, claim in ranked]

        selected = tuple(ordered[:limit])
        notes = (
            "Kayıtlar saldırgan veya şantaj gruplarının yayımladığı iddialardır; "
            "doğrulanmış ihlal değildir.",
            "XTI Tor ağına veya leak-site adreslerine bağlanmaz ve ham paylaşım metnini almaz.",
            "Sonuç yalnız bu kaynağın belirtilen zaman penceresidir; eşleşme olmaması güvenli "
            "olunduğunu ya da iddia bulunmadığını kanıtlamaz.",
        )
        return RansomwareClaimReport(
            source_name=feed.source_name,
            source_url=feed.source_url,
            fetched_at=feed.fetched_at,
            generated_at=feed.generated_at,
            window_days=feed.window_days,
            source_record_count=feed.source_record_count,
            content_sha256=feed.content_sha256,
            license=feed.license,
            query=query,
            status_filter=status,
            matched_count=len(ordered),
            displayed_count=len(selected),
            has_more=len(ordered) > len(selected),
            claims=selected,
            notes=notes,
        )


class RansomwareClaimHistoryService:
    """Explicitly refresh and inspect durable complete-snapshot history."""

    def __init__(
        self, repository: RansomwareClaimRepository,
        source: RansomwareClaimSource | None = None, *,
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
            raise ValidationError("Ransomware iddiası çalışma zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int, *, maximum: int, field: str) -> int:
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValidationError(f"{field} 1–{maximum} arasında olmalı.")
        return value

    def refresh(self, *, item_limit: int = 100) -> RansomwareClaimRunReport:
        item_limit = self._limit(item_limit, maximum=500, field="Değişiklik görünüm sınırı")
        if self.source is None:
            raise ValidationError("Ransomware iddiası kaynağı yapılandırılmamış.")
        started_at = self._now()
        try:
            feed = self.source.fetch()
        except SourceError as error:
            run = self.repository.record_failure(
                started_at=started_at, finished_at=self._now(), error=str(error),
            )
            return RansomwareClaimRunReport(
                run=run, items=(), total_item_count=0, is_baseline=False,
            )
        return self.repository.apply(
            feed, started_at=started_at, finished_at=self._now(),
            item_limit=item_limit,
        )

    def status(self, *, run_limit: int = 10) -> RansomwareClaimHistoryStatus:
        run_limit = self._limit(run_limit, maximum=100, field="Geçmiş sınırı")
        return self.repository.status(run_limit=run_limit)

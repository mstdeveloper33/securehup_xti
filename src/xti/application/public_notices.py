"""Explicit catalog refresh and entirely local public incident lookup."""

from collections.abc import Callable
from datetime import datetime, timezone
import unicodedata
from uuid import UUID

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.public_notices import (
    PublicNoticeDetail, PublicNoticeRefreshReport, PublicNoticeSearchReport,
    PublicNoticeStatus, notice_id,
)
from xti.ports.discovery import SourceError
from xti.ports.public_notices import PublicNoticeRepository, PublicNoticeSource


class PublicNoticeService:
    def __init__(self, repository: PublicNoticeRepository, source: PublicNoticeSource | None = None,
                 *, clock: Callable[[], datetime] | None = None) -> None:
        self.repository = repository
        self.source = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Kamu olay kataloğu çalışma zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int, maximum: int = 100) -> int:
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValidationError(f"Kamu olay görünüm sınırı 1–{maximum} olmalı.")
        return value

    def refresh(self, *, item_limit: int = 20) -> PublicNoticeRefreshReport:
        self._limit(item_limit, 500)
        if self.source is None:
            raise ValidationError("Kamu olay kaynağı yapılandırılmamış.")
        self.repository.validate()
        started_at = self._now()
        try:
            feed = self.source.fetch()
        except SourceError as error:
            run = self.repository.record_failure(started_at=started_at, finished_at=self._now(), error=str(error))
            return PublicNoticeRefreshReport(run, (), 0, False)
        return self.repository.apply(feed, started_at=started_at, finished_at=self._now(), item_limit=item_limit)

    @staticmethod
    def _offset(value: int) -> int:
        if type(value) is not int or not 0 <= value <= 1_000_000:
            raise ValidationError("Kamu olay görünüm başlangıcı 0–1000000 olmalı.")
        return value

    def status(self, *, run_limit: int = 10, offset: int = 0) -> PublicNoticeStatus:
        return self.repository.status(run_limit=self._limit(run_limit), offset=self._offset(offset))

    def run_show(self, identifier: str, *, item_limit: int = 20, offset: int = 0) -> PublicNoticeRefreshReport:
        try:
            if str(UUID(identifier)) != identifier:
                raise ValueError("Noncanonical UUID")
        except (AttributeError, TypeError, ValueError) as error:
            raise ValidationError("Kamu olay çalışma kimliği geçersiz.") from error
        return self.repository.run_show(identifier, item_limit=self._limit(item_limit, 500), offset=self._offset(offset))

    def search(self, query: str | None = None, *, domain: str | None = None,
               limit: int = 20, offset: int = 0) -> PublicNoticeSearchReport:
        self._limit(limit)
        self._offset(offset)
        if query is not None:
            if not isinstance(query, str) or any(not ch.isprintable() for ch in query):
                raise ValidationError("Kamu olay araması görünür metin olmalı.")
            query = " ".join(unicodedata.normalize("NFKC", query).strip().split())
            if not 1 <= len(query) <= 200:
                raise ValidationError("Kamu olay araması 1–200 karakter olmalı.")
        if domain is not None:
            domain = normalize_domain(domain)
        snapshot = self.repository.latest_snapshot()
        if snapshot.latest_complete_run is None or snapshot.latest_run is None:
            raise ValidationError("Henüz başarılı kamu olay kataloğu yok. Önce './xti notices refresh' çalıştırın.")
        needle = query.casefold() if query is not None else None
        selected = []
        for record in snapshot.notices:
            if domain is not None and record.domain != domain:
                continue
            values = tuple(value.casefold() for value in (record.id, record.title, record.domain) if value)
            if needle is None or any(needle in value for value in values):
                selected.append(record)
        selected.sort(key=lambda record: (record.modified_at, record.added_at, record.id), reverse=True)
        shown = tuple(selected[offset:offset + limit])
        return PublicNoticeSearchReport(query, domain, snapshot.latest_run, snapshot.latest_complete_run,
                                        len(selected), len(shown), len(selected) > offset + len(shown), shown, offset)

    def show(self, identifier: str) -> PublicNoticeDetail:
        identifier = notice_id(identifier)
        snapshot = self.repository.latest_snapshot()
        if snapshot.latest_complete_run is None or snapshot.latest_run is None:
            raise ValidationError("Henüz başarılı kamu olay kataloğu yok. Önce './xti notices refresh' çalıştırın.")
        for record in snapshot.notices:
            if record.id == identifier:
                return PublicNoticeDetail(record, snapshot.latest_run, snapshot.latest_complete_run)
        raise ValidationError("Bu kamu olay kimliği son başarılı katalogda bulunamadı.")

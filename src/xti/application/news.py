"""Explicit publisher refresh and local news lookup; collection is separate from watches."""

from datetime import datetime, timezone
from contextlib import nullcontext
import re
from uuid import UUID

from xti.domain.assets import ValidationError
from xti.domain.collection_history import CollectionOperationToken
from xti.domain.global_search import global_match, normalize_global_query
from xti.domain.news import (
    NEWS_SOURCES, NewsDetail, NewsRefreshReport, NewsSearchReport, news_source,
    validate_feed,
)
from xti.ports.discovery import SourceError
from xti.ports.jobs import ExecutionLock
from xti.ports.news import NewsRepository, NewsSource


class NewsService:
    def __init__(self, repository: NewsRepository, source: NewsSource | None = None,
                 lock: ExecutionLock | None = None, *, clock=None):
        self.repository, self.source, self.lock = repository, source, lock
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def sources():
        return NEWS_SOURCES

    def _now(self):
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Haber toplama zamanı saat dilimi içermeli.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _page(offset, limit):
        if (type(offset) is not int or not 0 <= offset <= 1_000_000
                or type(limit) is not int or not 1 <= limit <= 500):
            raise ValidationError("Haber görünüm başlangıcı 0–1.000.000, sınırı 1–500 olmalı.")

    def refresh(self, source_key: str, *, limit=20, operation: CollectionOperationToken | None = None):
        news_source(source_key)
        self._page(0, limit)
        if self.source is None or self.lock is None:
            raise ValidationError("Haber toplama kaynağı ve yazıcı kilidi yapılandırılmalı.")
        # Recorded collection owns the shared lock. Its durable operation must
        # be checked before transport, and again in the source commit.
        with self.lock.acquire() if operation is None else nullcontext():
            self.repository.validate()
            if operation is not None:
                self.repository.validate_operation(source_key, operation)
            kwargs = {"operation": operation} if operation is not None else {}
            started_at = self._now()
            try:
                feed = self.source.fetch(source_key)
                try:
                    validate_feed(feed)
                    if feed.source_key != source_key:
                        raise ValidationError("Haber yanıtı seçilen kaynağa ait değil.")
                except ValidationError as error:
                    raise SourceError("Haber kaynağından geçersiz kanıt alındı; önceki haberler korunur.") from error
            except SourceError as error:
                run = self.repository.record_failure(source_key, started_at=started_at,
                    finished_at=self._now(), error=str(error), **kwargs)
                return NewsRefreshReport(run, (), 0)
            return self.repository.apply(feed, started_at=started_at, finished_at=self._now(), limit=limit, **kwargs)

    def list(self, query=None, *, source_key=None, offset=0, limit=20):
        self._page(offset, limit)
        if source_key is not None:
            news_source(source_key)
        if query is not None:
            query = normalize_global_query(query)
        catalog = self.repository.catalog()
        records = []
        for record in catalog.articles:
            article = record.article
            if source_key is not None and article.source_key != source_key:
                continue
            if query is not None and global_match(query, (
                ("title", article.title), ("summary", article.summary), ("url", article.url),
                ("source_entry_id", article.source_entry_id),
            )) is None:
                continue
            records.append(record)
        records.sort(key=lambda r: (r.article.published_at or r.first_seen_at, r.article.id), reverse=True)
        sources = tuple(s for s in catalog.sources if source_key is None or s.source.key == source_key)
        shown = tuple(records[offset:offset + limit])
        return NewsSearchReport(query, source_key, shown, sources, len(records), offset,
                                offset + len(shown) < len(records))

    def show(self, identifier):
        if not isinstance(identifier, str) or re.fullmatch(r"[a-f0-9]{64}", identifier) is None:
            raise ValidationError("Haber kimliği 64 karakterlik içerik dışı kayıt kimliği olmalı.")
        catalog = self.repository.catalog()
        for record in catalog.articles:
            if record.article.id == identifier:
                source = next(s for s in catalog.sources if s.source.key == record.article.source_key)
                return NewsDetail(record, source)
        raise ValidationError("Bu haber kimliği kayıtlı değil.")

    def status(self, *, source_key=None, offset=0, limit=20):
        self._page(offset, limit)
        if source_key is not None:
            news_source(source_key)
        return self.repository.status(source_key=source_key, offset=offset, limit=limit)

    def run_show(self, identifier, *, offset=0, limit=20):
        self._page(offset, limit)
        try:
            if str(UUID(identifier)) != identifier:
                raise ValueError("Noncanonical UUID")
        except (AttributeError, TypeError, ValueError) as error:
            raise ValidationError("Haber çalışma kimliği geçersiz.") from error
        return self.repository.run_show(identifier, offset=offset, limit=limit)

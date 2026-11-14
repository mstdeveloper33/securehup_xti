"""Validate one search request without source collection or mutation."""
from collections.abc import Callable
from datetime import datetime, timezone
from xti.domain.assets import ValidationError
from xti.domain.global_search import normalize_global_query, normalize_global_kinds
from xti.ports.global_search import GlobalSearchRepository


class GlobalSearchService:
    def __init__(self, repository: GlobalSearchRepository, *, clock: Callable[[], datetime] | None = None):
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def search(self, query: str, *, kinds=None, include_inactive=False, offset=0, limit=50):
        query, kinds = normalize_global_query(query), normalize_global_kinds(kinds)
        if (type(include_inactive) is not bool or type(offset) is not int or not 0 <= offset <= 1_000_000
                or type(limit) is not int or not 1 <= limit <= 500):
            raise ValidationError('Arama başlangıcı 0–1.000.000, görünüm sınırı 1–500 arasında olmalı.')
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError('Arama zamanı saat dilimi bilgili olmalı.')
        return self.repository.search(query, kinds=kinds, include_inactive=include_inactive,
            checked_at=now.astimezone(timezone.utc).isoformat(), offset=offset, limit=limit)

"""Manage saved workspace searches while leaving collection to existing sources."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.global_search import normalize_global_kinds, normalize_global_query
from xti.domain.global_saved_searches import watch_id, watch_name, watch_reason
from xti.ports.global_saved_searches import GlobalSavedSearchRepository
from xti.ports.jobs import ExecutionLock


class GlobalSavedSearchService:
    def __init__(self, repository: GlobalSavedSearchRepository, lock: ExecutionLock, *,
                 clock: Callable[[], datetime] | None = None):
        self.repository, self.lock = repository, lock
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self):
        value = self.clock()
        try:
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Timezone required")
            return value.astimezone(timezone.utc).isoformat()
        except (ValueError, OverflowError) as error:
            raise ValidationError("Kayıtlı arama zamanı saat dilimi bilgili olmalı.") from error

    @staticmethod
    def _window(offset, limit):
        if (type(offset) is not int or not 0 <= offset <= 1_000_000
                or type(limit) is not int or not 1 <= limit <= 500):
            raise ValidationError("Görünüm başlangıcı 0–1.000.000, sınırı 1–500 olmalı.")

    def add(self, name, query, *, kinds=None, include_inactive=False):
        name, query, kinds = watch_name(name), normalize_global_query(query), normalize_global_kinds(kinds)
        if type(include_inactive) is not bool:
            raise ValidationError("Geçmiş kayıt filtresi doğru/yanlış olmalı.")
        with self.lock.acquire():
            at = self._now()
            return self.repository.upsert(name_key=name.casefold(), display_name=name, query=query,
                                          kinds=kinds, include_inactive=include_inactive, recorded_at=at)

    def disable(self, search_id, *, reason):
        search_id, reason = watch_id(search_id), watch_reason(reason)
        with self.lock.acquire():
            at = self._now()
            return self.repository.disable(search_id, reason=reason, recorded_at=at)

    def list(self, *, active_only=True, offset=0, limit=50):
        self._window(offset, limit)
        if type(active_only) is not bool:
            raise ValidationError("Etkin arama filtresi doğru/yanlış olmalı.")
        return self.repository.list(active_only=active_only, offset=offset, limit=limit)

    def show(self, search_id, *, event_offset=0, event_limit=50, run_offset=0, run_limit=20):
        search_id = watch_id(search_id)
        self._window(event_offset, event_limit)
        self._window(run_offset, run_limit)
        return self.repository.details(search_id, event_offset=event_offset, event_limit=event_limit,
                                       run_offset=run_offset, run_limit=run_limit)

    def run(self, search_id, *, offset=0, limit=50):
        search_id = watch_id(search_id)
        self._window(offset, limit)
        with self.lock.acquire():
            at = self._now()
            return self.repository.run(search_id, executed_at=at, offset=offset, limit=limit)

    def show_run(self, run_id, *, offset=0, limit=50):
        run_id = watch_id(run_id)
        self._window(offset, limit)
        return self.repository.run_details(run_id, offset=offset, limit=limit)

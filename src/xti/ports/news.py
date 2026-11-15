"""Small news transport and persistence boundaries."""

from typing import Protocol

from xti.domain.news import NewsCatalog, NewsFeed, NewsRefreshReport, NewsRun, NewsStatusReport
from xti.domain.collection_history import CollectionOperationToken


class NewsSource(Protocol):
    def fetch(self, source_key: str) -> NewsFeed: ...


class NewsRepository(Protocol):
    def validate(self) -> None: ...

    def validate_operation(self, source_key: str, operation: CollectionOperationToken) -> None: ...

    def apply(self, feed: NewsFeed, *, started_at: str, finished_at: str,
              limit: int = 20, offset: int = 0,
              operation: CollectionOperationToken | None = None) -> NewsRefreshReport: ...

    def record_failure(self, source_key: str, *, started_at: str, finished_at: str,
                       error: str, operation: CollectionOperationToken | None = None) -> NewsRun: ...

    def catalog(self) -> NewsCatalog: ...

    def status(self, *, source_key: str | None = None, limit: int = 20,
               offset: int = 0) -> NewsStatusReport: ...

    def run_show(self, identifier: str, *, limit: int = 20, offset: int = 0) -> NewsRefreshReport: ...

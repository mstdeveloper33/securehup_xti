"""Local saved-search selection and atomic news-evidence notification boundary."""

from typing import Protocol

from xti.domain.collection import CollectionWatchTarget
from xti.domain.collection_history import CollectionOperationToken
from xti.domain.global_saved_searches import GlobalSavedSearchRunReport


class CollectionNewsSearches(Protocol):
    def plan(self, search_ids: tuple[str, ...]) -> tuple[CollectionWatchTarget, ...]: ...

    def ready(self, operation: CollectionOperationToken) -> bool: ...

    def run(self, target: CollectionWatchTarget, *, operation: CollectionOperationToken,
            executed_at: str, limit: int = 100) -> GlobalSavedSearchRunReport: ...

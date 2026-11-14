"""Read-only personal search over already stored evidence."""
from typing import Protocol
from xti.domain.global_search import GlobalSearchReport


class GlobalSearchRepository(Protocol):
    def search(self, query: str, *, kinds: tuple[str, ...], include_inactive: bool,
               checked_at: str, offset: int, limit: int) -> GlobalSearchReport: ...

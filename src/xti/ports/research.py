"""Read-only bounded neighborhood within one selected workspace snapshot."""

from typing import ContextManager, Protocol
from xti.domain.research import Key, ResearchEdge, ResearchNode, ResearchQuery
from xti.domain.warninglists import WarninglistState


class ResearchReader(Protocol):
    limitations: set[str]
    coverage: list[dict]
    warninglists: tuple[WarninglistState, ...]

    def node(self, key: Key) -> ResearchNode: ...
    def neighbors(self, key: Key) -> tuple[ResearchEdge, ...]: ...


class ResearchRepository(Protocol):
    def open(self, query: ResearchQuery, checked_at: str) -> ContextManager[ResearchReader]: ...

"""Boundary to a public domain discovery source."""

from typing import Protocol

from xti.domain.discovery import SourceBatch


class SourceError(Exception):
    """The provider could not supply a bounded, valid response."""


class DomainSource(Protocol):
    provider: str

    def search_url(self, pattern: str) -> str:
        ...

    def search(self, pattern: str) -> SourceBatch:
        ...

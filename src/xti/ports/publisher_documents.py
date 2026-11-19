"""Optional publisher acquisition; the application never handles HTTP or PDF internals."""
from typing import Protocol
from xti.domain.publisher_documents import FetchedDocument


class PublisherDocumentSource(Protocol):
    def fetch(self, provider: str, url: str) -> FetchedDocument: ...

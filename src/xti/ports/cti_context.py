"""Read one exact local CTI neighborhood under a consistent snapshot."""

from typing import Protocol

from xti.domain.cti_context import CtiContextQuery, CtiContextReport


class CtiContextRepository(Protocol):
    def read(
        self, query: CtiContextQuery, *, checked_at: str, offset: int,
        limit: int, source_offset: int, source_limit: int,
    ) -> CtiContextReport: ...

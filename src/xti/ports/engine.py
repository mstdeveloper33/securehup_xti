"""Explicit stored-record detail boundary used by the engine read service."""

from typing import Protocol
from xti.domain.engine import EngineRecordReference


class EngineRecordRepository(Protocol):
    def get(self, reference: EngineRecordReference, *, offset: int = 0, limit: int = 50) -> dict: ...

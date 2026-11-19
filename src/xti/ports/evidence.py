"""Audited workspace read and atomic evidence commands."""
from typing import Protocol


class EvidenceRepository(Protocol):
    def read(self, operation: str, options: dict, at: str) -> dict: ...
    def mutate(self, operation: str, options: dict, at: str) -> dict: ...

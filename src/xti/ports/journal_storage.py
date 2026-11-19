from typing import Protocol


class JournalStorageRepository(Protocol):
    def execute(self, operation: str, options: dict, at: str) -> dict: ...

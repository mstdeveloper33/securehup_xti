"""A monitor invokes the normal budgeted group operation without overriding it."""

from typing import Protocol


class MentionGroupRunner(Protocol):
    def run(self, group_id: str, *, request_id: str | None = None) -> dict: ...

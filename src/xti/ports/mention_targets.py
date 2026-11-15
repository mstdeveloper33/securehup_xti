"""Read an explicitly selected local entity before a paid external search."""

from typing import Protocol

from xti.domain.mentions import MentionTarget


class MentionTargetRepository(Protocol):
    def resolve(self, kind: str, identifier: str) -> MentionTarget: ...

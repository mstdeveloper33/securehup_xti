"""A coherent read of audited public source evidence and existing decisions."""

from typing import Protocol

from xti.domain.event_candidates import EventCandidateSnapshot


class EventCandidateRepository(Protocol):
    def read(self) -> EventCandidateSnapshot: ...

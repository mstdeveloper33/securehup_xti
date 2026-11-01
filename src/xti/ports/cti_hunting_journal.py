"""Persistence boundary for saved CTI search tags and analyst notes."""

from typing import Protocol

from xti.domain.cti_hunting_journal import (
    CtiHuntingJournal,
    CtiHuntingNote,
    CtiHuntingTagMutation,
)


class CtiHuntingJournalRepository(Protocol):
    def add_tag(self, **values) -> CtiHuntingTagMutation:
        ...

    def remove_tag(self, **values) -> CtiHuntingTagMutation:
        ...

    def add_note(self, **values) -> CtiHuntingNote:
        ...

    def journal(
        self, saved_search_id: str, *, note_limit: int, event_limit: int,
    ) -> CtiHuntingJournal:
        ...

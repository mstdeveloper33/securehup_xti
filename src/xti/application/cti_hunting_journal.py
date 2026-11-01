"""Validated use cases for saved-search classification and analyst history."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.cti_hunting_journal import (
    CtiHuntingJournal,
    CtiHuntingNote,
    CtiHuntingTagMutation,
    hunting_tag_key,
    normalize_hunting_note_body,
    normalize_hunting_note_kind,
    normalize_hunting_tag,
)
from xti.domain.cti_saved_searches import normalize_saved_search_id
from xti.ports.cti_hunting_journal import CtiHuntingJournalRepository


class CtiHuntingJournalService:
    def __init__(
        self, repository: CtiHuntingJournalRepository, *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("CTI avcılık defteri zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int, *, field: str) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError(f"{field} 1–500 arasında olmalı.")
        return value

    def add_tag(self, saved_search_id: str, tag: str) -> CtiHuntingTagMutation:
        tag = normalize_hunting_tag(tag)
        return self.repository.add_tag(
            saved_search_id=normalize_saved_search_id(saved_search_id),
            tag_key=hunting_tag_key(tag), display_tag=tag, recorded_at=self._now(),
        )

    def remove_tag(self, saved_search_id: str, tag: str) -> CtiHuntingTagMutation:
        tag = normalize_hunting_tag(tag)
        return self.repository.remove_tag(
            saved_search_id=normalize_saved_search_id(saved_search_id),
            tag_key=hunting_tag_key(tag), recorded_at=self._now(),
        )

    def add_note(
        self, saved_search_id: str, body: str, *, note_kind: str = "observation",
        run_id: str | None = None,
    ) -> CtiHuntingNote:
        return self.repository.add_note(
            saved_search_id=normalize_saved_search_id(saved_search_id),
            run_id=(
                normalize_saved_search_id(run_id, field="CTI arama çalışma kimliği")
                if run_id is not None else None
            ),
            note_kind=normalize_hunting_note_kind(note_kind),
            body=normalize_hunting_note_body(body), recorded_at=self._now(),
        )

    def journal(
        self, saved_search_id: str, *, note_limit: int = 50, event_limit: int = 100,
    ) -> CtiHuntingJournal:
        return self.repository.journal(
            normalize_saved_search_id(saved_search_id),
            note_limit=self._limit(note_limit, field="Not sınırı"),
            event_limit=self._limit(event_limit, field="Etiket olayı sınırı"),
        )

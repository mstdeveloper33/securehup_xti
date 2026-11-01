"""Append-only analyst tags and notes for durable CTI search investigations."""

from dataclasses import dataclass
import unicodedata

from xti.domain.assets import ValidationError
from xti.domain.cti_saved_searches import CtiSavedSearch


HUNTING_TAG_ACTIONS = {"added", "updated", "reactivated", "removed"}
HUNTING_NOTE_KINDS = {"observation", "hypothesis", "conclusion", "follow-up"}
_TAG_PUNCTUATION = frozenset("-_.:/")


def normalize_hunting_tag(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("CTI avcılık etiketi gerekli.")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if (
        not 2 <= len(normalized) <= 40
        or not any(character.isalnum() for character in normalized)
        or any(
            not character.isalnum() and character not in _TAG_PUNCTUATION
            for character in normalized
        )
    ):
        raise ValidationError(
            "CTI avcılık etiketi 2–40 harf/rakam veya - _ . : / karakterinden oluşmalı."
        )
    return normalized


def hunting_tag_key(value: str) -> str:
    return normalize_hunting_tag(value).casefold()


def normalize_hunting_note_kind(value: str) -> str:
    if not isinstance(value, str) or value not in HUNTING_NOTE_KINDS:
        raise ValidationError("CTI avcılık notu türü geçersiz.")
    return value


def normalize_hunting_note_body(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("CTI avcılık notu gerekli.")
    normalized = unicodedata.normalize("NFKC", value)
    if any(not character.isprintable() for character in normalized):
        raise ValidationError("CTI avcılık notu güvenli yazdırılabilir metin olmalı.")
    normalized = " ".join(normalized.strip().split())
    if not 2 <= len(normalized) <= 2000:
        raise ValidationError("CTI avcılık notu 2–2000 karakter arasında olmalı.")
    return normalized


@dataclass(frozen=True, slots=True)
class CtiHuntingTag:
    saved_search_id: str
    tag_key: str
    display_tag: str
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CtiHuntingTagEvent:
    sequence: int
    id: str
    saved_search_id: str
    tag_key: str
    display_tag: str
    action: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class CtiHuntingTagMutation:
    action: str
    tag: CtiHuntingTag


@dataclass(frozen=True, slots=True)
class CtiHuntingNote:
    sequence: int
    id: str
    saved_search_id: str
    run_id: str | None
    note_kind: str
    body: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class CtiHuntingJournal:
    saved_search: CtiSavedSearch
    tags: tuple[CtiHuntingTag, ...]
    tag_events: tuple[CtiHuntingTagEvent, ...]
    notes: tuple[CtiHuntingNote, ...]
    total_tag_count: int
    total_tag_event_count: int
    total_note_count: int

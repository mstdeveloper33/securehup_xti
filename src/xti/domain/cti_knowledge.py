"""Source-preserving CTI entities and explicit graph relationships."""

from dataclasses import dataclass
import json
import unicodedata
from uuid import UUID

from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import (
    normalize_confidence,
    normalize_cti_timestamp,
    normalize_indicator_description,
    normalize_source_name,
    normalize_source_reference,
)


ENTITY_TYPES = ("threat-actor", "campaign", "malware", "report")
RELATIONSHIP_TYPES = (
    "attributed-to", "uses", "targets", "delivers", "communicates-with",
    "indicates", "related-to", "reports-on",
)
TARGET_KINDS = ("entity", "indicator")
KNOWLEDGE_ACTIONS = {"added", "observed", "updated", "reactivated", "revoked"}
SEARCH_KINDS = ("all", "entity", "indicator")
SEARCH_MATCH_TYPES = ("exact", "prefix", "contains")


def _safe_name(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} gerekli.")
    normalized = unicodedata.normalize("NFKC", value)
    if any(not character.isprintable() for character in normalized):
        raise ValidationError(f"{field} 2–200 güvenli karakter arasında olmalı.")
    normalized = " ".join(normalized.strip().split())
    if not 2 <= len(normalized) <= 200:
        raise ValidationError(f"{field} 2–200 güvenli karakter arasında olmalı.")
    return normalized


def normalize_entity_type(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("CTI varlık türü gerekli.")
    normalized = value.strip().lower()
    if normalized not in ENTITY_TYPES:
        raise ValidationError(
            "CTI varlık türü threat-actor, campaign, malware veya report olmalı."
        )
    return normalized


def normalize_entity_name(value: str) -> str:
    return _safe_name(value, field="CTI varlık adı")


def entity_name_key(value: str) -> str:
    return normalize_entity_name(value).casefold()


def normalize_aliases(values) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (tuple, list)):
        raise ValidationError("CTI alternatif adları bir liste olmalı.")
    if len(values) > 50:
        raise ValidationError("Bir kaynak iddiasında en fazla 50 alternatif ad olabilir.")
    aliases: dict[str, str] = {}
    for value in values:
        name = _safe_name(value, field="CTI alternatif adı")
        aliases.setdefault(name.casefold(), name)
    return tuple(aliases[key] for key in sorted(aliases))


def aliases_to_json(values) -> str:
    return json.dumps(
        normalize_aliases(values), ensure_ascii=True, separators=(",", ":"),
    )


def aliases_from_json(value: str) -> tuple[str, ...]:
    try:
        if not isinstance(value, str) or len(value) > 20_000:
            raise ValueError("Invalid aliases JSON")
        decoded = json.loads(value)
        aliases = normalize_aliases(decoded)
        if value != json.dumps(aliases, ensure_ascii=True, separators=(",", ":")):
            raise ValueError("Non-canonical aliases JSON")
        return aliases
    except (TypeError, ValueError, ValidationError, json.JSONDecodeError) as error:
        raise ValidationError("CTI alternatif adları bozuk.") from error


def normalize_relationship_type(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("CTI ilişki türü gerekli.")
    normalized = value.strip().lower()
    if normalized not in RELATIONSHIP_TYPES:
        raise ValidationError(
            "CTI ilişki türü attributed-to, uses, targets, delivers, "
            "communicates-with, indicates, related-to veya reports-on olmalı."
        )
    return normalized


def normalize_target_kind(value: str) -> str:
    if value not in TARGET_KINDS:
        raise ValidationError("CTI ilişki hedefi entity veya indicator olmalı.")
    return value


def normalize_knowledge_id(value: str, *, field: str = "CTI kimliği") -> str:
    if not isinstance(value, str):
        raise ValidationError(f"Geçerli bir {field} gerekli.")
    try:
        normalized = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError(f"Geçerli bir {field} gerekli.") from error
    if normalized != value:
        raise ValidationError(f"{field} kanonik UUID biçiminde olmalı.")
    return normalized


def normalize_search_query(value: str) -> str:
    return _safe_name(value, field="CTI arama ifadesi")


def search_query_key(value: str) -> str:
    return normalize_search_query(value).casefold()


def normalize_search_kind(value: str) -> str:
    if value not in SEARCH_KINDS:
        raise ValidationError("CTI arama kapsamı all, entity veya indicator olmalı.")
    return value


@dataclass(frozen=True, slots=True)
class CtiEntity:
    id: str
    entity_type: str
    name_key: str
    display_name: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CtiEntityAssertion:
    id: str
    entity_id: str
    source_name: str
    source_reference: str
    confidence: int
    aliases: tuple[str, ...]
    description: str
    active: bool
    first_seen_at: str
    last_seen_at: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CtiEntityAssertionEvent:
    id: str
    assertion_id: str
    action: str
    confidence: int
    aliases: tuple[str, ...]
    description: str
    reason: str
    observed_at: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class CtiEntityMutation:
    action: str
    entity: CtiEntity
    assertion: CtiEntityAssertion


@dataclass(frozen=True, slots=True)
class CtiEntitySummary:
    entity: CtiEntity
    active_assertion_count: int
    total_assertion_count: int
    max_active_confidence: int | None


@dataclass(frozen=True, slots=True)
class CtiEntityDetails:
    entity: CtiEntity
    assertions: tuple[CtiEntityAssertion, ...]
    events: tuple[CtiEntityAssertionEvent, ...]
    total_assertion_count: int
    total_event_count: int


@dataclass(frozen=True, slots=True)
class CtiRelationship:
    id: str
    source_entity_id: str
    relationship_type: str
    target_kind: str
    target_entity_id: str | None
    target_indicator_id: str | None
    target_key: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CtiRelationshipAssertion:
    id: str
    relationship_id: str
    source_name: str
    source_reference: str
    confidence: int
    description: str
    active: bool
    first_seen_at: str
    last_seen_at: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CtiRelationshipAssertionEvent:
    id: str
    assertion_id: str
    action: str
    confidence: int
    description: str
    reason: str
    observed_at: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class CtiRelationshipMutation:
    action: str
    relationship: CtiRelationship
    assertion: CtiRelationshipAssertion


@dataclass(frozen=True, slots=True)
class CtiRelationshipSummary:
    relationship: CtiRelationship
    source_entity: CtiEntity
    target_entity: CtiEntity | None
    target_indicator_type: str | None
    target_indicator_value: str | None
    active_assertion_count: int
    total_assertion_count: int
    max_active_confidence: int | None


@dataclass(frozen=True, slots=True)
class CtiRelationshipDetails:
    summary: CtiRelationshipSummary
    assertions: tuple[CtiRelationshipAssertion, ...]
    events: tuple[CtiRelationshipAssertionEvent, ...]
    total_assertion_count: int
    total_event_count: int


@dataclass(frozen=True, slots=True)
class CtiSearchResult:
    kind: str
    record_id: str
    record_type: str
    display_value: str
    matched_field: str
    matched_value: str
    match_type: str
    current_assertion_count: int
    total_assertion_count: int
    max_current_confidence: int | None


@dataclass(frozen=True, slots=True)
class CtiSearchReport:
    query: str
    kind: str
    entity_type: str | None
    indicator_type: str | None
    active_only: bool
    total_match_count: int
    results: tuple[CtiSearchResult, ...]


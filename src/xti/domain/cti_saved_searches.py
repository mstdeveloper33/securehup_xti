"""Durable local CTI search definitions and complete difference snapshots."""

from dataclasses import dataclass
import hashlib
import json
import unicodedata

from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import CtiSearchResult, normalize_knowledge_id


SAVED_SEARCH_ACTIONS = {"added", "updated", "reactivated", "revoked"}
SAVED_SEARCH_ITEM_ACTIONS = {"added", "updated", "unchanged", "removed"}


def normalize_saved_search_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Kayıtlı CTI arama adı gerekli.")
    normalized = unicodedata.normalize("NFKC", value)
    if any(not character.isprintable() for character in normalized):
        raise ValidationError("Kayıtlı CTI arama adı 2–100 güvenli karakter arasında olmalı.")
    normalized = " ".join(normalized.strip().split())
    if not 2 <= len(normalized) <= 100:
        raise ValidationError("Kayıtlı CTI arama adı 2–100 güvenli karakter arasında olmalı.")
    return normalized


def saved_search_name_key(value: str) -> str:
    return normalize_saved_search_name(value).casefold()


def normalize_saved_search_id(value: str, *, field: str = "kayıtlı CTI arama kimliği") -> str:
    return normalize_knowledge_id(value, field=field)


def canonical_definition_json(
    *, query: str, query_key: str, kind: str, entity_type: str | None,
    indicator_type: str | None, active_only: bool,
) -> str:
    return json.dumps(
        {
            "active_only": active_only,
            "entity_type": entity_type,
            "indicator_type": indicator_type,
            "kind": kind,
            "query": query,
            "query_key": query_key,
        },
        ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    )


def definition_sha256(**values) -> str:
    return hashlib.sha256(canonical_definition_json(**values).encode("utf-8")).hexdigest()


def search_result_state_json(result: CtiSearchResult) -> str:
    return json.dumps(
        {
            "current_assertion_count": result.current_assertion_count,
            "display_value": result.display_value,
            "kind": result.kind,
            "match_type": result.match_type,
            "matched_field": result.matched_field,
            "matched_value": result.matched_value,
            "max_current_confidence": result.max_current_confidence,
            "record_id": result.record_id,
            "record_type": result.record_type,
            "total_assertion_count": result.total_assertion_count,
        },
        ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    )


def search_result_state_sha256(result: CtiSearchResult) -> str:
    return hashlib.sha256(search_result_state_json(result).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CtiSavedSearch:
    id: str
    name_key: str
    display_name: str
    query: str
    query_key: str
    kind: str
    entity_type: str | None
    indicator_type: str | None
    active_only: bool
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CtiSavedSearchEvent:
    id: str
    saved_search_id: str
    action: str
    definition_sha256: str
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class CtiSavedSearchMutation:
    action: str
    saved_search: CtiSavedSearch


@dataclass(frozen=True, slots=True)
class CtiSavedSearchRun:
    sequence: int
    id: str
    saved_search_id: str
    definition_sha256: str
    previous_run_id: str | None
    executed_at: str
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    result_sha256: str


@dataclass(frozen=True, slots=True)
class CtiSavedSearchRunItem:
    id: str
    run_id: str
    kind: str
    record_id: str
    record_type: str
    display_value: str
    matched_field: str
    matched_value: str
    match_type: str
    action: str
    state_sha256: str


@dataclass(frozen=True, slots=True)
class CtiSavedSearchSummary:
    saved_search: CtiSavedSearch
    run_count: int
    last_run: CtiSavedSearchRun | None


@dataclass(frozen=True, slots=True)
class CtiSavedSearchDetails:
    saved_search: CtiSavedSearch
    events: tuple[CtiSavedSearchEvent, ...]
    runs: tuple[CtiSavedSearchRun, ...]
    total_event_count: int
    total_run_count: int


@dataclass(frozen=True, slots=True)
class CtiSavedSearchRunReport:
    saved_search: CtiSavedSearch
    run: CtiSavedSearchRun
    items: tuple[CtiSavedSearchRunItem, ...]
    total_item_count: int
    notification_id: str | None = None


@dataclass(frozen=True, slots=True)
class CtiSavedSearchBatchItem:
    position: int
    saved_search_id: str
    display_name: str
    run_id: str
    executed_at: str
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    notification_id: str | None


@dataclass(frozen=True, slots=True)
class CtiSavedSearchBatchReport:
    planned_search_count: int
    completed_search_count: int
    started_at: str
    finished_at: str
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    notification_count: int
    items: tuple[CtiSavedSearchBatchItem, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CtiSavedSearchChangeEvidence:
    saved_search_id: str
    display_name: str
    query: str
    run_id: str
    executed_at: str
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int


@dataclass(frozen=True, slots=True)
class CtiSavedSearchMonitorCycle:
    cycle: int
    run_id: str
    executed_at: str
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    notification_id: str | None


@dataclass(frozen=True, slots=True)
class CtiSavedSearchMonitorReport:
    saved_search: CtiSavedSearch
    planned_cycles: int
    completed_cycles: int
    started_at: str
    finished_at: str
    elapsed_seconds: float
    stop_reason: str
    added_count: int
    updated_count: int
    removed_count: int
    notification_count: int
    cycles: tuple[CtiSavedSearchMonitorCycle, ...]
    notes: tuple[str, ...]

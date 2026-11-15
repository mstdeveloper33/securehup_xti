"""Versioned local search watches, frozen evidence and reproducible differences."""

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
import hashlib
import json
import re
import unicodedata
from uuid import UUID

from xti.domain.assets import ValidationError
from xti.domain.global_search import (
    GLOBAL_SEARCH_KINDS, GlobalSearchCoverage, GlobalSearchResult,
    global_match, normalize_global_kinds, normalize_global_query,
)
from xti.domain.engine import EngineContractError, reference_for_result
from xti.domain.organization_report import ReportNavigation
from xti.domain.news import NewsArticle, validate_article
from xti.domain.mentions import (
    MentionHit, MentionRequest, MentionTarget, match_hit, request_key, result_id,
    validate_hit, validate_request,
)


GLOBAL_SEARCH_WATCH_VERSION = "global-search-watch-v1"
MENTION_SCOPED_WATCH_VERSION = "global-search-watch-v2"
MAX_WATCH_MATCHES = 50_000
MAX_WATCH_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_WATCH_TOTAL_SNAPSHOT_BYTES = 64 * 1024 * 1024
MAX_WATCHES = 1000
MAX_WATCH_EVENTS = 10_000
MAX_WATCH_RUNS = 20_000
WATCH_ACTIONS = ("added", "updated", "reactivated", "disabled")
WATCH_ITEM_ACTIONS = ("added", "updated", "unchanged", "removed")


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def parse_canonical_json(value: str):
    if not isinstance(value, str) or len(value.encode("utf-8")) > MAX_WATCH_SNAPSHOT_BYTES:
        raise ValueError("Search watch JSON exceeds its evidence limit")
    try:
        parsed = json.loads(value, object_pairs_hook=_object,
                            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON")))
        pending = [(parsed, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 32:
                raise ValueError("Search watch JSON is nested too deeply")
            if isinstance(item, dict):
                pending.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                pending.extend((child, depth + 1) for child in item)
        if canonical_json(parsed) != value:
            raise ValueError("Search watch JSON is not canonical")
    except (RecursionError, UnicodeError) as error:
        raise ValueError("Search watch JSON is malformed or nested too deeply") from error
    return parsed


def watch_id(value: str) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError("Invalid identifier")
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError("Genel arama kimliği geçersiz.") from error
    return value


def watch_time(value: str) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("Invalid search watch time")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Search watch time requires a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def watch_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Kayıtlı genel arama adı gerekli.")
    value = unicodedata.normalize("NFKC", value)
    if any(not character.isprintable() for character in value):
        raise ValidationError("Arama adı 2–100 görünür karakter olmalı.")
    value = " ".join(value.split())
    if not 2 <= len(value) <= 100:
        raise ValidationError("Arama adı 2–100 görünür karakter olmalı.")
    return value


def watch_reason(value: str) -> str:
    if not isinstance(value, str) or any(not character.isprintable() for character in value):
        raise ValidationError("Kapatma gerekçesi görünür metin olmalı.")
    value = " ".join(value.split())
    if not 2 <= len(value) <= 1000:
        raise ValidationError("Kapatma gerekçesi 2–1000 karakter olmalı.")
    return value


def _keys(value, cls):
    if not isinstance(value, dict) or set(value) != {field.name for field in fields(cls)}:
        raise ValueError("Search watch evidence fields differ")


def _string(value, *, empty=False):
    if not isinstance(value, str) or len(value) > 131_072 or (not empty and not value):
        raise ValueError("Invalid search watch evidence text")
    return value


def _sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Invalid search watch hash")
    return value


@dataclass(frozen=True, slots=True)
class GlobalSavedSearch:
    id: str
    name_key: str
    display_name: str
    query: str
    kinds: tuple[str, ...]
    include_inactive: bool
    active: bool
    revision: int
    created_at: str
    updated_at: str
    mention_request_key: str | None = None


def definition_json(search: GlobalSavedSearch) -> str:
    value = asdict(search)
    version = MENTION_SCOPED_WATCH_VERSION
    if search.mention_request_key is None:
        # Preserve every historical v1 definition byte and therefore its hash.
        del value['mention_request_key']
        version = GLOBAL_SEARCH_WATCH_VERSION
    return canonical_json({"rule_version": version, "search": value})


def definition_from_json(value: str) -> GlobalSavedSearch:
    payload = parse_canonical_json(value)
    if (not isinstance(payload, dict) or set(payload) != {"rule_version", "search"}
            or payload["rule_version"] not in {GLOBAL_SEARCH_WATCH_VERSION, MENTION_SCOPED_WATCH_VERSION}):
        raise ValueError("Unsupported saved search rule version")
    item = payload["search"]
    expected = {field.name for field in fields(GlobalSavedSearch)}
    if payload['rule_version'] == GLOBAL_SEARCH_WATCH_VERSION:
        expected.remove('mention_request_key')
    if not isinstance(item, dict) or set(item) != expected:
        raise ValueError('Search watch definition fields differ')
    item = dict(item)
    item["kinds"] = tuple(item["kinds"])
    search = GlobalSavedSearch(**item)
    watch_id(search.id)
    if (watch_name(search.display_name) != search.display_name
            or search.name_key != search.display_name.casefold()
            or normalize_global_query(search.query) != search.query
            or normalize_global_kinds(search.kinds) != search.kinds
            or type(search.include_inactive) is not bool or type(search.active) is not bool
            or type(search.revision) is not int or search.revision < 1
            or watch_time(search.created_at) != search.created_at
            or watch_time(search.updated_at) != search.updated_at):
        raise ValueError("Invalid saved search definition")
    if payload['rule_version'] == MENTION_SCOPED_WATCH_VERSION:
        _sha(search.mention_request_key)
        if (search.kinds != ('mention',) or search.include_inactive
                or search.query != search.mention_request_key):
            raise ValueError('Typed mention search requires its exact request scope')
    return search


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchEvent:
    sequence: int
    id: str
    search_id: str
    revision: int
    action: str
    definition_sha256: str
    reason: str
    recorded_at: str
    search: GlobalSavedSearch


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchMutation:
    action: str
    saved_search: GlobalSavedSearch


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchMatch:
    key: str
    identity: tuple[str, ...]
    semantic_json: str
    state_sha256: str
    result: GlobalSearchResult


def mention_semantic(record) -> dict:
    """Stable source content and query context; ranking and collection times vary."""
    hit = asdict(record.hit)
    del hit['score']
    return {'record_id': record.id, 'source_key': 'tavily',
            'request': asdict(record.request), 'hit': hit,
            'matched_terms': list(record.matched_terms), 'match_fields': list(record.match_fields)}


def _validate_mention_match(result, semantic):
    try:
        if set(semantic) != {'record_id', 'source_key', 'request', 'hit', 'matched_terms', 'match_fields'}:
            raise ValueError('Mention semantic fields differ')
        target_data = dict(semantic['request']['target'])
        target_data['domains'] = tuple(target_data['domains'])
        target = MentionTarget(**target_data)
        request_data = dict(semantic['request'])
        request_data['target'] = target
        request = validate_request(MentionRequest(**request_data))
        hit = validate_hit(MentionHit(score=None, **semantic['hit']))
        terms, match_fields = match_hit(target, hit)
        if (result.kind != 'mention' or result.record_type != 'company_mention'
                or result.source != 'tavily' or semantic['source_key'] != 'tavily'
                or result.record_id != semantic['record_id']
                or result.record_id != result_id(request, hit.url)
                or result.display_value != hit.title or result.status != 'search_candidate'
                or result.current is not True or semantic['matched_terms'] != list(terms)
                or semantic['match_fields'] != list(match_fields)):
            raise ValueError('Mention source context differs')
        fields = {'title': hit.title, 'summary': hit.summary, 'url': hit.url,
                  'target_name': target.name, 'target_domains': ', '.join(target.domains),
                  'mention_request_key': request_key(request)}
        if result.matched_field not in fields or result.matched_value != fields[result.matched_field]:
            raise ValueError('Mention visible match differs')
    except (TypeError, ValueError, KeyError, AttributeError) as error:
        raise ValueError('Mention semantic state differs from its typed source evidence') from error


def make_match(result: GlobalSearchResult, identity, semantic: dict) -> GlobalSavedSearchMatch:
    identity = tuple(identity)
    if not identity or any(not isinstance(item, str) or not item or len(item) > 2048 for item in identity):
        raise ValueError("Invalid stable search identity")
    if not isinstance(semantic, dict):
        raise ValueError("Search semantic state must be an object")
    if len(identity) % 2 or len(set(identity[::2])) != len(identity) // 2:
        raise ValueError("Search identity requires unique field pairs")
    identity_fields = dict(zip(identity[::2], identity[1::2]))
    if identity != tuple(value for key in sorted(identity_fields) for value in (key, identity_fields[key])):
        raise ValueError("Search identity fields are not canonical")
    if result.record_type == "social_profile":
        if set(identity_fields) != {"kind", "record_type", "namespace", "watch_id", "definition_sha256", "platform"}:
            raise ValueError("Social identity has unexpected fields")
        expected = {"kind": "social", "record_type": "social_profile",
                    "namespace": semantic.get("source_key"), "watch_id": semantic.get("watch_id"),
                    "definition_sha256": semantic.get("definition_sha256"), "platform": semantic.get("platform")}
        if identity_fields != expected or result.kind != "social" or expected["namespace"] not in {"maigret", "sherlock"}:
            raise ValueError("Social identity differs from typed evidence")
        watch_id(expected["watch_id"])
        _sha(expected["definition_sha256"])
    else:
        try:
            expected = reference_for_result(result).to_dict()
        except EngineContractError as error:
            raise ValueError("Search record identity is unsupported") from error
        if identity_fields != expected:
            raise ValueError("Search identity differs from its source record")
    if result.kind == "news" or result.record_type == "news_article":
        try:
            article = validate_article(NewsArticle(**semantic))
        except (TypeError, ValueError) as error:
            raise ValueError("News semantic state is not a complete publisher article") from error
        if (result.kind != "news" or result.record_type != "news_article"
                or (result.record_id, result.source, result.display_value)
                != (article.id, article.source_key, article.title)
                or result.status != "publisher_metadata" or result.current is not True
                or result.matched_field not in {"title", "summary", "url"}
                or result.matched_value != getattr(article, result.matched_field)):
            raise ValueError("News search metadata differs from its typed publisher evidence")
    if result.kind == 'mention' or result.record_type == 'company_mention':
        _validate_mention_match(result, semantic)
    # Common visible matching/state fields are always part of the comparison.
    state = canonical_json({
        "rule_version": GLOBAL_SEARCH_WATCH_VERSION,
        "kind": result.kind, "record_type": result.record_type,
        "display_value": result.display_value, "matched_field": result.matched_field,
        "matched_value": result.matched_value, "match_type": result.match_type,
        "status": result.status, "current": result.current, "semantic": semantic,
    })
    return GlobalSavedSearchMatch(text_sha256(canonical_json(identity)), identity,
                                  state, text_sha256(state), result)


def _result_from_dict(item) -> GlobalSearchResult:
    _keys(item, GlobalSearchResult)
    item = dict(item)
    if item["kind"] not in GLOBAL_SEARCH_KINDS or item["match_type"] not in {"exact", "prefix", "contains"}:
        raise ValueError("Unknown search result kind or match")
    for key in ("record_type", "record_id", "display_value", "matched_field", "matched_value", "status"):
        _string(item[key])
    _string(item["source"], empty=True)
    if type(item["current"]) is not bool or watch_time(item["recorded_at"]) != item["recorded_at"]:
        raise ValueError("Invalid search result state or date")
    if item["source_run_id"] is not None:
        watch_id(item["source_run_id"])
    if not isinstance(item["details"], list) or not isinstance(item["navigation"], list):
        raise ValueError("Invalid search result details")
    item["details"] = tuple(_string(value, empty=True) for value in item["details"])
    navigation = []
    for nav in item["navigation"]:
        _keys(nav, ReportNavigation)
        if not isinstance(nav["arguments"], list):
            raise ValueError("Invalid search navigation")
        navigation.append(ReportNavigation(_string(nav["label"]),
                                           tuple(_string(arg) for arg in nav["arguments"])))
    item["navigation"] = tuple(navigation)
    return GlobalSearchResult(**item)


def match_from_dict(item) -> GlobalSavedSearchMatch:
    _keys(item, GlobalSavedSearchMatch)
    if not isinstance(item["identity"], list):
        raise ValueError("Invalid search identity")
    state = parse_canonical_json(item["semantic_json"])
    if not isinstance(state, dict) or "semantic" not in state:
        raise ValueError("Missing typed semantic state")
    result = _result_from_dict(item["result"])
    rebuilt = make_match(result, item["identity"], state["semantic"])
    if (rebuilt.key != _sha(item["key"]) or rebuilt.semantic_json != item["semantic_json"]
            or rebuilt.state_sha256 != _sha(item["state_sha256"])):
        raise ValueError("Search match state differs from frozen evidence")
    return rebuilt


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchSnapshot:
    matches: tuple[GlobalSavedSearchMatch, ...]
    coverage: tuple[GlobalSearchCoverage, ...]


def snapshot_json(snapshot: GlobalSavedSearchSnapshot) -> str:
    if len(snapshot.matches) > MAX_WATCH_MATCHES or len({match.key for match in snapshot.matches}) != len(snapshot.matches):
        raise ValueError("Search snapshot is too large or contains duplicate identities")
    value = canonical_json({"matches": [asdict(match) for match in sorted(snapshot.matches, key=lambda item: item.key)],
                            "coverage": [asdict(item) for item in snapshot.coverage]})
    if len(value.encode("utf-8")) > MAX_WATCH_SNAPSHOT_BYTES:
        raise ValueError("Search snapshot evidence exceeds the storage limit")
    return value


def snapshot_from_json(value: str) -> GlobalSavedSearchSnapshot:
    payload = parse_canonical_json(value)
    if not isinstance(payload, dict) or set(payload) != {"matches", "coverage"}:
        raise ValueError("Invalid frozen search snapshot")
    if not isinstance(payload["matches"], list) or not isinstance(payload["coverage"], list):
        raise ValueError("Invalid frozen search snapshot lists")
    matches = tuple(match_from_dict(item) for item in payload["matches"])
    coverage = []
    for item in payload["coverage"]:
        _keys(item, GlobalSearchCoverage)
        item = dict(item)
        if item["kind"] not in GLOBAL_SEARCH_KINDS:
            raise ValueError("Unknown search coverage kind")
        _string(item["source"])
        for key in ("examined_count", "matched_count"):
            if type(item[key]) is not int or item[key] < 0:
                raise ValueError("Invalid search coverage count")
        if item["matched_count"] > item["examined_count"]:
            raise ValueError("Search coverage counts disagree")
        for key in ("latest_run_id", "latest_success_run_id"):
            if item[key] is not None:
                watch_id(item[key])
        for key in ("latest_success_at", "latest_run_at"):
            if item[key] is not None and watch_time(item[key]) != item[key]:
                raise ValueError("Invalid source coverage date")
        if item["latest_run_status"] not in {None, "complete", "partial", "failed"}:
            raise ValueError("Invalid source coverage status")
        if not isinstance(item["notes"], list):
            raise ValueError("Invalid source coverage notes")
        item["notes"] = tuple(_string(note, empty=True) for note in item["notes"])
        coverage.append(GlobalSearchCoverage(**item))
    snapshot = GlobalSavedSearchSnapshot(matches, tuple(coverage))
    if snapshot_json(snapshot) != value:
        raise ValueError("Search snapshot order or identity differs")
    if sum(item.matched_count for item in coverage) != len(matches):
        raise ValueError("Search coverage is incomplete")
    for kind in GLOBAL_SEARCH_KINDS:
        if sum(item.matched_count for item in coverage if item.kind == kind) != sum(match.result.kind == kind for match in matches):
            raise ValueError("Search coverage kind counts differ")
    return snapshot


def validate_snapshot_scope(snapshot: GlobalSavedSearchSnapshot, search: GlobalSavedSearch) -> None:
    if {item.kind for item in snapshot.coverage} != set(search.kinds):
        raise ValueError("Saved search source coverage differs from its definition")
    for item in snapshot.matches:
        result = item.result
        if result.kind not in search.kinds or (not search.include_inactive and not result.current):
            raise ValueError("Saved search result is outside the selected scope")
        if search.mention_request_key is not None:
            if (result.kind != 'mention' or result.matched_field != 'mention_request_key'
                    or result.matched_value != search.mention_request_key or result.match_type != 'exact'):
                raise ValueError('Saved mention result differs from its exact request scope')
        matched = global_match(search.query, ((result.matched_field, result.matched_value),))
        if matched is None or matched[0] != result.match_type:
            raise ValueError("Saved search result differs from its historical query")


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchRun:
    sequence: int
    id: str
    search_id: str
    event_id: str
    snapshot_sha256: str
    previous_run_id: str | None
    executed_at: str
    total_count: int
    added_count: int
    updated_count: int
    unchanged_count: int
    removed_count: int
    diff_sha256: str


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchRunItem:
    key: str
    action: str
    before: GlobalSavedSearchMatch | None
    after: GlobalSavedSearchMatch | None


def difference(before: GlobalSavedSearchSnapshot | None,
               after: GlobalSavedSearchSnapshot) -> tuple[GlobalSavedSearchRunItem, ...]:
    prior = {item.key: item for item in before.matches} if before else {}
    current = {item.key: item for item in after.matches}
    if len(current) != len(after.matches) or (before is not None and len(prior) != len(before.matches)):
        raise ValueError("Duplicate search match identity")
    items = []
    for key in sorted(prior.keys() | current.keys()):
        old, new = prior.get(key), current.get(key)
        action = "added" if old is None else "removed" if new is None else (
            "unchanged" if old.state_sha256 == new.state_sha256 else "updated")
        items.append(GlobalSavedSearchRunItem(key, action, old, new))
    return tuple(sorted(items, key=lambda item: (WATCH_ITEM_ACTIONS.index(item.action), item.key)))


def difference_sha256(items: tuple[GlobalSavedSearchRunItem, ...]) -> str:
    return text_sha256(canonical_json([asdict(item) for item in items]))


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchRunReport:
    saved_search: GlobalSavedSearch
    run: GlobalSavedSearchRun
    items: tuple[GlobalSavedSearchRunItem, ...]
    coverage: tuple[GlobalSearchCoverage, ...]
    total_item_count: int
    offset: int
    limit: int
    has_more: bool
    notification_id: str | None = None


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchSummary:
    saved_search: GlobalSavedSearch
    run_count: int
    last_run: GlobalSavedSearchRun | None


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchPage:
    items: tuple[GlobalSavedSearchSummary, ...]
    total_count: int
    offset: int
    limit: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchDetails:
    saved_search: GlobalSavedSearch
    events: tuple[GlobalSavedSearchEvent, ...]
    runs: tuple[GlobalSavedSearchRun, ...]
    total_event_count: int
    total_run_count: int
    event_offset: int
    event_limit: int
    run_offset: int
    run_limit: int
    has_more_events: bool
    has_more_runs: bool


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchMonitorCycle:
    run: GlobalSavedSearchRun
    notification_id: str | None


@dataclass(frozen=True, slots=True)
class GlobalSavedSearchMonitorReport:
    search_id: str
    planned_cycles: int
    completed_cycles: int
    started_at: str
    finished_at: str
    elapsed_seconds: float
    stop_reason: str
    runs: tuple[GlobalSavedSearchMonitorCycle, ...]
    notification_count: int

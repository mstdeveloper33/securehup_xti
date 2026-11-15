"""Personal workspace search with explicit source scope and stable match ranking."""

from dataclasses import dataclass
import unicodedata

from xti.domain.assets import ValidationError
from xti.domain.organization_report import ReportNavigation


GLOBAL_SEARCH_KINDS = (
    'domain', 'finding', 'social', 'ransomware', 'public-notice', 'case',
    'supplier', 'organization', 'cti', 'indicator', 'news', 'mention',
)
MAX_SEARCH_ROWS = 50_000


def normalize_global_query(value: str) -> str:
    if not isinstance(value, str) or any(not char.isprintable() for char in value):
        raise ValidationError('Arama metni görünür karakterlerden oluşmalı.')
    result = ' '.join(unicodedata.normalize('NFKC', value).split())
    if not 2 <= len(result) <= 200:
        raise ValidationError('Arama metni 2–200 karakter arasında olmalı.')
    return result


def normalize_global_kinds(values) -> tuple[str, ...]:
    if values is None:
        return GLOBAL_SEARCH_KINDS
    if not isinstance(values, (list, tuple)) or not values or any(value not in GLOBAL_SEARCH_KINDS for value in values):
        raise ValidationError('Arama kayıt türü geçersiz.')
    return tuple(kind for kind in GLOBAL_SEARCH_KINDS if kind in values)


def global_match(query: str, fields: tuple[tuple[str, str], ...]):
    query = unicodedata.normalize('NFKC', query).casefold()
    matches = []
    for name, value in fields:
        if not isinstance(value, str):
            continue
        key = unicodedata.normalize('NFKC', value).casefold()
        rank = 0 if key == query else 1 if key.startswith(query) else 2 if query in key else None
        if rank is not None:
            matches.append((rank, name, key, value))
    if not matches:
        return None
    rank, name, _, value = min(matches)
    return ('exact', 'prefix', 'contains')[rank], name, value


@dataclass(frozen=True, slots=True)
class GlobalSearchResult:
    kind: str
    record_type: str
    record_id: str
    display_value: str
    matched_field: str
    matched_value: str
    match_type: str
    status: str
    current: bool
    recorded_at: str
    source: str
    source_run_id: str | None = None
    details: tuple[str, ...] = ()
    navigation: tuple[ReportNavigation, ...] = ()


@dataclass(frozen=True, slots=True)
class GlobalSearchCoverage:
    kind: str
    source: str
    examined_count: int
    matched_count: int
    latest_run_id: str | None = None
    latest_run_status: str | None = None
    latest_success_run_id: str | None = None
    latest_success_at: str | None = None
    notes: tuple[str, ...] = ()
    latest_run_at: str | None = None


@dataclass(frozen=True, slots=True)
class GlobalSearchReport:
    query: str
    kinds: tuple[str, ...]
    include_inactive: bool
    checked_at: str
    total_match_count: int
    offset: int
    limit: int
    has_more: bool
    results: tuple[GlobalSearchResult, ...]
    coverage: tuple[GlobalSearchCoverage, ...]
    notes: tuple[str, ...]

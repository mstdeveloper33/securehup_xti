"""Explicit supplier watches over independent public-source records."""
from dataclasses import dataclass
import hashlib
import json
import unicodedata

from xti.domain.assets import ValidationError
from xti.domain.ransomware_watches import ransomware_claim_website_host
from xti.domain.suppliers import Supplier

SUPPLIER_WATCH_SOURCES = ('threatcluster', 'ransomlook', 'hibp')
SUPPLIER_WATCH_NOTES = (
    'Kaynak kayıtları iddia veya kamu metaverisidir; doğrulanmış ihlal ya da tedarikçinin sana etkisi değildir.',
    'İlk ölçüm, yeniden açılan izleme ve tedarikçi kimlik tanımı değişimi sessiz başlangıçtır.',
    'Yeni/değişen eşleşme yerel bildirim üretir; çıkarılma çözülmüş olay, kaynak hatası boş sonuç sayılmaz.',
    'Aynı adlı tedarikçiler ad eşleşmesini belirsiz kılabilir; domain dayanağı ayrıca gösterilir.',
)


def supplier_watch_source(value: str) -> str:
    if not isinstance(value, str) or value not in SUPPLIER_WATCH_SOURCES:
        raise ValidationError('İzleme kaynağı threatcluster, ransomlook veya hibp olmalı.')
    return value


def supplier_watch_window(offset: int, limit: int) -> None:
    if type(offset) is not int or not 0 <= offset <= 1_000_000 or type(limit) is not int or not 1 <= limit <= 500:
        raise ValidationError('İzleme başlangıcı 0–1000000, görünüm sınırı 1–500 olmalı.')


def canonical_watch_json(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def supplier_watch_hash(value) -> str:
    return hashlib.sha256(canonical_watch_json(value).encode('ascii')).hexdigest()


def supplier_record_match(source: str, supplier: dict, record: dict) -> tuple[str, ...]:
    domain = supplier['primary_domain']
    if source == 'hibp':
        return ('domain:exact',) if record['domain'] == domain else ()
    name = ' '.join(unicodedata.normalize('NFKC', record['victim']).casefold().split())
    matches = ['victim:exact'] if name == supplier['name_key'] else []
    if source == 'threatcluster':
        host = ransomware_claim_website_host(record['website'])
        if host == domain:
            matches.append('website:exact')
        elif host is not None and host.endswith('.' + domain):
            matches.append('website:subdomain')
    return tuple(matches)


@dataclass(frozen=True, slots=True)
class SupplierWatch:
    id: str
    supplier_id: str
    source_key: str
    active: bool
    revision: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class SupplierWatchEvent:
    sequence: int
    id: str
    watch_id: str
    supplier_id: str
    source_key: str
    action: str
    revision: int
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class SupplierWatchRun:
    sequence: int
    id: str
    watch_id: str
    supplier_id: str
    source_key: str
    source_run_id: str
    watch_event_id: str
    previous_run_id: str | None
    supplier_event_sequence: int
    recorded_at: str
    scope_sha256: str
    result_sha256: str
    matched_count: int
    baseline_count: int
    added_count: int
    updated_count: int
    removed_count: int
    unchanged_count: int


@dataclass(frozen=True, slots=True)
class SupplierWatchItem:
    record_id: str
    action: str
    before: dict | None
    after: dict | None
    match_before: tuple[str, ...]
    match_after: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SupplierWatchComparison:
    items: tuple[SupplierWatchItem, ...]
    matched_count: int
    baseline_count: int
    added_count: int
    updated_count: int
    removed_count: int
    unchanged_count: int


def compare_supplier_watch(before: dict[str, dict], after: dict[str, dict], *, source: str,
                           scope: dict, previous_scope: dict | None, same_watch_epoch: bool) -> SupplierWatchComparison:
    previous_supplier = previous_scope['supplier'] if previous_scope is not None else None
    supplier = scope['supplier']
    old_matches = {key: supplier_record_match(source, previous_supplier, record) for key, record in before.items()} if previous_supplier else {}
    new_matches = {key: supplier_record_match(source, supplier, record) for key, record in after.items()}
    old_matches = {key: value for key, value in old_matches.items() if value}
    new_matches = {key: value for key, value in new_matches.items() if value}
    baseline = not same_watch_epoch or previous_scope is None or scope['definition_sha256'] != previous_scope['definition_sha256']
    items = []
    for key in sorted(set(new_matches) | (set(old_matches) if not baseline else set())):
        old, new = before.get(key), after.get(key)
        if baseline:
            old, action = None, 'baseline'
        elif key not in new_matches:
            action = 'removed'
        elif key not in old_matches:
            action = 'added'
        else:
            action = 'unchanged' if supplier_watch_hash(old) == supplier_watch_hash(new) else 'updated'
        items.append(SupplierWatchItem(key, action, old, new,
            old_matches.get(key, ()) if old is not None else (), new_matches.get(key, ())))
    order = {'added': 0, 'updated': 1, 'baseline': 2, 'removed': 3, 'unchanged': 4}
    items.sort(key=lambda value: (order[value.action], value.record_id))
    counts = {action: sum(value.action == action for value in items) for action in order}
    return SupplierWatchComparison(tuple(items), len(new_matches), counts['baseline'], counts['added'],
                                    counts['updated'], counts['removed'], counts['unchanged'])


@dataclass(frozen=True, slots=True)
class SupplierWatchSource:
    source_key: str
    name: str
    url: str
    attribution: str
    license: str


@dataclass(frozen=True, slots=True)
class SupplierWatchSourceState:
    source: SupplierWatchSource
    latest_run: dict | None
    latest_complete_run: dict | None


@dataclass(frozen=True, slots=True)
class SupplierWatchMutation:
    action: str
    watch: SupplierWatch


@dataclass(frozen=True, slots=True)
class SupplierWatchSummary:
    watch: SupplierWatch
    supplier: Supplier
    latest_run: SupplierWatchRun | None
    total_run_count: int


@dataclass(frozen=True, slots=True)
class SupplierWatchPage:
    watches: tuple[SupplierWatchSummary, ...]
    total_count: int
    offset: int
    limit: int
    notes: tuple[str, ...] = SUPPLIER_WATCH_NOTES


@dataclass(frozen=True, slots=True)
class SupplierWatchDetails:
    watch: SupplierWatch
    supplier: Supplier
    events: tuple[SupplierWatchEvent, ...]
    runs: tuple[SupplierWatchRun, ...]
    total_event_count: int
    total_run_count: int
    event_offset: int
    run_offset: int
    source: SupplierWatchSourceState
    notes: tuple[str, ...] = SUPPLIER_WATCH_NOTES


@dataclass(frozen=True, slots=True)
class SupplierWatchRunReport:
    watch: SupplierWatch
    run: SupplierWatchRun
    scope: dict
    previous_scope: dict | None
    source: SupplierWatchSource
    source_run: dict
    previous_source_run: dict | None
    items: tuple[SupplierWatchItem, ...]
    total_item_count: int
    offset: int
    notification_id: str | None
    notes: tuple[str, ...] = SUPPLIER_WATCH_NOTES

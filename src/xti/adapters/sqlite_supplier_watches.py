"""Source-isolated supplier comparisons over audited, immutable local histories."""
from bisect import bisect_right
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.adapters.sqlite_supplier_history import read_supplier_history, supplier_scope
from xti.adapters.sqlite_public_notices import read_public_notice_history
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.domain.assets import ValidationError
from xti.domain.public_notices import notice_timestamp, HIBP_SOURCE_NAME, HIBP_SOURCE_URL, HIBP_ATTRIBUTION, HIBP_LICENSE
from xti.domain.ransomware_claims import RANSOMWARE_SOURCE_NAME, RANSOMWARE_SOURCE_URL, RANSOMWARE_SOURCE_LICENSE
from xti.domain.ransomlook_ransomware import RANSOMLOOK_SOURCE_NAME, RANSOMLOOK_SOURCE_URL, RANSOMLOOK_SOURCE_LICENSE
from xti.domain.suppliers import normalize_supplier_id, normalize_supplier_reason
from xti.domain.supplier_watches import (
    SupplierWatch, SupplierWatchEvent, SupplierWatchRun, SupplierWatchSource,
    SupplierWatchSourceState, SupplierWatchMutation, SupplierWatchSummary,
    SupplierWatchPage, SupplierWatchDetails, SupplierWatchRunReport,
    compare_supplier_watch, canonical_watch_json as _json, supplier_watch_hash as _hash,
    supplier_watch_source, supplier_watch_window,
)

_MAX_WATCHES = 10_000
_MAX_HISTORY = 100_000
_MAX_MATCHES = 10_000
_MAX_SCOPE_BYTES = 4_000_000
_WATCH_COLUMNS = tuple(SupplierWatch.__dataclass_fields__)
_EVENT_COLUMNS = tuple(SupplierWatchEvent.__dataclass_fields__)
_COUNTS = ('matched_count', 'baseline_count', 'added_count', 'updated_count', 'removed_count', 'unchanged_count')
_SOURCE_COLUMNS = {'threatcluster': 'threatcluster_run_id', 'ransomlook': 'ransomlook_run_id', 'hibp': 'public_notice_run_id'}
_RUN_COLUMNS = tuple(name for name in SupplierWatchRun.__dataclass_fields__ if name != 'source_run_id')
_RUN_SELECT = ','.join(_RUN_COLUMNS) + ',threatcluster_run_id,ransomlook_run_id,public_notice_run_id,scope_json'
_SOURCES = {
    'threatcluster': SupplierWatchSource('threatcluster', RANSOMWARE_SOURCE_NAME, RANSOMWARE_SOURCE_URL,
        'ThreatCluster — https://threatcluster.io', RANSOMWARE_SOURCE_LICENSE),
    'ransomlook': SupplierWatchSource('ransomlook', RANSOMLOOK_SOURCE_NAME, RANSOMLOOK_SOURCE_URL,
        'RansomLook — https://www.ransomlook.io', RANSOMLOOK_SOURCE_LICENSE),
    'hibp': SupplierWatchSource('hibp', HIBP_SOURCE_NAME, HIBP_SOURCE_URL, HIBP_ATTRIBUTION, HIBP_LICENSE),
}


def _positive(value):
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValueError('Invalid positive integer')


def _rows(connection, table, columns, order, maximum, supplier_id=None):
    where = ' WHERE supplier_id=?' if supplier_id is not None else ''
    values = (supplier_id, maximum + 1) if supplier_id is not None else (maximum + 1,)
    rows = connection.execute(f'SELECT {columns} FROM {table}{where} ORDER BY {order} LIMIT ?', values).fetchall()
    if len(rows) > maximum:
        raise ValueError('Supplier watch history capacity exceeded')
    if table in {'supplier_watch_events', 'supplier_watch_runs'}:
        allocated = connection.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (table,)).fetchone()
        count, first, last = connection.execute(f'SELECT COUNT(*),MIN(sequence),MAX(sequence) FROM {table}').fetchone()
        if ((allocated[0] if allocated else 0) != count
                or count and (first != 1 or last != count)):
            raise ValueError('Supplier watch append-only allocator differs')
    return rows


class _Catalog:
    """Replay delta history, retaining at most two full source snapshots."""
    def __init__(self, connection, source):
        if source == 'hibp':
            history = read_public_notice_history(connection)
            runs, changes = history.runs, history.changes
        else:
            repository = SQLiteRansomwareClaimRepository if source == 'threatcluster' else SQLiteRansomLookClaimRepository
            runs, changes = repository._audit(connection)
        self.runs = {run.id: run for run in runs}
        self.versions = {}
        for change in changes:
            record = change.notice if source == 'hibp' else change.claim
            sequences, values = self.versions.setdefault(record.id, ([], []))
            sequences.append(self.runs[change.run_id].sequence)
            values.append(None if change.action == 'removed' else asdict(record))
        self.snapshot = lru_cache(maxsize=2)(self._snapshot)

    def _snapshot(self, run_id):
        if run_id is None:
            return {}
        sequence = self.runs[run_id].sequence
        result = {}
        for identifier, (sequences, values) in self.versions.items():
            index = bisect_right(sequences, sequence) - 1
            if index >= 0 and values[index] is not None:
                result[identifier] = values[index]
        return result


@dataclass
class _State:
    suppliers: object
    catalogs: dict
    watches: dict
    events: dict
    runs: dict
    scopes: dict
    notifications: dict


def _comparison(state, run):
    previous = state.runs.get(run.previous_run_id)
    catalog = state.catalogs[run.source_key]
    comparison = compare_supplier_watch(catalog.snapshot(previous.source_run_id if previous else None),
        catalog.snapshot(run.source_run_id), source=run.source_key, scope=state.scopes[run.id],
        previous_scope=state.scopes[previous.id] if previous else None,
        same_watch_epoch=previous is not None and previous.watch_event_id == run.watch_event_id)
    if len(comparison.items) > _MAX_MATCHES or any(getattr(comparison, key) > _MAX_MATCHES for key in _COUNTS):
        raise StorageError('Tedarikçi eşleşmeleri güvenli kayıt sınırını aşıyor; veri kesilmedi, işlem kaydedilmedi.')
    return comparison


def _result_hash(run, comparison):
    values = asdict(run)
    del values['result_sha256']
    return _hash({'run': values, 'comparison': asdict(comparison)})


def _audit(connection, *, selected_supplier_id=None, supplier_history=None, catalogs=None):
    # A composed reader may select one supplier in its existing transaction.
    # Historical ambiguity still needs the FULL supplier identity history;
    # source catalogs and supplier history can be shared after bounded preflight.
    history = supplier_history if supplier_history is not None else read_supplier_history(connection)
    state = _State(history, dict(catalogs or {}), {}, {}, {}, {}, {})
    try:
        if not history.complete:
            raise ValueError('Full supplier identity history is required')
        for row in _rows(connection, 'supplier_watches', ','.join(_WATCH_COLUMNS), 'id', _MAX_WATCHES, selected_supplier_id):
            identifier, supplier_id, source, active, revision, created, updated = row
            normalize_supplier_id(identifier); normalize_supplier_id(supplier_id); supplier_watch_source(source)
            _positive(revision); notice_timestamp(created); notice_timestamp(updated)
            if type(active) is not int or active not in {0, 1} or supplier_id not in state.suppliers.suppliers:
                raise ValueError('Invalid supplier watch identity')
            state.watches[identifier] = SupplierWatch(identifier, supplier_id, source, bool(active), revision, created, updated)
        current = {}
        for row in _rows(connection, 'supplier_watch_events', ','.join(_EVENT_COLUMNS), 'sequence', _MAX_HISTORY, selected_supplier_id):
            event = SupplierWatchEvent(*row)
            _positive(event.sequence); _positive(event.revision)
            normalize_supplier_id(event.id); notice_timestamp(event.recorded_at)
            watch, before = state.watches.get(event.watch_id), current.get(event.watch_id)
            if (watch is None or (event.supplier_id, event.source_key) != (watch.supplier_id, watch.source_key)
                    or event.action not in {'enabled', 'disabled'} or normalize_supplier_reason(event.reason) != event.reason
                    or event.revision != (before.revision + 1 if before else 1)
                    or before is None and event.action != 'enabled'
                    or before is not None and (before.active == (event.action == 'enabled') or event.recorded_at < before.updated_at)):
                raise ValueError('Invalid supplier watch lifecycle')
            current[watch.id] = SupplierWatch(watch.id, watch.supplier_id, watch.source_key, event.action == 'enabled',
                event.revision, before.created_at if before else event.recorded_at, event.recorded_at)
            state.events[event.id] = event
        if current != state.watches:
            raise ValueError('Supplier watch differs from event history')
        for source in {watch.source_key for watch in state.watches.values()}:
            if source not in state.catalogs:
                state.catalogs[source] = _Catalog(connection, source)
        previous_by_watch, source_sequences = {}, {}
        for row in _rows(connection, 'supplier_watch_runs', _RUN_SELECT, 'sequence', _MAX_HISTORY, selected_supplier_id):
            values = dict(zip(_RUN_COLUMNS, row[:-4]))
            providers = dict(zip(_SOURCE_COLUMNS, row[-4:-1]))
            source_key = supplier_watch_source(values['source_key'])
            if providers[source_key] is None or any(value is not None for key, value in providers.items() if key != source_key):
                raise ValueError('Invalid source foreign key')
            run = SupplierWatchRun(**values, source_run_id=providers[source_key])
            raw_scope = row[-1]
            _positive(run.sequence); normalize_supplier_id(run.id); notice_timestamp(run.recorded_at)
            watch, event = state.watches.get(run.watch_id), state.events.get(run.watch_event_id)
            catalog = state.catalogs.get(source_key)
            source = catalog.runs.get(run.source_run_id) if catalog else None
            previous = previous_by_watch.get(run.watch_id)
            if (watch is None or (run.supplier_id, source_key) != (watch.supplier_id, watch.source_key)
                    or event is None or event.watch_id != watch.id or event.action != 'enabled'
                    or source is None or source.status != 'complete' or run.recorded_at != source.finished_at
                    or source.sequence < source_sequences.get(source_key, 0) or source.finished_at < event.recorded_at
                    or run.previous_run_id != (previous.id if previous else None)
                    or previous and (catalog.runs[previous.source_run_id].sequence >= source.sequence
                        or state.events[previous.watch_event_id].sequence > event.sequence)):
                raise ValueError('Invalid supplier watch source or lifecycle binding')
            if not isinstance(raw_scope, str) or len(raw_scope) > _MAX_SCOPE_BYTES:
                raise ValueError('Invalid supplier scope payload')
            scope = supplier_scope(state.suppliers, run.supplier_id, run.supplier_event_sequence)
            if (not scope['supplier']['active'] or raw_scope != _json(scope) or run.scope_sha256 != _hash(scope)
                    or previous and previous.supplier_event_sequence > run.supplier_event_sequence):
                raise ValueError('Supplier scope differs from historical identity')
            state.runs[run.id], state.scopes[run.id] = run, scope
            comparison = _comparison(state, run)
            if (any(type(getattr(run, key)) is not int or getattr(run, key) != getattr(comparison, key) for key in _COUNTS)
                    or run.result_sha256 != _result_hash(run, comparison)):
                raise ValueError('Supplier result differs from historical source evidence')
            previous_by_watch[watch.id], source_sequences[source_key] = run, source.sequence
        notified = set()
        for row in _rows(connection, 'supplier_watch_notifications',
                'sequence,id,run_id,watch_id,supplier_id,source_key,event_type,origin,created_at,read_at', 'sequence', _MAX_HISTORY, selected_supplier_id):
            sequence, identifier, run_id, watch_id, supplier_id, source_key, event_type, origin, created, read_at = row
            _positive(sequence); normalize_supplier_id(identifier); notice_timestamp(created)
            if read_at is not None:
                notice_timestamp(read_at)
            run = state.runs.get(run_id)
            if (run is None or (watch_id, supplier_id, source_key, created) != (run.watch_id, run.supplier_id, run.source_key, run.recorded_at)
                    or event_type != 'supplier_watch_changed' or origin != 'new'
                    or run.added_count + run.updated_count < 1 or run_id in notified):
                raise ValueError('Supplier notification evidence binding differs')
            notified.add(run_id)
            state.notifications[identifier] = run_id
        if notified != {run.id for run in state.runs.values() if run.added_count + run.updated_count > 0}:
            raise ValueError('Supplier atomic notification missing')
        return state
    except (ValueError, TypeError, KeyError, AttributeError, StopIteration, OverflowError, RecursionError) as error:
        raise StorageError('Tedarikçi izleme geçmişi veya kanıt bütünlüğü bozuk; kayıtlar değiştirilmedi.') from error


def preflight_supplier_watches(connection):
    """Fail before HTTP when the existing immutable history cannot advance."""
    state = _audit(connection)
    active = [watch for watch in state.watches.values() if watch.active and state.suppliers.suppliers[watch.supplier_id].active]
    if len(state.runs) + len(active) > _MAX_HISTORY:
        raise StorageError('Tedarikçi izleme geçmişi kapasitesi doldu.')
    for watch in active:
        if len(_json(supplier_scope(state.suppliers, watch.supplier_id))) > _MAX_SCOPE_BYTES:
            raise StorageError('Tedarikçi izleme kapsamı güvenli kayıt sınırını aşıyor.')


def process_supplier_watches(connection, source_key, source_run_id):
    """Advance only inside the successful source apply transaction."""
    supplier_watch_source(source_key)
    state = _audit(connection)
    if not connection.in_transaction:
        raise StorageError('Tedarikçi izlemesi kaynak kayıt işleminin içinde çalışmalı.')
    eligible = [watch for watch in state.watches.values() if watch.active and watch.source_key == source_key
                and state.suppliers.suppliers[watch.supplier_id].active]
    if not eligible:
        return
    catalog = state.catalogs.setdefault(source_key, None)
    if catalog is None:
        catalog = state.catalogs[source_key] = _Catalog(connection, source_key)
    source = catalog.runs.get(source_run_id)
    if (not connection.in_transaction or source is None or source.status != 'complete'
            or next(reversed(catalog.runs), None) != source_run_id):
        raise StorageError('Tedarikçi izlemesi yalnız aynı işlemdeki başarılı katalog çalışmasıyla ilerletilebilir.')
    for watch in sorted(eligible, key=lambda value: value.id):
        previous = next((run for run in reversed(tuple(state.runs.values())) if run.watch_id == watch.id), None)
        if previous and previous.source_run_id == source_run_id:
            continue
        if len(state.runs) >= _MAX_HISTORY:
            raise StorageError('Tedarikçi izleme geçmişi kapasitesi doldu.')
        scope = supplier_scope(state.suppliers, watch.supplier_id)
        raw_scope = _json(scope)
        if len(raw_scope) > _MAX_SCOPE_BYTES:
            raise StorageError('Tedarikçi izleme kapsamı güvenli kayıt sınırını aşıyor.')
        event = next(event for event in reversed(tuple(state.events.values())) if event.watch_id == watch.id)
        if source.finished_at < event.recorded_at:
            raise StorageError('Katalog çalışması tedarikçi izlemesini açma zamanından önce olamaz.')
        run = SupplierWatchRun(len(state.runs) + 1, str(uuid4()), watch.id, watch.supplier_id, source_key,
            source_run_id, event.id, previous.id if previous else None, scope['supplier_event_sequence'],
            source.finished_at, _hash(scope), '', 0, 0, 0, 0, 0, 0)
        state.scopes[run.id] = scope
        comparison = _comparison(state, run)
        run = replace(run, **{key: getattr(comparison, key) for key in _COUNTS})
        run = replace(run, result_sha256=_result_hash(run, comparison))
        columns = _RUN_COLUMNS + (_SOURCE_COLUMNS[source_key], 'scope_json')
        values = tuple(getattr(run, key) for key in _RUN_COLUMNS) + (source_run_id, raw_scope)
        connection.execute(f"INSERT INTO supplier_watch_runs ({','.join(columns)}) VALUES ({','.join('?' for _ in values)})", values)
        state.runs[run.id] = run
        if run.added_count + run.updated_count:
            connection.execute('INSERT INTO supplier_watch_notifications '
                '(sequence,id,run_id,watch_id,supplier_id,source_key,event_type,origin,created_at,read_at) '
                "VALUES (?,?,?,?,?,?,'supplier_watch_changed','new',?,NULL)",
                (next_notification_sequence(connection), str(uuid4()), run.id, watch.id, watch.supplier_id, source_key, run.recorded_at))


def _source_state(state, source):
    runs = tuple(state.catalogs[source].runs.values())
    latest = runs[-1] if runs else None
    complete = next((run for run in reversed(runs) if run.status == 'complete'), None)
    return SupplierWatchSourceState(_SOURCES[source], asdict(latest) if latest else None, asdict(complete) if complete else None)


def _run_report(state, run, *, item_limit, offset=0):
    comparison = _comparison(state, run)
    previous = state.runs.get(run.previous_run_id)
    event, watch = state.events[run.watch_event_id], state.watches[run.watch_id]
    catalog = state.catalogs[run.source_key]
    historical = replace(watch, active=True, revision=event.revision, updated_at=event.recorded_at)
    return SupplierWatchRunReport(historical, run, state.scopes[run.id], state.scopes[previous.id] if previous else None,
        _SOURCES[run.source_key], asdict(catalog.runs[run.source_run_id]),
        asdict(catalog.runs[previous.source_run_id]) if previous else None,
        comparison.items[offset:offset + item_limit], len(comparison.items), offset,
        next((identifier for identifier, run_id in state.notifications.items() if run_id == run.id), None))


class SQLiteSupplierWatchRepository:
    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    def configure(self, supplier_id, *, source, enabled, reason, recorded_at):
        normalize_supplier_id(supplier_id); supplier_watch_source(source); notice_timestamp(recorded_at)
        reason = normalize_supplier_reason(reason)
        if type(enabled) is not bool:
            raise ValidationError('İzleme etkinliği doğru/yanlış olmalı.')
        with self._storage._connection() as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                state = _audit(connection)
                supplier = state.suppliers.suppliers.get(supplier_id)
                if supplier is None:
                    raise ValidationError('Tedarikçi bulunamadı.')
                if enabled and not supplier.active:
                    raise ValidationError('Geri çekilmiş tedarikçi için izleme açılamaz.')
                before = next((watch for watch in state.watches.values() if (watch.supplier_id, watch.source_key) == (supplier_id, source)), None)
                if before is None and not enabled:
                    raise ValidationError('Bu tedarikçi ve kaynak için izleme bulunamadı.')
                if before is not None and before.active == enabled:
                    return SupplierWatchMutation('unchanged', before)
                if recorded_at < (before.updated_at if before else supplier.created_at):
                    raise ValidationError('İzleme zamanı son değişiklikten önce olamaz.')
                if len(state.events) >= _MAX_HISTORY or before is None and len(state.watches) >= _MAX_WATCHES:
                    raise StorageError('Tedarikçi izleme geçmişi kapasitesi doldu.')
                watch = SupplierWatch(before.id if before else str(uuid4()), supplier_id, source, enabled,
                    before.revision + 1 if before else 1, before.created_at if before else recorded_at, recorded_at)
                if before:
                    connection.execute('UPDATE supplier_watches SET active=?,revision=?,updated_at=? WHERE id=?',
                        (int(enabled), watch.revision, recorded_at, watch.id))
                else:
                    connection.execute('INSERT INTO supplier_watches (id,supplier_id,source_key,active,revision,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                        (watch.id, supplier_id, source, int(enabled), watch.revision, recorded_at, recorded_at))
                action = 'enabled' if enabled else 'disabled'
                connection.execute('INSERT INTO supplier_watch_events (id,watch_id,supplier_id,source_key,action,revision,reason,recorded_at) VALUES (?,?,?,?,?,?,?,?)',
                    (str(uuid4()), watch.id, supplier_id, source, action, watch.revision, reason, recorded_at))
                _audit(connection)
                connection.commit()
                return SupplierWatchMutation(action, watch)
            except BaseException:
                connection.rollback()
                raise

    def list(self, *, active_only=True, offset=0, limit=50):
        supplier_watch_window(offset, limit)
        if type(active_only) is not bool:
            raise ValidationError('İzleme etkinlik filtresi geçersiz.')
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = _audit(connection)
            values = []
            for watch in state.watches.values():
                if active_only and not watch.active:
                    continue
                runs = tuple(run for run in state.runs.values() if run.watch_id == watch.id)
                values.append(SupplierWatchSummary(watch, state.suppliers.suppliers[watch.supplier_id], runs[-1] if runs else None, len(runs)))
            values.sort(key=lambda value: (value.supplier.name_key, value.supplier.id, value.watch.source_key))
            return SupplierWatchPage(tuple(values[offset:offset + limit]), len(values), offset, limit)

    def show(self, watch_id, *, event_limit=20, run_limit=20, event_offset=0, run_offset=0):
        normalize_supplier_id(watch_id); supplier_watch_window(event_offset, event_limit); supplier_watch_window(run_offset, run_limit)
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = _audit(connection)
            watch = state.watches.get(watch_id)
            if watch is None:
                raise ValidationError('Tedarikçi izlemesi bulunamadı.')
            events = tuple(event for event in reversed(tuple(state.events.values())) if event.watch_id == watch_id)
            runs = tuple(run for run in reversed(tuple(state.runs.values())) if run.watch_id == watch_id)
            return SupplierWatchDetails(watch, state.suppliers.suppliers[watch.supplier_id],
                events[event_offset:event_offset + event_limit], runs[run_offset:run_offset + run_limit],
                len(events), len(runs), event_offset, run_offset, _source_state(state, watch.source_key))

    def run_show(self, run_id, *, item_limit=20, offset=0):
        normalize_supplier_id(run_id); supplier_watch_window(offset, item_limit)
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = _audit(connection)
            run = state.runs.get(run_id)
            if run is None:
                raise ValidationError('Tedarikçi izleme çalışması bulunamadı.')
            return _run_report(state, run, item_limit=item_limit, offset=offset)

    @staticmethod
    def notification_evidences(connection, notification_ids):
        state = _audit(connection)
        results = {}
        for identifier in notification_ids:
            run_id = state.notifications.get(identifier)
            if run_id is None:
                raise StorageError('Tedarikçi bildiriminin izleme kanıtı bulunamadı.')
            results[identifier] = _run_report(state, state.runs[run_id], item_limit=20)
        return results

    @staticmethod
    def notification_evidence(connection, notification_id):
        return SQLiteSupplierWatchRepository.notification_evidences(connection, (notification_id,))[notification_id]

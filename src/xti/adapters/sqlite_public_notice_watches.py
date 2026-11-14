"""Audited explicit organization scope and atomic public-catalog notifications."""

from bisect import bisect_right
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_public_notices import read_public_notice_history
from xti.domain.assets import ValidationError
from xti.domain.organizations import normalize_organization_id, normalize_organization_reason
from xti.domain.public_notices import notice_timestamp
from xti.domain.public_notice_watches import (
    PublicNoticeWatch, PublicNoticeWatchEvent, PublicNoticeWatchScopeMember,
    PublicNoticeWatchScope, PublicNoticeWatchRun, PublicNoticeWatchMutation,
    PublicNoticeWatchSummary, PublicNoticeWatchPage, PublicNoticeWatchDetails,
    PublicNoticeWatchRunReport, PublicNoticeWatchChangeEvidence,
    compare_public_notice_watch,
)

_MAX_WATCHES = 10_000
_MAX_HISTORY = 100_000
_MAX_SCOPE_BYTES = 4_000_000
_RUN_COLUMNS = tuple(PublicNoticeWatchRun.__dataclass_fields__)
_EVENT_COLUMNS = tuple(PublicNoticeWatchEvent.__dataclass_fields__)
_WATCH_COLUMNS = tuple(PublicNoticeWatch.__dataclass_fields__)
_COUNTS = ('matched_count', 'baseline_count', 'added_count', 'updated_count', 'removed_count', 'unchanged_count')


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'))


def _hash(value):
    return hashlib.sha256(_json(value).encode('ascii')).hexdigest()


def _positive(value):
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValueError('Invalid positive number')
    return value


def _window(limit, offset=0):
    if type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or not 0 <= offset <= 1_000_000:
        raise ValidationError('İzleme görünüm sınırı veya başlangıcı geçersiz.')


def _rows(connection, table, columns, order, maximum):
    rows = connection.execute(f'SELECT {columns} FROM {table} ORDER BY {order} LIMIT ?', (maximum + 1,)).fetchall()
    if len(rows) > maximum:
        raise ValueError('Watch history limit exceeded')
    if table in {'public_notice_watch_events', 'public_notice_watch_runs'}:
        # These append-only tables have never had deletion or INSERT OR IGNORE.
        # SQLite's transactional allocator also anchors a deleted final row.
        allocator = connection.execute('SELECT seq FROM sqlite_sequence WHERE name=?', (table,)).fetchone()
        allocated = allocator[0] if allocator else 0
        if (type(allocated) is not int or allocated != len(rows)
                or any(type(row[0]) is not int or row[0] != index for index, row in enumerate(rows, 1))):
            raise ValueError('Append-only history sequence or allocator differs')
    return rows


def _scope(organizations, organization_id, org_cutoff=None, link_cutoff=None):
    """Rebuild historical membership from audited event prefixes, not current links."""
    org_cutoff = max((event.sequence for event in organizations.events), default=0) if org_cutoff is None else org_cutoff
    link_cutoff = max((event.sequence for event in organizations.link_events), default=0) if link_cutoff is None else link_cutoff
    if (type(org_cutoff) is not int or type(link_cutoff) is not int or org_cutoff < 1 or link_cutoff < 0
            or org_cutoff not in {event.sequence for event in organizations.events}
            or (link_cutoff and link_cutoff not in {event.sequence for event in organizations.link_events})):
        raise ValueError('Invalid historical scope watermark')
    events = [event for event in organizations.events if event.organization_id == organization_id and event.sequence <= org_cutoff]
    if not events:
        raise ValueError('Organization absent at scope capture')
    last = events[-1]
    # Rename preserves the previous lifecycle, including renaming a revoked organization.
    active_event = next(event for event in reversed(events) if event.action != 'renamed')
    active = active_event.action != 'revoked'
    epoch = next(event.id for event in reversed(events) if event.action in {'added', 'reactivated'})
    latest, epochs = {}, {}
    for event in organizations.link_events:
        if event.sequence > link_cutoff or event.organization_id != organization_id or event.target.kind != 'domain':
            continue
        latest[event.link_id] = event
        if event.action in {'linked', 'reactivated'}:
            epochs[event.link_id] = event.id
    members = tuple(sorted((PublicNoticeWatchScopeMember(event.target.value, event.link_id, event.revision,
                        event.id, epochs[event.link_id]) for event in latest.values()
                        if active and event.action != 'revoked'), key=lambda member: (member.domain, member.link_id)))
    if len({member.domain for member in members}) != len(members):
        raise ValueError('Duplicate domain membership')
    return PublicNoticeWatchScope(organization_id, last.display_name, active, last.revision, last.id,
                                   epoch, org_cutoff, link_cutoff, members)


class _Catalog:
    """Bounded snapshot cache; no full copy per historical watch run is retained."""
    def __init__(self, history):
        self.runs = {run.id: run for run in history.runs}
        self.versions = {}
        for change in history.changes:
            sequence = self.runs[change.run_id].sequence
            sequences, values = self.versions.setdefault(change.notice.id, ([], []))
            sequences.append(sequence)
            values.append(None if change.action == 'removed' else change.notice)
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
    organizations: object
    source_history: object
    catalog: _Catalog
    watches: dict
    events: dict
    runs: dict
    scopes: dict
    notifications: dict


def _comparison(state, run):
    previous = state.runs.get(run.previous_run_id)
    return compare_public_notice_watch(
        state.catalog.snapshot(previous.source_run_id if previous else None),
        state.catalog.snapshot(run.source_run_id), scope=state.scopes[run.id],
        previous_scope=state.scopes[previous.id] if previous else None,
        same_watch_epoch=previous is not None and previous.watch_event_id == run.watch_event_id,
    )


def _result_hash(run, comparison):
    values = asdict(run)
    del values['result_sha256']
    return _hash({'run': values, 'comparison': asdict(comparison)})


def _audit(connection):
    """Validate immutable evidence and mutable state within the caller snapshot."""
    organizations = SQLiteOrganizationRepository._audit(connection)
    history = read_public_notice_history(connection)
    state = _State(organizations, history, _Catalog(history), {}, {}, {}, {}, {})
    try:
        for row in _rows(connection, 'public_notice_watches', ','.join(_WATCH_COLUMNS), 'id', _MAX_WATCHES):
            identifier, organization_id, active, revision, created, updated = row
            normalize_organization_id(identifier); normalize_organization_id(organization_id)
            if type(active) is not int or active not in {0, 1} or organization_id not in organizations.organizations:
                raise ValueError('Invalid watch identity or activity')
            _positive(revision); notice_timestamp(created); notice_timestamp(updated)
            state.watches[identifier] = PublicNoticeWatch(identifier, organization_id, bool(active), revision, created, updated)
        current = {}
        for row in _rows(connection, 'public_notice_watch_events', ','.join(_EVENT_COLUMNS), 'sequence', _MAX_HISTORY):
            event = PublicNoticeWatchEvent(*row)
            _positive(event.sequence); _positive(event.revision)
            normalize_organization_id(event.id); notice_timestamp(event.recorded_at)
            watch = state.watches.get(event.watch_id)
            before = current.get(event.watch_id)
            if (watch is None or event.organization_id != watch.organization_id
                    or event.reason != normalize_organization_reason(event.reason)
                    or event.action not in {'enabled', 'disabled'}
                    or event.revision != (before.revision + 1 if before else 1)
                    or (before is None and event.action != 'enabled')
                    or (before is not None and (before.active == (event.action == 'enabled') or event.recorded_at < before.updated_at))):
                raise ValueError('Invalid watch lifecycle')
            current[watch.id] = PublicNoticeWatch(watch.id, watch.organization_id, event.action == 'enabled',
                                    event.revision, before.created_at if before else event.recorded_at, event.recorded_at)
            state.events[event.id] = event
        if current != state.watches:
            raise ValueError('Watch differs from event history')
        previous_by_watch = {}
        previous_source_sequence = 0
        for row in _rows(connection, 'public_notice_watch_runs', ','.join(_RUN_COLUMNS) + ',scope_json', 'sequence', _MAX_HISTORY):
            run, raw_scope = PublicNoticeWatchRun(*row[:-1]), row[-1]
            _positive(run.sequence); normalize_organization_id(run.id); notice_timestamp(run.recorded_at)
            watch, event = state.watches.get(run.watch_id), state.events.get(run.watch_event_id)
            source = state.catalog.runs.get(run.source_run_id)
            previous = previous_by_watch.get(run.watch_id)
            if (watch is None or run.organization_id != watch.organization_id or event is None
                    or event.watch_id != watch.id or event.action != 'enabled'
                    or source is None or source.status != 'complete' or run.recorded_at != source.finished_at
                    or source.sequence < previous_source_sequence or source.finished_at < event.recorded_at
                    or run.previous_run_id != (previous.id if previous else None)
                    or (previous and (state.catalog.runs[previous.source_run_id].sequence >= source.sequence
                        or state.events[previous.watch_event_id].sequence > event.sequence))):
                raise ValueError('Invalid watch run source or lifecycle')
            if not isinstance(raw_scope, str) or len(raw_scope) > _MAX_SCOPE_BYTES:
                raise ValueError('Invalid scope payload')
            decoded = json.loads(raw_scope)
            scope = _scope(organizations, run.organization_id, decoded['organization_event_sequence'], decoded['link_event_sequence'])
            if raw_scope != _json(asdict(scope)) or run.scope_sha256 != _hash(asdict(scope)):
                raise ValueError('Scope differs from explicit historical membership')
            if previous and (scope.organization_event_sequence < state.scopes[previous.id].organization_event_sequence
                             or scope.link_event_sequence < state.scopes[previous.id].link_event_sequence):
                raise ValueError('Scope watermarks regressed')
            state.runs[run.id], state.scopes[run.id] = run, scope
            comparison = _comparison(state, run)
            if (any(type(getattr(run, key)) is not int or getattr(run, key) != getattr(comparison, key) for key in _COUNTS)
                    or run.result_sha256 != _result_hash(run, comparison)):
                raise ValueError('Watch result differs from source history')
            previous_by_watch[watch.id] = run
            previous_source_sequence = source.sequence
        notified = set()
        for row in _rows(connection, 'public_notice_watch_notifications',
                         'sequence,id,run_id,watch_id,organization_id,event_type,origin,created_at,read_at', 'sequence', _MAX_HISTORY):
            sequence, identifier, run_id, watch_id, organization_id, event_type, origin, created, read_at = row
            _positive(sequence); normalize_organization_id(identifier); notice_timestamp(created)
            if read_at is not None:
                notice_timestamp(read_at)
            run = state.runs.get(run_id)
            if (run is None or (watch_id, organization_id, created) != (run.watch_id, run.organization_id, run.recorded_at)
                    or event_type != 'public_notice_watch_changed' or origin != 'new'
                    or run.added_count + run.updated_count < 1 or run_id in notified):
                raise ValueError('Invalid notification evidence binding')
            notified.add(run_id)
            state.notifications[identifier] = run_id
        if notified != {run.id for run in state.runs.values() if run.added_count + run.updated_count > 0}:
            raise ValueError('Missing atomic notification')
        return state
    except (ValueError, TypeError, KeyError, AttributeError, StopIteration, OverflowError, RecursionError) as error:
        raise StorageError('Kamu olay izleme geçmişi veya kanıt bütünlüğü bozuk; kayıtlar değiştirilmedi.') from error


def validate_public_notice_watches(connection):
    state = _audit(connection)
    for watch in state.watches.values():
        if watch.active and len(_json(asdict(_scope(state.organizations, watch.organization_id)))) > _MAX_SCOPE_BYTES:
            raise StorageError('Kamu olay izleme kapsamı güvenli kayıt sınırını aşıyor; kapsamı daraltın.')


def process_public_notice_watches(connection, source_run_id):
    """Called after source insertion, before its receipt and transaction commit."""
    state = _audit(connection)
    source = state.catalog.runs.get(source_run_id)
    if (source is None or source.status != 'complete' or not connection.in_transaction
            or not state.source_history.runs or state.source_history.runs[-1].id != source_run_id):
        raise StorageError('İzleme yalnız aynı işlemdeki başarılı katalog çalışmasıyla ilerletilebilir.')
    for watch in sorted(state.watches.values(), key=lambda value: value.id):
        if not watch.active:
            continue
        previous = next((run for run in reversed(tuple(state.runs.values())) if run.watch_id == watch.id), None)
        if previous and previous.source_run_id == source_run_id:
            continue
        if len(state.runs) >= _MAX_HISTORY:
            raise StorageError('Kamu olay izleme geçmişi kapasitesi doldu.')
        scope = _scope(state.organizations, watch.organization_id)
        raw_scope = _json(asdict(scope))
        if len(raw_scope) > _MAX_SCOPE_BYTES:
            raise StorageError('Kamu olay izleme kapsamı güvenli kayıt sınırını aşıyor; kapsamı daraltın.')
        event = next(event for event in reversed(tuple(state.events.values())) if event.watch_id == watch.id)
        if source.finished_at < event.recorded_at:
            raise StorageError('Katalog çalışması izleme etkinleştirme zamanından önce olamaz.')
        run = PublicNoticeWatchRun(max((value.sequence for value in state.runs.values()), default=0) + 1,
                str(uuid4()), watch.id, watch.organization_id, source_run_id, event.id,
                previous.id if previous else None, source.finished_at, _hash(asdict(scope)), '', 0, 0, 0, 0, 0, 0)
        state.scopes[run.id] = scope
        comparison = _comparison(state, run)
        run = replace(run, **{key: getattr(comparison, key) for key in _COUNTS})
        run = replace(run, result_sha256=_result_hash(run, comparison))
        values = tuple(getattr(run, key) for key in _RUN_COLUMNS) + (raw_scope,)
        connection.execute(f"INSERT INTO public_notice_watch_runs ({','.join(_RUN_COLUMNS)},scope_json) VALUES ({','.join('?' for _ in values)})", values)
        state.runs[run.id] = run
        if run.added_count + run.updated_count:
            connection.execute('INSERT INTO public_notice_watch_notifications '
                '(sequence,id,run_id,watch_id,organization_id,event_type,origin,created_at,read_at) '
                "VALUES (?,?,?,?,?,'public_notice_watch_changed','new',?,NULL)",
                (next_notification_sequence(connection), str(uuid4()), run.id, watch.id, watch.organization_id, run.recorded_at))


def _heads(state):
    runs = state.source_history.runs
    return (runs[-1] if runs else None, next((run for run in reversed(runs) if run.status == 'complete'), None))


def _details(state, organization_id, event_limit, run_limit, run_offset=0, event_offset=0):
    organization = SQLiteOrganizationRepository._organization_by_id(state.organizations, organization_id)
    watch = next((watch for watch in state.watches.values() if watch.organization_id == organization_id), None)
    if watch is None:
        return None
    scope = _scope(state.organizations, organization_id)
    events = tuple(event for event in reversed(tuple(state.events.values())) if event.watch_id == watch.id)
    runs = tuple(run for run in reversed(tuple(state.runs.values())) if run.watch_id == watch.id)
    return PublicNoticeWatchDetails(watch, organization, tuple(member.domain for member in scope.members),
                                    events[event_offset:event_offset + event_limit], runs[run_offset:run_offset + run_limit],
                                    len(events), len(runs), *_heads(state), run_offset=run_offset, event_offset=event_offset)


def read_public_notice_watch_details(connection, organization_id, *, event_limit=20, run_limit=20, run_offset=0, event_offset=0):
    normalize_organization_id(organization_id); _window(event_limit, event_offset); _window(run_limit, run_offset)
    return _details(_audit(connection), organization_id, event_limit, run_limit, run_offset, event_offset)


def _run_report(state, run, *, item_limit, offset=0):
    comparison = _comparison(state, run)
    previous = state.runs.get(run.previous_run_id)
    watch = state.watches[run.watch_id]
    event = state.events[run.watch_event_id]
    historical_watch = replace(watch, active=True, revision=event.revision, updated_at=event.recorded_at)
    return PublicNoticeWatchRunReport(historical_watch, run, state.scopes[run.id],
        previous.source_run_id if previous else None, comparison.items[offset:offset + item_limit], len(comparison.items), offset,
        next((key for key, value in state.notifications.items() if value == run.id), None),
        comparison.baseline_domains, comparison.continuing_domains)


def read_complete_public_notice_watch(connection, organization_id, *, maximum_records):
    """All history for exactly one organization in the caller's read snapshot."""
    normalize_organization_id(organization_id)
    if type(maximum_records) is not int or maximum_records < 1:
        raise ValidationError('Tam izleme raporu sınırı geçersiz.')
    state = _audit(connection)
    details = _details(state, organization_id, maximum_records, maximum_records)
    if details is None:
        return None, ()
    count = details.total_event_count + details.total_run_count
    if count > maximum_records:
        raise ValidationError('Tam izleme geçmişi dışa aktarım sınırını aşıyor; dosya yazılmadı.')
    reports = []
    for run in details.runs:
        report = _run_report(state, run, item_limit=maximum_records)
        count += report.total_item_count + len(report.scope.members)
        if count > maximum_records or report.total_item_count != len(report.items):
            raise ValidationError('Tam izleme kanıtı dışa aktarım sınırını aşıyor; dosya yazılmadı.')
        reports.append(report)
    return details, tuple(reports)


class SQLitePublicNoticeWatchRepository:
    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    def configure(self, organization_id, *, enabled, reason, recorded_at):
        normalize_organization_id(organization_id)
        if type(enabled) is not bool:
            raise ValidationError('İzleme etkinliği doğru/yanlış olmalı.')
        reason = normalize_organization_reason(reason)
        notice_timestamp(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                state = _audit(connection)
                organization = SQLiteOrganizationRepository._organization_by_id(state.organizations, organization_id)
                if enabled and not organization.active:
                    raise ValidationError('Geri çekilmiş kuruluş için izleme etkinleştirilemez.')
                before = next((watch for watch in state.watches.values() if watch.organization_id == organization_id), None)
                if before is None and not enabled:
                    raise ValidationError('Kuruluş için kayıtlı kamu olay izlemesi bulunamadı.')
                if before is not None and before.active == enabled:
                    return PublicNoticeWatchMutation('unchanged', before)
                if recorded_at < (before.updated_at if before else organization.created_at):
                    raise ValidationError('İzleme zamanı son değişiklikten önce olamaz.')
                if len(state.events) >= _MAX_HISTORY or (before is None and len(state.watches) >= _MAX_WATCHES):
                    raise StorageError('Kamu olay izleme geçmişi kapasitesi doldu.')
                watch = PublicNoticeWatch(before.id if before else str(uuid4()), organization_id, enabled,
                    before.revision + 1 if before else 1, before.created_at if before else recorded_at, recorded_at)
                if before:
                    connection.execute('UPDATE public_notice_watches SET active=?, revision=?, updated_at=? WHERE id=?',
                                       (int(enabled), watch.revision, recorded_at, watch.id))
                else:
                    connection.execute('INSERT INTO public_notice_watches (id,organization_id,active,revision,created_at,updated_at) VALUES (?,?,?,?,?,?)',
                                       (watch.id, organization_id, int(enabled), watch.revision, recorded_at, recorded_at))
                action = 'enabled' if enabled else 'disabled'
                connection.execute('INSERT INTO public_notice_watch_events (id,watch_id,organization_id,action,revision,reason,recorded_at) VALUES (?,?,?,?,?,?,?)',
                                   (str(uuid4()), watch.id, organization_id, action, watch.revision, reason, recorded_at))
                _audit(connection)
                connection.commit()
                return PublicNoticeWatchMutation(action, watch)
            except BaseException:
                connection.rollback()
                raise

    def list(self, *, active_only=True, offset=0, limit=50):
        _window(limit, offset)
        if type(active_only) is not bool:
            raise ValidationError('İzleme etkinlik filtresi geçersiz.')
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = _audit(connection)
            summaries = []
            for watch in state.watches.values():
                if active_only and not watch.active:
                    continue
                details = _details(state, watch.organization_id, 1, 1)
                summaries.append(PublicNoticeWatchSummary(watch, details.organization.display_name, details.organization.active,
                                 len(details.effective_domains), details.runs[0] if details.runs else None, details.total_run_count))
            summaries.sort(key=lambda value: (value.organization_name.casefold(), value.watch.organization_id))
            return PublicNoticeWatchPage(tuple(summaries[offset:offset + limit]), len(summaries), offset, limit, *_heads(state))

    def show(self, organization_id, *, event_limit=20, run_limit=20, run_offset=0, event_offset=0):
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            details = read_public_notice_watch_details(connection, organization_id, event_limit=event_limit, run_limit=run_limit,
                                                       run_offset=run_offset, event_offset=event_offset)
            if details is None:
                raise ValidationError('Kuruluş için kayıtlı kamu olay izlemesi bulunamadı.')
            return details

    def run_show(self, run_id, *, item_limit=20, offset=0):
        normalize_organization_id(run_id); _window(item_limit, offset)
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = _audit(connection)
            run = state.runs.get(run_id)
            if run is None:
                raise ValidationError('Kamu olay izleme çalışması bulunamadı.')
            return _run_report(state, run, item_limit=item_limit, offset=offset)

    @staticmethod
    def notification_evidences(connection, notification_ids):
        state = _audit(connection)
        results = {}
        for identifier in notification_ids:
            run_id = state.notifications.get(identifier)
            if run_id is None:
                raise StorageError('Kamu olay bildiriminin izleme kanıtı bulunamadı.')
            run, scope = state.runs[run_id], state.scopes[run_id]
            comparison = _comparison(state, run)
            previous = state.runs.get(run.previous_run_id)
            results[identifier] = PublicNoticeWatchChangeEvidence(run.watch_id, run.organization_id, scope.organization_name,
                run.id, run.source_run_id, previous.source_run_id if previous else None, run.recorded_at, run.scope_sha256, scope,
                run.matched_count, run.baseline_count, run.added_count, run.updated_count, run.removed_count,
                comparison.items[:20], len(comparison.items), len(comparison.items) > 20)
        return results

    @staticmethod
    def notification_evidence(connection, notification_id):
        return SQLitePublicNoticeWatchRepository.notification_evidences(connection, (notification_id,))[notification_id]

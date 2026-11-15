"""Atomic general search watches with deduplicated, immutable evidence snapshots."""

from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
import re
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_global_search import read_global_search_snapshot
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.domain.assets import ValidationError
from xti.domain.engine import EngineContractError, reference_for_result
from xti.domain.global_saved_searches import (
    MAX_WATCHES, MAX_WATCH_EVENTS, MAX_WATCH_RUNS,
    MAX_WATCH_TOTAL_SNAPSHOT_BYTES, MAX_WATCH_SNAPSHOT_BYTES,
    GlobalSavedSearch, GlobalSavedSearchEvent, GlobalSavedSearchMutation,
    GlobalSavedSearchSnapshot, GlobalSavedSearchRun, GlobalSavedSearchRunReport,
    GlobalSavedSearchSummary, GlobalSavedSearchPage, GlobalSavedSearchDetails,
    canonical_json, definition_json, definition_from_json, make_match,
    snapshot_json, snapshot_from_json, difference, difference_sha256,
    parse_canonical_json, text_sha256, watch_id, watch_time, watch_reason,
    validate_snapshot_scope,
)


_SEARCH = 'id,name_key,display_name,query,kinds_json,include_inactive,active,revision,created_at,updated_at,mention_request_key'
_EVENT = 'sequence,id,search_id,revision,action,definition_json,definition_sha256,reason,recorded_at'
_RUN = ('sequence,id,search_id,event_id,snapshot_sha256,previous_run_id,executed_at,'
        'total_count,added_count,updated_count,unchanged_count,removed_count,diff_sha256')
_NOTICE = 'sequence,id,run_id,search_id,event_type,origin,created_at,read_at'


def _hash(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Invalid saved search hash')
    return value


def _time(value):
    if watch_time(value) != value:
        raise ValueError('Noncanonical saved search time')
    return value


def _page(offset, limit):
    if (type(offset) is not int or not 0 <= offset <= 1_000_000
            or type(limit) is not int or not 1 <= limit <= 500):
        raise ValidationError('Genel arama sayfası başlangıcı 0–1.000.000, sınırı 1–500 olmalı.')


def _rows(connection, table, columns, order, maximum):
    # All table and column names are fixed adapter constants.
    count = connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    if type(count) is not int or not 0 <= count <= maximum:
        raise StorageError('Kayıtlı genel arama geçmişi güvenli kayıt sınırını aşıyor.')
    return connection.execute(f'SELECT {columns} FROM {table} ORDER BY {order}').fetchall()


def _definition_row(row):
    if type(row[5]) is not int or row[5] not in (0, 1) or type(row[6]) is not int or row[6] not in (0, 1):
        raise ValueError('Invalid saved search flags')
    kinds = parse_canonical_json(row[4])
    if not isinstance(kinds, list):
        raise ValueError('Invalid saved search kinds')
    value = GlobalSavedSearch(*row[:4], tuple(kinds), bool(row[5]), bool(row[6]), *row[7:])
    return definition_from_json(definition_json(value))


def _identity(match):
    values = match.identity
    if len(values) % 2 or len(set(values[::2])) != len(values) // 2:
        raise ValueError('Invalid saved search identity fields')
    identity = dict(zip(values[::2], values[1::2]))
    if values != tuple(value for key in sorted(identity) for value in (key, identity[key])):
        raise ValueError('Noncanonical saved search identity')
    result = match.result
    if result.kind == 'social' and result.record_type == 'social_profile':
        semantic = parse_canonical_json(match.semantic_json)['semantic']
        expected = {'kind': 'social', 'record_type': 'social_profile',
                    'namespace': semantic.get('source_key'), 'watch_id': semantic.get('watch_id'),
                    'definition_sha256': semantic.get('definition_sha256'), 'platform': semantic.get('platform')}
        if identity != expected or identity['namespace'] not in {'maigret', 'sherlock'}:
            raise ValueError('Social tracking identity differs from frozen evidence')
        watch_id(identity['watch_id'])
        watch_id(result.record_id)
        _hash(identity['definition_sha256'])
        if not identity['platform'] or len(identity['platform']) > 200:
            raise ValueError('Invalid social platform')
        display = semantic.get('profile_url') or f"{semantic.get('username')} / {semantic.get('platform')}"
        if result.display_value != display:
            raise ValueError('Social profile evidence differs')
        fields = {'username': semantic.get('username'), 'profile_url': semantic.get('profile_url'),
                  'platform': semantic.get('platform')}
        if result.matched_field not in fields or fields[result.matched_field] != result.matched_value:
            raise ValueError('Social match does not belong to frozen profile')
    elif identity != reference_for_result(result).to_dict():
        raise ValueError('Saved search identity differs from source-qualified record')


@dataclass
class _State:
    searches: dict
    events: dict
    runs: dict
    snapshots: dict
    notices: dict


class SQLiteGlobalSavedSearchRepository:
    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    @classmethod
    def _audit(cls, connection):
        try:
            snapshot_size = connection.execute(
                'SELECT COALESCE(SUM(LENGTH(CAST(payload_json AS BLOB))),0), '
                'COALESCE(MAX(LENGTH(CAST(payload_json AS BLOB))),0) FROM global_search_snapshots'
            ).fetchone()
            event_size = connection.execute(
                'SELECT COALESCE(SUM(LENGTH(CAST(definition_json AS BLOB))),0) FROM global_saved_search_events'
            ).fetchone()[0]
            if (snapshot_size[0] > MAX_WATCH_TOTAL_SNAPSHOT_BYTES
                    or snapshot_size[1] > MAX_WATCH_SNAPSHOT_BYTES
                    or event_size > MAX_WATCH_TOTAL_SNAPSHOT_BYTES):
                raise StorageError('Kayıtlı genel arama kanıt geçmişi güvenli boyut sınırını aşıyor.')
            searches = {value.id: value for value in map(_definition_row,
                _rows(connection, 'global_saved_searches', _SEARCH, 'id', MAX_WATCHES))}
            events, latest_events, events_by_revision = {}, {}, {}
            for row in _rows(connection, 'global_saved_search_events', _EVENT, 'sequence', MAX_WATCH_EVENTS):
                sequence, identifier, search_id, revision, action, raw, digest, reason, at = row
                if type(sequence) is not int or sequence < 1 or identifier in events:
                    raise ValueError('Invalid definition event sequence')
                frozen = definition_from_json(raw)
                _time(at)
                if (watch_id(identifier) != identifier or search_id not in searches
                        or frozen.id != search_id or frozen.revision != revision
                        or frozen.updated_at != at or text_sha256(raw) != _hash(digest)):
                    raise ValueError('Definition event binding differs')
                previous = latest_events.get(search_id)
                if previous is None:
                    if action != 'added' or revision != 1 or not frozen.active or frozen.created_at != at:
                        raise ValueError('Definition history has no valid beginning')
                else:
                    old = previous.search
                    if (revision != old.revision + 1 or frozen.created_at != old.created_at
                            or frozen.name_key != old.name_key or at < previous.recorded_at):
                        raise ValueError('Definition revision chain differs')
                    if action == 'disabled':
                        if not old.active or frozen != replace(old, active=False, revision=revision, updated_at=at):
                            raise ValueError('Invalid disable transition')
                    elif action in {'updated', 'reactivated'}:
                        if not frozen.active or (action == 'updated') != old.active:
                            raise ValueError('Invalid active definition transition')
                        if action == 'updated' and replace(frozen, revision=old.revision, updated_at=old.updated_at) == old:
                            raise ValueError('Empty definition update')
                    else:
                        raise ValueError('Invalid definition event action')
                if (action == 'disabled' and watch_reason(reason) != reason) or (action != 'disabled' and reason != ''):
                    raise ValueError('Invalid definition event reason')
                value = GlobalSavedSearchEvent(sequence, identifier, search_id, revision, action, digest, reason, at, frozen)
                events[identifier] = value
                latest_events[search_id] = value
                events_by_revision[(search_id, revision)] = value
            if set(latest_events) != set(searches) or any(latest_events[key].search != value for key, value in searches.items()):
                raise ValueError('Current definition differs from lifecycle history')

            snapshots = {}
            for digest, raw in _rows(connection, 'global_search_snapshots', 'sha256,payload_json', 'sha256', MAX_WATCH_RUNS):
                if text_sha256(raw) != _hash(digest):
                    raise ValueError('Frozen search snapshot hash differs')
                snapshot = snapshot_from_json(raw)
                for match in snapshot.matches:
                    _identity(match)
                snapshots[digest] = snapshot

            @lru_cache(maxsize=2)
            def diff(prior, current):
                items = difference(snapshots[prior] if prior else None, snapshots[current])
                counts = tuple(sum(item.action == action for item in items)
                               for action in ('added', 'updated', 'unchanged', 'removed'))
                return counts, difference_sha256(items)

            runs, last_runs, expected_notices, used_snapshots = {}, {}, set(), set()
            validated_scopes = set()
            for row in _rows(connection, 'global_saved_search_runs', _RUN, 'sequence', MAX_WATCH_RUNS):
                run = GlobalSavedSearchRun(*row)
                if (type(run.sequence) is not int or run.sequence < 1 or run.id in runs
                        or watch_id(run.id) != run.id or run.search_id not in searches
                        or run.event_id not in events or run.snapshot_sha256 not in snapshots):
                    raise ValueError('Invalid saved search run identity')
                event = events[run.event_id]
                if (event.search_id != run.search_id or not event.search.active
                        or _time(run.executed_at) < event.recorded_at):
                    raise ValueError('Run definition or time differs')
                previous = last_runs.get(run.search_id)
                if previous is not None:
                    if (run.executed_at < previous.executed_at
                            or event.revision < events[previous.event_id].revision):
                        raise ValueError('Run history regressed')
                expected_previous = previous if previous is not None and previous.event_id == run.event_id else None
                if run.previous_run_id != (expected_previous.id if expected_previous else None):
                    raise ValueError('Run previous state is not the latest matching definition')
                snapshot = snapshots[run.snapshot_sha256]
                scope_key = (run.snapshot_sha256, run.event_id)
                if scope_key not in validated_scopes:
                    validate_snapshot_scope(snapshot, event.search)
                    validated_scopes.add(scope_key)
                counts, digest = diff(expected_previous.snapshot_sha256 if expected_previous else None, run.snapshot_sha256)
                stored_counts = (run.added_count, run.updated_count, run.unchanged_count, run.removed_count)
                if (any(type(value) is not int or value < 0 for value in (run.total_count, *stored_counts))
                        or counts != stored_counts or run.total_count != len(snapshot.matches)
                        or digest != _hash(run.diff_sha256)):
                    raise ValueError('Frozen search difference differs from recorded counts or hash')
                if expected_previous is not None and run.added_count + run.updated_count > 0:
                    expected_notices.add(run.id)
                runs[run.id] = run
                last_runs[run.search_id] = run
                used_snapshots.add(run.snapshot_sha256)
            if used_snapshots != set(snapshots):
                raise ValueError('Unlinked saved search snapshot')
            for run in runs.values():
                later = events_by_revision.get((run.search_id, events[run.event_id].revision + 1))
                if later is not None and run.executed_at > later.recorded_at:
                    raise ValueError('Run executed after its definition was replaced')

            notices, notification_runs, sequences = {}, set(), set()
            for row in _rows(connection, 'global_saved_search_notifications', _NOTICE, 'sequence', MAX_WATCH_RUNS):
                sequence, identifier, run_id, search_id, event_type, origin, created_at, read_at = row
                if (type(sequence) is not int or not 1 <= sequence <= 2**63 - 1 or sequence in sequences
                        or identifier in notices or run_id in notification_runs or run_id not in expected_notices
                        or watch_id(identifier) != identifier or runs[run_id].search_id != search_id
                        or event_type != 'global_saved_search_changed' or origin != 'new'
                        or created_at != runs[run_id].executed_at):
                    raise ValueError('Invalid saved search notification binding')
                if read_at is not None:
                    _time(read_at)
                notices[identifier] = row
                notification_runs.add(run_id)
                sequences.add(sequence)
            if notification_runs != expected_notices:
                raise ValueError('A required saved search notification is missing')
            return _State(searches, events, runs, snapshots, notices)
        except (TypeError, ValueError, KeyError, IndexError, AttributeError, OverflowError, RecursionError) as error:
            raise StorageError('Kayıtlı genel arama tanımı, geçmişi veya kanıt bağı bozuk; işlem durduruldu.') from error

    @staticmethod
    def _insert_event(connection, search, action, reason):
        raw = definition_json(search)
        connection.execute(
            'INSERT INTO global_saved_search_events '
            '(id,search_id,revision,action,definition_json,definition_sha256,reason,recorded_at) VALUES (?,?,?,?,?,?,?,?)',
            (str(uuid4()), search.id, search.revision, action, raw, text_sha256(raw), reason, search.updated_at),
        )

    def _upsert_in_transaction(self, connection, state, *, name_key, display_name, query,
                               kinds, include_inactive, recorded_at, mention_request_key=None,
                               identifier=None):
        old = next((value for value in state.searches.values() if value.name_key == name_key), None)
        if old is not None and old.mention_request_key != mention_request_key:
            raise ValidationError('Yönetilen içerik izlemesi serbest metin aramasına dönüştürülemez.')
        if old is not None and recorded_at < old.updated_at:
            raise ValidationError('Arama güncelleme zamanı mevcut geçmişten eski olamaz.')
        value = GlobalSavedSearch(old.id if old else identifier or str(uuid4()), name_key, display_name, query,
            kinds, include_inactive, True, old.revision + 1 if old else 1,
            old.created_at if old else recorded_at, recorded_at, mention_request_key)
        value = definition_from_json(definition_json(value))
        if old is not None and replace(value, revision=old.revision, updated_at=old.updated_at) == old:
            return GlobalSavedSearchMutation('unchanged', old)
        if len(state.events) >= MAX_WATCH_EVENTS or (old is None and len(state.searches) >= MAX_WATCHES):
            raise StorageError('Kayıtlı genel arama tanım geçmişi güvenli sınırına ulaştı.')
        action = 'added' if old is None else 'updated' if old.active else 'reactivated'
        row = (value.id, value.name_key, value.display_name, value.query, canonical_json(value.kinds),
               int(value.include_inactive), int(value.active), value.revision, value.created_at, value.updated_at, value.mention_request_key)
        if old is None:
            connection.execute(f'INSERT INTO global_saved_searches ({_SEARCH}) VALUES ({",".join("?" for _ in row)})', row)
        else:
            connection.execute('UPDATE global_saved_searches SET display_name=?,query=?,kinds_json=?,include_inactive=?,active=1,revision=?,updated_at=?,mention_request_key=? WHERE id=?',
                (value.display_name, value.query, canonical_json(value.kinds), int(value.include_inactive),
                 value.revision, value.updated_at, value.mention_request_key, value.id))
        self._insert_event(connection, value, action, '')
        return GlobalSavedSearchMutation(action, value)

    def upsert(self, *, name_key, display_name, query, kinds, include_inactive, recorded_at,
               mention_request_key=None):
        with self._storage._connection() as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                state = self._audit(connection)
                result = self._upsert_in_transaction(connection, state, name_key=name_key,
                    display_name=display_name, query=query, kinds=kinds,
                    include_inactive=include_inactive, recorded_at=recorded_at,
                    mention_request_key=mention_request_key)
                self._audit(connection)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def disable(self, search_id, *, reason, recorded_at):
        search_id, reason = watch_id(search_id), watch_reason(reason)
        recorded_at = watch_time(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                state = self._audit(connection)
                old = state.searches.get(search_id)
                if old is None:
                    raise ValidationError('Kayıtlı genel arama bulunamadı.')
                if not old.active:
                    return GlobalSavedSearchMutation('unchanged', old)
                if recorded_at < old.updated_at:
                    raise ValidationError('Arama kapatma zamanı mevcut geçmişten eski olamaz.')
                if len(state.events) >= MAX_WATCH_EVENTS:
                    raise StorageError('Kayıtlı genel arama tanım geçmişi güvenli sınırına ulaştı.')
                value = replace(old, active=False, revision=old.revision + 1, updated_at=recorded_at)
                connection.execute('UPDATE global_saved_searches SET active=0,revision=?,updated_at=? WHERE id=?',
                                   (value.revision, value.updated_at, value.id))
                self._insert_event(connection, value, 'disabled', reason)
                self._audit(connection)
                connection.commit()
                return GlobalSavedSearchMutation('disabled', value)
            except BaseException:
                connection.rollback()
                raise

    def list(self, *, active_only, offset, limit):
        _page(offset, limit)
        if type(active_only) is not bool:
            raise ValidationError('Etkin arama filtresi boolean olmalı.')
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = self._audit(connection)
            values = sorted((value for value in state.searches.values() if value.active or not active_only),
                            key=lambda value: (value.name_key, value.id))
            items = []
            for search in values[offset:offset + limit]:
                runs = sorted((run for run in state.runs.values() if run.search_id == search.id), key=lambda run: run.sequence)
                items.append(GlobalSavedSearchSummary(search, len(runs), runs[-1] if runs else None))
            return GlobalSavedSearchPage(tuple(items), len(values), offset, limit, offset + len(items) < len(values))

    def details(self, search_id, *, event_offset, event_limit, run_offset, run_limit):
        search_id = watch_id(search_id)
        _page(event_offset, event_limit)
        _page(run_offset, run_limit)
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = self._audit(connection)
            search = state.searches.get(search_id)
            if search is None:
                raise ValidationError('Kayıtlı genel arama bulunamadı.')
            events = sorted((event for event in state.events.values() if event.search_id == search_id), key=lambda event: event.sequence, reverse=True)
            runs = sorted((run for run in state.runs.values() if run.search_id == search_id), key=lambda run: run.sequence, reverse=True)
            return GlobalSavedSearchDetails(search, tuple(events[event_offset:event_offset + event_limit]),
                tuple(runs[run_offset:run_offset + run_limit]), len(events), len(runs), event_offset, event_limit,
                run_offset, run_limit, event_offset + event_limit < len(events), run_offset + run_limit < len(runs))

    @staticmethod
    def _report(state, run, *, offset, limit):
        snapshot = state.snapshots[run.snapshot_sha256]
        prior = state.runs.get(run.previous_run_id)
        items = difference(state.snapshots[prior.snapshot_sha256] if prior else None, snapshot)
        selected = items[offset:offset + limit]
        notification_id = next((identifier for identifier, row in state.notices.items() if row[2] == run.id), None)
        return GlobalSavedSearchRunReport(state.events[run.event_id].search, run, selected, snapshot.coverage,
            len(items), offset, limit, offset + len(selected) < len(items), notification_id)

    def _run_in_transaction(self, connection, state, search_id, *, executed_at, offset, limit,
                            run_id=None, mention_run_id=None, news_run_ids=None):
        search = state.searches.get(search_id)
        existing = state.runs.get(run_id) if run_id is not None else None
        if existing is not None:
            prior = state.events[existing.event_id].search
            if (search is None or existing.search_id != search_id
                    or (prior.query, prior.kinds, prior.include_inactive, prior.mention_request_key)
                    != (search.query, search.kinds, search.include_inactive, search.mention_request_key)):
                raise ValidationError('Aynı arama işlem kimliği farklı kapsam için kullanılamaz.')
            return self._report(state, existing, offset=offset, limit=limit)
        if search is None or not search.active:
            raise ValidationError('Etkin kayıtlı genel arama bulunamadı.')
        event = max((value for value in state.events.values() if value.search_id == search_id), key=lambda value: value.revision)
        latest = max((value for value in state.runs.values() if value.search_id == search_id), key=lambda value: value.sequence, default=None)
        if executed_at < max(event.recorded_at, latest.executed_at if latest else event.recorded_at):
            raise ValidationError('Arama çalışma zamanı mevcut geçmişten eski olamaz.')
        if len(state.runs) >= MAX_WATCH_RUNS:
            raise StorageError('Kayıtlı genel arama çalışma geçmişi güvenli sınırına ulaştı.')
        # User arguments and the saved definition have already been
        # validated. Errors here concern stored source evidence or the
        # bounded snapshot, and must reach the CLI as storage failures.
        try:
            scope = ({'mention_request_key': search.mention_request_key, 'mention_run_id': mention_run_id}
                     if search.mention_request_key is not None else {})
            if news_run_ids is not None:
                scope['news_run_ids'] = news_run_ids
            reader = read_global_search_snapshot(connection, self._storage.path, search.query,
                kinds=search.kinds, include_inactive=search.include_inactive, checked_at=executed_at, tracking=True, **scope)
            matches = tuple(make_match(result,
                tuple(value for key in sorted(identity) for value in (key, identity[key])), semantic)
                for result, identity, semantic in reader.observations)
            snapshot = GlobalSavedSearchSnapshot(matches, tuple(reader.coverage))
            raw = snapshot_json(snapshot)
            snapshot = snapshot_from_json(raw)
            validate_snapshot_scope(snapshot, search)
            for match in snapshot.matches:
                _identity(match)
        except (TypeError, ValueError, KeyError, IndexError, AttributeError,
                OverflowError, RecursionError, EngineContractError) as error:
            raise StorageError('Genel arama kaynak kanıtı bozuk veya güvenli boyut sınırını aşıyor; çalışma kaydedilmedi.') from error
        digest = text_sha256(raw)
        if digest not in state.snapshots:
            size = connection.execute('SELECT COALESCE(SUM(LENGTH(CAST(payload_json AS BLOB))),0) FROM global_search_snapshots').fetchone()[0]
            if size + len(raw.encode('utf-8')) > MAX_WATCH_TOTAL_SNAPSHOT_BYTES:
                raise StorageError('Kayıtlı genel arama kanıt geçmişi güvenli boyut sınırına ulaştı.')
            connection.execute('INSERT INTO global_search_snapshots (sha256,payload_json) VALUES (?,?)', (digest, raw))
        previous = latest if latest is not None and latest.event_id == event.id else None
        items = difference(state.snapshots[previous.snapshot_sha256] if previous else None, snapshot)
        counts = tuple(sum(item.action == action for item in items)
                       for action in ('added', 'updated', 'unchanged', 'removed'))
        identifier = run_id or str(uuid4())
        row = (identifier, search_id, event.id, digest, previous.id if previous else None,
               executed_at, len(matches), *counts, difference_sha256(items))
        cursor = connection.execute(f'INSERT INTO global_saved_search_runs ({_RUN.split(",", 1)[1]}) VALUES ({",".join("?" for _ in row)})', row)
        run = GlobalSavedSearchRun(cursor.lastrowid, *row)
        notice_id = None
        if previous is not None and counts[0] + counts[1] > 0:
            notice_id = str(uuid4())
            notice = (next_notification_sequence(connection), notice_id, identifier, search_id,
                      'global_saved_search_changed', 'new', executed_at, None)
            connection.execute(f'INSERT INTO global_saved_search_notifications ({_NOTICE}) VALUES ({",".join("?" for _ in notice)})', notice)
            state.notices[notice_id] = notice
        state.runs[identifier] = run
        state.snapshots[digest] = snapshot
        result = self._report(state, run, offset=offset, limit=limit)
        return result

    def run(self, search_id, *, executed_at, offset, limit, run_id=None):
        search_id, executed_at = watch_id(search_id), watch_time(executed_at)
        if run_id is not None:
            run_id = watch_id(run_id)
        _page(offset, limit)
        with self._storage._connection() as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                state = self._audit(connection)
                search = state.searches.get(search_id)
                if search is not None and search.mention_request_key is not None:
                    raise ValidationError(
                        'Bu içerik izlemesini firma grubu yönetir; '
                        "'./xti mentions groups run' veya 'resume' kullanın."
                    )
                result = self._run_in_transaction(connection, state, search_id,
                    executed_at=executed_at, offset=offset, limit=limit, run_id=run_id)
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def run_details(self, run_id, *, offset, limit):
        run_id = watch_id(run_id)
        _page(offset, limit)
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = self._audit(connection)
            run = state.runs.get(run_id)
            if run is None:
                raise ValidationError('Kayıtlı genel arama çalışması bulunamadı.')
            return self._report(state, run, offset=offset, limit=limit)

    @classmethod
    def notification_evidences(cls, connection, notification_ids, *, item_limit=50):
        _page(0, item_limit)
        state = cls._audit(connection)
        result = {}
        for identifier in notification_ids:
            row = state.notices.get(identifier)
            if row is None:
                raise StorageError('Genel arama bildiriminin tarihî çalışma kanıtı bulunamadı.')
            result[identifier] = cls._report(state, state.runs[row[2]], offset=0, limit=item_limit)
        return result

    @classmethod
    def notification_evidence(cls, connection, notification_id, *, item_limit=50):
        return cls.notification_evidences(connection, (notification_id,), item_limit=item_limit)[notification_id]

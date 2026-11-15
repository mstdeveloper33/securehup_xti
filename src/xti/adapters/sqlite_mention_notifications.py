"""Reuse atomic saved-search differences and inbox notices for exact source scopes."""

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid5

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
from xti.adapters.sqlite_mentions import read_mentions_catalog
from xti.domain.assets import ValidationError
from xti.domain.global_saved_searches import (
    MAX_WATCHES, MAX_WATCH_EVENTS, MAX_WATCH_RUNS, MAX_WATCH_SNAPSHOT_BYTES,
    MAX_WATCH_TOTAL_SNAPSHOT_BYTES, GlobalSavedSearch, GlobalSavedSearchSnapshot,
    definition_json, snapshot_json, watch_name, watch_time,
)
from xti.domain.global_search import GlobalSearchCoverage
from xti.domain.mentions import mention_uuid, request_key, validate_request


_WATCH_NAMESPACE = UUID('745de0b5-a534-4070-9b15-7b6c0fbd4bba')
_RUN_NAMESPACE = UUID('e66d24bb-c6a6-4f43-9df8-78e18f1f4180')
_COLUMNS = 'operation_id,group_id,request_key,mention_run_id,search_run_id,created_at'


def mention_watch_id(group_id, scope):
    return str(uuid5(_WATCH_NAMESPACE, group_id + ':' + scope))


def mention_notification_run_id(operation_id):
    return str(uuid5(_RUN_NAMESPACE, operation_id))


def _watch_name(group_id, request):
    identifier = mention_watch_id(group_id, request_key(request))
    return watch_name(f'İçerik grubu {group_id[:8]} / {request.target.name[:40]} / {identifier[:8]}')


class SQLiteMentionNotificationBridge:
    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)
        self._watches = SQLiteGlobalSavedSearchRepository(path)

    def validate(self, *, group_id, requests):
        mention_uuid(group_id)
        if not isinstance(requests, tuple) or len(requests) > 20:
            raise ValidationError('Bildirim ön kontrolü en çok 20 dondurulmuş hedef isteği almalı.')
        for request in requests:
            validate_request(request)
        scopes = tuple(map(request_key, requests))
        if len(set(scopes)) != len(scopes):
            raise ValidationError('Bildirim ön kontrolünde aynı sorgu kapsamı yinelenemez.')
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = self._watches._audit(connection)
            sources = {run.id: run for run in read_mentions_catalog(connection).runs}
            bindings = self._audit_bindings(connection, state, sources)
            missing, minimum_definition_bytes = 0, 0
            for request, scope in zip(requests, scopes):
                identifier = mention_watch_id(group_id, scope)
                search = state.searches.get(identifier)
                if search is not None:
                    if (not search.active or search.mention_request_key != scope or search.query != scope
                            or search.kinds != ('mention',) or search.include_inactive):
                        raise ValidationError('Grubun içerik izlemesi kapalı veya kapsamı değiştirilmiş; yeni sorgu başlatılmadı.')
                else:
                    name = _watch_name(group_id, request)
                    if any(value.name_key == name.casefold() for value in state.searches.values()):
                        raise ValidationError('Otomatik içerik izleme adı başka bir kayıt tarafından kullanılıyor; yeni sorgu başlatılmadı.')
                    missing += 1
                    # UTC timestamps contain at least this much text; future fractional
                    # seconds and source content may need additional room after HTTP.
                    at = '1970-01-01T00:00:00+00:00'
                    minimum_definition_bytes += len(definition_json(GlobalSavedSearch(identifier,
                        name.casefold(), name, scope, ('mention',), False, True, 1, at, at, scope)).encode('utf-8'))
            if (len(state.searches) + missing > MAX_WATCHES
                    or len(state.events) + missing > MAX_WATCH_EVENTS
                    or len(state.runs) + len(requests) > MAX_WATCH_RUNS
                    or len(bindings) + len(requests) > MAX_WATCH_RUNS):
                raise StorageError('İçerik bildirim geçmişinde yeni hedefler için yeterli kayıt kapasitesi yok; yeni sorgu başlatılmadı.')
            if requests:
                minimum_snapshot = len(snapshot_json(GlobalSavedSearchSnapshot((),
                    (GlobalSearchCoverage('mention', 'tavily', 0, 0),))).encode('utf-8'))
                snapshot_bytes = connection.execute(
                    'SELECT COALESCE(SUM(LENGTH(CAST(payload_json AS BLOB))),0) FROM global_search_snapshots'
                ).fetchone()[0]
                definition_bytes = connection.execute(
                    'SELECT COALESCE(SUM(LENGTH(CAST(definition_json AS BLOB))),0) FROM global_saved_search_events'
                ).fetchone()[0]
                if (minimum_snapshot > MAX_WATCH_SNAPSHOT_BYTES
                        or snapshot_bytes + minimum_snapshot * len(requests) > MAX_WATCH_TOTAL_SNAPSHOT_BYTES
                        or definition_bytes + minimum_definition_bytes > MAX_WATCH_TOTAL_SNAPSHOT_BYTES):
                    raise StorageError('İçerik bildirim kanıtında asgari kayıt payı yok; yeni sorgu başlatılmadı.')
            # This checks known lower bounds, not a reservation or a guarantee for
            # unknown future results. Notify repeats the full validation atomically.

    @staticmethod
    def _audit_bindings(connection, state, sources):
        count = connection.execute('SELECT COUNT(*) FROM mention_notification_operations').fetchone()[0]
        if count > MAX_WATCH_RUNS:
            raise StorageError('İçerik bildirim bağlantısı kapasitesi aşıldı.')
        if connection.execute(
            'SELECT 1 FROM mention_notification_operations WHERE length(operation_id)!=36 '
            'OR length(group_id)!=36 OR length(request_key)!=64 OR length(mention_run_id)!=36 '
            'OR length(search_run_id)!=36 OR length(created_at)>64 LIMIT 1'
        ).fetchone():
            raise StorageError('İçerik bildirim bağlantısı beklenen alan sınırlarını aşıyor.')
        bindings = {}
        try:
            for row in connection.execute('SELECT ' + _COLUMNS + ' FROM mention_notification_operations'):
                operation_id, group_id, scope, source_id, search_run_id, created_at = row
                mention_uuid(operation_id)
                mention_uuid(group_id)
                source = sources[source_id]
                run = state.runs[search_run_id]
                frozen = state.events[run.event_id].search
                snapshot = state.snapshots[run.snapshot_sha256]
                if (source.status != 'complete' or source.response is None
                        or request_key(source.request) != scope
                        or search_run_id != mention_notification_run_id(operation_id)
                        or run.search_id != mention_watch_id(group_id, scope)
                        or frozen.mention_request_key != scope or frozen.query != scope
                        or frozen.kinds != ('mention',) or frozen.include_inactive
                        or created_at != run.executed_at or watch_time(created_at) != created_at
                        or datetime.fromisoformat(created_at) < datetime.fromisoformat(source.finished_at)
                        or len(snapshot.coverage) != 1
                        or snapshot.coverage[0].latest_run_id != source.id
                        or snapshot.coverage[0].latest_run_status != 'complete'
                        or snapshot.coverage[0].latest_success_run_id != source.id
                        or snapshot.coverage[0].latest_run_at != source.finished_at
                        or snapshot.coverage[0].latest_success_at != source.finished_at):
                    raise ValueError('Mention notification scope differs')
                bindings[operation_id] = row
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise StorageError('İçerik bildiriminin kaynak/iş/kapsam bağı bozuk.') from error
        return bindings

    def notify(self, *, group_id, request, mention_run_id, operation_id, executed_at):
        group_id, mention_run_id, operation_id = map(mention_uuid, (group_id, mention_run_id, operation_id))
        validate_request(request)
        executed_at = watch_time(executed_at)
        scope = request_key(request)
        search_id = mention_watch_id(group_id, scope)
        run_id = mention_notification_run_id(operation_id)
        with self._storage._connection() as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                state = self._watches._audit(connection)
                catalog = read_mentions_catalog(connection)
                sources = {run.id: run for run in catalog.runs}
                bindings = self._audit_bindings(connection, state, sources)
                previous = bindings.get(operation_id)
                if previous is not None:
                    if previous[1:4] != (group_id, scope, mention_run_id):
                        raise ValidationError('Aynı içerik bildirim işi farklı hedef veya kaynak için kullanılamaz.')
                    return self._watches._report(state, state.runs[previous[4]], offset=0, limit=50)
                source = sources.get(mention_run_id)
                if (source is None or source.status != 'complete' or source.response is None
                        or source.request != request or request_key(source.request) != scope):
                    raise ValidationError('İçerik bildirimi başarılı ve aynı kapsamdaki kaynak çalışmasını gerektirir.')
                if datetime.fromisoformat(executed_at) < datetime.fromisoformat(source.finished_at):
                    raise ValidationError('İçerik bildirimi kaynak çalışmasından önce kaydedilemez.')
                # A retry must not compare old evidence against a newer baseline.
                later_bindings = (row for row in bindings.values() if row[1:3] == (group_id, scope))
                if any(sources[row[3]].sequence >= source.sequence for row in later_bindings):
                    raise ValidationError('Bu kaynak çalışması zaten işlendi veya daha yeni bildirim kanıtının gerisinde.')
                search = state.searches.get(search_id)
                if search is None:
                    name = _watch_name(group_id, request)
                    mutation = self._watches._upsert_in_transaction(connection, state,
                        name_key=name.casefold(), display_name=name, query=scope, kinds=('mention',),
                        include_inactive=False, recorded_at=executed_at,
                        mention_request_key=scope, identifier=search_id)
                    if mutation.saved_search.id != search_id:
                        raise ValidationError('Otomatik içerik izleme adı başka bir kayıt tarafından kullanılıyor.')
                    state = self._watches._audit(connection)
                    search = state.searches[search_id]
                if (not search.active or search.mention_request_key != scope or search.query != scope
                        or search.kinds != ('mention',) or search.include_inactive):
                    raise ValidationError('Grubun içerik izlemesi kapalı veya kapsamı değiştirilmiş; bildirim yapılmadı.')
                latest = max((run for run in state.runs.values() if run.search_id == search_id),
                             key=lambda run: run.sequence, default=None)
                if latest is not None:
                    coverage = state.snapshots[latest.snapshot_sha256].coverage
                    prior_source = sources.get(coverage[0].latest_run_id) if len(coverage) == 1 else None
                    if prior_source is None or prior_source.sequence >= source.sequence:
                        raise ValidationError('İzleme başlangıcı kaynak çalışmasından daha yeni veya aynı; eski kanıt tekrar karşılaştırılmadı.')
                if run_id in state.runs:
                    raise StorageError('Bildirim işi için ayrılmış çalışma kimliği başka bir çalışmada kullanılmış.')
                report = self._watches._run_in_transaction(connection, state, search_id,
                    executed_at=executed_at, offset=0, limit=50, run_id=run_id, mention_run_id=mention_run_id)
                connection.execute('INSERT INTO mention_notification_operations (' + _COLUMNS
                    + ') VALUES (?,?,?,?,?,?)', (operation_id, group_id, scope, mention_run_id, report.run.id, executed_at))
                self._audit_bindings(connection, state, sources)
                connection.commit()
                return report
            except BaseException:
                connection.rollback()
                raise

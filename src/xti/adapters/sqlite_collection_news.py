"""Selected news watches use frozen collection receipts, one atomic local write."""

from uuid import NAMESPACE_URL, uuid5

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_receipts import (
    operation_context, record_collection_step_receipt, canonical_time, _row,
)
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository, _page
from xti.adapters.sqlite_news import _audit as audit_news
from xti.domain.assets import ValidationError
from xti.domain.collection import CollectionWatchTarget
from xti.domain.collection_history import history_uuid, history_sha256
from xti.domain.global_saved_searches import GLOBAL_SEARCH_WATCH_VERSION
from xti.domain.news import NEWS_SOURCES


def search_run_id(step_id):
    return str(uuid5(NAMESPACE_URL, 'xti:collection-news-search:' + history_uuid(step_id)))


def _matches(search, target):
    return (search.id == target.watch_id and search.display_name == target.display_name
            and search.query == target.query and search.kinds == ('news',)
            and not search.include_inactive and search.mention_request_key is None
            and target.kind == 'news' and target.match_mode == 'global' and target.platforms == ())


def validate_search_target(connection, target):
    state = SQLiteGlobalSavedSearchRepository._audit(connection)
    search = state.searches.get(target.watch_id)
    event = max((value for value in state.events.values() if value.search_id == target.watch_id),
                key=lambda value: value.revision, default=None)
    if (search is None or not search.active or not _matches(search, target)
            or event is None or event.id != target.search_event_id):
        raise ValidationError('Seçilen haber araması değişmiş veya kapatılmış; güncel seçimle yeni toplama başlatın.')
    return state


def news_source_cutoffs(connection, session_id):
    """Only successful steps in this bounded linear ancestry supply cutoffs.

    Callers audit the session before using this helper. Receipt validation also
    calls it during that audit, so this helper must never recurse into _details.
    """
    session = _row(connection, 'collection_sessions', session_id)
    rows = connection.execute(
        "SELECT t.source,r.news_run_id FROM collection_sessions s "
        "JOIN collection_session_steps t ON t.session_id=s.id "
        "JOIN collection_step_receipts r ON r.step_id=t.id "
        "WHERE s.root_id=? AND s.generation<=? AND t.kind='news_refresh' "
        "AND t.status='complete' AND r.result_status='complete'",
        (session['root_id'], session['generation']),
    ).fetchmany(4)
    if len(rows) > 3 or len({row[0] for row in rows}) != len(rows):
        raise StorageError('Haber toplama zincirinde yinelenen başarılı kaynak kanıtı var.')
    cutoffs = dict(rows)
    if set(cutoffs) != {source.key for source in NEWS_SOURCES}:
        return None
    return cutoffs


def news_dependencies_failed(connection, session_id):
    if news_source_cutoffs(connection, session_id) is not None:
        return False
    states = [row[0] for row in connection.execute(
        "SELECT status FROM collection_session_steps WHERE session_id=? AND kind='news_refresh'",
        (session_id,))]
    return (not any(status in {'pending', 'running'} for status in states)
            and any(status in {'failed', 'partial', 'interrupted', 'skipped'} for status in states))


def validate_search_receipt(connection, unit, definition, step, result_id, result_status):
    if (unit.kind != 'search_watch' or unit.source != 'local' or unit.watch is None
            or unit.contract_version != GLOBAL_SEARCH_WATCH_VERSION
            or unit.step_key != 'search-watch:' + unit.watch.watch_id
            or unit.watch.watch_id not in definition.search_watch_ids
            or result_status != 'complete' or result_id != search_run_id(step['id'])):
        raise StorageError('Haber araması makbuzu dondurulmuş toplama tanımıyla uyuşmuyor.')
    state = SQLiteGlobalSavedSearchRepository._audit(connection)
    run = state.runs.get(result_id)
    cutoffs = news_source_cutoffs(connection, step['session_id'])
    if (run is None or cutoffs is None or run.event_id != unit.watch.search_event_id
            or not _matches(state.events[run.event_id].search, unit.watch)
            or step['started_at'] is None or run.executed_at < step['started_at']):
        raise StorageError('Haber araması kaynakları veya dondurulmuş izleme kanıtı eksik.')
    sources = {run.id: run for run in audit_news(connection).runs}
    coverage = state.snapshots[run.snapshot_sha256].coverage
    if len(coverage) != 3 or {item.source for item in coverage} != set(cutoffs):
        raise StorageError('Haber aramasının kaynak kapsamı eksik.')
    for item in coverage:
        source = sources.get(cutoffs[item.source])
        if (source is None or source.source_key != item.source or source.status != 'complete'
                or item.kind != 'news' or item.latest_run_id != source.id
                or item.latest_success_run_id != source.id or item.latest_run_status != 'complete'
                or item.latest_run_at != source.finished_at or item.latest_success_at != source.finished_at
                or run.executed_at < source.finished_at):
            raise StorageError('Haber araması bildirimi toplama kaynak kesitiyle uyuşmuyor.')
    counters = {key: getattr(run, key) for key in run.__dataclass_fields__ if key.endswith('_count')}
    return run.executed_at, counters


class SQLiteCollectionNewsSearches:
    def __init__(self, path):
        self._storage = SQLiteAssetRepository(path)
        self._watches = SQLiteGlobalSavedSearchRepository(path)

    def plan(self, search_ids):
        if not isinstance(search_ids, tuple) or len(search_ids) > 50 or len(set(search_ids)) != len(search_ids):
            raise ValidationError('Haber araması seçimi en çok 50 farklı kimlik içermeli.')
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = self._watches._audit(connection)
            result = []
            for identifier in search_ids:
                history_uuid(identifier)
                search = state.searches.get(identifier)
                if (search is None or not search.active or search.kinds != ('news',)
                        or search.include_inactive or search.mention_request_key is not None):
                    raise ValidationError('Toplama için etkin ve yalnız haber kapsamındaki kayıtlı aramalar seçilmeli.')
                event = max((value for value in state.events.values() if value.search_id == search.id),
                            key=lambda value: value.revision)
                result.append(CollectionWatchTarget(search.id, search.display_name, search.query, 'news', 'global',
                                                    search_event_id=event.id))
            return tuple(result)

    def ready(self, operation):
        from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            session, _, unit, _ = operation_context(connection, operation, allow_pending=True)
            if unit.kind != 'search_watch':
                raise ValidationError('Haber araması toplama adımı gerekli.')
            SQLiteCollectionHistoryRepository._details(connection, session['id'])
            return news_source_cutoffs(connection, session['id']) is not None

    def run(self, target, *, operation, executed_at, limit=100):
        from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
        executed_at = canonical_time(executed_at)
        _page(0, limit)
        history_uuid(operation.session_id)
        history_uuid(operation.step_id)
        history_sha256(operation.target_sha256)
        with self._storage._connection() as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                details = SQLiteCollectionHistoryRepository._details(connection, operation.session_id)
                step = next((value for value in details.steps if value.id == operation.step_id), None)
                unit = next((value for value in details.session.plan.units if step and value.step_key == step.step_key), None)
                if (step is None or unit is None or unit.watch != target
                        or step.target_sha256 != operation.target_sha256 or operation.depends_on_step_id is not None):
                    raise ValidationError('Haber araması işlem kimliği dondurulmuş adımla uyuşmuyor.')
                previous = next((value for value in details.receipts if value.step_id == step.id), None)
                if previous is not None:
                    if previous.result_kind != 'saved_search_run' or previous.result_status != 'complete':
                        raise ValidationError('Haber araması işleminin sonucu uyuşmuyor.')
                    state = self._watches._audit(connection)
                    return self._watches._report(state, state.runs[previous.result_id], offset=0, limit=limit)
                _, _, unit, plan = operation_context(connection, operation)
                SQLiteCollectionHistoryRepository._current_origin(connection, plan)
                state = validate_search_target(connection, target)
                cutoffs = news_source_cutoffs(connection, operation.session_id)
                if cutoffs is None:
                    raise ValidationError('Haber araması üç kaynağın başarılı toplama kanıtını gerektirir.')
                sources = {value.id: value for value in audit_news(connection).runs}
                if any(executed_at < sources[identifier].finished_at for identifier in cutoffs.values()):
                    raise ValidationError('Haber araması kaynak toplamasından önce kaydedilemez.')
                latest = max((value for value in state.runs.values() if value.search_id == target.watch_id),
                             key=lambda value: value.sequence, default=None)
                if latest is not None:
                    for item in state.snapshots[latest.snapshot_sha256].coverage:
                        prior = sources.get(item.latest_run_id)
                        if prior is not None and prior.sequence > sources[cutoffs[item.source]].sequence:
                            raise ValidationError('Haber araması daha yeni kaynak kanıtıyla çalıştırılmış; eski toplama kesiti yeniden karşılaştırılmadı.')
                identifier = search_run_id(operation.step_id)
                if identifier in state.runs:
                    raise StorageError('Toplama araması çalışma kimliğinin makbuzu eksik.')
                report = self._watches._run_in_transaction(connection, state, target.watch_id,
                    executed_at=executed_at, offset=0, limit=limit, run_id=identifier, news_run_ids=cutoffs)
                record_collection_step_receipt(connection, operation, result_kind='saved_search_run',
                                               result_id=report.run.id, result_status='complete')
                connection.commit()
                return report
            except BaseException:
                connection.rollback()
                raise

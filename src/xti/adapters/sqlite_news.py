"""Atomic rolling publisher feeds with replay-audited immutable evidence."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_receipts import (
    validate_news_operation, record_collection_step_receipt,
)
from xti.domain.assets import ValidationError
from xti.domain.news import (
    NEWS_POLICY, NEWS_SOURCES, MAX_FEED_ARTICLES, MAX_NEWS_ARTICLES,
    MAX_NEWS_RUNS, MAX_NEWS_SNAPSHOT_BYTES, MAX_NEWS_TOTAL_BYTES,
    NewsCatalog, NewsChange, NewsFeed, NewsRefreshReport, NewsRun,
    NewsSourceStatus, NewsStatusReport, NewsStoredArticle,
    article_json, article_sha256, articles_from_json, articles_json,
    news_source, news_text, news_time, validate_feed,
)


_RUN_COLUMNS = tuple(NewsRun.__dataclass_fields__)
_RUN_SELECT = ','.join(_RUN_COLUMNS)
_ARTICLE_SELECT = ('id,source_key,record_json,state_sha256,first_run_id,last_change_run_id,'
                   'last_seen_run_id,first_seen_at,last_changed_at,last_seen_at')


def _digest(value):
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def _chain(previous, run):
    return _digest(json.dumps([NEWS_POLICY, previous, asdict(run)],
                             sort_keys=True, ensure_ascii=True, separators=(',', ':')))


def _sha(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Invalid news digest')
    return value


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError('Invalid news run identifier')
    return value


def _times(started, finished):
    news_time(started)
    news_time(finished)
    if datetime.fromisoformat(started) > datetime.fromisoformat(finished):
        raise ValidationError('Haber çalışmasının bitişi başlangıcından önce olamaz.')


def _fetch_time(fetched, started, finished):
    news_time(fetched)
    value = datetime.fromisoformat(fetched)
    if not (datetime.fromisoformat(started) - timedelta(minutes=15)
            <= value <= datetime.fromisoformat(finished) + timedelta(minutes=15)):
        raise ValidationError('Haber toplama zamanı çalışma aralığıyla uyuşmuyor.')


def _page(limit, offset):
    if (type(limit) is not int or not 1 <= limit <= 500
            or type(offset) is not int or not 0 <= offset <= 1_000_000):
        raise ValidationError('Haber görünüm sınırı 1–500, başlangıcı 0–1.000.000 olmalı.')


def _row(record):
    article = record.article
    return (article.id, article.source_key, article_json(article), record.state_sha256,
            record.first_run_id, record.last_change_run_id, record.last_seen_run_id,
            record.first_seen_at, record.last_changed_at, record.last_seen_at)


def _advance(current, run, entries):
    changes = []
    for article, state in entries:
        old = current.get(article.id)
        if old is None:
            changes.append(NewsChange('added', None, article))
            record = NewsStoredArticle(article, state, run.id, run.id, run.id,
                                       run.finished_at, run.finished_at, run.finished_at)
        elif old.state_sha256 != state:
            changes.append(NewsChange('updated', old.article, article))
            record = replace(old, article=article, state_sha256=state,
                             last_change_run_id=run.id, last_seen_run_id=run.id,
                             last_changed_at=run.finished_at, last_seen_at=run.finished_at)
        else:
            changes.append(NewsChange('unchanged', old.article, article))
            record = replace(old, last_seen_run_id=run.id, last_seen_at=run.finished_at)
        current[article.id] = record
    return tuple(changes)


@dataclass
class _State:
    runs: tuple[NewsRun, ...]
    current: dict[str, NewsStoredArticle]
    snapshots: dict[str, tuple[str, str]]
    chain: str | None
    changes: tuple[NewsChange, ...]


def _audit(connection, *, selected_run=None):
    """Read every source from one caller-owned transaction without repairing it."""
    try:
        limits = connection.execute(
            'SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(payload_json AS BLOB))),0),'
            'COALESCE(MAX(LENGTH(CAST(payload_json AS BLOB))),0) FROM news_snapshots'
        ).fetchone()
        if (limits[0] > MAX_NEWS_RUNS or limits[1] > MAX_NEWS_TOTAL_BYTES
                or limits[2] > MAX_NEWS_SNAPSHOT_BYTES):
            raise ValueError('News snapshot capacity')
        projection_size = connection.execute(
            'SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(record_json AS BLOB))),0) FROM news_articles'
        ).fetchone()
        if projection_size[0] > MAX_NEWS_ARTICLES or projection_size[1] > MAX_NEWS_TOTAL_BYTES:
            raise ValueError('News projection capacity')
        if connection.execute(
            'SELECT 1 FROM news_runs WHERE LENGTH(error)>2000 OR LENGTH(id)>36 '
            'OR LENGTH(started_at)>64 OR LENGTH(finished_at)>64 OR LENGTH(fetched_at)>64 LIMIT 1'
        ).fetchone():
            raise ValueError('News run metadata capacity')
        raw_runs = connection.execute(
            f'SELECT {_RUN_SELECT},chain_sha256 FROM news_runs ORDER BY sequence'
        ).fetchmany(MAX_NEWS_RUNS + 1)
        if len(raw_runs) > MAX_NEWS_RUNS:
            raise ValueError('News run capacity')
        snapshots = {}
        for sha, source, payload in connection.execute('SELECT sha256,source_key,payload_json FROM news_snapshots'):
            news_source(source)
            if _sha(sha) != _digest(payload):
                raise ValueError('News snapshot digest differs')
            snapshots[sha] = (source, payload)

        @lru_cache(maxsize=2)
        def entries(sha):
            source, payload = snapshots[sha]
            parsed_source, articles = articles_from_json(payload)
            if source != parsed_source:
                raise ValueError('Snapshot publisher differs')
            return tuple((article, article_sha256(article)) for article in articles)

        runs, current, used = [], {}, set()
        previous, sequence, finished = None, 0, None
        selected_changes = ()
        for row in raw_runs:
            run = NewsRun(*row[:-1])
            _uuid(run.id)
            news_source(run.source_key)
            _times(run.started_at, run.finished_at)
            at = datetime.fromisoformat(run.finished_at)
            if (type(run.sequence) is not int or run.sequence <= sequence
                    or (finished is not None and at < finished)):
                raise ValueError('News sequence or time differs')
            counts = (run.article_count, run.added_count, run.updated_count, run.unchanged_count)
            if any(type(value) is not int or not 0 <= value <= MAX_FEED_ARTICLES for value in counts):
                raise ValueError('Invalid news counts')
            changes = ()
            if run.status == 'failed':
                if any(counts) or any(value is not None for value in
                                     (run.fetched_at, run.content_sha256, run.snapshot_sha256)):
                    raise ValueError('Failed news run has feed evidence')
                news_text(run.error, maximum=2000)
            elif run.status == 'complete':
                if run.error is not None:
                    raise ValueError('Complete news run has an error')
                _fetch_time(run.fetched_at, run.started_at, run.finished_at)
                _sha(run.content_sha256)
                _sha(run.snapshot_sha256)
                if snapshots[run.snapshot_sha256][0] != run.source_key:
                    raise ValueError('Run and snapshot publisher differ')
                feed_entries = entries(run.snapshot_sha256)
                changes = _advance(current, run, feed_entries)
                added = sum(change.action == 'added' for change in changes)
                updated = sum(change.action == 'updated' for change in changes)
                if counts != (len(feed_entries), added, updated, len(feed_entries) - added - updated):
                    raise ValueError('News result counts differ from evidence')
                if len(current) > MAX_NEWS_ARTICLES:
                    raise ValueError('Retained news capacity')
                used.add(run.snapshot_sha256)
            else:
                raise ValueError('Invalid news run state')
            if _sha(row[-1]) != _chain(previous, run):
                raise ValueError('News history chain differs')
            if run.id == selected_run:
                selected_changes = changes
            runs.append(run)
            previous, sequence, finished = row[-1], run.sequence, at
        if used != snapshots.keys():
            raise ValueError('Unowned news snapshot')
        projection = dict((row[0], row) for row in connection.execute(
            f'SELECT {_ARTICLE_SELECT} FROM news_articles ORDER BY id'))
        if len(projection) != len(current) or any(projection.get(key) != _row(value)
                                                  for key, value in current.items()):
            raise ValueError('News projection differs from immutable history')
        return _State(tuple(runs), current, snapshots, previous, selected_changes)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError,
            RecursionError, UnicodeError) as error:
        raise StorageError('Haber geçmişi, kaynak bağı veya kanıt bütünlüğü bozuk; kayıtlar değiştirilmedi.') from error


def _catalog(state):
    sources = []
    for source in NEWS_SOURCES:
        runs = tuple(run for run in state.runs if run.source_key == source.key)
        complete = next((run for run in reversed(runs) if run.status == 'complete'), None)
        sources.append(NewsSourceStatus(source, runs[-1] if runs else None, complete,
                       sum(item.article.source_key == source.key for item in state.current.values()), len(runs)))
    return NewsCatalog(tuple(state.current[key] for key in sorted(state.current)), tuple(sources))


def read_news_catalog(connection, *, through_run_ids=None):
    state = _audit(connection)
    if through_run_ids is None:
        return _catalog(state)
    if (not isinstance(through_run_ids, dict)
            or set(through_run_ids) != {source.key for source in NEWS_SOURCES}):
        raise ValidationError('Haber kesiti üç yayıncı için açık kaynak çalışması gerektirir.')
    by_id = {run.id: run for run in state.runs}
    cutoffs = {}
    for source, identifier in through_run_ids.items():
        run = by_id.get(identifier)
        if run is None or run.source_key != source or run.status != 'complete':
            raise ValidationError('Haber kesitinin başarılı kaynak çalışma bağı geçersiz.')
        cutoffs[source] = run.sequence
    current, runs = {}, []
    for run in state.runs:
        if run.sequence > cutoffs[run.source_key]:
            continue
        runs.append(run)
        if run.status == 'complete':
            _, payload = state.snapshots[run.snapshot_sha256]
            _, articles = articles_from_json(payload)
            _advance(current, run, tuple((article, article_sha256(article)) for article in articles))
    return _catalog(_State(tuple(runs), current, state.snapshots, state.chain, ()))


class SQLiteNewsRepository:
    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    def validate(self):
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            _audit(connection)

    def validate_operation(self, source_key, operation):
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = _audit(connection)
            self._capacity(state, state.runs[-1].finished_at if state.runs else '0001-01-01T00:00:00+00:00')
            validate_news_operation(connection, operation, source_key=source_key)

    @staticmethod
    def _capacity(state, finished_at):
        if len(state.runs) >= MAX_NEWS_RUNS:
            raise StorageError('Haber çalışma geçmişi kapasitesi doldu; kayıtlar değiştirilmedi.')
        if state.runs and datetime.fromisoformat(finished_at) < datetime.fromisoformat(state.runs[-1].finished_at):
            raise ValidationError('Haber çalışması son kayıttan daha eski bir zamanda yazılamaz.')

    @staticmethod
    def _insert_run(connection, run, previous):
        values = tuple(getattr(run, name) for name in _RUN_COLUMNS) + (_chain(previous, run),)
        connection.execute(f'INSERT INTO news_runs ({_RUN_SELECT},chain_sha256) '
                           f'VALUES ({",".join("?" for _ in values)})', values)

    def apply(self, feed: NewsFeed, *, started_at, finished_at, limit=20, offset=0, operation=None):
        _page(limit, offset)
        _times(started_at, finished_at)
        validate_feed(feed)
        _fetch_time(feed.fetched_at, started_at, finished_at)
        payload = articles_json(feed.source_key, feed.articles)
        digest = _digest(payload)
        with self._storage._connection() as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                state = _audit(connection)
                validate_news_operation(connection, operation, source_key=feed.source_key)
                self._capacity(state, finished_at)
                byte_count = sum(len(item[1]) for item in state.snapshots.values())
                if digest not in state.snapshots and byte_count + len(payload) > MAX_NEWS_TOTAL_BYTES:
                    raise StorageError('Haber kanıt kapasitesi doldu; kayıtlar değiştirilmedi.')
                entries = tuple((article, article_sha256(article)) for article in sorted(feed.articles, key=lambda item: item.id))
                added = sum(article.id not in state.current for article, _ in entries)
                updated = sum(article.id in state.current and state.current[article.id].state_sha256 != sha
                              for article, sha in entries)
                if len(state.current) + added > MAX_NEWS_ARTICLES:
                    raise StorageError('Saklanan haber kapasitesi doldu; kayıtlar değiştirilmedi.')
                run = NewsRun(state.runs[-1].sequence + 1 if state.runs else 1, str(uuid4()),
                    feed.source_key, 'complete', started_at, finished_at, feed.fetched_at,
                    feed.content_sha256, digest, len(entries), added, updated,
                    len(entries) - added - updated, None)
                changes = _advance(state.current, run, entries)
                if digest not in state.snapshots:
                    connection.execute('INSERT INTO news_snapshots VALUES (?,?,?)', (digest, feed.source_key, payload))
                self._insert_run(connection, run, state.chain)
                for article, _ in entries:
                    row = _row(state.current[article.id])
                    connection.execute(f'INSERT INTO news_articles ({_ARTICLE_SELECT}) VALUES '
                        '(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                        'source_key=excluded.source_key,record_json=excluded.record_json,state_sha256=excluded.state_sha256,'
                        'first_run_id=excluded.first_run_id,last_change_run_id=excluded.last_change_run_id,'
                        'last_seen_run_id=excluded.last_seen_run_id,first_seen_at=excluded.first_seen_at,'
                        'last_changed_at=excluded.last_changed_at,last_seen_at=excluded.last_seen_at', row)
                record_collection_step_receipt(connection, operation, result_kind='news_run',
                                               result_id=run.id, result_status=run.status)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return NewsRefreshReport(run, changes[offset:offset + limit], len(changes), offset)

    def record_failure(self, source_key, *, started_at, finished_at, error, operation=None):
        news_source(source_key)
        _times(started_at, finished_at)
        news_text(error, maximum=2000)
        with self._storage._connection() as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                state = _audit(connection)
                validate_news_operation(connection, operation, source_key=source_key)
                self._capacity(state, finished_at)
                run = NewsRun(state.runs[-1].sequence + 1 if state.runs else 1, str(uuid4()),
                              source_key, 'failed', started_at, finished_at, None, None, None, 0, 0, 0, 0, error)
                self._insert_run(connection, run, state.chain)
                record_collection_step_receipt(connection, operation, result_kind='news_run',
                                               result_id=run.id, result_status=run.status)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return run

    def catalog(self):
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            return read_news_catalog(connection)

    def status(self, *, source_key=None, limit=20, offset=0):
        _page(limit, offset)
        if source_key is not None:
            news_source(source_key)
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = _audit(connection)
            sources = tuple(source for source in _catalog(state).sources
                            if source_key is None or source.source.key == source_key)
            runs = tuple(run for run in reversed(state.runs) if source_key is None or run.source_key == source_key)
            return NewsStatusReport(sources, runs[offset:offset + limit], len(runs), offset)

    def run_show(self, identifier, *, limit=20, offset=0):
        _page(limit, offset)
        try:
            _uuid(identifier)
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationError('Haber çalışma kimliği geçersiz.') from error
        with self._storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            state = _audit(connection, selected_run=identifier)
            run = next((run for run in state.runs if run.id == identifier), None)
            if run is None:
                raise ValidationError('Haber çalışması bulunamadı.')
            return NewsRefreshReport(run, state.changes[offset:offset + limit], len(state.changes), offset)

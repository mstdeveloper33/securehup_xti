"""An explicitly provisioned sidecar queue with immutable requests and bounded event chains."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from uuid import uuid4

from xti.adapters.sqlite import StorageError
from xti.domain.assets import ValidationError
from xti.domain.collection_history import history_uuid
from xti.domain.engine_jobs import (
    EngineJob, EngineJobClaim, EngineJobError, EngineJobPayload,
    ENGINE_JOB_TERMINAL, canonical_json, digest, job_time, parse_result_json, request_key,
    payload_request, parse_job_payload, result_json,
)
from xti.domain.source_jobs import SourceJobPayload, result_for
from xti.domain.source_job_events import replay_source_job
from xti.ports.jobs import WorkerBusyError


ENGINE_JOB_DATABASE_NAME = 'engine-jobs.sqlite3'
ENGINE_JOB_SCHEMA_VERSION = 4
MAX_ENGINE_JOBS = 10_000
MAX_HISTORY_OFFSET = 2_147_483_647
_APPLICATION_ID = 0x58544A31
_JOBS_DDL = """CREATE TABLE engine_jobs (
    id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
    request_json TEXT NOT NULL, request_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
)"""
_EVENTS_DDL_V1 = """CREATE TABLE engine_job_events (
    job_id TEXT NOT NULL REFERENCES engine_jobs(id), ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 3),
    kind TEXT NOT NULL CHECK(kind IN ('claimed','session','finished','cancelled')),
    event_json TEXT NOT NULL, event_sha256 TEXT NOT NULL,
    PRIMARY KEY(job_id, ordinal)
)"""
_EVENTS_DDL_V2 = _EVENTS_DDL_V1.replace('BETWEEN 1 AND 3', 'BETWEEN 1 AND 12').replace(
    "'claimed','session','finished','cancelled'",
    "'claimed','session','finished','cancelled','step_started','step_finished','cancel_requested'")
_EVENTS_DDL = _EVENTS_DDL_V2.replace('BETWEEN 1 AND 12', 'BETWEEN 1 AND 16')
_JOB_COLUMNS = 'id, request_key, request_json, request_sha256, payload_json, payload_sha256, created_at'
_EVENT_FIELDS = {'kind', 'recorded_at', 'token', 'session_id', 'status', 'result_json',
                 'result_sha256', 'error_code', 'previous_sha256'}


def _private_file(path: Path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise StorageError('Motor iş dosyası tek bağlantılı, yalnız sahibine açık normal dosya olmalı.')
    return info


class SQLiteEngineJobRepository:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser().absolute()

    @staticmethod
    def _schema(connection, *, allow_dirty=False):
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        if (connection.execute('PRAGMA application_id').fetchone() != (_APPLICATION_ID,)
                or version not in {1, 2, 3, 4}
                or connection.execute('PRAGMA journal_mode').fetchone() != ('delete',)):
            raise StorageError('Motor işi şeması desteklenmiyor; otomatik geçiş yapılmadı.')
        objects = set(connection.execute(
            "SELECT name, type, sql FROM sqlite_master WHERE sql IS NOT NULL"
        ).fetchall())
        expected = {('engine_jobs', 'table', _JOBS_DDL),
                    ('engine_job_events', 'table', {1: _EVENTS_DDL_V1, 2: _EVENTS_DDL_V2, 3: _EVENTS_DDL, 4: _EVENTS_DDL}[version])}
        if version == 4:
            from xti.adapters.engine_job_catalog import OBJECTS, check_guard
            expected |= OBJECTS
        if objects != expected:
            raise StorageError('Motor işi şeması beklenen yapıyla uyuşmuyor.')
        if version == 4:
            if not allow_dirty:
                check_guard(connection)
            return
        SQLiteEngineJobRepository._integrity(connection)
        if connection.execute('SELECT COUNT(*) FROM engine_jobs').fetchone()[0] > MAX_ENGINE_JOBS:
            raise StorageError('Motor işi geçmişi güvenli kayıt sınırını aşıyor.')

    @staticmethod
    def _integrity(connection):
        if (connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]
                or connection.execute('PRAGMA foreign_key_check').fetchall()):
            raise StorageError('Motor işi veritabanı bütünlük denetimini geçemedi.')

    @contextmanager
    def _connection(self, *, readonly=False, allow_dirty=False):
        connection = None
        try:
            before = _private_file(self.path)
            for suffix in ('-journal', '-wal', '-shm'):
                companion = self.path.with_name(self.path.name + suffix)
                if companion.exists() or companion.is_symlink():
                    _private_file(companion)
            connection = sqlite3.connect(self.path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'),
                                         uri=True, timeout=5, isolation_level=None)
            after = _private_file(self.path)
            if (before.st_ino, before.st_dev) != (after.st_ino, after.st_dev):
                raise StorageError('Motor işi dosyası işlem sırasında değişti.')
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA foreign_keys=ON')
            self._schema(connection, allow_dirty=allow_dirty)
            yield connection
        except (OSError, sqlite3.Error) as error:
            raise StorageError('Motor işi kayıt alanına erişilemedi; dosya, izin ve disk durumunu kontrol edin.') from error
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _publish(temporary: Path, destination: Path):
        with temporary.open('rb') as handle:
            os.fsync(handle.fileno())
        os.link(temporary, destination)
        temporary.unlink()
        descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def initialize(self) -> None:
        """Explicit creation only; existing paths, backups and databases are never overwritten."""
        temporary = None
        try:
            if self.path.exists() or self.path.is_symlink():
                raise StorageError('Motor işi dosyası zaten var; mevcut kayıtların üzerine kurulum yapılamaz.')
            if not self.path.parent.is_dir():
                raise StorageError('Motor işi kayıt klasörünü önce açıkça oluşturun.')
            descriptor, name = tempfile.mkstemp(prefix='.engine-jobs-', dir=self.path.parent)
            os.close(descriptor)
            temporary = Path(name)
            connection = sqlite3.connect(temporary)
            try:
                connection.execute('PRAGMA journal_mode=DELETE')
                connection.execute('PRAGMA synchronous=FULL')
                connection.execute('PRAGMA foreign_keys=ON')
                connection.execute('BEGIN IMMEDIATE')
                connection.execute(_JOBS_DDL)
                connection.execute(_EVENTS_DDL)
                if ENGINE_JOB_SCHEMA_VERSION >= 4:
                    from xti.adapters.engine_job_catalog import install
                    install(connection)
                connection.execute(f'PRAGMA application_id={_APPLICATION_ID}')
                connection.execute(f'PRAGMA user_version={ENGINE_JOB_SCHEMA_VERSION}')
                connection.commit()
                self._schema(connection)
            finally:
                connection.close()
            self._publish(temporary, self.path)
        except (OSError, sqlite3.Error) as error:
            raise StorageError('Motor işi kayıt alanı oluşturulamadı; mevcut dosyalar korunur.') from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _read(self, connection, job_id: str, ancestry=(), *, verify_catalog=True) -> tuple[EngineJob, str | None, str | None]:
        result = self._original(connection, job_id, ancestry, verify_catalog=verify_catalog)
        if verify_catalog and connection.execute('PRAGMA user_version').fetchone()[0] == 4:
            from xti.adapters.engine_job_catalog import verify
            verify(connection, result[0])
        return result

    def _original(self, connection, job_id, ancestry, *, verify_catalog):
        if job_id in ancestry or len(ancestry) > 32:
            raise StorageError('Motor işi tekrar zinciri doğrulanamadı veya 32 tekrar sınırını aşıyor.')
        row = connection.execute(f'SELECT {_JOB_COLUMNS} FROM engine_jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise EngineJobError('not_found', 'Motor işi bulunamadı.')
        try:
            payload = parse_job_payload(row[4])
            if (payload_request(payload) != row[2]
                    or digest(row[2]) != row[3] or digest(row[4]) != row[5]):
                raise ValueError('immutable request mismatch')
            job = EngineJob(history_uuid(row[0]), request_key(row[1]), row[3], row[5], payload,
                            'queued', job_time(row[6]))
            token, previous_hash, previous_time = None, None, job.created_at
            events = connection.execute(
                'SELECT ordinal, kind, event_json, event_sha256 FROM engine_job_events '
                'WHERE job_id=? ORDER BY ordinal LIMIT 17', (job_id,),
            ).fetchall()
            if isinstance(payload, SourceJobPayload):
                if connection.execute('PRAGMA user_version').fetchone()[0] not in {2, 3, 4}:
                    raise ValueError('Source job schema')
                if payload.retry_of:
                    try:
                        parent = self._read(connection, payload.retry_of, (*ancestry, job_id), verify_catalog=verify_catalog)[0]
                    except EngineJobError as error:
                        raise ValueError('Retry parent missing') from error
                    if (not isinstance(parent.payload, SourceJobPayload) or parent.status not in ENGINE_JOB_TERMINAL - {'complete'}
                            or parent.payload.plan != payload.plan
                            or datetime.fromisoformat(job.created_at) < datetime.fromisoformat(parent.finished_at)
                            or (parent.status == 'interrupted' and not payload.allow_uncertain)):
                        raise ValueError('Retry parent binding')
                    from xti.domain.source_jobs import reusable_steps
                    reusable = reusable_steps(parent, version=payload.version)
                    if payload.reused != reusable:
                        raise ValueError('Retry receipt binding')
                return replay_source_job(job, events)
            if len(events) > 3:
                raise ValueError('event capacity')
            for expected, (ordinal, kind, encoded, event_hash) in enumerate(events, 1):
                if kind not in {'claimed', 'session', 'finished', 'cancelled'}:
                    raise ValueError('Profile event kind')
                if (ordinal != expected or not isinstance(encoded, str) or len(encoded) > 1_100_000
                        or digest(encoded) != event_hash):
                    raise ValueError('event digest')
                event = json.loads(encoded)
                if (not isinstance(event, dict) or set(event) != _EVENT_FIELDS
                        or canonical_json(event) != encoded or event['kind'] != kind
                        or event['previous_sha256'] != previous_hash):
                    raise ValueError('event shape')
                at = job_time(event['recorded_at'])
                if datetime.fromisoformat(at) < datetime.fromisoformat(previous_time):
                    raise ValueError('event time')
                status, session_id = event['status'], event['session_id']
                result, result_hash, error = event['result_json'], event['result_sha256'], event['error_code']
                if (result is None) != (result_hash is None):
                    raise ValueError('result digest presence')
                parsed_result = None
                if result is not None:
                    parsed_result = parse_result_json(result)
                    if digest(result) != result_hash:
                        raise ValueError('result digest')
                if kind == 'claimed':
                    if (job.status != 'queued' or status != 'running' or session_id is not None
                            or result is not None or error is not None):
                        raise ValueError('claim lifecycle')
                    token = history_uuid(event['token'])
                    job = replace(job, status='running', started_at=at)
                elif kind == 'session':
                    if (job.status != 'running' or job.collection_session_id is not None
                            or event['token'] != token or status != 'running'
                            or result is not None or error is not None):
                        raise ValueError('session lifecycle')
                    job = replace(job, collection_session_id=history_uuid(session_id))
                elif kind == 'cancelled':
                    if (job.status != 'queued' or status != 'cancelled' or event['token'] is not None
                            or session_id is not None or result is not None
                            or error not in {'cancelled_by_caller', 'restored_uncertain'}):
                        raise ValueError('cancel lifecycle')
                    job = replace(job, status='cancelled', finished_at=at, error_code=error)
                else:
                    if (job.status != 'running' or event['token'] != token
                            or session_id != job.collection_session_id
                            or status not in ENGINE_JOB_TERMINAL - {'cancelled'}):
                        raise ValueError('finish lifecycle')
                    if result is None:
                        if status != 'interrupted' or error not in {'execution_uncertain', 'recovered_uncertain'}:
                            raise ValueError('uncertain finish')
                    elif (error is not None or parsed_result['collection_status'] != status
                          or parsed_result['collection_session_id'] != session_id
                          or parsed_result['asset_value'] != payload.definition.asset_value):
                        raise ValueError('result linkage')
                    if parsed_result is not None:
                        expected_steps = [(unit.step_key, unit.source) for unit in payload.frozen_plan.units]
                        actual_steps = [(step['step_key'], step['source']) for step in parsed_result['steps']]
                        if actual_steps != expected_steps:
                            raise ValueError('result frozen plan linkage')
                    job = replace(job, status=status, finished_at=at, result=parsed_result, error_code=error)
                previous_hash, previous_time = event_hash, at
            return job, token, previous_hash
        except (ValidationError, ValueError, TypeError, RecursionError, KeyError, AttributeError) as error:
            raise StorageError('Motor işi geçmişi veya sonuç bağı doğrulanamadı; işlem durduruldu.') from error

    def _append(self, connection, job: EngineJob, *, kind: str, at: str, token=None,
                session_id=None, status: str, result=None, error_code=None, step_key=None, receipt=None, reason=None):
        _, _, previous_hash = self._read(connection, job.id)
        ordinal = connection.execute('SELECT COUNT(*) FROM engine_job_events WHERE job_id=?', (job.id,)).fetchone()[0] + 1
        encoded_result = result_json(result) if result is not None else None
        fields = {
            'kind': kind, 'recorded_at': job_time(at), 'token': token, 'session_id': session_id,
            'status': status, 'result_json': encoded_result,
            'result_sha256': digest(encoded_result) if encoded_result is not None else None,
            'error_code': error_code, 'previous_sha256': previous_hash,
        }
        if isinstance(job.payload, SourceJobPayload):
            fields.update(step_key=step_key, receipt=receipt, reason=reason)
        event = canonical_json(fields)
        connection.execute('INSERT INTO engine_job_events VALUES (?, ?, ?, ?, ?)',
                           (job.id, ordinal, kind, event, digest(event)))
        changed = self._read(connection, job.id, verify_catalog=False)[0]
        self._catalog_update(connection, changed)
        return changed

    @staticmethod
    def _catalog_update(connection, job):
        if connection.execute('PRAGMA user_version').fetchone()[0] == 4:
            from xti.adapters.engine_job_catalog import sync, seal
            sync(connection, job)
            seal(connection)

    @staticmethod
    def _begin(connection, *, readonly=False, allow_dirty=False):
        connection.execute('BEGIN' if readonly else 'BEGIN IMMEDIATE')
        # Admission and the selected operation must observe the same guard.
        # A separate writer may have committed between connection setup and BEGIN.
        if not allow_dirty and connection.execute('PRAGMA user_version').fetchone()[0] == 4:
            from xti.adapters.engine_job_catalog import check_guard
            check_guard(connection)

    def readiness(self, *, allow_dirty=False):
        """Constant-size structural admission; full history validation is explicit."""
        with self._connection(readonly=True, allow_dirty=allow_dirty) as connection:
            legacy = connection.execute('PRAGMA user_version').fetchone()[0] < 4
        if legacy:
            self.validate()

    def validate(self) -> dict:
        with self._connection(readonly=True, allow_dirty=True) as connection:
            self._begin(connection, readonly=True, allow_dirty=True)
            self._integrity(connection)
            for row in connection.execute('SELECT id FROM engine_jobs'):
                self._read(connection, row[0])
            self._running(connection)
            if connection.execute('PRAGMA user_version').fetchone()[0] == 4:
                from xti.adapters.engine_job_catalog import check_guard
                check_guard(connection)
            return {'state': 'verified', **self._capacity_in(connection)}

    @staticmethod
    def _require_catalog(connection):
        if connection.execute('PRAGMA user_version').fetchone()[0] != 4:
            raise EngineJobError('migration_required', 'İş geçmişi için kuyruğu açıkça şema 4’e yükseltin.')

    @staticmethod
    def _capacity_in(connection):
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        if version < 4:
            return {'schema_version': version, 'retained_jobs': connection.execute('SELECT COUNT(*) FROM engine_jobs').fetchone()[0],
                    'active_limit': MAX_ENGINE_JOBS, 'limit_scope': 'all_retained_jobs', 'automatic_deletion': False}
        states = dict(connection.execute('SELECT status,COUNT(*) FROM engine_job_catalog GROUP BY status'))
        active = states.get('queued', 0) + states.get('running', 0)
        return {'schema_version': version, 'retained_jobs': sum(states.values()), 'active_jobs': active,
                'archived_jobs': sum(states.values()) - active, 'active_limit': MAX_ENGINE_JOBS,
                'available_active_slots': max(0, MAX_ENGINE_JOBS - active), 'by_status': states,
                'limit_scope': 'queued_and_running_jobs', 'automatic_archiving': True,
                'automatic_deletion': False, 'archive_storage': 'same_database_original_requests_and_events'}

    def capacity(self):
        with self._connection(readonly=True) as connection:
            self._begin(connection, readonly=True)
            return self._capacity_in(connection)

    def history(self, *, bucket='archive', limit=20, before_sequence=None, expected_snapshot=None):
        from xti.domain.job_history import parameters
        parameters('jobs.history', dict(bucket=bucket, limit=limit, before_sequence=before_sequence, expected_snapshot=expected_snapshot))
        with self._connection(readonly=True) as connection:
            self._begin(connection, readonly=True)
            self._require_catalog(connection)
            revision = connection.execute('SELECT revision FROM engine_job_guard WHERE singleton=1').fetchone()[0]
            snapshot = digest(canonical_json(['job-history-v1', bucket, revision]))
            if expected_snapshot is not None and expected_snapshot != snapshot:
                raise EngineJobError('snapshot_changed', 'İş geçmişi değişti; ilk sayfadan yeniden başlayın.')
            clauses, values = [], []
            if bucket != 'all':
                clauses.append('bucket=?')
                values.append(bucket)
            if before_sequence is not None:
                clauses.append('sequence<?')
                values.append(before_sequence)
            where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
            rows = connection.execute('SELECT job_id,sequence,bucket FROM engine_job_catalog' + where +
                ' ORDER BY sequence DESC LIMIT ?', (*values, limit + 1)).fetchall()
            items = []
            for job_id, sequence, storage in rows[:limit]:
                job = self._read(connection, job_id)[0]
                items.append({'job_id': job_id, 'sequence': sequence, 'bucket': storage,
                    'job_kind': 'source' if isinstance(job.payload, SourceJobPayload) else 'profile',
                    'status': job.status, 'created_at': job.created_at, 'finished_at': job.finished_at,
                    'result_available': job.result is not None, 'idempotency_key': job.request_key})
            return {'model_version': 1, 'bucket': bucket, 'snapshot_id': snapshot, 'items': items,
                    'limit': limit, 'has_more': len(rows) > limit,
                    'next_before_sequence': rows[limit-1][1] if len(rows) > limit else None}

    def active_job(self) -> EngineJob | None:
        """Read running/uncertain state without recovering or claiming anything."""
        with self._connection(readonly=True) as connection:
            self._begin(connection, readonly=True)
            running = self._running(connection)
            return running[0][0] if running else None

    def find_request(self, key: str) -> EngineJob | None:
        request_key(key)
        with self._connection(readonly=True) as connection:
            self._begin(connection, readonly=True)
            row = connection.execute('SELECT id FROM engine_jobs WHERE request_key=?', (key,)).fetchone()
            return self._read(connection, row[0])[0] if row else None

    def create(self, key: str, request: str, payload: EngineJobPayload | SourceJobPayload, *, recorded_at: str) -> EngineJob:
        request_key(key)
        encoded = payload.to_json()
        if request != payload_request(payload):
            raise ValidationError('Motor işi isteği profil seçimiyle uyuşmuyor.')
        job_time(recorded_at)
        with self._connection() as connection:
            self._begin(connection)
            if isinstance(payload, SourceJobPayload) and connection.execute('PRAGMA user_version').fetchone()[0] < (3 if payload.version >= 3 else 2):
                raise EngineJobError('migration_required', 'Yeni kaynak işleri için iş kuyruğunu açıkça güncel şema 4’e yükseltin.')
            row = connection.execute('SELECT id FROM engine_jobs WHERE request_key=?', (key,)).fetchone()
            if row:
                previous = self._read(connection, row[0])[0]
                if previous.request_sha256 != digest(request):
                    raise EngineJobError('idempotency_conflict', 'Bu tekrar önleme anahtarı başka bir isteğe bağlı.')
                return previous
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            count_sql = ("SELECT COUNT(*) FROM engine_job_catalog WHERE bucket='active'" if version == 4
                         else 'SELECT COUNT(*) FROM engine_jobs')
            if connection.execute(count_sql).fetchone()[0] >= MAX_ENGINE_JOBS:
                raise EngineJobError('capacity_exceeded', 'Etkin motor işi sınırına ulaşıldı; sıradaki işleri tamamlayın veya iptal edin. Eski anahtarlar korunur.' if version == 4 else
                    'Motor işi geçmişi kayıt sınırına ulaştı; şema 4 geçişi tamamlanan geçmişi etkin kapasiteden ayırır.')
            job_id = str(uuid4())
            connection.execute(f'INSERT INTO engine_jobs ({_JOB_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)',
                               (job_id, key, request, digest(request), encoded, digest(encoded), recorded_at))
            job = self._read(connection, job_id, verify_catalog=False)[0]
            self._catalog_update(connection, job)
            connection.commit()
            return job

    def get(self, job_id: str) -> EngineJob:
        history_uuid(job_id)
        with self._connection(readonly=True) as connection:
            self._begin(connection, readonly=True)
            return self._read(connection, job_id)[0]

    def _running(self, connection) -> list[tuple[EngineJob, str]]:
        rows = connection.execute("SELECT job_id FROM engine_job_catalog WHERE status='running' LIMIT 2"
        ).fetchall() if connection.execute('PRAGMA user_version').fetchone()[0] == 4 else connection.execute(
            "SELECT e.job_id FROM engine_job_events e WHERE e.kind='claimed' AND NOT EXISTS "
            "(SELECT 1 FROM engine_job_events f WHERE f.job_id=e.job_id AND f.kind='finished') LIMIT 2"
        ).fetchall()
        if len(rows) > 1:
            raise StorageError('Birden fazla çalışan motor işi bulundu; geçmiş bozuk olabilir.')
        running = []
        for (job_id,) in rows:
            job, token, _ = self._read(connection, job_id)
            if job.status != 'running' or token is None:
                raise StorageError('Motor işi çalıştırma durumu doğrulanamadı.')
            running.append((job, token))
        return running

    def claim(self, job_id: str | None, *, recorded_at: str) -> EngineJobClaim | None:
        if job_id is not None:
            history_uuid(job_id)
        with self._connection() as connection:
            self._begin(connection)
            if self._running(connection):
                raise WorkerBusyError('Önceki motor işi çalışıyor veya açık kurtarma bekliyor.')
            if job_id is None:
                row = connection.execute("SELECT job_id FROM engine_job_catalog WHERE status='queued' ORDER BY sequence LIMIT 1"
                ).fetchone() if connection.execute('PRAGMA user_version').fetchone()[0] == 4 else connection.execute(
                    'SELECT j.id FROM engine_jobs j WHERE NOT EXISTS '
                    '(SELECT 1 FROM engine_job_events e WHERE e.job_id=j.id) ORDER BY j.rowid LIMIT 1'
                ).fetchone()
                if row is None:
                    return None
                job_id = row[0]
            job = self._read(connection, job_id)[0]
            if job.status != 'queued':
                return None
            if isinstance(job.payload, SourceJobPayload) and job.payload.version >= 3 and connection.execute('PRAGMA user_version').fetchone()[0] < 3:
                raise EngineJobError('migration_required', 'Yeni kaynak işini çalıştırmadan önce kuyruğu güncel şema 4’e yükseltin.')
            token = str(uuid4())
            job = self._append(connection, job, kind='claimed', at=recorded_at, token=token, status='running')
            connection.commit()
            return EngineJobClaim(job, token)

    def _owned(self, connection, claim):
        job, token, _ = self._read(connection, claim.job.id)
        if job.status != 'running' or token != claim.token:
            raise EngineJobError('invalid_job_state', 'Motor işi bu çalıştırıcıya ait çalışan durumda değil.')
        return job

    def link_session(self, claim: EngineJobClaim, session_id: str, *, recorded_at: str) -> None:
        history_uuid(session_id)
        with self._connection() as connection:
            self._begin(connection)
            job = self._owned(connection, claim)
            if job.collection_session_id == session_id:
                return
            if job.collection_session_id is not None:
                raise EngineJobError('invalid_job_state', 'Motor işi başka bir toplama oturumuna bağlı.')
            self._append(connection, job, kind='session', at=recorded_at, token=claim.token,
                         session_id=session_id, status='running')
            connection.commit()

    def finish(self, claim: EngineJobClaim, *, status: str, result: dict | None,
               error_code: str | None, recorded_at: str) -> EngineJob:
        with self._connection() as connection:
            self._begin(connection)
            job = self._owned(connection, claim)
            if isinstance(job.payload, SourceJobPayload) and result is not None:
                # Cancellation can arrive after the runner reads its final progress.
                current = result_for(job)
                if any(result.get(key) != current[key] for key in ('operation', 'version', 'job_id', 'plan_sha256', 'steps')):
                    raise EngineJobError('invalid_job_state', 'Kaynak işi sonucu kalıcı ilerlemeyle uyuşmuyor.')
                result, status = current, current['status']
            job = self._append(connection, job, kind='finished', at=recorded_at, token=claim.token,
                               session_id=job.collection_session_id, status=status,
                               result=result, error_code=error_code)
            connection.commit()
            return job

    def cancel(self, job_id: str, *, recorded_at: str) -> EngineJob:
        history_uuid(job_id)
        with self._connection() as connection:
            self._begin(connection)
            job, token, _ = self._read(connection, job_id)
            if job.status == 'cancelled':
                return job
            if job.status == 'running' and isinstance(job.payload, SourceJobPayload):
                if job.cancel_requested:
                    return job
                job = self._append(connection, job, kind='cancel_requested', at=recorded_at,
                                   token=token, session_id=job.collection_session_id,
                                   status='running', error_code='cancelled_by_caller')
                connection.commit()
                return job
            if job.status != 'queued':
                raise EngineJobError('invalid_job_state', 'Yalnız henüz başlamamış motor işi iptal edilebilir.')
            job = self._append(connection, job, kind='cancelled', at=recorded_at,
                               status='cancelled', error_code='cancelled_by_caller')
            connection.commit()
            return job

    def source_step(self, claim, key, *, action, recorded_at, receipt=None, reason=None):
        if action not in {'start', 'finish', 'skip'}:
            raise ValidationError('Kaynak adımı eylemi desteklenmiyor.')
        with self._connection() as connection:
            self._begin(connection)
            job = self._owned(connection, claim)
            if not isinstance(job.payload, SourceJobPayload):
                raise EngineJobError('invalid_job_state', 'Bu iş kaynak güncellemesi değil.')
            if action == 'start' and job.cancel_requested:
                return job
            if (action == 'finish' and (receipt is None or reason is not None)
                    or action == 'skip' and (receipt is not None or reason is None)
                    or action == 'start' and (receipt is not None or reason is not None)):
                raise ValidationError('Kaynak adımı kanıtı eylemle uyuşmuyor.')
            job = self._append(connection, job, kind='step_started' if action == 'start' else 'step_finished',
                               at=recorded_at, token=claim.token, session_id=job.collection_session_id,
                               status='running', step_key=key, receipt=receipt, reason=reason)
            connection.commit()
            return job

    def list_sources(self, *, limit=20, offset=0):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= MAX_HISTORY_OFFSET:
            raise ValidationError('İş listesi sınırları geçersiz.')
        with self._connection(readonly=True) as connection:
            self._begin(connection, readonly=True)
            if connection.execute('PRAGMA user_version').fetchone()[0] == 4:
                rows = connection.execute("SELECT job_id FROM engine_job_catalog WHERE job_kind='source' "
                    'ORDER BY sequence DESC LIMIT ? OFFSET ?', (limit + 1, offset)).fetchall()
                return tuple(self._read(connection, row[0])[0] for row in rows[:limit]), len(rows) > limit
            results = []
            # Bounded queue; validate each visited record instead of trusting a JSON SQL selector.
            for (job_id,) in connection.execute('SELECT id FROM engine_jobs ORDER BY rowid DESC'):
                job = self._read(connection, job_id)[0]
                if isinstance(job.payload, SourceJobPayload):
                    results.append(job)
                    if len(results) >= offset + limit + 1:
                        break
            return tuple(results[offset:offset + limit]), len(results) > offset + limit

    def migrate(self):
        """Explicit, backed-up migration. Caller holds the common queue worker lock."""
        with self._connection() as connection:
            self._begin(connection)
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version == ENGINE_JOB_SCHEMA_VERSION:
                return {'from_version': version, 'to_version': version, 'backup': None, 'changed': False}
            if self._running(connection):
                raise WorkerBusyError('Çalışan veya kurtarma bekleyen iş varken kuyruk yükseltilemez.')
            for (job_id,) in connection.execute('SELECT id FROM engine_jobs'):
                self._read(connection, job_id)
            backup = self.path.with_name(f'{self.path.name}.v{version}-{uuid4()}.backup')
            self.backup(backup)
            if version < 3:
                rows = connection.execute('SELECT rowid,* FROM engine_job_events ORDER BY rowid').fetchall()
                connection.execute('DROP TABLE engine_job_events')
                connection.execute(_EVENTS_DDL)
                connection.executemany('INSERT INTO engine_job_events(rowid,job_id,ordinal,kind,event_json,event_sha256) VALUES (?, ?, ?, ?, ?, ?)', rows)
            connection.execute(f'PRAGMA user_version={ENGINE_JOB_SCHEMA_VERSION}')
            if ENGINE_JOB_SCHEMA_VERSION >= 4:
                from xti.adapters.engine_job_catalog import install, sync, seal
                install(connection)
                for (job_id,) in connection.execute('SELECT id FROM engine_jobs'):
                    sync(connection, self._read(connection, job_id, verify_catalog=False)[0])
                seal(connection)
            self._schema(connection)
            for (job_id,) in connection.execute('SELECT id FROM engine_jobs'):
                self._read(connection, job_id)
            connection.commit()
            return {'from_version': version, 'to_version': ENGINE_JOB_SCHEMA_VERSION, 'backup': str(backup), 'changed': True}

    def recover_interrupted(self, *, recorded_at: str) -> tuple[EngineJob, ...]:
        with self._connection() as connection:
            self._begin(connection)
            result = tuple(self._append(connection, job, kind='finished', at=recorded_at,
                                        token=token, session_id=job.collection_session_id,
                                        status='interrupted', error_code='recovered_uncertain')
                           for job, token in self._running(connection))
            connection.commit()
            return result

    def quarantine_restored_queue(self, *, recorded_at: str) -> tuple[EngineJob, ...]:
        """Before publishing a restored workspace, retire queued requests of uncertain age.

        The original deployment may have sent them after this backup was made.
        Preserve their keys and immutable request evidence; never dispatch them again.
        Caller owns the restored workspace and excludes workers throughout restore.
        """
        job_time(recorded_at)
        with self._connection() as connection:
            self._begin(connection)
            if self._running(connection):
                raise WorkerBusyError('Çalışan iş içeren yedek güvenli geri yükleme için uygun değil.')
            rows = connection.execute(
                'SELECT j.id FROM engine_jobs j WHERE NOT EXISTS '
                '(SELECT 1 FROM engine_job_events e WHERE e.job_id=j.id) ORDER BY j.rowid'
            ).fetchall()
            results = []
            for (job_id,) in rows:
                job = self._read(connection, job_id)[0]
                at = max((recorded_at, job.created_at), key=datetime.fromisoformat)
                results.append(self._append(connection, job, kind='cancelled', at=at,
                                            status='cancelled', error_code='restored_uncertain'))
            connection.commit()
            return tuple(results)

    def backup(self, destination: Path) -> Path:
        """Verified SQLite snapshot, published without overwrite; caller locks cross-database work."""
        destination = Path(destination).expanduser().absolute()
        temporary = None
        try:
            if destination.exists() or destination.is_symlink():
                raise StorageError('Motor işi yedeği zaten var; üzerine yazılmaz.')
            descriptor, name = tempfile.mkstemp(prefix='.engine-jobs-backup-', dir=destination.parent)
            os.close(descriptor)
            temporary = Path(name)
            self.validate()
            with self._connection(readonly=True) as source:
                target = sqlite3.connect(temporary)
                try:
                    source.backup(target)
                finally:
                    target.close()
            SQLiteEngineJobRepository(temporary).validate()
            self._publish(temporary, destination)
            return destination
        except (OSError, sqlite3.Error) as error:
            raise StorageError('Motor işi yedeği oluşturulamadı; mevcut dosyalar korunur.') from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @classmethod
    def restore(cls, source: Path, destination: Path) -> Path:
        return cls(source).backup(destination)

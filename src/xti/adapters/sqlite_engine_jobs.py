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
    request_json, result_json,
)
from xti.ports.jobs import WorkerBusyError


ENGINE_JOB_DATABASE_NAME = 'engine-jobs.sqlite3'
ENGINE_JOB_SCHEMA_VERSION = 1
MAX_ENGINE_JOBS = 10_000
_APPLICATION_ID = 0x58544A31
_JOBS_DDL = """CREATE TABLE engine_jobs (
    id TEXT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
    request_json TEXT NOT NULL, request_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
)"""
_EVENTS_DDL = """CREATE TABLE engine_job_events (
    job_id TEXT NOT NULL REFERENCES engine_jobs(id), ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 3),
    kind TEXT NOT NULL CHECK(kind IN ('claimed','session','finished','cancelled')),
    event_json TEXT NOT NULL, event_sha256 TEXT NOT NULL,
    PRIMARY KEY(job_id, ordinal)
)"""
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
    def _schema(connection):
        if (connection.execute('PRAGMA application_id').fetchone() != (_APPLICATION_ID,)
                or connection.execute('PRAGMA user_version').fetchone() != (ENGINE_JOB_SCHEMA_VERSION,)
                or connection.execute('PRAGMA journal_mode').fetchone() != ('delete',)):
            raise StorageError('Motor işi şeması desteklenmiyor; otomatik geçiş yapılmadı.')
        objects = set(connection.execute(
            "SELECT name, type, sql FROM sqlite_master WHERE sql IS NOT NULL"
        ).fetchall())
        if objects != {('engine_jobs', 'table', _JOBS_DDL),
                       ('engine_job_events', 'table', _EVENTS_DDL)}:
            raise StorageError('Motor işi şeması beklenen yapıyla uyuşmuyor.')
        if (connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]
                or connection.execute('PRAGMA foreign_key_check').fetchall()):
            raise StorageError('Motor işi veritabanı bütünlük denetimini geçemedi.')
        if connection.execute('SELECT COUNT(*) FROM engine_jobs').fetchone()[0] > MAX_ENGINE_JOBS:
            raise StorageError('Motor işi geçmişi güvenli kayıt sınırını aşıyor.')

    @contextmanager
    def _connection(self, *, readonly=False):
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
            self._schema(connection)
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

    def _read(self, connection, job_id: str) -> tuple[EngineJob, str | None, str | None]:
        row = connection.execute(f'SELECT {_JOB_COLUMNS} FROM engine_jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise EngineJobError('not_found', 'Motor işi bulunamadı.')
        try:
            payload = EngineJobPayload.from_json(row[4])
            if (request_json(payload.profile_name, payload.profile_revision) != row[2]
                    or digest(row[2]) != row[3] or digest(row[4]) != row[5]):
                raise ValueError('immutable request mismatch')
            job = EngineJob(history_uuid(row[0]), request_key(row[1]), row[3], row[5], payload,
                            'queued', job_time(row[6]))
            token, previous_hash, previous_time = None, None, job.created_at
            events = connection.execute(
                'SELECT ordinal, kind, event_json, event_sha256 FROM engine_job_events '
                'WHERE job_id=? ORDER BY ordinal LIMIT 4', (job_id,),
            ).fetchall()
            if len(events) > 3:
                raise ValueError('event capacity')
            for expected, (ordinal, kind, encoded, event_hash) in enumerate(events, 1):
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
        except (ValidationError, ValueError, TypeError, RecursionError, KeyError) as error:
            raise StorageError('Motor işi geçmişi veya sonuç bağı doğrulanamadı; işlem durduruldu.') from error

    def _append(self, connection, job: EngineJob, *, kind: str, at: str, token=None,
                session_id=None, status: str, result=None, error_code=None):
        _, _, previous_hash = self._read(connection, job.id)
        ordinal = connection.execute('SELECT COUNT(*) FROM engine_job_events WHERE job_id=?', (job.id,)).fetchone()[0] + 1
        encoded_result = result_json(result) if result is not None else None
        event = canonical_json({
            'kind': kind, 'recorded_at': job_time(at), 'token': token, 'session_id': session_id,
            'status': status, 'result_json': encoded_result,
            'result_sha256': digest(encoded_result) if encoded_result is not None else None,
            'error_code': error_code, 'previous_sha256': previous_hash,
        })
        connection.execute('INSERT INTO engine_job_events VALUES (?, ?, ?, ?, ?)',
                           (job.id, ordinal, kind, event, digest(event)))
        return self._read(connection, job.id)[0]

    def validate(self) -> None:
        with self._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            for row in connection.execute('SELECT id FROM engine_jobs'):
                self._read(connection, row[0])
            self._running(connection)

    def active_job(self) -> EngineJob | None:
        """Read running/uncertain state without recovering or claiming anything."""
        with self._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            running = self._running(connection)
            return running[0][0] if running else None

    def find_request(self, key: str) -> EngineJob | None:
        request_key(key)
        with self._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            row = connection.execute('SELECT id FROM engine_jobs WHERE request_key=?', (key,)).fetchone()
            return self._read(connection, row[0])[0] if row else None

    def create(self, key: str, request: str, payload: EngineJobPayload, *, recorded_at: str) -> EngineJob:
        request_key(key)
        encoded = payload.to_json()
        if request != request_json(payload.profile_name, payload.profile_revision):
            raise ValidationError('Motor işi isteği profil seçimiyle uyuşmuyor.')
        job_time(recorded_at)
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT id FROM engine_jobs WHERE request_key=?', (key,)).fetchone()
            if row:
                previous = self._read(connection, row[0])[0]
                if previous.request_sha256 != digest(request):
                    raise EngineJobError('idempotency_conflict', 'Bu tekrar önleme anahtarı başka bir isteğe bağlı.')
                return previous
            if connection.execute('SELECT COUNT(*) FROM engine_jobs').fetchone()[0] >= MAX_ENGINE_JOBS:
                raise EngineJobError('capacity_exceeded', 'Motor işi geçmişi kayıt sınırına ulaştı; eski anahtarlar silinmez.')
            job_id = str(uuid4())
            connection.execute(f'INSERT INTO engine_jobs ({_JOB_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)',
                               (job_id, key, request, digest(request), encoded, digest(encoded), recorded_at))
            job = self._read(connection, job_id)[0]
            connection.commit()
            return job

    def get(self, job_id: str) -> EngineJob:
        history_uuid(job_id)
        with self._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            return self._read(connection, job_id)[0]

    def _running(self, connection) -> list[tuple[EngineJob, str]]:
        rows = connection.execute(
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
            connection.execute('BEGIN IMMEDIATE')
            if self._running(connection):
                raise WorkerBusyError('Önceki motor işi çalışıyor veya açık kurtarma bekliyor.')
            if job_id is None:
                row = connection.execute(
                    'SELECT j.id FROM engine_jobs j WHERE NOT EXISTS '
                    '(SELECT 1 FROM engine_job_events e WHERE e.job_id=j.id) ORDER BY j.rowid LIMIT 1'
                ).fetchone()
                if row is None:
                    return None
                job_id = row[0]
            job = self._read(connection, job_id)[0]
            if job.status != 'queued':
                return None
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
            connection.execute('BEGIN IMMEDIATE')
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
            connection.execute('BEGIN IMMEDIATE')
            job = self._owned(connection, claim)
            job = self._append(connection, job, kind='finished', at=recorded_at, token=claim.token,
                               session_id=job.collection_session_id, status=status,
                               result=result, error_code=error_code)
            connection.commit()
            return job

    def cancel(self, job_id: str, *, recorded_at: str) -> EngineJob:
        history_uuid(job_id)
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            job = self._read(connection, job_id)[0]
            if job.status == 'cancelled':
                return job
            if job.status != 'queued':
                raise EngineJobError('invalid_job_state', 'Yalnız henüz başlamamış motor işi iptal edilebilir.')
            job = self._append(connection, job, kind='cancelled', at=recorded_at,
                               status='cancelled', error_code='cancelled_by_caller')
            connection.commit()
            return job

    def recover_interrupted(self, *, recorded_at: str) -> tuple[EngineJob, ...]:
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
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
            connection.execute('BEGIN IMMEDIATE')
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

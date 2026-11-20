"""Derived queue index; original requests/events remain the source of truth."""

from xti.adapters.sqlite import StorageError
from xti.domain.engine_jobs import ENGINE_JOB_TERMINAL
from xti.domain.source_jobs import SourceJobPayload


CATALOG_DDL = """CREATE TABLE engine_job_catalog (
    job_id TEXT PRIMARY KEY REFERENCES engine_jobs(id),
    sequence INTEGER NOT NULL UNIQUE,
    job_kind TEXT NOT NULL CHECK(job_kind IN ('profile','source')),
    status TEXT NOT NULL CHECK(status IN ('queued','running','complete','partial','failed','cancelled','interrupted')),
    bucket TEXT NOT NULL CHECK(bucket IN ('active','archive')),
    event_count INTEGER NOT NULL CHECK(event_count BETWEEN 0 AND 16),
    event_sha256 TEXT,
    CHECK((bucket='active') = (status IN ('queued','running')))
)"""
GUARD_DDL = """CREATE TABLE engine_job_guard (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    dirty INTEGER NOT NULL CHECK(dirty IN (0,1)),
    revision INTEGER NOT NULL CHECK(revision>=0)
)"""
INDEXES = {
    'idx_engine_job_status': 'CREATE INDEX idx_engine_job_status ON engine_job_catalog(status,sequence)',
    'idx_engine_job_bucket': 'CREATE INDEX idx_engine_job_bucket ON engine_job_catalog(bucket,sequence)',
    'idx_engine_job_kind': 'CREATE INDEX idx_engine_job_kind ON engine_job_catalog(job_kind,sequence)',
}
TRIGGERS = {
    f'guard_{table}_{action.lower()}':
        f'CREATE TRIGGER guard_{table}_{action.lower()} AFTER {action} ON {table} '
        'BEGIN UPDATE engine_job_guard SET dirty=1 WHERE singleton=1; END'
    for table in ('engine_jobs', 'engine_job_events', 'engine_job_catalog')
    for action in ('INSERT', 'UPDATE', 'DELETE')
}
OBJECTS = {('engine_job_catalog', 'table', CATALOG_DDL),
           ('engine_job_guard', 'table', GUARD_DDL)} | {
    (name, 'index', sql) for name, sql in INDEXES.items()} | {
    (name, 'trigger', sql) for name, sql in TRIGGERS.items()}


def install(connection):
    connection.execute(CATALOG_DDL)
    connection.execute(GUARD_DDL)
    connection.execute('INSERT INTO engine_job_guard VALUES (1,0,0)')
    for sql in (*INDEXES.values(), *TRIGGERS.values()):
        connection.execute(sql)


def check_guard(connection):
    if connection.execute('SELECT singleton,dirty FROM engine_job_guard').fetchall() != [(1, 0)]:
        raise StorageError('İş kuyruğu özgün kayıtları veya indeksi olağan işlem dışında değişmiş; '
                           'kuyruk denetimi ve doğrulanmış yedekten dönüş gerekli.')


def seal(connection):
    connection.execute('UPDATE engine_job_guard SET dirty=0,revision=revision+1 WHERE singleton=1')


def expected(connection, job):
    sequence = connection.execute('SELECT rowid FROM engine_jobs WHERE id=?', (job.id,)).fetchone()[0]
    last = connection.execute('SELECT ordinal,event_sha256 FROM engine_job_events '
                              'WHERE job_id=? ORDER BY ordinal DESC LIMIT 1', (job.id,)).fetchone()
    return (job.id, sequence, 'source' if isinstance(job.payload, SourceJobPayload) else 'profile',
            job.status, 'archive' if job.status in ENGINE_JOB_TERMINAL else 'active',
            last[0] if last else 0, last[1] if last else None)


def verify(connection, job):
    row = connection.execute('SELECT * FROM engine_job_catalog WHERE job_id=?', (job.id,)).fetchone()
    if row != expected(connection, job):
        raise StorageError('İş kuyruğu indeksi özgün iş/olay kanıtıyla uyuşmuyor.')


def sync(connection, job):
    connection.execute('INSERT INTO engine_job_catalog VALUES (?,?,?,?,?,?,?) '
        'ON CONFLICT(job_id) DO UPDATE SET sequence=excluded.sequence,job_kind=excluded.job_kind,'
        'status=excluded.status,bucket=excluded.bucket,event_count=excluded.event_count,'
        'event_sha256=excluded.event_sha256', expected(connection, job))

"""Accumulated history, original replay, cursor fencing and queue4 migration."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.domain.engine_jobs import EngineJobError, request_json
from xti.domain.job_history import parameters
from tests.test_engine_jobs_storage import payload, result, NOW


def seed_terminal_history(repo, count):
    """Controlled fixture: distinct cancelled requests with valid original chains."""
    value = payload()
    first = repo.create('seed-original', request_json(value.profile_name, value.profile_revision), value, recorded_at=NOW)
    repo.cancel(first.id, recorded_at=NOW)
    with closing(sqlite3.connect(repo.path)) as connection, connection:
        row = connection.execute('SELECT * FROM engine_jobs WHERE id=?', (first.id,)).fetchone()
        events = connection.execute('SELECT ordinal,kind,event_json,event_sha256 FROM engine_job_events WHERE job_id=?', (first.id,)).fetchall()
        for index in range(count - 1):
            identifier = str(uuid4())
            connection.execute('INSERT INTO engine_jobs VALUES (?,?,?,?,?,?,?)', (identifier, f'seed-{index}', *row[2:]))
            connection.executemany('INSERT INTO engine_job_events VALUES (?,?,?,?,?)', [(identifier, *event) for event in events])
            repo._catalog_update(connection, repo._read(connection, identifier, verify_catalog=False)[0])
    return repo.get(first.id)


class JobHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.repo = SQLiteEngineJobRepository(self.root / 'engine-jobs.sqlite3')
        self.repo.initialize()
        self.payload = payload()

    def create(self, key):
        return self.repo.create(key, request_json(self.payload.profile_name, 1), self.payload, recorded_at=NOW)

    def test_terminal_archive_frees_capacity_preserving_original_result_and_key(self):
        first = self.create('first')
        with patch('xti.adapters.sqlite_engine_jobs.MAX_ENGINE_JOBS', 1):
            with self.assertRaises(EngineJobError):
                self.create('blocked')
            claim = self.repo.claim(first.id, recorded_at=NOW)
            session = str(uuid4())
            self.repo.link_session(claim, session, recorded_at=NOW)
            original = result(session)
            complete = self.repo.finish(claim, status='complete', result=original, error_code=None, recorded_at=NOW)
            fresh = self.create('next')
            self.assertEqual(self.create('first'), complete)
            self.assertEqual(self.repo.get(first.id).result, original)
            self.assertEqual(self.repo.capacity()['active_jobs'], 1)
            self.assertEqual(self.repo.capacity()['archived_jobs'], 1)
            self.assertEqual(self.repo.claim(None, recorded_at=NOW).job.id, fresh.id)
        backup = self.root / 'backup'
        self.repo.recover_interrupted(recorded_at=NOW)
        self.repo.backup(backup)
        restored = self.root / 'restored'
        SQLiteEngineJobRepository.restore(backup, restored)
        copy = SQLiteEngineJobRepository(restored)
        self.assertEqual(copy.find_request('first'), complete)
        self.assertEqual(copy.validate()['state'], 'verified')

    def test_over_ten_thousand_archived_jobs_do_not_enter_admission_or_selected_reads(self):
        original = seed_terminal_history(self.repo, 10_025)
        with patch.object(self.repo, '_original', wraps=self.repo._original) as read:
            self.assertEqual(self.repo.find_request('seed-original'), original)
            new = self.create('after-large-history')
            self.assertEqual(self.repo.claim(None, recorded_at=NOW).job.id, new.id)
            self.assertLess(read.call_count, 10)
        self.assertEqual(self.repo.capacity()['archived_jobs'], 10_025)
        self.assertEqual(len(self.repo.history(limit=2)['items']), 2)
        self.repo.validate()

    def test_keyset_history_has_no_duplicates_and_detects_intervening_change(self):
        jobs = [self.create(str(index)) for index in range(4)]
        for job in jobs:
            self.repo.cancel(job.id, recorded_at=NOW)
        first = self.repo.history(limit=2)
        second = self.repo.history(limit=2, before_sequence=first['next_before_sequence'], expected_snapshot=first['snapshot_id'])
        self.assertEqual([j['job_id'] for j in first['items'] + second['items']], [job.id for job in reversed(jobs)])
        self.assertFalse(second['has_more'])
        self.create('later')
        with self.assertRaises(EngineJobError) as error:
            self.repo.history(before_sequence=first['next_before_sequence'], expected_snapshot=first['snapshot_id'])
        self.assertEqual(error.exception.code, 'snapshot_changed')

    def test_index_tampering_rejects_admission_worker_reads_audit_and_backup(self):
        first = self.create('first')
        with closing(sqlite3.connect(self.repo.path)) as db, db:
            db.execute('DELETE FROM engine_job_catalog WHERE job_id=?', (first.id,))
        for action in (lambda: self.repo.get(first.id), lambda: self.create('bad'),
                       lambda: self.repo.claim(None, recorded_at=NOW), self.repo.validate,
                       lambda: self.repo.backup(self.root / 'bad-backup')):
            with self.subTest(action=action), self.assertRaises(StorageError):
                action()
        self.assertFalse((self.root / 'bad-backup').exists())

    def test_parallel_admissions_cannot_oversubscribe_the_active_capacity(self):
        barrier = Barrier(2)
        def attempt(key):
            barrier.wait(timeout=5)
            try:
                return self.create(key).status
            except EngineJobError as error:
                return error.code
        with patch('xti.adapters.sqlite_engine_jobs.MAX_ENGINE_JOBS', 1):
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(attempt, ['concurrent-one', 'concurrent-two']))
            self.assertCountEqual(outcomes, ['queued', 'capacity_exceeded'])
            self.assertEqual(self.repo.capacity()['active_jobs'], 1)
        self.repo.validate()

    def test_external_write_between_connection_and_transaction_is_not_resealed(self):
        first = self.create('first')
        begin = self.repo._begin
        def corrupt_then_begin(connection, **options):
            with closing(sqlite3.connect(self.repo.path)) as other, other:
                other.execute('DELETE FROM engine_job_catalog WHERE job_id=?', (first.id,))
            return begin(connection, **options)
        with patch.object(self.repo, '_begin', side_effect=corrupt_then_begin):
            with self.assertRaises(StorageError):
                self.create('must-not-hide-external-change')
        with closing(sqlite3.connect(self.repo.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM engine_jobs').fetchone(), (1,))
            self.assertEqual(db.execute('SELECT dirty FROM engine_job_guard').fetchone(), (1,))

    def test_v3_migration_preserves_original_rows_and_old_backup(self):
        old = SQLiteEngineJobRepository(self.root / 'old-queue')
        with patch('xti.adapters.sqlite_engine_jobs.ENGINE_JOB_SCHEMA_VERSION', 3):
            old.initialize()
        job = old.create('old', request_json(self.payload.profile_name, 1), self.payload, recorded_at=NOW)
        job = old.cancel(job.id, recorded_at=NOW)
        def original_rows(path):
            with closing(sqlite3.connect(path)) as db:
                return tuple(db.execute('SELECT rowid,* FROM ' + table).fetchall() for table in ('engine_jobs', 'engine_job_events'))
        before = original_rows(old.path)
        migration = old.migrate()
        self.assertEqual((migration['from_version'], migration['to_version']), (3, 4))
        self.assertEqual(before, original_rows(old.path))
        self.assertEqual(before, original_rows(migration['backup']))
        self.assertEqual(old.find_request('old'), job)
        self.assertEqual(old.capacity()['archived_jobs'], 1)
        self.assertFalse(old.migrate()['changed'])

    def test_history_validation_rejects_unknown_fields_and_unbounded_page(self):
        for values in ({'limit': True}, {'limit': 101}, {'before_sequence': 0},
                       {'expected_snapshot': 'wrong'}, {'company': 'other'}, {'bucket': 'delete'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                parameters('jobs.history', values)

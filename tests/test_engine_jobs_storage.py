"""Durable engine identity, one-time claims, append-only recovery and no-overwrite snapshots."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.domain.assets import ValidationError
from xti.domain.collection_history import CollectionFrozenPlan, CollectionFrozenUnit, CollectionProfileOrigin
from xti.domain.collection_profiles import CollectionProfileDefinition, definition_sha256
from xti.domain.engine_jobs import EngineJobError, EngineJobPayload, request_json
from xti.ports.jobs import WorkerBusyError


NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc).isoformat()


def payload(name='Acme profile', revision=1):
    definition = CollectionProfileDefinition('example.com', task_ids=('scan-crtsh',))
    profile_id = str(uuid4())
    origin = CollectionProfileOrigin(str(uuid4()), profile_id, name, revision, definition_sha256(definition))
    frozen = CollectionFrozenPlan(definition, (
        CollectionFrozenUnit('scan-crtsh', 'scan', 'crt.sh', 'example.com', None, 'rules-v1'),
    ), origin)
    return EngineJobPayload(profile_id, name, revision, definition, frozen)


def result(session_id):
    return {'collection_session_id': session_id, 'collection_status': 'complete',
            'asset_value': 'example.com', 'analysis_status': 'complete', 'started_at': NOW,
            'finished_at': NOW, 'steps': [{'step_key': 'scan-crtsh', 'source': 'crt.sh',
                'status': 'complete', 'receipt': {'kind': 'scan_attempt', 'id': str(uuid4()),
                    'status': 'complete', 'recorded_at': NOW, 'summary': {'queries': 1},
                    'source_run_id': None, 'attribution': None, 'license': None, 'scope': None}}]}


class EngineJobStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'engine-jobs.sqlite3'
        self.repo = SQLiteEngineJobRepository(self.path)
        self.repo.initialize()
        self.payload = payload()

    def create(self, key='key-one', *, value=None):
        value = self.payload if value is None else value
        return self.repo.create(key, request_json(value.profile_name, value.profile_revision), value, recorded_at=NOW)

    def claim(self, job):
        return self.repo.claim(job.id, recorded_at=NOW)

    def complete(self, claim):
        session_id = str(uuid4())
        self.repo.link_session(claim, session_id, recorded_at=NOW)
        return self.repo.finish(claim, status='complete', result=result(session_id), error_code=None, recorded_at=NOW)

    def test_same_request_replays_original_immutable_payload(self):
        first = self.create()
        changed_snapshot = payload()
        replay = self.create(value=changed_snapshot)
        self.assertEqual(replay, first)
        self.assertNotEqual(changed_snapshot.profile_id, replay.payload.profile_id)
        self.assertEqual(SQLiteEngineJobRepository(self.path).get(first.id), first)

    def test_conflicting_request_key_preserves_original(self):
        first = self.create()
        before = self.path.read_bytes()
        with self.assertRaises(EngineJobError) as caught:
            self.create(value=payload('Other profile'))
        self.assertEqual(caught.exception.code, 'idempotency_conflict')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.repo.get(first.id), first)

    def test_result_survives_restart_and_reads_do_not_write(self):
        done = self.complete(self.claim(self.create()))
        before = self.path.read_bytes()
        reopened = SQLiteEngineJobRepository(self.path)
        self.assertEqual(reopened.get(done.id), done)
        self.assertEqual(reopened.find_request(done.request_key), done)
        reopened.validate()
        self.assertEqual(self.path.read_bytes(), before)

    def test_concurrent_submissions_are_one_durable_job(self):
        barrier = threading.Barrier(2)
        def submit(_):
            barrier.wait(timeout=5)
            return SQLiteEngineJobRepository(self.path).create(
                'same-key', request_json(self.payload.profile_name, 1), self.payload, recorded_at=NOW)
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = list(pool.map(submit, range(2)))
        self.assertEqual(jobs[0], jobs[1])

    def test_concurrent_claims_allow_exactly_one_running_job(self):
        jobs = [self.create('first'), self.create('second')]
        barrier = threading.Barrier(2)
        def claim(job):
            barrier.wait(timeout=5)
            try:
                return SQLiteEngineJobRepository(self.path).claim(job.id, recorded_at=NOW)
            except WorkerBusyError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            claimed = list(pool.map(claim, jobs))
        self.assertEqual(sum(item is not None for item in claimed), 1)
        self.assertIsNotNone(self.repo.active_job())

    def test_crash_before_session_link_requires_recovery_never_requeues(self):
        job = self.create()
        claim = self.claim(job)
        with self.assertRaises(WorkerBusyError):
            self.repo.claim(None, recorded_at=NOW)
        recovered = self.repo.recover_interrupted(recorded_at=NOW)
        self.assertEqual([value.status for value in recovered], ['interrupted'])
        self.assertEqual(self.repo.recover_interrupted(recorded_at=NOW), ())
        self.assertIsNone(self.claim(job))
        self.assertEqual(self.create(), recovered[0])
        with self.assertRaises(EngineJobError):
            self.repo.link_session(claim, str(uuid4()), recorded_at=NOW)

    def test_crash_after_session_link_preserves_provenance_without_replaying(self):
        claim = self.claim(self.create())
        session_id = str(uuid4())
        self.repo.link_session(claim, session_id, recorded_at=NOW)
        recovered = self.repo.recover_interrupted(recorded_at=NOW)[0]
        self.assertEqual(recovered.collection_session_id, session_id)
        self.assertEqual(recovered.error_code, 'recovered_uncertain')
        with self.assertRaises(EngineJobError):
            self.repo.finish(claim, status='complete', result=result(session_id), error_code=None, recorded_at=NOW)

    def test_session_link_is_idempotent_but_not_replaceable(self):
        claim = self.claim(self.create())
        session_id = str(uuid4())
        self.repo.link_session(claim, session_id, recorded_at=NOW)
        before = self.path.read_bytes()
        self.repo.link_session(claim, session_id, recorded_at=NOW)
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(EngineJobError):
            self.repo.link_session(claim, str(uuid4()), recorded_at=NOW)

    def test_queued_cancel_is_idempotent_and_cannot_cancel_running_or_finished(self):
        queued = self.create('cancelled')
        cancelled = self.repo.cancel(queued.id, recorded_at=NOW)
        self.assertEqual(cancelled.status, 'cancelled')
        self.assertEqual(self.repo.cancel(queued.id, recorded_at=NOW), cancelled)
        self.assertIsNone(self.claim(cancelled))
        claim = self.claim(self.create('running'))
        with self.assertRaises(EngineJobError):
            self.repo.cancel(claim.job.id, recorded_at=NOW)
        complete = self.complete(claim)
        with self.assertRaises(EngineJobError):
            self.repo.cancel(complete.id, recorded_at=NOW)

    def test_result_cannot_cross_session_or_domain(self):
        claim = self.claim(self.create())
        session_id = str(uuid4())
        self.repo.link_session(claim, session_id, recorded_at=NOW)
        for invalid in (result(str(uuid4())), {**result(session_id), 'asset_value': 'other.example'}):
            with self.subTest(invalid=invalid['collection_session_id']):
                with self.assertRaises(StorageError):
                    self.repo.finish(claim, status='complete', result=invalid, error_code=None, recorded_at=NOW)
                self.assertEqual(self.repo.get(claim.job.id).status, 'running')

    def test_result_steps_must_match_frozen_plan_and_source(self):
        claim = self.claim(self.create())
        session_id = str(uuid4())
        self.repo.link_session(claim, session_id, recorded_at=NOW)
        for field, value in (('step_key', 'scan-urlscan'), ('source', 'urlscan')):
            invalid = result(session_id)
            invalid['steps'][0][field] = value
            with self.assertRaises(StorageError):
                self.repo.finish(claim, status='complete', result=invalid, error_code=None, recorded_at=NOW)
        self.assertEqual(self.repo.get(claim.job.id).status, 'running')

    def test_missing_database_is_not_created_by_read_or_submit(self):
        path = self.root / 'missing.sqlite3'
        repo = SQLiteEngineJobRepository(path)
        with self.assertRaises(StorageError):
            repo.find_request('some-key')
        self.assertFalse(path.exists())

    def test_initialize_never_overwrites_existing_file(self):
        job = self.create()
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.repo.initialize()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.repo.get(job.id), job)

    def test_symlink_hardlink_and_group_readable_queue_are_rejected(self):
        self.create()
        link = self.root / 'alias.sqlite3'
        link.symlink_to(self.path)
        with self.assertRaises(StorageError):
            SQLiteEngineJobRepository(link).validate()
        link.unlink()
        os.link(self.path, link)
        with self.assertRaises(StorageError):
            self.repo.validate()
        link.unlink()
        self.path.chmod(0o640)
        with self.assertRaises(StorageError):
            self.repo.validate()

    def test_request_hash_tampering_and_event_hash_tampering_fail_closed(self):
        job = self.create()
        other = self.create('other')
        self.claim(other)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE engine_jobs SET request_sha256='bad' WHERE id=?", (job.id,))
        with self.assertRaises(StorageError):
            self.repo.get(job.id)
        # Schema 4 rejects all queue use after an out-of-band mutation.
        with self.assertRaises(StorageError):
            self.create('after-tampering')
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE engine_job_events SET event_sha256='bad' WHERE job_id=?", (other.id,))
        with self.assertRaises(StorageError):
            self.repo.get(other.id)

    def test_capacity_preserves_existing_replay_keys(self):
        first = self.create()
        with patch('xti.adapters.sqlite_engine_jobs.MAX_ENGINE_JOBS', 1):
            self.assertEqual(self.create(), first)
            with self.assertRaises(EngineJobError) as caught:
                self.create('new-key')
            self.assertEqual(caught.exception.code, 'capacity_exceeded')

    def test_backup_restore_preserve_request_keys_and_results_without_overwrite(self):
        done = self.complete(self.claim(self.create()))
        backup = self.root / 'snapshot.sqlite3'
        restored = self.root / 'restored.sqlite3'
        self.assertEqual(self.repo.backup(backup), backup)
        self.assertEqual(SQLiteEngineJobRepository.restore(backup, restored), restored)
        self.assertEqual(SQLiteEngineJobRepository(restored).get(done.id), done)
        self.assertEqual(restored.stat().st_mode & 0o777, 0o600)
        for action in (lambda: self.repo.backup(backup),
                       lambda: SQLiteEngineJobRepository.restore(backup, self.path)):
            with self.assertRaises(StorageError):
                action()
        self.assertEqual(self.repo.get(done.id), done)

    def test_invalid_payload_or_result_is_rejected_before_commit(self):
        with self.assertRaises(ValidationError):
            self.create(value=replace(self.payload, profile_id=str(uuid4())))
        claim = self.claim(self.create())
        self.repo.link_session(claim, str(uuid4()), recorded_at=NOW)
        with self.assertRaises(ValidationError):
            self.repo.finish(claim, status='complete', result={'secret': 'not a result'}, error_code=None, recorded_at=NOW)
        self.assertEqual(self.repo.get(claim.job.id).status, 'running')

    def test_restored_queued_requests_are_retired_without_losing_identity(self):
        queued = self.create()
        backup = self.root / 'snapshot.sqlite3'
        self.repo.backup(backup)
        # Original installation sends the request after the backup point.
        completed = self.complete(self.claim(queued))
        restored_path = self.root / 'restored.sqlite3'
        SQLiteEngineJobRepository.restore(backup, restored_path)
        restored = SQLiteEngineJobRepository(restored_path)
        retired = restored.quarantine_restored_queue(recorded_at=NOW)
        self.assertEqual(len(retired), 1)
        self.assertEqual((retired[0].id, retired[0].status, retired[0].error_code),
                         (queued.id, 'cancelled', 'restored_uncertain'))
        self.assertEqual(retired[0].payload_sha256, queued.payload_sha256)
        self.assertIsNone(restored.claim(queued.id, recorded_at=NOW))
        self.assertEqual(restored.find_request(queued.request_key), retired[0])
        self.assertEqual(restored.quarantine_restored_queue(recorded_at=NOW), ())
        self.assertEqual(self.repo.get(queued.id), completed)


if __name__ == '__main__':
    unittest.main()

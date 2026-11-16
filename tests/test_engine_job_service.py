"""Worker cancellation, response-loss replay, process death and source-request ambiguity."""

from datetime import datetime
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.engine_jobs import EngineJobService
from xti.domain.engine_jobs import EngineJobError
from xti.ports.jobs import WorkerBusyError
from tests.test_engine_jobs_storage import NOW, payload, result


class Runner:
    def __init__(self):
        self.payload = payload()
        self.prepares = 0
        self.calls = 0
        self.error = None
        self.before_source = lambda: None

    def prepare(self, name, revision):
        self.prepares += 1
        return self.payload

    def run(self, value, *, session_started):
        session_id = str(uuid4())
        session_started(session_id)
        self.before_source()
        self.calls += 1
        if self.error:
            raise self.error
        return result(session_id)


def claim_and_die(path, job_id):
    with LocalExecutionLock(Path(path)).acquire():
        SQLiteEngineJobRepository(Path(path)).claim(job_id, recorded_at=NOW)
        # Exit without returning through the worker or context managers.
        import os
        os._exit(9)


class EngineJobServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'engine-jobs.sqlite3'
        self.repo = SQLiteEngineJobRepository(self.path)
        self.repo.initialize()
        self.runner = Runner()
        self.service = EngineJobService(self.repo, self.runner, LocalExecutionLock(self.path),
                                       clock=lambda: datetime.fromisoformat(NOW))

    def submit(self, key='external-request'):
        return self.service.submit(key, 'Acme profile', 1)

    def test_acceptance_does_not_execute_and_response_loss_replay_is_read_only(self):
        job = self.submit()
        self.assertEqual((self.runner.prepares, self.runner.calls), (1, 0))
        before = self.path.read_bytes()
        with patch.object(self.runner, 'prepare', side_effect=AssertionError('Replay must not prepare')):
            self.assertEqual(self.submit(), job)
        self.assertEqual(self.path.read_bytes(), before)

    def test_worker_persists_session_before_source_and_freezes_results(self):
        job = self.submit()
        self.runner.before_source = lambda: self.assertIsNotNone(self.service.status(job.id).collection_session_id)
        complete = self.service.work_one()
        self.assertEqual(complete.status, 'complete')
        frozen = self.service.results(job.id)
        self.assertEqual(frozen['result']['collection_session_id'], complete.collection_session_id)
        self.assertEqual(self.submit(), complete)
        self.assertIsNone(self.service.work_one(job.id))
        self.assertIsNone(self.service.work_one())
        self.assertEqual(self.runner.calls, 1)

    def test_same_key_different_revision_is_rejected_before_prepare(self):
        self.submit()
        with self.assertRaises(EngineJobError) as caught:
            self.service.submit('external-request', 'Acme profile', 2)
        self.assertEqual(caught.exception.code, 'idempotency_conflict')
        self.assertEqual(self.runner.prepares, 1)

    def test_failed_session_link_prevents_source_call_and_never_requeues(self):
        job = self.submit()
        with patch.object(self.repo, 'link_session', side_effect=StorageError('controlled failure')):
            with self.assertRaises(StorageError):
                self.service.work_one()
        self.assertEqual(self.runner.calls, 0)
        self.assertEqual(self.service.status(job.id).status, 'interrupted')
        self.assertIsNone(self.service.work_one(job.id))

    def test_exception_after_source_is_ambiguous_and_retry_key_never_repeats(self):
        job = self.submit()
        self.runner.error = RuntimeError('a secret in a source error')
        with self.assertRaises(RuntimeError):
            self.service.work_one()
        interrupted = self.service.status(job.id)
        self.assertEqual(interrupted.status, 'interrupted')
        self.assertEqual(interrupted.error_code, 'execution_uncertain')
        self.assertNotIn('secret', str(interrupted.to_dict()))
        self.assertEqual(self.submit(), interrupted)
        self.assertIsNone(self.service.work_one(job.id))
        self.assertEqual(self.runner.calls, 1)

    def test_failed_completion_persistence_requires_explicit_recovery(self):
        job = self.submit()
        with patch.object(self.repo, 'finish', side_effect=StorageError('disk unavailable')):
            with self.assertRaises(StorageError):
                self.service.work_one()
        self.assertEqual(self.service.status(job.id).status, 'running')
        with self.assertRaises(WorkerBusyError):
            self.service.work_one()
        recovered = self.service.recover()
        self.assertEqual(recovered[0].id, job.id)
        self.assertEqual(self.submit().status, 'interrupted')
        self.assertEqual(self.runner.calls, 1)

    def test_live_worker_lock_rejects_recovery_and_second_worker_without_claim(self):
        job = self.submit()
        with LocalExecutionLock(self.path).acquire():
            for operation in (self.service.recover, self.service.work_one):
                with self.assertRaises(WorkerBusyError):
                    operation()
        self.assertEqual(self.service.status(job.id).status, 'queued')
        self.assertEqual(self.runner.calls, 0)

    def test_process_death_releases_lock_but_does_not_grant_retry(self):
        job = self.submit()
        process = multiprocessing.get_context('spawn').Process(target=claim_and_die, args=(str(self.path), job.id))
        process.start()
        process.join(timeout=15)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        self.assertEqual(process.exitcode, 9)
        self.assertEqual(self.submit().status, 'running')
        with self.assertRaises(WorkerBusyError):
            self.service.work_one()
        self.assertEqual(self.service.recover()[0].status, 'interrupted')
        self.assertIsNone(self.service.work_one(job.id))
        self.assertEqual(self.runner.calls, 0)


if __name__ == '__main__':
    unittest.main()

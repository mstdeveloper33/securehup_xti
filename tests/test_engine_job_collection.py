"""Real collection receipt integration; all source adapters are offline fixtures."""

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from xti.adapters.engine_job_collection import CollectionProfileJobRunner
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.engine_jobs import EngineJobService
from xti.config import Settings
from xti.domain.assets import ValidationError
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.engine_jobs import EngineJobError
from xti.interfaces.cli import make_collection_history_service
from xti.ports.discovery import SourceError
from tests import test_collection_watch_cli as fixtures


class EngineJobCollectionTests(unittest.TestCase):
    add_tc = fixtures.CollectionWatchCLITests.add_tc

    def setUp(self):
        fixtures.CollectionWatchCLITests.setUp(self)
        self.profiles = SQLiteCollectionProfileRepository(self.database)
        self.queue_path = self.data / 'engine-jobs.sqlite3'
        self.queue = SQLiteEngineJobRepository(self.queue_path)
        self.queue.initialize()
        self.runner = CollectionProfileJobRunner(self.profiles, lambda:
            make_collection_history_service(Settings(self.data), SQLiteAssetRepository(self.database)))
        self.service = EngineJobService(self.queue, self.runner, LocalExecutionLock(self.queue_path))

    def save(self, definition=None):
        definition = definition or CollectionProfileDefinition('example.com', task_ids=('scan-crtsh',))
        return self.profiles.save('Company collection', definition,
                                  recorded_at=datetime.now(timezone.utc).isoformat()).profile

    def submit(self):
        profile = self.save()
        return self.service.submit('platform-request', profile.display_name, profile.revision)

    def test_submit_reads_only_core_and_worker_links_before_first_source(self):
        self.save()
        before = self.database.read_bytes()
        job = self.service.submit('platform-request', 'Company collection', 1)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.crt.calls, [])
        search = self.crt.search
        def checked_search(pattern):
            active = self.service.status(job.id)
            self.assertIsNotNone(active.collection_session_id)
            self.assertEqual(self.runner.history_factory().show(active.collection_session_id).session.status, 'running')
            return search(pattern)
        with patch.object(self.crt, 'search', checked_search):
            complete = self.service.work_one(job.id)
        self.assertEqual(complete.status, 'complete')
        frozen = self.service.results(job.id)['result']
        self.assertEqual(frozen['steps'][0]['receipt']['kind'], 'scan_attempt')
        self.assertEqual(frozen['collection_session_id'], complete.collection_session_id)
        calls = list(self.crt.calls)
        self.assertEqual(self.service.submit('platform-request', 'Company collection', 1), complete)
        self.assertIsNone(self.service.work_one(job.id))
        self.assertEqual(self.crt.calls, calls)

    def test_queued_profile_edit_is_rejected_without_source_request(self):
        job = self.submit()
        self.save(CollectionProfileDefinition('example.com', task_ids=('discover-crtsh',)))
        with self.assertRaises(EngineJobError) as caught:
            self.service.work_one(job.id)
        self.assertEqual(caught.exception.code, 'profile_changed')
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.service.status(job.id).status, 'interrupted')
        self.assertEqual(self.runner.history_factory().list().sessions, ())

    def test_queued_watch_edit_changes_frozen_plan_and_prevents_all_sources(self):
        watch = self.add_tc()
        profile = self.save(CollectionProfileDefinition('example.com', task_ids=('scan-crtsh',),
                                                       ransomware_watch_ids=(watch.id,)))
        job = self.service.submit('watch-request', profile.display_name, 1)
        updated = self.tc.add(watch.display_name, 'Changed Holding', kind='organization').watch
        self.assertEqual(watch.id, updated.id)
        with self.assertRaises(ValidationError):
            self.service.work_one(job.id)
        self.assertEqual((self.crt.calls, self.threatcluster.calls), ([], 0))
        self.assertEqual(self.runner.history_factory().list().sessions, ())

    def test_profile_change_inside_lock_is_rechecked_before_begin(self):
        job = self.submit()
        original = self.runner.history_factory
        def factory():
            history = original()
            old_acquire = history.lock.acquire
            from contextlib import contextmanager
            @contextmanager
            def acquire():
                with old_acquire():
                    self.save(CollectionProfileDefinition('example.com', task_ids=('discover-crtsh',)))
                    yield
            history.lock.acquire = acquire
            return history
        self.runner.history_factory = factory
        with self.assertRaises(EngineJobError):
            self.service.work_one(job.id)
        self.assertEqual(self.crt.calls, [])

    def test_session_link_failure_stops_before_source_and_keeps_history(self):
        job = self.submit()
        with patch.object(self.queue, 'link_session', side_effect=StorageError('queue unavailable')):
            with self.assertRaises(StorageError):
                self.service.work_one(job.id)
        self.assertEqual(self.crt.calls, [])
        sessions = self.runner.history_factory().list().sessions
        self.assertEqual(len(sessions), 1)
        self.assertNotEqual(sessions[0].status, 'running')
        self.assertEqual(self.service.status(job.id).status, 'interrupted')

    def test_source_failure_receipt_is_frozen_and_never_implicitly_retried(self):
        job = self.submit()
        self.crt.responses['%example%'] = SourceError('Controlled source failure')
        done = self.service.work_one(job.id)
        self.assertIn(done.status, {'failed', 'partial'})
        self.assertIsNotNone(done.result)
        calls = list(self.crt.calls)
        self.assertEqual(self.service.submit('platform-request', 'Company collection', 1), done)
        self.assertIsNone(self.service.work_one(job.id))
        self.assertEqual(self.crt.calls, calls)

    def test_completed_receipt_results_survive_later_profile_revocation(self):
        job = self.submit()
        done = self.service.work_one(job.id)
        before = self.service.results(job.id)
        self.profiles.revoke('Company collection', reason='Explicit profile closure',
                             recorded_at=datetime.now(timezone.utc).isoformat())
        self.assertEqual(self.service.results(job.id), before)
        self.assertEqual(self.service.submit('platform-request', 'Company collection', 1), done)


if __name__ == '__main__':
    unittest.main()

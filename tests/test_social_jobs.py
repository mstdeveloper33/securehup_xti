"""Durable social queue boundaries, honest traffic and crash recovery."""
from copy import deepcopy
from datetime import datetime
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.source_job_social import SocialTrackingStep
from xti.adapters.source_job_steps import ExistingSourceJobOperations
from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.engine_jobs import EngineJobService
from xti.application.source_jobs import SourceJobService, CooperativeSourceJobRunner
from xti.domain.assets import ValidationError
from xti.domain.engine_jobs import EngineJobError
from xti.domain.social_discovery import SocialDiscoveryError
from xti.domain.source_jobs import SourceJobPayload, source_plan, plan_data, validate_receipt
from xti.interfaces.source_jobs import source_job_lines
from tests import test_social_tracking as tracking


class SocialJobTests(unittest.TestCase):
    def setUp(self):
        self.f = tracking.TrackingTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        f = self.f
        self.watch = f.add()
        self.queue = SQLiteEngineJobRepository(f.path.parent / 'engine-jobs.sqlite3'); self.queue.initialize()
        self.service = SourceJobService(self.queue, social_tracking=f.service, clock=lambda: datetime.fromisoformat(f.at))
        self.step = SocialTrackingStep(f.service, f.discovery_repo, self.queue)
        self.operations = ExistingSourceJobOperations(None, None, None, social_tracking=lambda **kw: self.step)
        self.runner = CooperativeSourceJobRunner(self.operations, LocalExecutionLock(f.path))
        self.worker = EngineJobService(self.queue, None, LocalExecutionLock(self.queue.path),
            source_runner=self.runner, clock=lambda: datetime.fromisoformat(f.at))
        self.options = dict(indicator_type='domain', value='acme.example', sources=['social-tracking'],
                            social_watch_id=self.watch['id'], social_watch_revision=1)
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No live requests')))
        self.enterContext(patch.object(f.sources, 'search', side_effect=AssertionError('No paid search')))

    def submit(self, key='one', **options):
        values = {**self.options, **options}
        plan = plan_data(source_plan(**values))
        return self.service.submit(**values, idempotency_key=key, plan_sha256=plan['plan_sha256'])

    def pause(self):
        return self.f.service.execute('brand.tracking.set', identifier=self.watch['id'], enabled=False,
                                     expected_revision=1, idempotency_key='pause')

    def test_offline_admission_and_durable_worker_share_receipts_without_paid_or_repeated_calls(self):
        with patch.object(self.f.discovery, '_collect', side_effect=AssertionError('Admission stays offline')):
            plan = self.service.plan(**self.options)
            job = self.submit()
        self.assertIsNone(plan['maximum_external_requests']); self.assertFalse(plan['paid_api'])
        self.assertEqual(plan['social_watch']['scope']['web_search'], False)
        done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'partial')  # GitHub fixture cannot be checked.
        receipt = done.steps[0]['receipt']
        self.step.verify(receipt, done.payload.plan)
        run = self.f.service.execute('brand.tracking.run.show', identifier=receipt['run_id'])['record']
        self.assertTrue(run['baseline']); self.assertEqual(run['watch_revision'], 1)
        usage = done.to_dict()['execution']['requests']
        self.assertFalse(usage['measurement_complete']); self.assertIsNone(usage['attempts'])
        self.assertIsNone(usage['possible_unrecorded_attempts_maximum'])
        self.assertEqual(usage['recorded_social_page_http_requests'], receipt['usage']['page_http_requests'])
        self.assertIn('ölçülmüyor', '\n'.join(source_job_lines(done.to_dict())))
        calls = len(self.f.pages.calls)
        self.assertEqual(self.submit(), done); self.assertIsNone(self.worker.work_one(job.id))
        self.assertEqual(len(self.f.pages.calls), calls)
        self.assertEqual(SQLiteEngineJobRepository(self.queue.path).get(job.id), done)

    def test_scope_revision_id_and_unknown_options_rejected_before_admission(self):
        for options in ({'value': 'other.example'}, {'social_watch_revision': 2},
                        {'social_watch_id': str(uuid4())}, {'social_watch_revision': True},
                        {'social_force': 'yes'}, {'urls': ['https://127.0.0.1/']},
                        {'sources': ['news:ncsc']}, {'indicator_type': 'ipv4', 'value': '192.0.2.1'}):
            with self.subTest(options=options), self.assertRaises((ValidationError, EngineJobError, SocialDiscoveryError)):
                self.submit(**options)
        self.assertEqual(self.service.list()['jobs'], [])

    def test_paused_or_revised_watch_stops_pending_job_and_old_admission_replays(self):
        job = self.submit(); self.pause()
        with patch.object(self.f.discovery, '_collect', side_effect=AssertionError('No changed scope dispatch')):
            self.assertEqual(self.submit(), job)
            with self.assertRaises(EngineJobError): self.submit('new')
            done = self.worker.work_one(job.id)
        self.assertEqual(done.steps[0]['receipt']['reason'], 'revision_changed')
        self.assertEqual(done.to_dict()['execution']['requests']['attempts'], 0)
        self.assertEqual(self.f.service.execute('brand.tracking.show', identifier=self.watch['id'])['record']['last_run_id'], None)

    def test_not_due_and_busy_are_durable_non_network_results(self):
        self.worker.work_one(self.submit().id)
        with patch.object(self.f.discovery, '_collect', side_effect=AssertionError('Not due')):
            done = self.worker.work_one(self.submit('early').id)
        self.assertEqual(done.steps[0]['receipt']['reason'], 'not_due')
        self.f.later()
        self.f.repo.write('brand.tracking.run', dict(identifier=self.watch['id'], force=False, idempotency_key='outside'), self.f.at)
        done = self.worker.work_one(self.submit('busy').id)
        self.assertEqual(done.steps[0]['receipt']['reason'], 'busy')

    def test_queue_crash_after_core_commit_reuses_parent_receipt_without_duplicate_notification(self):
        self.worker.work_one(self.submit().id); self.f.later(); self.f.mode = 'changed'
        job = self.submit('changed'); original = self.step.execute
        def crash(*args): original(*args); raise KeyboardInterrupt()
        with patch.object(self.step, 'execute', side_effect=crash), self.assertRaises(KeyboardInterrupt):
            self.worker.work_one(job.id)
        self.assertEqual(self.service.status(job.id).status, 'interrupted')
        with self.assertRaises(EngineJobError): self.service.retry(job.id, idempotency_key='no-ack')
        retry = self.service.retry(job.id, idempotency_key='recover', allow_uncertain=True)
        self.pause()  # A committed receipt may be read even after pause.
        with patch.object(self.f.discovery, '_collect', side_effect=AssertionError('No repeat')):
            done = self.worker.work_one(retry.id)
        self.assertEqual(done.status, 'partial'); self.assertTrue(done.steps[0]['receipt']['usage']['receipt_reused'])
        self.assertEqual(done.to_dict()['execution']['requests']['attempts'], 0)
        self.assertEqual(self.f.inbox.list(status='all', limit=20, before=None).total_count, 1)

    def test_crash_after_discovery_before_tracking_commit_is_recovered_without_new_requests(self):
        job = self.submit(); original = self.f.discovery_repo.finish
        def crash(*args): original(*args); raise KeyboardInterrupt()
        with patch.object(self.f.discovery_repo, 'finish', side_effect=crash), self.assertRaises(KeyboardInterrupt):
            self.worker.work_one(job.id)
        retry = self.service.retry(job.id, idempotency_key='recover', allow_uncertain=True)
        self.pause()
        with patch.object(self.f.discovery, '_collect', side_effect=AssertionError('No repeat')):
            done = self.worker.work_one(retry.id)
        self.assertEqual(done.status, 'partial'); self.assertTrue(done.steps[0]['receipt']['usage']['receipt_reused'])

    def test_crash_before_discovery_and_later_pause_closes_reservation_without_leaving_watch_busy(self):
        job = self.submit()
        with patch.object(self.f.discovery, 'run_tracking', side_effect=KeyboardInterrupt()), self.assertRaises(KeyboardInterrupt):
            self.worker.work_one(job.id)
        run = self.f.service.find_run(self.step.key(job.id)); self.assertEqual(run['status'], 'running')
        retry = self.service.retry(job.id, idempotency_key='recover', allow_uncertain=True); self.pause()
        with patch.object(self.f.discovery, '_collect', side_effect=AssertionError('Paused reservation')):
            done = self.worker.work_one(retry.id)
        self.assertEqual(done.steps[0]['receipt']['reason'], 'revision_changed')
        self.assertEqual(self.f.service.find_run(self.step.key(job.id))['status'], 'interrupted')
        self.f.service.execute('brand.tracking.set', identifier=self.watch['id'], enabled=True,
                              expected_revision=2, idempotency_key='resume')
        self.f.later()
        self.assertEqual(self.worker.work_one(self.submit('later', social_watch_revision=3).id).status, 'partial')

    def test_uncommitted_discovery_is_not_silently_retried_and_explicit_ack_starts_one_new_round(self):
        job = self.submit()
        with patch.object(self.f.discovery, '_collect', side_effect=KeyboardInterrupt()), self.assertRaises(KeyboardInterrupt):
            self.worker.work_one(job.id)
        parent = self.f.service.find_run(self.step.key(job.id))
        with self.assertRaises(EngineJobError): self.service.retry(job.id, idempotency_key='no-ack')
        retry = self.service.retry(job.id, idempotency_key='recover', allow_uncertain=True)
        self.f.later()
        with patch.object(self.f.discovery, '_collect', wraps=self.f.discovery._collect) as collect:
            done = self.worker.work_one(retry.id)
        self.assertEqual(collect.call_count, 1); self.assertEqual(done.status, 'partial')
        self.assertNotEqual(done.steps[0]['receipt']['run_id'], parent['id'])
        self.assertEqual(self.f.service.find_run(self.step.key(job.id))['status'], 'interrupted')

    def test_explicit_partial_retry_and_force_start_new_receipt_with_new_key(self):
        done = self.worker.work_one(self.submit(social_force=True).id)
        retry = self.service.retry(done.id, idempotency_key='retry')
        next_done = self.worker.work_one(retry.id)
        self.assertNotEqual(done.steps[0]['receipt']['run_id'], next_done.steps[0]['receipt']['run_id'])
        self.assertTrue(next_done.steps[0]['receipt']['usage']['attempted'])

    def test_cancel_and_elapsed_deadline_leave_no_social_run(self):
        job = self.submit(); self.service.cancel(job.id)
        self.assertIsNone(self.worker.work_one(job.id))
        job = self.submit('expired')
        times = iter((0, 1000)); self.runner.monotonic = lambda: next(times)
        with patch.object(self.f.discovery, '_collect', side_effect=AssertionError('No cancelled work')):
            done = self.worker.work_one(job.id)
        self.assertEqual(done.steps[0]['reason'], 'budget_exhausted')
        self.assertEqual(done.to_dict()['execution']['requests']['attempts'], 0)
        self.assertIsNone(self.f.service.find_run(self.step.key(job.id)))

    def test_receipt_metric_scope_and_hash_tampering_rejected(self):
        done = self.worker.work_one(self.submit().id); receipt = done.steps[0]['receipt']; plan = done.payload.plan
        for change in ({'watch_id': str(uuid4())}, {'run_sha256': '0' * 64},
                       {'usage': {**receipt['usage'], 'page_http_requests': 0}},
                       {'usage': {**receipt['usage'], 'tool_requests': 0}}):
            with self.subTest(change=change), self.assertRaises((ValidationError, StorageError)):
                forged = {**deepcopy(receipt), **change}
                validate_receipt('social-tracking', forged, plan); self.step.verify(forged, plan)

    def test_execution_versions_one_to_five_stay_readable_but_cannot_claim_social_support(self):
        plain = source_plan(indicator_type='sha256', value='a' * 64, sources=['circl'])
        for version in range(1, 6):
            old = SourceJobPayload(plain, version=version).to_json()
            self.assertEqual(SourceJobPayload.from_json(old).to_json(), old)
            with self.assertRaises(ValidationError): SourceJobPayload(source_plan(**self.options), version=version).to_json()


if __name__ == '__main__': unittest.main()

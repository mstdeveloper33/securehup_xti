"""Durable source progress, explicit retry, cooperative cancellation and queue migration."""

from contextlib import closing, redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository, _EVENTS_DDL_V1
from xti.adapters.sqlite_enrichment import SQLiteEnrichmentRepository
from xti.adapters.sqlite_warninglists import SQLiteWarninglistRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.adapters.source_job_steps import ExistingSourceJobOperations
from xti.application.engine_jobs import EngineJobService
from xti.application.source_jobs import SourceJobService, CooperativeSourceJobRunner
from xti.application.indicator_enrichment import EnrichmentService
from xti.application.warninglists import WarninglistService
from xti.domain.assets import ValidationError
from xti.domain.engine_jobs import EngineJobError, request_json
from xti.domain.source_jobs import SourceJobPayload, result_for
from xti.interfaces.cli import main
from xti.interfaces.research_history import make_history_service
from xti.ports.discovery import SourceError
from xti.ports.jobs import WorkerBusyError
from tests.test_indicator_enrichment import Source as EnrichmentSource, HASH, URL, url_body
from tests.test_warninglists import Source as ListSource
from tests.test_engine_jobs_storage import payload as profile_payload


NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)


class SourceJobTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.core = self.root / 'xti.db'
        SQLiteAssetRepository(self.core).initialize()
        self.queue = SQLiteEngineJobRepository(self.root / 'engine-jobs.sqlite3')
        self.queue.initialize()
        self.service = SourceJobService(self.queue, clock=lambda: NOW)
        self.enrichment = EnrichmentSource()
        self.lists = ListSource()
        self.enrichment_service = EnrichmentService(SQLiteEnrichmentRepository(self.core), self.enrichment)
        self.list_service = WarninglistService(SQLiteWarninglistRepository(self.core), self.lists)
        self.operations = ExistingSourceJobOperations(lambda **kw: self.enrichment_service,
            lambda **kw: self.list_service, lambda: make_history_service(self.core))
        self.runner = CooperativeSourceJobRunner(self.operations, LocalExecutionLock(self.core))
        self.worker = EngineJobService(self.queue, None, LocalExecutionLock(self.queue.path),
            clock=lambda: NOW, source_runner=self.runner)
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No real network')))

    def submit(self, key='one', **options):
        parameters = {'indicator_type': 'sha256', 'value': HASH, 'sources': ['circl'], **options}
        plan = self.service.plan(**parameters)
        return self.service.submit(**parameters, idempotency_key=key, plan_sha256=plan['plan_sha256'])

    def test_plan_is_offline_explicit_and_canonical(self):
        before = self.core.read_bytes(), self.queue.path.read_bytes()
        plan = self.service.plan(indicator_type='domain', value='EXAMPLE.COM', sources=['misp'], warninglist_ids=['rfc6761'])
        self.assertEqual(plan['plan']['value'], 'example.com')
        self.assertEqual(plan['maximum_external_requests'], 3)
        self.assertFalse(plan['disclosure'][0]['target_sent'])
        self.assertEqual(before, (self.core.read_bytes(), self.queue.path.read_bytes()))
        self.assertEqual(self.lists.calls, [])

    def test_unsupported_source_scope_budgets_and_booleans_rejected_before_admission(self):
        bad = [dict(sources=[]), dict(sources=['circl', 'circl']), dict(sources=['misp']),
            dict(warninglist_ids=['rfc6761']), dict(sources=['urlscan']), dict(max_requests=0),
            dict(max_requests=True), dict(max_seconds=False), dict(record_review=1),
            dict(sources=['circl', 'misp'], warninglist_ids=['rfc6761'], max_requests=3),
            dict(sources=['arbitrary']), dict(unknown='x')]
        before = self.queue.path.read_bytes()
        for options in bad:
            with self.subTest(options=options), self.assertRaises(ValidationError):
                self.submit(**options)
        self.assertEqual(before, self.queue.path.read_bytes())

    def test_hash_mismatch_and_cross_kind_idempotency_conflict(self):
        with self.assertRaises(EngineJobError) as caught:
            self.service.submit(idempotency_key='one', plan_sha256='0' * 64,
                indicator_type='sha256', value=HASH, sources=['circl'])
        self.assertEqual(caught.exception.code, 'plan_changed')
        payload = profile_payload()
        self.queue.create('one', request_json(payload.profile_name, payload.profile_revision), payload, recorded_at=NOW.isoformat())
        with self.assertRaises(EngineJobError) as caught:
            self.submit()
        self.assertEqual(caught.exception.code, 'idempotency_conflict')

    def test_persistent_success_and_replay_with_original_evidence_no_repeat(self):
        job = self.submit(record_review=True)
        self.assertEqual(self.enrichment.calls, [])
        done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual([step['status'] for step in done.steps], ['complete', 'complete'])
        self.assertEqual(done.steps[0]['receipt']['source_status'], 'matched')
        self.assertEqual(len(self.enrichment.calls), 1)
        review = make_history_service(self.core).show(done.steps[1]['receipt']['review_id'])
        self.assertEqual(review['review']['comparison']['state'], 'baseline')
        self.assertEqual(self.submit(record_review=True), done)
        self.assertIsNone(self.worker.work_one(job.id))
        self.assertEqual(len(self.enrichment.calls), 1)
        self.assertEqual(SQLiteEngineJobRepository(self.queue.path).get(job.id), done)
        self.assertEqual(self.service.results(job.id)['result'], done.result)
        self.queue.validate()

    def test_combined_url_misp_and_review_preserve_order_and_source_receipts(self):
        self.enrichment.content = url_body()
        job = self.submit(indicator_type='url', value=URL, sources=['urlscan', 'misp'],
                          warninglist_ids=['rfc6761'], record_review=True)
        done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual([step['key'] for step in done.steps], ['misp', 'urlscan', 'review'])
        self.assertEqual(self.lists.calls[0], 'revision')
        self.assertEqual(done.steps[1]['receipt']['provider'], 'urlscan')
        with closing(sqlite3.connect(self.queue.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM engine_job_events').fetchone()[0], 9)

    def test_failure_preserves_prior_source_and_review_does_not_turn_failure_into_success(self):
        good = self.enrichment_service.refresh(indicator_type='sha256', value=HASH)
        self.enrichment.error = SourceError('Controlled timeout')
        job = self.submit(record_review=True)
        done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'failed')
        self.assertEqual(done.steps[0]['receipt']['source_status'], 'failed')
        self.assertIsNone(done.steps[0]['receipt']['snapshot_sha256'])
        self.assertEqual(done.steps[1]['status'], 'complete')
        self.assertEqual(self.enrichment_service.lookup(indicator_type='sha256', value=HASH)['successful_run']['id'], good['run']['id'])

    def test_explicit_retry_reuses_only_completed_sources_and_records_fresh_review(self):
        self.enrichment.error = SourceError('Controlled timeout')
        first = self.submit(sources=['circl', 'misp'], warninglist_ids=['rfc6761'], record_review=True)
        done = self.worker.work_one(first.id)
        self.assertEqual(done.status, 'partial')
        old_review = done.steps[-1]['receipt']['review_id']
        list_calls = len(self.lists.calls)
        self.enrichment.error = None
        retry = self.service.retry(first.id, idempotency_key='retry')
        self.assertEqual(retry.steps[1]['status'], 'complete')
        self.assertEqual(retry.steps[1]['reused_from'], first.id)
        self.assertEqual(retry.steps[-1]['status'], 'pending')
        second = self.worker.work_one(retry.id)
        self.assertEqual(second.status, 'complete')
        self.assertEqual(len(self.lists.calls), list_calls)
        self.assertEqual(len(self.enrichment.calls), 2)
        self.assertNotEqual(second.steps[-1]['receipt']['review_id'], old_review)
        self.assertEqual(self.service.retry(first.id, idempotency_key='retry'), second)
        with self.assertRaises(EngineJobError):
            self.service.retry(second.id, idempotency_key='invalid')

    def test_partial_misp_batch_retry_is_explicit_and_preserves_success_receipts(self):
        self.lists.payloads['rfc1918'] = SourceError('List unavailable')
        job = self.submit(indicator_type='domain', value='example.com', sources=['misp'], warninglist_ids=['rfc1918', 'rfc6761'])
        done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'partial')
        self.assertEqual(done.steps[0]['status'], 'partial')
        self.assertEqual(len(done.steps[0]['receipt']['runs']), 2)
        retry = self.service.retry(job.id, idempotency_key='retry')
        self.assertEqual(retry.steps[0]['status'], 'pending')

    def test_cancel_queued_is_repeatable_never_dispatches(self):
        job = self.submit()
        self.assertEqual(self.service.cancel(job.id).status, 'cancelled')
        before = self.queue.path.read_bytes()
        self.assertEqual(self.service.cancel(job.id).status, 'cancelled')
        self.assertEqual(before, self.queue.path.read_bytes())
        self.assertIsNone(self.worker.work_one(job.id))
        self.assertEqual(self.enrichment.calls, [])

    def test_cancel_during_external_request_retains_receipt_and_skips_following_steps(self):
        job = self.submit(sources=['circl', 'misp'], warninglist_ids=['rfc6761'], record_review=True)
        original = self.enrichment.fetch
        def fetch(query):
            cancelled = self.service.cancel(job.id)
            self.assertTrue(cancelled.cancel_requested)
            self.assertEqual(cancelled.status, 'running')
            self.assertEqual(self.service.cancel(job.id), cancelled)
            return original(query)
        with patch.object(self.enrichment, 'fetch', side_effect=fetch):
            done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'cancelled')
        self.assertEqual([step['status'] for step in done.steps], ['complete', 'skipped', 'skipped'])
        self.assertEqual(self.lists.calls, [])
        self.assertEqual(done.steps[1]['reason'], 'cancelled')
        self.queue.validate()

    def test_cancel_between_check_and_start_does_not_send_request(self):
        job = self.submit()
        original = self.queue.source_step
        def step(*args, **kwargs):
            if kwargs['action'] == 'start':
                self.service.cancel(job.id)
            return original(*args, **kwargs)
        with patch.object(self.queue, 'source_step', side_effect=step):
            done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'cancelled')
        self.assertEqual(self.enrichment.calls, [])

    def test_late_cancel_before_finish_retains_consistent_terminal_result(self):
        job = self.submit()
        original = self.queue.finish
        def finish(*args, **kwargs):
            self.service.cancel(job.id)
            return original(*args, **kwargs)
        with patch.object(self.queue, 'finish', side_effect=finish):
            done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'cancelled')
        self.assertEqual(done.result['status'], 'cancelled')
        self.assertEqual(done.steps[0]['status'], 'complete')

    def test_budget_exhaustion_skips_remaining_sources_without_claiming_success(self):
        job = self.submit(record_review=True, max_seconds=1)
        self.runner.monotonic = iter((0, 2, 3)).__next__
        done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'failed')
        self.assertEqual([step['reason'] for step in done.steps], ['budget_exhausted', 'budget_exhausted'])
        self.assertEqual(self.enrichment.calls, [])

    def test_crash_after_request_or_evidence_commit_requires_explicit_uncertain_retry(self):
        job = self.submit()
        original = self.operations.execute
        def crash(key, plan, job_id, **kwargs):
            original(key, plan, job_id, **kwargs)
            raise RuntimeError('Lost progress acknowledgement')
        with patch.object(self.operations, 'execute', side_effect=crash), self.assertRaises(RuntimeError):
            self.worker.work_one(job.id)
        interrupted = self.service.status(job.id)
        self.assertEqual(interrupted.status, 'interrupted')
        self.assertEqual(interrupted.steps[0]['status'], 'running')
        self.assertIsNone(interrupted.steps[0]['receipt'])
        self.assertIsNone(self.worker.work_one(job.id))
        with self.assertRaises(EngineJobError) as caught:
            self.service.retry(job.id, idempotency_key='retry')
        self.assertEqual(caught.exception.code, 'uncertain_outcome')
        self.assertEqual(len(self.enrichment.calls), 1)
        retry = self.service.retry(job.id, idempotency_key='retry', allow_uncertain=True)
        self.assertEqual(self.worker.work_one(retry.id).status, 'complete')
        self.assertEqual(len(self.enrichment.calls), 2)

    def test_recovery_never_requeues_and_running_state_fences_other_jobs(self):
        first, second = self.submit('one'), self.submit('two')
        claim = self.queue.claim(first.id, recorded_at=NOW.isoformat())
        self.queue.link_session(claim, first.id, recorded_at=NOW.isoformat())
        self.queue.source_step(claim, 'circl', action='start', recorded_at=NOW.isoformat())
        with self.assertRaises(WorkerBusyError):
            self.worker.work_one(second.id)
        recovered = self.worker.recover()
        self.assertEqual(recovered[0].status, 'interrupted')
        self.assertEqual(recovered[0].steps[0]['status'], 'running')
        self.assertEqual(self.worker.recover(), ())
        self.assertEqual(self.enrichment.calls, [])

    def test_missing_reused_core_evidence_stops_before_new_external_requests(self):
        self.enrichment.error = SourceError('Timeout')
        first = self.submit(sources=['circl', 'misp'], warninglist_ids=['rfc6761'])
        self.worker.work_one(first.id)
        retry = self.service.retry(first.id, idempotency_key='retry')
        before = len(self.enrichment.calls), len(self.lists.calls)
        with patch.object(self.operations, 'verify', side_effect=StorageError('Missing core evidence')), self.assertRaises(StorageError):
            self.worker.work_one(retry.id)
        self.assertEqual(before, (len(self.enrichment.calls), len(self.lists.calls)))

    def test_wrong_order_identity_and_result_are_rejected_atomically(self):
        job = self.submit(record_review=True)
        claim = self.queue.claim(job.id, recorded_at=NOW.isoformat())
        self.queue.link_session(claim, job.id, recorded_at=NOW.isoformat())
        before = self.queue.path.read_bytes()
        with self.assertRaises(StorageError):
            self.queue.source_step(claim, 'review', action='start', recorded_at=NOW.isoformat())
        self.assertEqual(before, self.queue.path.read_bytes())
        with self.assertRaises(StorageError):
            self.queue.finish(claim, status='complete', result=result_for(self.queue.get(job.id)),
                              error_code=None, recorded_at=NOW.isoformat())
        self.assertEqual(before, self.queue.path.read_bytes())

    def test_tampered_progress_hash_fails_closed(self):
        job = self.submit()
        self.worker.work_one(job.id)
        with closing(sqlite3.connect(self.queue.path)) as db:
            db.execute("UPDATE engine_job_events SET event_sha256=? WHERE job_id=? AND ordinal=3", ('0' * 64, job.id))
            db.commit()
        with self.assertRaises(StorageError):
            self.service.status(job.id)

    def test_retry_payload_cannot_import_unrelated_receipt(self):
        job = self.submit()
        self.service.cancel(job.id)
        payload = SourceJobPayload(job.payload.plan, job.id, False, ({'key': 'circl', 'receipt': {
            'kind': 'enrichment_run', 'run_id': str(uuid4()), 'provider': 'circl', 'indicator_type': 'sha256',
            'value': HASH, 'source_status': 'no_match', 'snapshot_sha256': 'a' * 64, 'has_more': False}},))
        before = self.queue.path.read_bytes()
        with self.assertRaises(StorageError):
            self.queue.create('tampered', payload.request_json(), payload, recorded_at=NOW.isoformat())
        self.assertEqual(before, self.queue.path.read_bytes())

    def test_retry_depth_is_bounded_and_cycle_rejected(self):
        job = self.submit()
        self.service.cancel(job.id)
        self.service.clock = lambda: datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
        with self.assertRaises(StorageError):
            self.service.retry(job.id, idempotency_key='backwards-clock')
        self.service.clock = lambda: NOW
        for index in range(32):
            self.service.cancel(job.id)
            job = self.service.retry(job.id, idempotency_key=f'retry:{index}')
        self.service.cancel(job.id)
        with self.assertRaises(StorageError):
            self.service.retry(job.id, idempotency_key='too-deep')

    def test_list_pagination_does_not_include_legacy_profile_jobs(self):
        first, second = self.submit('one'), self.submit('two')
        payload = profile_payload()
        legacy = self.queue.create('legacy', request_json(payload.profile_name, payload.profile_revision), payload, recorded_at=NOW.isoformat())
        page = self.service.list(limit=1)
        self.assertEqual(page['jobs'][0]['job_id'], second.id)
        self.assertTrue(page['has_more'])
        self.assertEqual(self.service.list(offset=1, limit=1)['jobs'][0]['job_id'], first.id)
        with self.assertRaises(EngineJobError):
            self.service.status(legacy.id)

    def test_restore_quarantines_queued_work_and_preserves_completed_result(self):
        done = self.worker.work_one(self.submit('done', record_review=True).id)
        queued = self.submit('queued')
        destination = self.root / 'restored.sqlite3'
        SQLiteEngineJobRepository.restore(self.queue.path, destination)
        restored = SQLiteEngineJobRepository(destination)
        restored.quarantine_restored_queue(recorded_at=NOW.isoformat())
        self.assertEqual(restored.get(done.id), done)
        self.assertEqual(restored.get(queued.id).error_code, 'restored_uncertain')
        self.assertIsNone(restored.claim(None, recorded_at=NOW.isoformat()))

    def old_queue(self):
        path = self.root / 'old.sqlite3'
        repo = SQLiteEngineJobRepository(path)
        with patch('xti.adapters.sqlite_engine_jobs.ENGINE_JOB_SCHEMA_VERSION', 1), \
                patch('xti.adapters.sqlite_engine_jobs._EVENTS_DDL', _EVENTS_DDL_V1):
            repo.initialize()
        return repo

    def test_queue_v1_explicit_migration_preserves_legacy_events_and_backup(self):
        repo = self.old_queue()
        payload = profile_payload()
        old = repo.create('old', request_json(payload.profile_name, payload.profile_revision), payload, recorded_at=NOW.isoformat())
        old = repo.cancel(old.id, recorded_at=NOW.isoformat())
        with self.assertRaises(EngineJobError) as caught:
            SourceJobService(repo).submit(idempotency_key='new', plan_sha256=self.service.plan(
                indicator_type='sha256', value=HASH, sources=['circl'])['plan_sha256'],
                indicator_type='sha256', value=HASH, sources=['circl'])
        self.assertEqual(caught.exception.code, 'migration_required')
        with LocalExecutionLock(repo.path).acquire():
            migrated = repo.migrate()
        self.assertTrue(migrated['changed'])
        self.assertEqual(repo.get(old.id), old)
        backup = SQLiteEngineJobRepository(Path(migrated['backup']))
        self.assertEqual(backup.get(old.id), old)
        with closing(sqlite3.connect(backup.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
        self.assertFalse(repo.migrate()['changed'])
        self.assertEqual(len(list(self.root.glob('*.backup'))), 1)

    def test_migration_failure_rolls_back_and_keeps_readable_original_backup(self):
        repo = self.old_queue()
        original = repo._schema
        def fail_after_change(db, **options):
            if db.execute('PRAGMA user_version').fetchone()[0] == 4:
                raise StorageError('Controlled failure before commit')
            return original(db, **options)
        with patch.object(repo, '_schema', side_effect=fail_after_change), self.assertRaises(StorageError):
            repo.migrate()
        repo.validate()
        with closing(sqlite3.connect(repo.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
        backups = list(self.root.glob('*.backup'))
        self.assertEqual(len(backups), 1)
        SQLiteEngineJobRepository(backups[0]).validate()

    def test_migration_refuses_running_legacy_job(self):
        repo = self.old_queue()
        payload = profile_payload()
        job = repo.create('old', request_json(payload.profile_name, payload.profile_revision), payload, recorded_at=NOW.isoformat())
        repo.claim(job.id, recorded_at=NOW.isoformat())
        with self.assertRaises(WorkerBusyError):
            repo.migrate()
        self.assertEqual(list(self.root.glob('*.backup')), [])

    def test_cli_plan_needs_no_database_and_terminal_result_contains_evidence_commands(self):
        def invoke(arguments):
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(arguments)
            return code, out.getvalue(), err.getvalue()
        missing = self.root / 'absent'
        code, out, err = invoke(['--data-dir', str(missing), '--json', 'source-jobs', 'plan', HASH,
                                '--type', 'sha256', '--source', 'circl'])
        self.assertEqual(code, 0, err)
        self.assertFalse(missing.exists())
        self.assertFalse(json.loads(out)['data']['request_network_access'])
        done = self.worker.work_one(self.submit(record_review=True).id)
        code, out, err = invoke(['--data-dir', str(self.root), 'source-jobs', 'result', done.id])
        self.assertEqual(code, 0, err)
        self.assertIn('enrich run-show', out)
        self.assertIn('research-history show', out)
        self.assertIn(str(self.root), out)

"""Persisted HTTP attempt accounting, old jobs, uncertainty and consumer boundaries."""

from contextlib import closing, redirect_stdout, redirect_stderr
from datetime import datetime, timezone, timedelta
from io import BytesIO, StringIO
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from xti.adapters.enrichment_sources import PublicEnrichmentSource
from xti.adapters.misp_warninglists import MispWarninglistSource, REVISION_URL
from xti.adapters.metered_source_http import MeteredSourceOpener
from xti.adapters.source_job_steps import ExistingSourceJobOperations
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.adapters.sqlite_enrichment import SQLiteEnrichmentRepository
from xti.adapters.sqlite_warninglists import SQLiteWarninglistRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.engine_jobs import EngineJobService
from xti.application.indicator_enrichment import EnrichmentService
from xti.application.source_jobs import SourceJobService, CooperativeSourceJobRunner
from xti.application.warninglists import WarninglistService
from xti.domain.assets import ValidationError
from xti.domain.engine_jobs import canonical_json, digest
from xti.domain.source_jobs import SourceJobPayload
from xti.domain.source_job_usage import RequestUsageMeter, validate_usage
from xti.domain.warninglists import REVIEWED_REVISION
from xti.interfaces.cli import main
from xti.interfaces.research_history import make_history_service
from xti.interfaces.source_jobs import source_job_lines
from xti.ports.discovery import SourceError
from tests.test_indicator_enrichment import HASH, hash_body
from tests.test_warninglists import body


class Response(BytesIO):
    def __init__(self, content, url, status=200):
        super().__init__(content)
        self.url, self.status, self.headers = url, status, {}

    def geturl(self):
        return self.url


class Opener:
    def __init__(self):
        self.calls, self.error = [], None
        self.revision, self.readme = REVIEWED_REVISION, b'controlled terms'
        self.callback = None

    def open(self, request, **kwargs):
        url = request.full_url
        self.calls.append(url)
        if self.callback:
            self.callback(url)
        if self.error:
            raise self.error
        if url == REVISION_URL:
            content = json.dumps({'sha': self.revision}).encode()
        elif url.endswith('/README.md'):
            content = self.readme
        elif '/lists/' in url:
            content = body(url.split('/lists/')[1].split('/')[0])
        else:
            content = hash_body()
        return Response(content, url)


class SourceJobUsageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.core = self.root / 'xti.db'
        SQLiteAssetRepository(self.core).initialize()
        self.queue = SQLiteEngineJobRepository(self.root / 'engine-jobs.sqlite3')
        self.queue.initialize()
        self.now = datetime(2026, 11, 18, 14, tzinfo=timezone.utc)
        self.service = SourceJobService(self.queue, clock=lambda: self.now)
        self.http = Opener()
        self.lists = Opener()
        self.operations = ExistingSourceJobOperations(self.enrichment, self.warninglists,
            lambda: make_history_service(self.core))
        self.runner = CooperativeSourceJobRunner(self.operations, LocalExecutionLock(self.core))
        self.worker = EngineJobService(self.queue, None, LocalExecutionLock(self.queue.path),
            clock=lambda: self.now, source_runner=self.runner)
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No real network')))

    def enrichment(self, *, refresh=False, request_usage=None):
        source = PublicEnrichmentSource(SQLiteCooldownRepository(self.core), opener=self.http,
            request_usage=request_usage, wall_clock=lambda: self.now) if refresh else None
        return EnrichmentService(SQLiteEnrichmentRepository(self.core), source, clock=lambda: self.now)

    def warninglists(self, *, refresh=False, request_usage=None):
        source = MispWarninglistSource(opener=self.lists, request_usage=request_usage) if refresh else None
        return WarninglistService(SQLiteWarninglistRepository(self.core), source, clock=lambda: self.now)

    def submit(self, key='one', **changes):
        parameters = {'indicator_type': 'sha256', 'value': HASH, 'sources': ['circl'], **changes}
        plan = self.service.plan(**parameters)
        return self.service.submit(**parameters, idempotency_key=key, plan_sha256=plan['plan_sha256'])

    def usage(self, job):
        return self.service.status(job.id).to_dict()['execution']['requests']

    def test_success_survives_reopen_and_replay_without_double_counting(self):
        job = self.submit(record_review=True)
        self.assertEqual(self.usage(job)['attempts'], 0)
        done = self.worker.work_one(job.id)
        self.assertEqual(done.payload.version, 12)
        self.assertEqual(done.result['version'], 12)
        self.assertEqual(len(self.http.calls), 1)
        usage = SQLiteEngineJobRepository(self.queue.path).get(job.id).to_dict()['execution']['requests']
        self.assertEqual(usage['attempts'], 1)
        self.assertEqual(usage['recorded']['responses'], 1)
        self.assertEqual(usage['by_step'][1]['attempts'], 0)
        self.assertEqual(self.submit(record_review=True), done)
        self.assertIsNone(self.worker.work_one(job.id))
        self.assertEqual(self.usage(job), usage)

    def test_misp_actual_count_is_lower_than_planned_worst_case(self):
        job = self.submit(sources=['circl', 'misp'], warninglist_ids=['rfc1918', 'rfc6761'])
        done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual(done.to_dict()['plan']['maximum_external_requests'], 5)
        self.assertEqual(self.usage(job)['attempts'], 4)
        self.assertEqual(len(self.lists.calls), 3)

    def test_misp_changed_revision_counts_terms_request(self):
        self.lists.revision = 'a' * 40
        job = self.submit(indicator_type='domain', value='example.com', sources=['misp'], warninglist_ids=['rfc6761'])
        with patch('xti.adapters.misp_warninglists.REVIEWED_README_SHA256', hashlib.sha256(self.lists.readme).hexdigest()):
            done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual(self.usage(job)['attempts'], 3)

    def test_manifest_failure_records_one_attempt_not_one_per_failed_list(self):
        self.lists.error = URLError('controlled connection failure')
        job = self.submit(indicator_type='domain', value='example.com', sources=['misp'], warninglist_ids=['rfc1918', 'rfc6761'])
        self.assertEqual(self.worker.work_one(job.id).status, 'failed')
        usage = self.usage(job)
        self.assertEqual(usage['attempts'], 1)
        self.assertEqual(usage['recorded']['transport_errors'], 1)
        self.assertEqual(usage['recorded']['responses'], 0)

    def test_rate_limit_and_existing_cooldown_have_distinct_attempt_counts(self):
        self.http.error = HTTPError('https://hashlookup.circl.lu/', 429, 'Controlled', {'Retry-After': '60'}, BytesIO())
        first = self.submit()
        done = self.worker.work_one(first.id)
        self.assertEqual(self.usage(first)['recorded']['rate_limited'], 1)
        self.assertIn('provider_rate_limit', done.to_dict()['execution']['stop_reasons'])
        retry = self.service.retry(first.id, idempotency_key='retry')
        self.http.error = None
        self.assertEqual(self.worker.work_one(retry.id).status, 'failed')
        self.assertEqual(self.usage(retry)['attempts'], 0)
        self.assertEqual(len(self.http.calls), 1)

    def test_retry_reuses_completed_source_without_charging_old_usage(self):
        self.http.error = URLError('Controlled')
        first = self.submit(sources=['circl', 'misp'], warninglist_ids=['rfc6761'])
        self.assertEqual(self.worker.work_one(first.id).status, 'partial')
        self.assertEqual(self.usage(first)['attempts'], 3)
        self.http.error = None
        self.now += timedelta(seconds=3)
        retry = self.service.retry(first.id, idempotency_key='retry')
        done = self.worker.work_one(retry.id)
        self.assertEqual(done.status, 'complete')
        usage = self.usage(retry)
        self.assertEqual(usage['attempts'], 1)
        self.assertEqual(usage['by_step'][1]['state'], 'reused')
        self.assertEqual(usage['by_step'][1]['attempts'], 0)
        self.assertEqual(len(self.lists.calls), 2)

    def test_cancel_during_open_preserves_one_attempt_and_skips_next_source(self):
        job = self.submit(sources=['circl', 'misp'], warninglist_ids=['rfc6761'])
        self.http.callback = lambda url: self.service.cancel(job.id)
        done = self.worker.work_one(job.id)
        self.assertEqual(done.status, 'cancelled')
        self.assertEqual(self.usage(job)['attempts'], 1)
        self.assertEqual(self.lists.calls, [])
        self.assertIn('cancelled', done.to_dict()['execution']['stop_reasons'])

    def test_no_started_step_means_zero_requests_when_cancelled_or_time_exhausted(self):
        cancelled = self.submit('cancelled')
        self.service.cancel(cancelled.id)
        self.assertEqual(self.usage(cancelled)['attempts'], 0)
        expired = self.submit('expired', max_seconds=1)
        self.runner.monotonic = iter((0, 2)).__next__
        done = self.worker.work_one(expired.id)
        self.assertEqual(self.usage(expired)['attempts'], 0)
        self.assertIn('time_budget_exhausted', done.to_dict()['execution']['stop_reasons'])
        self.assertEqual(self.http.calls, [])

    def test_crash_after_request_does_not_invent_zero_or_exact_total(self):
        job = self.submit(sources=['circl', 'misp'], warninglist_ids=['rfc6761'])
        original = self.operations.execute
        def crash(key, *args, **kwargs):
            result = original(key, *args, **kwargs)
            if key == 'misp':
                raise RuntimeError('Receipt commit acknowledgement lost')
            return result
        with patch.object(self.operations, 'execute', side_effect=crash), self.assertRaises(RuntimeError):
            self.worker.work_one(job.id)
        usage = self.usage(job)
        self.assertFalse(usage['measurement_complete'])
        self.assertIsNone(usage['attempts'])
        self.assertEqual(usage['recorded']['attempts'], 1)
        self.assertEqual(usage['possible_unrecorded_attempts_maximum'], 3)
        self.assertIn('kesin toplam bilinmiyor', '\n'.join(source_job_lines(self.service.status(job.id).to_dict())))

    def test_running_snapshot_reports_inflight_uncertainty(self):
        job = self.submit()
        observations = []
        self.http.callback = lambda url: observations.append(self.usage(job))
        self.worker.work_one(job.id)
        self.assertIsNone(observations[0]['attempts'])
        self.assertEqual(observations[0]['by_step'][0]['state'], 'unrecorded')
        self.assertEqual(self.usage(job)['attempts'], 1)

    def test_legacy_job_preserves_payload_results_and_idempotency(self):
        plan = self.service.plan(indicator_type='sha256', value=HASH, sources=['circl'])['plan']
        payload = SourceJobPayload(plan, version=1)
        old = self.queue.create('one', payload.request_json(), payload, recorded_at=self.now.isoformat())
        done = self.worker.work_one(old.id)
        self.assertEqual(done.result['version'], 1)
        self.assertNotIn('usage', done.steps[0]['receipt'])
        before = self.queue.path.read_bytes()
        self.assertEqual(self.submit(), done)
        self.assertIsNone(self.usage(old)['attempts'])
        self.assertEqual(self.usage(old)['by_step'][0]['state'], 'legacy_unmeasured')
        self.assertEqual(self.queue.path.read_bytes(), before)
        self.assertEqual(SourceJobPayload.from_json(payload.to_json()).to_json(), payload.to_json())

    def test_old_failed_job_can_retry_with_new_measurement(self):
        plan = self.service.plan(indicator_type='sha256', value=HASH, sources=['circl'])['plan']
        payload = SourceJobPayload(plan, version=1)
        old = self.queue.create('old', payload.request_json(), payload, recorded_at=self.now.isoformat())
        self.http.error = URLError('Controlled')
        self.worker.work_one(old.id)
        self.http.error = None
        self.now += timedelta(seconds=3)
        new = self.service.retry(old.id, idempotency_key='new')
        self.worker.work_one(new.id)
        self.assertEqual(new.payload.version, 12)
        self.assertEqual(self.usage(new)['attempts'], 1)
        self.assertIsNone(self.usage(old)['attempts'])

    def test_timing_separates_queue_wait_from_execution(self):
        job = self.submit()
        self.now += timedelta(seconds=8)
        self.http.callback = lambda url: setattr(self, 'now', self.now + timedelta(seconds=3))
        done = self.worker.work_one(job.id)
        timing = done.to_dict()['execution']['timing']
        self.assertEqual(timing['queue_wait_seconds'], 8)
        self.assertEqual(timing['execution_seconds'], 3)

    def test_request_guard_blocks_before_calling_transport(self):
        meter = RequestUsageMeter(1)
        opener = MeteredSourceOpener(self.http, meter)
        from urllib.request import Request
        request = Request('https://example.com/')
        with opener.open(request):
            pass
        with self.assertRaises(SourceError):
            opener.open(request)
        self.assertEqual(len(self.http.calls), 1)
        self.assertEqual(meter.snapshot()['budget_rejections'], 1)

    def test_invalid_persisted_counters_are_rejected_even_with_recomputed_event_hash(self):
        job = self.submit()
        self.worker.work_one(job.id)
        with closing(sqlite3.connect(self.queue.path)) as db:
            ordinal, encoded = db.execute("SELECT ordinal, event_json FROM engine_job_events WHERE job_id=? AND kind='step_finished'", (job.id,)).fetchone()
            event = json.loads(encoded)
            event['receipt']['usage']['attempts'] = True
            encoded = canonical_json(event)
            db.execute('UPDATE engine_job_events SET event_json=?,event_sha256=? WHERE job_id=? AND ordinal=?',
                (encoded, digest(encoded), job.id, ordinal))
            db.commit()
        with self.assertRaises(StorageError):
            self.service.status(job.id)

    def test_counter_validation_rejects_over_budget_invalid_types_and_inconsistent_totals(self):
        meter = RequestUsageMeter(1)
        meter.begin()
        meter.received(200)
        valid = meter.snapshot()
        for changes in ({'attempts': True}, {'attempts': 2, 'responses': 2}, {'transport_errors': 1},
                        {'rate_limited': 2}, {'extra': 1}, {'version': True}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                validate_usage({**valid, **changes}, 1)

    def test_cli_status_and_result_share_persisted_usage_without_network(self):
        job = self.submit()
        self.worker.work_one(job.id)
        calls = len(self.http.calls)
        before = self.queue.path.read_bytes()
        for action in ('status', 'result'):
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(['--data-dir', str(self.root), '--json', 'source-jobs', action, job.id])
            self.assertEqual(code, 0, err.getvalue())
            data = json.loads(out.getvalue())['data']
            data = data['job'] if action == 'result' else data
            self.assertEqual(data['execution']['requests']['attempts'], 1)
        self.assertEqual(len(self.http.calls), calls)
        self.assertEqual(self.queue.path.read_bytes(), before)

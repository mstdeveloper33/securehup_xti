"""Document-level progress, transport usage, partial retry and lost acknowledgement."""
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from xti.adapters.publisher_documents import PublisherDocumentSource
from xti.adapters.source_job_publishers import PublisherDocumentStep
from xti.adapters.sqlite_reports import SQLiteReportRepository
from xti.domain.assets import ValidationError
from xti.domain.source_jobs import SourceJobPayload, source_plan
from xti.interfaces.source_jobs import source_job_lines
from tests import test_source_jobs as base
from tests import test_publisher_documents as publisher


class PublisherJobTests(unittest.TestCase):
    def setUp(self):
        self.f = base.SourceJobTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.repo = SQLiteReportRepository(self.f.core)
        self.calls, self.responses = [], []
        self.f.operations.publishers = lambda request_usage=None: PublisherDocumentStep(self.repo, self.f.queue,
            PublisherDocumentSource(resolve=lambda host: '1.1.1.1', connect=self.connect,
                clock=lambda: base.NOW, request_usage=request_usage))

    def connect(self, host, address, timeout):
        status, media, body = self.responses.pop(0)
        headers = {'Content-Type': media, 'Location': publisher.URL + 'redirect'}
        return SimpleNamespace(sock=None,
            request=lambda method, path, headers: self.calls.append((host, path)),
            getresponse=lambda: SimpleNamespace(status=status, getheader=lambda key, default=None: headers.get(key, default),
                                               read1=BytesIO(body).read1), close=lambda: None)

    def submit(self, count=2, **options):
        return self.f.submit(indicator_type='ipv4', value='192.0.2.10', sources=['publisher'],
            publisher_documents=[{'provider': 'cert-fr', 'url': publisher.URL + str(i)} for i in range(count)],
            max_requests=4 * count, **options)

    def test_real_html_pdf_parsers_and_offline_plan_keep_per_document_proof_and_usage(self):
        self.responses = [(200, 'text/html', publisher.HTML), (200, 'application/pdf', publisher.pdf())]
        job = self.submit()
        self.assertFalse(self.calls)
        done = self.f.worker.work_one(job.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual([s['key'] for s in done.steps], ['publisher:1', 'publisher:2'])
        self.assertEqual(done.to_dict()['execution']['requests']['attempts'], 2)
        self.assertEqual(len(self.repo.fetches()), 2)
        for step in done.steps:
            self.f.operations.verify(step['key'], step['receipt'], done.payload.plan)
        self.assertIn('reports fetch-show', '\n'.join(source_job_lines(done.to_dict())))
        self.assertEqual(self.submit().id, job.id)
        self.assertIsNone(self.f.worker.work_one(job.id))
        self.assertEqual(len(self.calls), 2)

    def test_partial_retry_only_fetches_failed_document_and_keeps_successful_revision(self):
        self.responses = [(200, 'text/html', publisher.HTML), (503, 'text/html', b'')]
        job = self.submit()
        first = self.f.worker.work_one(job.id)
        self.assertEqual(first.status, 'partial')
        self.assertEqual([s['status'] for s in first.steps], ['complete', 'failed'])
        successful = first.steps[0]['receipt']
        self.responses = [(200, 'text/html', publisher.HTML)]
        retry = self.f.service.retry(job.id, idempotency_key='retry')
        done = self.f.worker.work_one(retry.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual(done.steps[0]['receipt'], successful)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(done.to_dict()['execution']['requests']['attempts'], 1)
        self.f.queue.validate()

    def test_crash_after_core_commit_reuses_durable_success_without_network_retry(self):
        self.responses = [(200, 'text/html', publisher.HTML)]
        job = self.submit(count=1)
        execute = self.f.operations.execute
        def crash(*args, **options):
            execute(*args, **options)
            raise RuntimeError('Lost acknowledgement after committed document')
        with patch.object(self.f.operations, 'execute', side_effect=crash), self.assertRaises(RuntimeError):
            self.f.worker.work_one(job.id)
        broken = self.f.service.status(job.id)
        self.assertEqual(broken.status, 'interrupted')
        self.assertFalse(broken.to_dict()['execution']['requests']['measurement_complete'])
        retry = self.f.service.retry(job.id, idempotency_key='recover', allow_uncertain=True)
        done = self.f.worker.work_one(retry.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual(done.to_dict()['execution']['requests']['attempts'], 0)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.repo.fetches()), 1)

    def test_cancel_after_first_document_and_time_limit_preserve_completed_proof(self):
        self.responses = [(200, 'text/html', publisher.HTML)]
        job = self.submit()
        execute = self.f.operations.execute
        def cancel(key, *args, **options):
            receipt = execute(key, *args, **options)
            self.f.service.cancel(job.id)
            return receipt
        with patch.object(self.f.operations, 'execute', side_effect=cancel):
            done = self.f.worker.work_one(job.id)
        self.assertEqual(done.status, 'cancelled')
        self.assertEqual([s['status'] for s in done.steps], ['complete', 'skipped'])
        self.assertEqual(len(self.calls), 1)
        retry = self.f.service.retry(job.id, idempotency_key='retry')
        self.f.runner.monotonic = iter([0, 999]).__next__
        expired = self.f.worker.work_one(retry.id)
        self.assertEqual(expired.status, 'partial')
        self.assertEqual(expired.steps[1]['reason'], 'budget_exhausted')
        self.assertEqual(len(self.calls), 1)

    def test_redirect_response_and_failure_are_counted_without_claiming_parser_calls(self):
        self.responses = [(302, 'text/html', b''), (429, 'text/html', b'')]
        job = self.submit(count=1)
        done = self.f.worker.work_one(job.id)
        usage = done.steps[0]['receipt']['usage']
        self.assertEqual(done.status, 'failed')
        self.assertEqual((usage['attempts'], usage['responses'], usage['rate_limited']), (2, 2, 1))

    def test_old_models_keep_bytes_and_cannot_admit_publisher_steps_or_higher_budgets(self):
        old_plan = source_plan(indicator_type='sha256', value='a' * 64, sources=['circl'])
        for version in (1, 2, 3, 4):
            payload = SourceJobPayload(old_plan, version=version)
            self.assertEqual(SourceJobPayload.from_json(payload.to_json()).to_json(), payload.to_json())
        plan = self.submit(count=1).payload.plan
        with self.assertRaises(ValidationError):
            SourceJobPayload(plan, version=4).to_json()
        for options in ({'max_requests': 8}, {'publisher_documents': []}):
            with self.assertRaises(ValidationError):
                source_plan(**{**old_plan, **options})
        for docs in ([], [{'provider': 'cert-fr', 'url': 'https://127.0.0.1/a'}], plan['publisher_documents'] * 2):
            with self.assertRaises(ValidationError):
                source_plan(**{**plan, 'publisher_documents': docs})

    def test_expanded_plan_respects_existing_six_step_queue_limit_and_late_cancel(self):
        from xti.adapters.source_job_relationships import RelationshipNotificationStep
        from xti.interfaces.evidence import make_evidence_service
        self.f.operations.relationship_notifications = lambda: RelationshipNotificationStep(self.f.core, make_evidence_service(self.f.core))
        order = ['publisher', 'relationship-notify']
        options = dict(indicator_type='ipv4', value='192.0.2.10', sources=order, source_order=order,
            publisher_documents=[{'provider': 'cert-fr', 'url': publisher.URL + str(i)} for i in range(5)], max_requests=20)
        before = self.f.queue.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.f.submit(**options, record_review=True)
        self.assertEqual(self.f.queue.path.read_bytes(), before)
        job = self.f.submit(**options)
        self.responses = [(200, 'text/html', publisher.HTML)] * 5
        execute = self.f.operations.execute
        def cancel(key, *args, **kwargs):
            result = execute(key, *args, **kwargs)
            if key == 'relationship-notify':
                self.f.service.cancel(job.id)
            return result
        with patch.object(self.f.operations, 'execute', side_effect=cancel):
            done = self.f.worker.work_one(job.id)
        self.assertEqual(done.status, 'cancelled')
        self.assertEqual(len(done.steps), 6)
        self.assertTrue(all(step['status'] == 'complete' for step in done.steps))
        self.f.queue.validate()

    def test_empty_notification_step_cannot_hide_total_publisher_failure(self):
        from xti.domain.source_jobs import final_status
        self.assertEqual(final_status([{'key': 'publisher:1', 'status': 'failed'},
            {'key': 'relationship-notify', 'status': 'complete'}]), 'failed')

    def test_original_object_capacity_rejects_next_document_without_losing_eight_objects(self):
        from xti.application.reports import ReportService
        from xti.domain.publisher_documents import MAX_BODY_BYTES
        from xti.adapters.sqlite import SQLiteAssetRepository
        from unittest.mock import Mock
        source = Mock()
        service = ReportService(self.repo, publisher=source, clock=lambda: base.NOW)
        for index in range(9):
            prefix = publisher.HTML + b'<!--'
            suffix = str(index).encode() + b'-->'
            body = prefix + b'x' * (MAX_BODY_BYTES - len(prefix) - len(suffix)) + suffix
            source.fetch.return_value = publisher.document(body, url=publisher.URL + str(index))
            request = dict(provider='cert-fr', url=publisher.URL + str(index), idempotency_key=f'capacity-{index}')
            if index < 8:
                service.execute('reports.fetch', **request)
            else:
                before = self.f.core.read_bytes()
                with self.assertRaisesRegex(ValidationError, '64 MiB'):
                    service.execute('reports.fetch', **request)
                self.assertEqual(before, self.f.core.read_bytes())
        with SQLiteAssetRepository(self.f.core)._connection(readonly=True) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*),SUM(raw_size) FROM publisher_objects').fetchone(), (8, 64 * 1024 * 1024))
        self.assertEqual(len(self.repo.fetches()), 8)

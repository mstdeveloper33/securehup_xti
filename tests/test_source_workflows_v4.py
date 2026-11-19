"""Explicit ordering, failure policy, revision receipts and new provider scope."""
from dataclasses import replace
import json
import unittest
from unittest.mock import patch
from xti.adapters.source_job_reports import VersionedReportStep
from xti.adapters.sqlite_news import SQLiteNewsRepository
from xti.application.news import NewsService
from xti.adapters.source_job_news import HeldSourceJobLock
from xti.domain.news import NewsFeed
from xti.domain.source_jobs import source_plan, SourceJobPayload
from xti.domain.assets import ValidationError
from xti.domain.indicator_enrichment import enrichment_query, parse_enrichment
from xti.ports.discovery import SourceError
from xti.interfaces.reports import make_report_service
from xti.interfaces.research import make_research_service
from xti.application.research import research_data
from tests import test_source_jobs as jobs
from tests.test_news_storage import article


def whois_body(**changes):
    return json.dumps({'status': 'ok', 'data_call_name': 'whois',
        'data': {'resource': '1.1.1.1', 'authorities': ['apnic'], 'records': [[
            {'key': 'inetnum', 'value': '1.1.1.0 - 1.1.1.255'},
            {'key': 'netname', 'value': 'CONTROLLED'},
            {'key': 'organisation', 'value': 'ORG-EXAMPLE'},
            {'key': 'e-mail', 'value': 'not-retained@example.test'}]]}, **changes}).encode()


class WorkflowV4Tests(unittest.TestCase):
    def setUp(self):
        self.f = jobs.SourceJobTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.item = article(summary='Candidate 192.0.2.10 and other[.]example')
        owner = self
        class Source:
            calls = 0
            error = None
            def fetch(self, key):
                self.calls += 1
                if self.error:
                    raise self.error
                return NewsFeed(key, jobs.NOW.isoformat(), 'a' * 64, (owner.item,))
        self.source = Source()
        self.f.operations.news = lambda **kwargs: NewsService(SQLiteNewsRepository(self.f.core),
            self.source, HeldSourceJobLock(), clock=lambda: jobs.NOW)
        self.f.operations.reports = lambda: VersionedReportStep(self.f.core)

    def submit(self, **options):
        return self.f.submit(**{'indicator_type': 'domain', 'value': 'example.com',
            'sources': ['news:cisa', 'report-capture'], **options})

    def test_news_capture_changed_version_replay_and_old_receipt_survive(self):
        job = self.submit()
        done = self.f.worker.work_one(job.id)
        self.assertEqual(done.status, 'complete', done.to_dict())
        receipt = done.steps[1]['receipt']
        self.assertEqual(receipt['kind'], 'report_documents')
        self.assertEqual(receipt['usage']['attempts'], 0)
        rid = receipt['records'][0]['id']
        repeat = self.f.worker.work_one(self.submit(key='unchanged').id)
        self.assertEqual(repeat.steps[1]['receipt']['records'], receipt['records'])
        self.item = replace(self.item, summary='Changed report mentions 192.0.2.10')
        changed = self.f.worker.work_one(self.submit(key='changed').id)
        self.assertEqual(changed.steps[1]['receipt']['records'][0]['document_revision'], 2)
        self.f.operations.verify('report-capture', receipt, job.payload.plan)
        old = make_report_service(self.f.core).execute('reports.show', identifier=rid, document_revision=1)
        self.assertIn('other[.]example', old['record']['document']['text'])

    def test_stop_after_source_failure_skips_capture_and_review_but_continue_preserves_old_data(self):
        self.f.worker.work_one(self.submit(key='seed').id)
        self.source.error = SourceError('Controlled provider unavailable')
        stopped = self.f.worker.work_one(self.submit(key='stop', failure_policy='stop', record_review=True).id)
        self.assertEqual(stopped.steps[0]['status'], 'failed')
        self.assertEqual([s['reason'] for s in stopped.steps[1:]], ['dependency_failed', 'dependency_failed'])
        continued = self.f.worker.work_one(self.submit(key='continue', failure_policy='continue').id)
        self.assertEqual(continued.steps[1]['status'], 'complete')
        self.assertEqual(continued.steps[1]['receipt']['records'][0]['document_revision'], 1)

    def test_explicit_order_and_invalid_dependency_or_duplicate_order(self):
        options = dict(indicator_type='ipv4', value='1.1.1.1', sources=['news:cisa', 'ripestat-whois', 'report-capture'],
            source_order=['ripestat-whois', 'news:cisa', 'report-capture'])
        self.f.enrichment.content = whois_body()
        job = self.f.submit(**options)
        done = self.f.worker.work_one(job.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual([step['key'] for step in done.steps], options['source_order'])
        for order in (['report-capture', 'news:cisa', 'ripestat-whois'], ['news:cisa'] * 3):
            with self.assertRaises(ValidationError):
                source_plan(**{**options, 'source_order': order})
        for version in (1, 2, 3):
            with self.assertRaises(ValidationError):
                SourceJobPayload(source_plan(**options), version=version).to_json()

    def test_retry_of_failed_news_recaptures_dependent_report_instead_of_reusing_stale_success(self):
        self.f.worker.work_one(self.submit(key='seed').id)
        self.source.error = SourceError('Provider temporarily unavailable')
        failed = self.f.worker.work_one(self.submit(key='failed-news', failure_policy='continue').id)
        self.assertEqual(failed.steps[1]['status'], 'complete')
        self.source.error = None
        self.item = replace(self.item, summary='Corrected source now mentions 192.0.2.10')
        retried = self.f.service.retry(failed.id, idempotency_key='retry-failed-news')
        self.assertEqual(retried.steps[1]['status'], 'pending')
        done = self.f.worker.work_one(retried.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual(done.steps[1]['receipt']['records'][0]['document_revision'], 2)
        self.assertEqual(self.f.service.status(done.id), done)
        self.f.operations.verify('report-capture', failed.steps[1]['receipt'], failed.payload.plan)

    def test_capture_receipt_cannot_claim_a_different_selected_publisher(self):
        job = self.submit()
        done = self.f.worker.work_one(job.id)
        wrong_plan = source_plan(indicator_type='domain', value='example.com', sources=['news:ncsc', 'report-capture'])
        from xti.adapters.sqlite import StorageError
        with self.assertRaises(StorageError):
            self.f.operations.verify('report-capture', done.steps[1]['receipt'], wrong_plan)

    def test_capture_source_selection_limit_and_validation_do_not_invent_root_match(self):
        self.f.operations.news().refresh('cisa')
        plan = source_plan(indicator_type='domain', value='unrelated.example', sources=['report-capture'], capture_limit=1)
        receipt = VersionedReportStep(self.f.core).execute(plan, 'controlled-job')
        self.assertEqual(len(receipt['records']), 1)
        record = make_report_service(self.f.core).execute('reports.show', identifier=receipt['records'][0]['id'])['record']
        self.assertEqual(record['document']['scope'], [])
        for options in ({'capture_limit': True}, {'capture_source': 'arbitrary'}, {'capture_limit': 21}):
            with self.assertRaises(ValidationError):
                source_plan(**{**plan, **options})

    def test_interruption_after_capture_commit_requires_explicit_retry_without_duplicate_document(self):
        job = self.submit()
        original = self.f.operations.execute
        def fail_after_capture(key, *args, **kwargs):
            receipt = original(key, *args, **kwargs)
            if key == 'report-capture':
                raise RuntimeError('Controlled lost acknowledgement after report commit')
            return receipt
        with patch.object(self.f.operations, 'execute', side_effect=fail_after_capture), self.assertRaises(RuntimeError):
            self.f.worker.work_one(job.id)
        failed = self.f.service.status(job.id)
        self.assertEqual(failed.status, 'interrupted')
        from xti.domain.engine_jobs import EngineJobError
        with self.assertRaises(EngineJobError):
            self.f.service.retry(job.id, idempotency_key='no-ack')
        retry = self.f.service.retry(job.id, idempotency_key='ack-retry', allow_uncertain=True)
        done = self.f.worker.work_one(retry.id)
        self.assertEqual(done.status, 'complete')
        self.assertEqual(self.source.calls, 1)
        records = make_report_service(self.f.core).execute('reports.list')
        self.assertEqual(records['total_count'], 1)
        self.assertEqual(records['records'][0]['document_revision'], 1)

    def test_whois_context_minimizes_fields_and_rejects_wrong_scope(self):
        query = enrichment_query(indicator_type='ipv4', value='1.1.1.1', provider='ripestat-whois')
        parsed = parse_enrichment(query, 200, whois_body())
        self.assertEqual(parsed.status, 'matched')
        self.assertNotIn('not-retained', json.dumps(parsed.records))
        self.assertIsNone(parsed.records[0]['observed_at'])
        for changes in ({'status': 'error'}, {'data_call_name': 'different'},
                        {'data': {'resource': '8.8.8.8', 'authorities': [], 'records': []}},
                        {'query_params': {'resource': '8.8.8.8'}}, {'query_params': []}, {'data': []}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                parse_enrichment(query, 200, whois_body(**changes))
        outside = json.loads(whois_body())
        outside['data']['records'][0][0]['value'] = '8.8.8.0 - 8.8.8.255'
        self.assertEqual(parse_enrichment(query, 200, json.dumps(outside).encode()).status, 'no_match')

    def test_whois_failure_preserves_last_success_and_graph_source(self):
        self.f.enrichment.content = whois_body()
        self.f.enrichment_service.refresh(indicator_type='ipv4', value='1.1.1.1', provider='ripestat-whois')
        self.f.enrichment.error = SourceError('Provider failed')
        self.f.enrichment_service.refresh(indicator_type='ipv4', value='1.1.1.1', provider='ripestat-whois')
        graph = research_data(make_research_service(self.f.core).show(indicator_type='ipv4', value='1.1.1.1', max_hops=2))
        self.assertTrue(any(e['relationship_type'] == 'registry_reports_range' for e in graph['edges']))
        self.assertTrue(any(e['source'] == 'ripestat-whois' and e['status'] == 'failed' for n in graph['nodes'] for e in n['evidence']))
        self.assertFalse(any(e['kind'] == 'source_claim' for e in graph['edges']))

    def test_whois_ipv6_query_and_prefix_are_validated_without_ipv4_assumptions(self):
        query = enrichment_query(indicator_type='ipv6', value='2001:db8::1', provider='ripestat-whois')
        content = json.loads(whois_body())
        content['data']['resource'] = '2001:db8::1'
        content['data']['records'][0][0] = {'key': 'inet6num', 'value': '2001:db8::/32'}
        parsed = parse_enrichment(query, 200, json.dumps(content).encode())
        self.assertEqual(parsed.status, 'matched')
        self.assertEqual(parsed.records[0]['relationships'][0]['source_type'], 'ipv6')
        content['data']['records'][0][0]['value'] = 'not-a-network'
        with self.assertRaises(ValidationError):
            parse_enrichment(query, 200, json.dumps(content).encode())

"""New passive sources retain bounded receipts, original evidence and job semantics."""

from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch

from xti.adapters.sqlite_enrichment import SQLiteEnrichmentRepository
from xti.adapters.sqlite_news import SQLiteNewsRepository
from xti.adapters.sqlite_research import SQLiteResearchRepository
from xti.adapters.source_job_news import HeldSourceJobLock
from xti.application.news import NewsService
from xti.application.research import ResearchService, research_data
from xti.domain.assets import ValidationError
from xti.domain.indicator_enrichment import enrichment_query, parse_enrichment, request_url
from xti.domain.source_jobs import SourceJobPayload, source_plan
from xti.domain.news import NewsFeed
from xti.interfaces.investigation import make_investigation_service
from xti.interfaces.source_jobs import source_job_lines
from tests import test_source_jobs as job_fixtures
from tests.test_news_storage import article


def ripe_body(**changes):
    return json.dumps({'status': 'ok', 'data_call_name': 'network-info', 'query_params': {'resource': '1.1.1.1'},
                      'data': {'asns': ['13335'], 'prefix': '1.1.1.0/24'}, **changes}).encode()


class ExtendedSourceTests(unittest.TestCase):
    def fixture(self):
        fixture = job_fixtures.SourceJobTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def test_ripestat_validates_query_and_prefix_and_has_no_ownership_or_cve_claim(self):
        query = enrichment_query(indicator_type='ipv4', value='1.1.1.1')
        self.assertEqual(query.provider, 'ripestat')
        parsed = parse_enrichment(query, 200, ripe_body())
        self.assertEqual(parsed.records[0]['attributes']['asns'], [13335])
        without_echo = json.loads(ripe_body())
        del without_echo['query_params']
        self.assertEqual(parse_enrichment(query, 200, json.dumps(without_echo).encode()).status, 'matched')
        self.assertTrue(request_url(query).startswith('https://stat.ripe.net/data/network-info/'))
        for changes in ({'query_params': {'resource': '8.8.8.8'}}, {'data': {'asns': ['1'], 'prefix': '8.8.8.0/24'}},
                        {'data': {'asns': [True], 'prefix': '1.1.1.0/24'}}, {'status': 'error'}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                parse_enrichment(query, 200, ripe_body(**changes))

    def test_ripestat_worker_receipt_history_and_two_hop_prefix_asn(self):
        fixture = self.fixture()
        fixture.enrichment.content = ripe_body()
        job = fixture.submit(indicator_type='ipv4', value='1.1.1.1', sources=['ripestat'], record_review=True)
        result = fixture.worker.work_one(job.id)
        self.assertEqual(result.status, 'complete')
        self.assertEqual(result.payload.version, 3)
        self.assertEqual(result.steps[0]['receipt']['provider'], 'ripestat')
        graph = research_data(ResearchService(SQLiteResearchRepository(fixture.core)).show(indicator_type='ipv4', value='1.1.1.1'))
        self.assertTrue(any(row['kind'] == 'asn' and row['value'] == '13335' for row in graph['nodes']))
        self.assertFalse(any(edge['kind'] == 'source_claim' for edge in graph['edges']))
        fixture.operations.verify('ripestat', result.steps[0]['receipt'], result.payload.plan)

    def test_news_then_report_extraction_and_replay_keep_source_provenance(self):
        fixture = self.fixture()
        at = job_fixtures.NOW
        item = article(summary='Report lists hxxps://sample[.]example/a and 192.0.2.12')

        class Source:
            calls = 0
            def fetch(self, key):
                self.calls += 1
                return NewsFeed(key, at.isoformat(), 'a' * 64, (item,))

        source = Source()
        fixture.operations.news = lambda **kwargs: NewsService(SQLiteNewsRepository(fixture.core),
            source, HeldSourceJobLock(), clock=lambda: at)
        fixture.operations.investigations = lambda: make_investigation_service(fixture.core)
        job = fixture.submit(indicator_type='domain', value='example.com', sources=['news:cisa', 'reports'])
        result = fixture.worker.work_one(job.id)
        self.assertEqual(result.status, 'complete', result.to_dict())
        self.assertEqual(source.calls, 1)
        receipt = result.steps[1]['receipt']
        self.assertEqual(len(receipt['records']), 1)
        self.assertEqual(receipt['usage']['attempts'], 0)
        fixture.operations.verify('reports', receipt, result.payload.plan)
        fixture.operations.verify('news:cisa', result.steps[0]['receipt'], result.payload.plan)
        text = '\n'.join(source_job_lines(result.to_dict(), data_dir=fixture.root))
        self.assertIn('investigate show', text)
        stored = fixture.operations.investigations().show(receipt['records'][0]['id'])['record']
        self.assertEqual(stored['proposal']['source_record_id'], item.id)
        self.assertEqual(stored['proposal']['source_run_id'], result.steps[0]['receipt']['run_id'])
        second = fixture.submit(key='second-report-pass', indicator_type='domain', value='example.com', sources=['news:cisa', 'reports'])
        replay = fixture.worker.work_one(second.id)
        self.assertEqual(replay.steps[1]['receipt']['records'], receipt['records'])
        self.assertEqual(source.calls, 2)

    def test_legacy_job_bytes_remain_readable_and_cannot_claim_new_sources(self):
        legacy = SourceJobPayload(source_plan(indicator_type='sha256', value='a' * 64, sources=['circl']), version=2)
        self.assertEqual(SourceJobPayload.from_json(legacy.to_json()), legacy)
        with self.assertRaises(ValidationError):
            SourceJobPayload(source_plan(indicator_type='ipv4', value='1.1.1.1', sources=['ripestat']), version=2).to_json()

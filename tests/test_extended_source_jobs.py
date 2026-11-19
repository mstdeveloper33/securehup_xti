"""New passive sources retain bounded receipts, original evidence and job semantics."""

from datetime import datetime, timezone
import json
import sqlite3
import unittest
from pathlib import Path
from contextlib import closing
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
        self.assertEqual(result.payload.version, 4)
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

    def test_maximum_five_sources_plus_review_finish_and_late_cancel_fit_journal(self):
        fixture = self.fixture()
        fixture.enrichment.content = ripe_body()
        class Source:
            def fetch(self, key):
                return NewsFeed(key, job_fixtures.NOW.isoformat(), 'a' * 64,
                    (article(key, source=key, summary='Candidate 192.0.2.12'),))
        fixture.operations.news = lambda **kwargs: NewsService(SQLiteNewsRepository(fixture.core),
            Source(), HeldSourceJobLock(), clock=lambda: job_fixtures.NOW)
        fixture.operations.investigations = lambda: make_investigation_service(fixture.core)
        options = {'indicator_type': 'ipv4', 'value': '1.1.1.1',
            'sources': ['news:cisa', 'news:ncsc', 'news:cert-fr', 'reports', 'ripestat'], 'record_review': True}
        first = fixture.submit(key='six-steps', **options)
        done = fixture.worker.work_one(first.id)
        self.assertEqual(done.status, 'complete', done.to_dict())
        self.assertEqual(len(done.result['steps']), 6)
        second = fixture.submit(key='six-steps-late-cancel', **options)
        execute = fixture.operations.execute
        def cancel_after_last_step(key, *args, **kwargs):
            receipt = execute(key, *args, **kwargs)
            if key == 'review':
                fixture.service.cancel(second.id)
            return receipt
        with patch.object(fixture.operations, 'execute', side_effect=cancel_after_last_step):
            cancelled = fixture.worker.work_one(second.id)
        self.assertEqual(cancelled.status, 'cancelled')
        self.assertEqual(len(cancelled.result['steps']), 6)
        self.assertTrue(all(step['status'] == 'complete' for step in cancelled.steps))
        with closing(sqlite3.connect(fixture.queue.path)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM engine_job_events WHERE job_id=?',
                                               (second.id,)).fetchone()[0], 16)
        fixture.queue.validate()

    def test_queue_v2_upgrade_preserves_payload_event_bytes_and_original_backup(self):
        from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository, _EVENTS_DDL_V2
        from xti.application.source_jobs import SourceJobService
        from xti.domain.engine_jobs import EngineJobError
        fixture = self.fixture()
        repo = SQLiteEngineJobRepository(fixture.root / 'legacy-v2.sqlite3')
        with patch('xti.adapters.sqlite_engine_jobs.ENGINE_JOB_SCHEMA_VERSION', 2), \
             patch('xti.adapters.sqlite_engine_jobs._EVENTS_DDL', _EVENTS_DDL_V2):
            repo.initialize()
        payload = SourceJobPayload(source_plan(indicator_type='sha256', value='a' * 64, sources=['circl']), version=2)
        old = repo.create('legacy-v2', payload.request_json(), payload, recorded_at=job_fixtures.NOW.isoformat())
        repo.cancel(old.id, recorded_at=job_fixtures.NOW.isoformat())
        service = SourceJobService(repo)
        options = dict(indicator_type='ipv4', value='1.1.1.1', sources=['ripestat'])
        with self.assertRaises(EngineJobError) as caught:
            service.submit(**options, idempotency_key='new-v3', plan_sha256=service.plan(**options)['plan_sha256'])
        self.assertEqual(caught.exception.code, 'migration_required')
        def rows(path):
            with closing(sqlite3.connect(path)) as connection:
                return [connection.execute('SELECT rowid,* FROM ' + table + ' ORDER BY rowid').fetchall()
                        for table in ('engine_jobs', 'engine_job_events')]
        before = rows(repo.path)
        migrated = repo.migrate()
        self.assertEqual((migrated['from_version'], migrated['to_version']), (2, 3))
        self.assertEqual(rows(repo.path), before)
        self.assertEqual(rows(Path(migrated['backup'])), before)
        self.assertEqual(repo.get(old.id).payload.version, 2)
        self.assertEqual(service.submit(**options, idempotency_key='new-v3',
            plan_sha256=service.plan(**options)['plan_sha256']).payload.version, 4)

    def test_existing_v3_job_in_v2_queue_is_readable_but_never_started_before_migration(self):
        from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository, _EVENTS_DDL_V2
        from xti.domain.engine_jobs import EngineJobError, digest
        fixture = self.fixture()
        repo = SQLiteEngineJobRepository(fixture.root / 'candidate-v2.sqlite3')
        with patch('xti.adapters.sqlite_engine_jobs.ENGINE_JOB_SCHEMA_VERSION', 2), \
             patch('xti.adapters.sqlite_engine_jobs._EVENTS_DDL', _EVENTS_DDL_V2):
            repo.initialize()
        legacy = SourceJobPayload(source_plan(indicator_type='sha256', value='a' * 64, sources=['circl']), version=2)
        old = repo.create('candidate-job', legacy.request_json(), legacy, recorded_at=job_fixtures.NOW.isoformat())
        # Reproduce immutable bytes produced by the earlier development candidate,
        # which admitted v3 source plans while its queue was still schema 2.
        pending = SourceJobPayload(source_plan(indicator_type='ipv4', value='1.1.1.1',
            sources=['news:cisa', 'news:ncsc', 'news:cert-fr', 'reports', 'ripestat'], record_review=True))
        with closing(sqlite3.connect(repo.path)) as connection, connection:
            connection.execute('UPDATE engine_jobs SET request_json=?,request_sha256=?,payload_json=?,payload_sha256=? WHERE id=?',
                (pending.request_json(), digest(pending.request_json()), pending.to_json(), digest(pending.to_json()), old.id))
        self.assertEqual(repo.get(old.id).payload, pending)
        with self.assertRaises(EngineJobError) as caught:
            repo.claim(old.id, recorded_at=job_fixtures.NOW.isoformat())
        self.assertEqual(caught.exception.code, 'migration_required')
        self.assertEqual(repo.get(old.id).status, 'queued')
        repo.migrate()
        self.assertEqual(repo.get(old.id).payload, pending)
        self.assertEqual(repo.claim(old.id, recorded_at=job_fixtures.NOW.isoformat()).job.status, 'running')

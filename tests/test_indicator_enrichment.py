"""Source identity, evidence persistence, migration and offline company boundaries."""
from contextlib import closing, redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from xti.adapters.company_workspaces import resolve_company_workspace
from xti.adapters.enrichment_sources import PublicEnrichmentSource, _NoRedirect
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.sqlite_enrichment import SQLiteEnrichmentRepository
from xti.adapters.sqlite_research import SQLiteResearchRepository
from xti.application.indicator_enrichment import EnrichmentService
from xti.application.research import ResearchService, research_data
from xti.domain.assets import ValidationError
from xti.domain.indicator_enrichment import enrichment_query, parse_enrichment, request_url, MAX_BYTES
from xti.domain.research import ResearchSnapshotChanged
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 11, 17, 10, tzinfo=timezone.utc)
HASH = 'a' * 64
URL = 'https://example.com/Path?X=1'
SCAN = '018fe222-1111-7111-a111-111111111111'


def encoded(data):
    return json.dumps(data).encode()


def hash_body(**changes):
    return encoded({'SHA-256': HASH.upper(), 'SHA-1': 'b' * 40, 'MD5': 'c' * 32,
        'FileName': 'bin/example', 'FileSize': '42', 'source': 'controlled-fixture',
        'hashlookup:trust': 50, **changes})


def url_body(**changes):
    data = {'results': [{'_id': SCAN,
        'task': {'uuid': SCAN, 'time': '2026-11-01T10:00:00Z', 'url': URL, 'visibility': 'public'},
        'page': {'url': 'https://destination.example/', 'ip': '192.0.2.7', 'title': 'Controlled page'}}],
        'has_more': False, 'total': 1}
    return encoded({**data, **changes})


class Source:
    def __init__(self):
        self.status, self.content, self.error, self.calls = 200, hash_body(), None, []

    def fetch(self, query):
        self.calls.append(query)
        if self.error:
            raise self.error
        return self.status, self.content


class IndicatorEnrichmentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.data = self.root / 'selected data'
        self.path = self.data / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.repository = SQLiteEnrichmentRepository(self.path)
        self.source = Source()
        self.now = NOW
        self.service = EnrichmentService(self.repository, self.source, clock=lambda: self.now)
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No unplanned network')))
        self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No subprocess')))

    def refresh(self, value=HASH, kind='sha256'):
        return self.service.refresh(indicator_type=kind, value=value)

    def lookup(self, value=HASH, kind='sha256'):
        return self.service.lookup(indicator_type=kind, value=value)

    def files(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def graph(self, value=HASH, kind='sha256', **options):
        return research_data(ResearchService(SQLiteResearchRepository(self.path), clock=lambda: self.now).show(
            indicator_type=kind, value=value, **options))

    def invoke(self, args, request=None):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', StringIO(json.dumps(request))):
            result = main(args)
        return result, out.getvalue(), err.getvalue()

    def request(self, operation='enrichment.lookup', parameters=None):
        return {'contract_version': 1, 'request_id': 'context-test', 'operation': operation,
            'parameters': {'indicator_type': 'sha256', 'value': HASH} if parameters is None else parameters}

    def test_new_state_and_offline_reads_never_touch_network_or_create_records(self):
        before = self.files()
        self.assertEqual(self.lookup()['status'], 'never')
        self.assertEqual(self.graph()['status'], 'not_recorded')
        self.assertEqual(self.source.calls, [])
        self.assertEqual(before, self.files())

    def test_receipt_metadata_known_file_is_not_an_ioc(self):
        data = self.refresh()
        self.assertEqual(data['status'], 'matched')
        self.assertEqual(data['source']['license'], 'CC-BY (version unspecified)')
        self.assertIsNone(data['records'][0]['observed_at'])
        self.assertEqual(data['records'][0]['attributes']['provider_trust'], 50)
        self.assertEqual(data['freshness_basis'], 'response_received_at')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM cti_indicators').fetchone()[0], 0)
        self.assertEqual(self.service.show(data['run']['id'])['records'], data['records'])

    def test_repeated_receipts_deduplicate_payload_but_keep_query_history(self):
        first = self.refresh()
        self.now += timedelta(minutes=1)
        second = self.refresh()
        self.assertNotEqual(first['run']['id'], second['run']['id'])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM enrichment_snapshots').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM enrichment_runs').fetchone()[0], 2)
        history = self.service.history(indicator_type='sha256', value=HASH, limit=1)
        self.assertTrue(history['has_more'])
        self.assertEqual(history['runs'][0]['id'], second['run']['id'])
        self.assertEqual(self.service.history(indicator_type='sha256', value=HASH, offset=1)['runs'][0]['id'], first['run']['id'])

    def test_failure_preserves_previous_success_and_its_age(self):
        first = self.refresh()
        self.now += timedelta(days=2)
        self.source.error = SourceError('Controlled provider timeout')
        data = self.refresh()
        self.assertEqual((data['status'], data['result_status'], data['freshness']), ('failed', 'matched', 'stale'))
        self.assertEqual(data['successful_run']['id'], first['run']['id'])
        self.assertEqual(data['records'], first['records'])
        self.assertIsNone(data['run']['snapshot_sha256'])
        self.assertEqual(self.service.show(data['run']['id'])['records'], [])

    def test_known_absence_replaces_latest_result_without_erasing_history(self):
        first = self.refresh()
        self.source.status = 404
        self.source.content = encoded({'message': 'Non existing SHA-256', 'query': HASH})
        data = self.refresh()
        self.assertEqual((data['status'], data['records']), ('no_match', []))
        self.assertTrue(self.service.show(first['run']['id'])['records'])

    def test_bad_payload_creates_failed_receipt(self):
        self.source.content = hash_body(**{'SHA-256': 'd' * 64})
        self.assertEqual(self.refresh()['status'], 'failed')
        self.assertIsNone(self.lookup()['successful_run'])

    def test_tampered_payload_is_rejected_by_read_and_research(self):
        self.refresh()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('UPDATE enrichment_snapshots SET content=?', (hash_body(FileName='tampered'),))
            db.commit()
        for call in (self.lookup, self.graph):
            with self.assertRaises(StorageError):
                call()

    def test_receipt_status_tampering_is_rejected(self):
        self.refresh()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("UPDATE enrichment_runs SET status='no_match'")
            db.commit()
        with self.assertRaises(StorageError):
            self.lookup()

    def test_hash_research_has_source_backed_links_and_read_snapshot_guard(self):
        self.refresh()
        before = self.files()
        graph = self.graph(limit=1)
        self.assertEqual(graph['collected_edge_count'], 2)
        self.assertTrue(all(edge['kind'] == 'source_context' for edge in graph['edges']))
        self.assertTrue(all(edge['evidence'][0]['time_basis'] == 'response_received_at' for edge in graph['edges']))
        self.assertEqual(before, self.files())
        self.source.content = hash_body(FileName='new-name')
        self.refresh()
        with self.assertRaises(ResearchSnapshotChanged):
            self.graph(expected_snapshot=graph['snapshot_id'])

    def test_url_navigation_ip_stays_on_final_page_not_submission(self):
        self.source.content = url_body()
        self.refresh(URL, 'url')
        graph = self.graph(URL, 'url')
        self.assertEqual(graph['collected_edge_count'], 2)
        nodes = {node['id']: node['value'] for node in graph['nodes']}
        edge = next(item for item in graph['edges'] if item['relationship_type'] == 'archived_page_ip')
        self.assertEqual(nodes[edge['source_id']], 'https://destination.example/')
        self.assertEqual(nodes[edge['target_id']], '192.0.2.7')
        self.assertEqual(edge['evidence'][0]['observed_at'], '2026-11-01T10:00:00+00:00')

    def test_url_result_window_is_explicit_in_research(self):
        self.source.content = url_body(has_more=True, total=100, search_date_limit_days=90)
        data = self.refresh(URL, 'url')
        self.assertTrue(data['has_more'])
        self.assertEqual(data['search_date_limit_days'], 90)
        self.assertIn('enrichment_result_window', self.graph(URL, 'url')['limitations'])

    def test_query_validation_precedes_source_call(self):
        for kind, value in (('sha256', 'a'), ('domain', 'example.com'), ('url', 'https://user:pass@example.com/')):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                self.refresh(value, kind)
        self.assertEqual(self.source.calls, [])
        self.assertEqual(self.lookup()['status'], 'never')
        for provider in ('', False, [], 'unknown', 'urlscan'):
            with self.subTest(provider=provider), self.assertRaises(ValidationError):
                self.service.refresh(indicator_type='sha256', value=HASH, provider=provider)

    def test_cli_fetch_lookup_history_and_json_failure(self):
        with patch('xti.interfaces.indicator_enrichment.make_enrichment_service', return_value=self.service):
            code, out, err = self.invoke(['--data-dir', str(self.data), '--json', 'enrich', 'fetch', HASH, '--type', 'sha256'])
        self.assertEqual((code, err), (0, ''))
        data = json.loads(out)['data']
        for args in (['enrich', 'lookup', HASH, '--type', 'sha256'], ['enrich', 'run-show', data['run']['id']],
                     ['enrich', 'history', HASH, '--type', 'sha256'], ['research', HASH, '--type', 'sha256']):
            code, out, err = self.invoke(['--data-dir', str(self.data), *args])
            self.assertEqual((code, err), (0, ''), out)
            self.assertIn('CIRCL', out)
        self.source.error = SourceError('Controlled failure')
        with patch('xti.interfaces.indicator_enrichment.make_enrichment_service', return_value=self.service):
            code, out, err = self.invoke(['--data-dir', str(self.data), '--json', 'enrich', 'fetch', HASH, '--type', 'sha256'])
        self.assertEqual((code, err), (3, ''))
        self.assertFalse(json.loads(out)['ok'])

    def test_engine_reads_and_rejects_refresh_and_unknown_fields(self):
        run = self.refresh()['run']
        before = self.files()
        for request in (self.request(), self.request('enrichment.history'),
                        self.request('enrichment.run.get', {'run_id': run['id']}), self.request('research.show')):
            code, out, err = self.invoke(['--data-dir', str(self.data), 'engine'], request)
            self.assertEqual((code, err), (0, ''), out)
            self.assertEqual(json.loads(out)['status'], 'complete')
        self.assertEqual(before, self.files())
        for request in (self.request('enrichment.fetch'), self.request(parameters={'indicator_type': 'sha256', 'value': HASH, 'path': '/tmp/other'})):
            code, out, err = self.invoke(['--data-dir', str(self.data), 'engine'], request)
            self.assertEqual(code, 2)
        code, out, err = self.invoke(['--data-dir', str(self.data), 'engine'], self.request('enrichment.run.get', {'run_id': str(uuid4())}))
        self.assertEqual(json.loads(out)['error']['code'], 'not_found')

    def test_company_context_and_run_ids_cannot_leak_across_workspaces(self):
        self.refresh()
        root = self.root / 'companies'
        for company in ('first', 'second'):
            code, out, err = self.invoke(['platform', 'provision', '--root', str(root), '--company', company])
            self.assertEqual((code, err), (0, ''), out)
        workspace = resolve_company_workspace(root, 'first')
        service = EnrichmentService(SQLiteEnrichmentRepository(workspace.database), self.source, clock=lambda: NOW)
        run = service.refresh(indicator_type='sha256', value=HASH)['run']
        for company, status in (('first', 'matched'), ('second', 'never')):
            code, out, err = self.invoke(['platform', 'request', '--root', str(root), '--company', company], self.request())
            self.assertEqual((code, err), (0, ''), out)
            self.assertEqual(json.loads(out)['data']['status'], status)
        code, out, err = self.invoke(['platform', 'request', '--root', str(root), '--company', 'second'],
            self.request('enrichment.run.get', {'run_id': run['id']}))
        self.assertEqual(json.loads(out)['error']['code'], 'not_found')

    def test_source_status_contains_context_and_failure(self):
        self.refresh()
        self.source.error = SourceError('Controlled timeout')
        self.refresh()
        code, out, err = self.invoke(['--data-dir', str(self.data), '--json', 'sources', 'status'])
        self.assertEqual((code, err), (0, ''), out)
        self.assertIn('Controlled timeout', out)
        self.assertIn('enrichment:circl', out)

    def test_schema73_migration_keeps_assets_and_backup_and_never_automigrates(self):
        asset, _ = self.storage.add('example.com')
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DROP TABLE enrichment_runs')
            db.execute('DROP TABLE enrichment_snapshots')
            db.execute('PRAGMA user_version=73')
            db.commit()
        before = self.files()
        with self.assertRaises(StorageError):
            self.lookup()
        self.assertEqual(before, self.files())
        result = self.storage.migrate()
        from xti.adapters.schema import SCHEMA_VERSION
        self.assertEqual((result['from_version'], result['to_version']), (73, SCHEMA_VERSION))
        self.assertEqual(self.storage.list(), [asset])
        with closing(sqlite3.connect(result['backup'])) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 73)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_schema WHERE name='enrichment_runs'").fetchone())
        self.assertEqual(self.lookup()['status'], 'never')

    def test_interrupted_migration_rolls_back_and_retains_backup(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA user_version=73')
            db.commit()
        with patch('xti.adapters.sqlite.create_enrichment_schema', side_effect=RuntimeError('Interrupted')):
            with self.assertRaises(RuntimeError):
                self.storage.migrate()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 73)
        self.assertEqual(len(list((self.data / 'backups').glob('*.db'))), 1)

    def test_backup_restore_keeps_receipts_and_source_context(self):
        first = self.refresh()
        self.source.error = SourceError('Controlled failure after success')
        self.refresh()
        backup, restored = self.root / 'backups' / 'context.db', self.root / 'restored' / 'xti.db'
        self.storage.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        service = EnrichmentService(SQLiteEnrichmentRepository(restored), clock=lambda: NOW)
        data = service.lookup(indicator_type='sha256', value=HASH)
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(data['records'], first['records'])
        self.assertEqual(data['successful_run']['id'], first['run']['id'])
        self.assertEqual(len(service.history(indicator_type='sha256', value=HASH)['runs']), 2)

    def test_populated_future_schema_is_not_accepted_as_schema73(self):
        self.refresh()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA user_version=73')
            db.commit()
        with self.assertRaises(StorageError):
            self.storage.migrate()


class EnrichmentParserTests(unittest.TestCase):
    def test_canonical_exact_hash_and_no_parent_equivalence(self):
        query = enrichment_query(indicator_type='sha256', value=HASH.upper())
        result = parse_enrichment(query, 200, hash_body(parents=[{'SHA-1': 'd' * 40}]))
        self.assertEqual(query.value, HASH)
        self.assertEqual(len(result.records[0]['relationships']), 2)
        self.assertNotIn('d' * 40, str(result.records))

    def test_invalid_json_identity_status_and_types_are_not_empty_success(self):
        query = enrichment_query(indicator_type='sha256', value=HASH)
        examples = [(200, b'<html>blocked</html>'), (200, b'{"a":1,"a":2}'), (200, b'{"a":NaN}'),
            (200, hash_body(**{'SHA-256': 'b'*64})), (200, hash_body(**{'hashlookup:trust': True})),
            (200, hash_body(FileName='bad\x1b[31m')), (200, hash_body(FileSize=True)), (403, hash_body()),
            (404, b'{}'), (404, encoded({'message': 'Non existing SHA-256', 'query': 'b'*64})),
            (200, b'x'*(MAX_BYTES+1)), (200, b'['*2000+b']'*2000)]
        for status, content in examples:
            with self.subTest(status=status, size=len(content)), self.assertRaises(ValidationError):
                parse_enrichment(query, status, content)

    def test_url_path_case_query_and_scheme_are_not_conflated(self):
        for value in ('https://example.com/path?X=1', 'http://example.com/Path?X=1', 'https://example.com/Path?X=2'):
            query = enrichment_query(indicator_type='url', value=value)
            result = parse_enrichment(query, 200, url_body())
            self.assertEqual((result.status, result.excluded_count), ('no_match', 1))

    def test_keyword_query_escapes_quotes_and_cannot_choose_destination(self):
        query = enrichment_query(indicator_type='url', value='https://example.com/x?q="OR*')
        request = urlsplit(request_url(query))
        self.assertEqual(request.netloc, 'urlscan.io')
        self.assertIn('q=\\"OR*', parse_qs(request.query)['q'][0])

    def test_private_scan_bad_time_and_duplicate_scan_are_rejected(self):
        for mutate in ('visibility', 'time', 'duplicate', 'uuid'):
            data = json.loads(url_body())
            if mutate == 'duplicate':
                data['results'] *= 2
                data['total'] = 2
            else:
                data['results'][0]['task'][mutate] = {'visibility': 'private', 'time': '2026-11-17', 'uuid': str(uuid4())}[mutate]
            with self.subTest(mutate=mutate), self.assertRaises(ValidationError):
                parse_enrichment(enrichment_query(indicator_type='url', value=URL), 200, encoded(data))


class Response(BytesIO):
    def __init__(self, content, *, status=200, headers=None):
        super().__init__(content)
        self.status, self.headers = status, headers or {}


class EnrichmentHttpTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'xti.db'
        SQLiteAssetRepository(self.path).initialize()
        self.cooldowns = SQLiteCooldownRepository(self.path)
        self.calls = []
        self.response = Response(hash_body())
        owner = self
        class Opener:
            def open(self, req, timeout):
                owner.calls.append((req, timeout))
                return owner.response
        self.source = PublicEnrichmentSource(self.cooldowns, opener=Opener(), clock=lambda: 100,
            wall_clock=lambda: NOW, sleep=lambda delay: None)
        self.query = enrichment_query(indicator_type='sha256', value=HASH)

    def test_fixed_endpoint_get_no_file_upload(self):
        status, content = self.source.fetch(self.query)
        req, timeout = self.calls[0]
        self.assertEqual(status, 200)
        self.assertEqual(req.get_method(), 'GET')
        self.assertIsNone(req.data)
        self.assertEqual(req.full_url, request_url(self.query))
        self.assertEqual(timeout, 20)
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, '', {}, 'http://127.0.0.1/'))

    def test_ripestat_real_http_composition_uses_registered_cooldown_provider(self):
        from tests.test_extended_source_jobs import ripe_body
        self.response = Response(ripe_body())
        query = enrichment_query(indicator_type='ipv4', value='1.1.1.1')
        status, content = self.source.fetch(query)
        self.assertEqual(parse_enrichment(query, status, content).status, 'matched')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0].full_url, request_url(query))

    def test_rate_limit_is_persisted_and_next_call_sends_nothing(self):
        self.response = Response(b'{}', status=429, headers={'Retry-After': '120'})
        with self.assertRaises(SourceError):
            self.source.fetch(self.query)
        self.assertEqual(self.cooldowns.get('circl').not_before, (NOW + timedelta(seconds=120)).isoformat())
        with self.assertRaises(SourceError):
            self.source.fetch(self.query)
        self.assertEqual(len(self.calls), 1)

    def test_html_404_is_not_converted_to_absence_by_http_adapter(self):
        self.response = Response(b'<html>not found</html>', status=404)
        status, content = self.source.fetch(self.query)
        with self.assertRaises(ValidationError):
            parse_enrichment(self.query, status, content)

    def test_url_provider_404_is_failure(self):
        self.response = Response(b'{}', status=404)
        with self.assertRaises(SourceError):
            self.source.fetch(enrichment_query(indicator_type='url', value=URL))


if __name__ == '__main__':
    unittest.main()

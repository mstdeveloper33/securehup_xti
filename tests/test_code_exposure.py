import base64
from dataclasses import replace
from contextlib import closing
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from xti.adapters.code_sources import PublicCodeSources
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_code_exposure import SQLiteCodeRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.application.code_exposure import CodeExposureService
from xti.domain.assets import ValidationError
from xti.domain.code_exposure import CodeExposureError, Document, scope, observations, parameters


class Scanner:
    def status(self): return {'state': 'ready', 'tool': 'fixture', 'validation': False}
    def scan(self, content, *, seconds):
        return [{'rule': 'fixture-secret', 'line': 2}] if 'synthetic-secret' in content else []


class Source:
    def __init__(self):
        self.calls = 0
        self.documents = [Document('github-repositories', 'repo:file', 'https://github.com/example/example',
            'https://github.com/example/example', 'config.txt', '1' * 40, 'example.com\nsynthetic-secret', 'declared_repository')]
        self.state = 'complete'

    def status(self): return []
    def collect(self, selected, checkpoints, consume):
        self.calls += 1
        for document in self.documents: consume(document)
        return {'sources': [{'source': selected['sources'][0], 'status': self.state,
            'cursor': 0, 'retry_at': None, 'observed': self.state == 'complete', 'files': len(self.documents),
            'requests': 1, 'bytes': 100, 'http_status': 200 if self.state == 'complete' else 503}],
            'requests': 1, 'bytes': 100, 'elapsed_seconds': .01,
            'http_usage': {'attempts': 1, 'responses': 1, 'transport_errors': 0, 'rate_limited': 0, 'budget_rejections': 0}}


class CodeFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'xti.db'
        SQLiteAssetRepository(self.path).initialize()
        self.repo = SQLiteCodeRepository(self.path); self.source = Source(); self.scanner = Scanner()
        self.at = datetime(2026, 11, 21, tzinfo=timezone.utc)
        self.service = CodeExposureService(self.repo, self.source, self.scanner, now=lambda: self.at.isoformat())
        self.watch = self.service.execute('code.watch.add', domain='example.com', sources=['github-repositories'], idempotency_key='watch')
        self.inbox = SQLiteInboxRepository(self.path)

    def run_collection(self, key='run', **options):
        self.at += timedelta(days=1)
        return self.service.execute('code.run', identifier=self.watch['id'], expected_revision=self.watch['revision'], idempotency_key=key, **options)

    def findings(self): return self.service.execute('code.findings')['items']

    def test_baseline_masked_storage_and_replay_make_no_network_or_duplicate(self):
        first = self.run_collection()
        self.assertEqual(first['status'], 'complete')
        self.assertEqual(len(self.findings()), 2)
        self.assertEqual(self.inbox.list().total_count, 0)
        replay = self.run_collection()
        self.assertTrue(replay['replayed']); self.assertEqual(self.source.calls, 1)
        self.assertEqual(replay['report_sha256'], first['report_sha256'])
        self.assertNotIn(b'synthetic-secret', self.path.read_bytes())
        second = self.run_collection('same')
        self.assertEqual(second['report']['new_evidence'], 0)
        self.assertEqual(second['report']['changes'], 0)
        with closing(sqlite3.connect(self.path)) as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM code_evidence').fetchone()[0], 2)

    def test_change_is_atomic_inbox_read_state_and_review_are_preserved(self):
        self.run_collection()
        finding = self.findings()[1]
        review = self.service.execute('code.review', identifier=finding['id'], evidence_id=finding['evidence_id'],
            expected_revision=0, expected_observation_revision=1, decision='uncertain', reason='Controlled evidence', idempotency_key='review')
        self.source.documents = [replace(self.source.documents[0], revision='2' * 40, content='example.com\nsynthetic-secret\nnew material')]
        self.run_collection('changed')
        current = self.service.execute('code.finding.show', identifier=finding['id'])
        self.assertTrue(current['needs_review']); self.assertEqual(current['review']['id'], review['id'])
        page = self.inbox.list(); self.assertEqual(page.total_count, 2)
        identifier = page.items[0].notification.id
        frozen = self.inbox.get(identifier).code_change
        self.inbox.mark([identifier], True, self.at.isoformat())
        self.run_collection('changed')
        self.assertEqual(self.inbox.list().unread_count, 1)
        self.assertEqual(self.inbox.get(identifier).code_change, frozen)
        from xti.adapters.sqlite_status import SQLiteStatusRepository
        counts = SQLiteAssetRepository(self.path).inspect()
        status = SQLiteStatusRepository(self.path).snapshot(('crt.sh',), None, 10)
        self.assertEqual((counts['notification_count'], counts['unread_notification_count']), (2, 1))
        self.assertEqual((status.notification_count, status.unread_notification_count), (2, 1))

    def test_incomplete_source_never_removes_evidence_complete_file_can(self):
        self.run_collection()
        old = self.source.documents[0]
        self.source.state = 'unavailable'; self.source.documents = []
        failed = self.run_collection('unavailable')
        self.assertEqual(failed['status'], 'failed')
        self.assertTrue(all(f['state'] == 'observed' for f in self.findings()))
        self.source.state = 'complete'; self.source.documents = [replace(old, content='Nothing here')]
        self.run_collection('removed')
        self.assertTrue(all(f['state'] == 'not_observed_in_file' for f in self.findings()))
        self.assertEqual(self.inbox.list().total_count, 2)

    def test_missing_scanner_is_partial_and_never_clears_secret(self):
        self.run_collection()
        self.scanner.status = lambda: {'state': 'not_installed'}
        self.source.documents = [replace(self.source.documents[0], content='example.com')]
        result = self.run_collection('missing-tool')
        self.assertEqual(result['status'], 'partial')
        secret = next(f for f in self.findings() if f['kind'] == 'secret_candidate')
        self.assertEqual(secret['state'], 'observed')

    def test_request_conflict_stale_revision_disabled_and_recovery(self):
        with self.assertRaises(CodeExposureError):
            self.service.execute('code.watch.add', domain='other.example', idempotency_key='watch')
        values = dict(identifier=self.watch['id'], expected_revision=1, idempotency_key='pending')
        pending, _ = self.repo.reserve(values, self.at.isoformat())
        self.assertEqual(self.service.execute('code.run', **values)['status'], 'running')
        self.assertEqual(self.source.calls, 0)
        with self.assertRaises(CodeExposureError): self.run_collection('busy')
        recovered = self.service.execute('code.recover', identifier=pending['id'], idempotency_key='recover')
        self.assertEqual(recovered['status'], 'interrupted')
        self.assertEqual(self.source.calls, 0)
        self.watch = self.service.execute('code.watch.update', identifier=self.watch['id'], expected_revision=1, enabled=False, idempotency_key='disable')
        with self.assertRaises(CodeExposureError): self.run_collection('disabled')

    def test_stale_evidence_cannot_be_reviewed_and_old_case_is_frozen(self):
        from xti.config import Settings
        from xti.interfaces.cli import make_case_service
        self.run_collection()
        finding = self.findings()[1]
        cases = make_case_service(Settings(data_dir=Path(self.temp.name)))
        case = cases.create('Code test', summary='Fixture', reason='Verification').case
        linked = cases.add_evidence(case.id, 'code_exposure', finding['id'], reason='Freeze proof').evidence
        self.source.documents = [replace(self.source.documents[0], content='example.com\nsynthetic-secret\nchanged')]
        self.run_collection('changed')
        with self.assertRaises(CodeExposureError):
            self.service.execute('code.review', identifier=finding['id'], evidence_id=finding['evidence_id'],
                expected_revision=0, expected_observation_revision=1, decision='relevant', reason='Stale', idempotency_key='stale')
        self.assertEqual(json.loads(linked.snapshot_json)['finding']['evidence_id'], finding['evidence_id'])

    def test_reappearance_requires_new_review_even_when_evidence_is_reused(self):
        self.run_collection()
        original = self.source.documents[0]
        finding = self.findings()[1]
        values = dict(identifier=finding['id'], evidence_id=finding['evidence_id'], expected_revision=0,
                      expected_observation_revision=1, decision='remediated', reason='Human decision', idempotency_key='closed')
        self.service.execute('code.review', **values)
        self.run_collection('unchanged')
        self.assertFalse(self.service.execute('code.finding.show', identifier=finding['id'])['needs_review'])
        self.source.documents = [replace(original, content='Empty')]
        self.run_collection('absent')
        self.source.documents = [original]
        result = self.run_collection('reappeared')
        current = self.service.execute('code.finding.show', identifier=finding['id'])
        self.assertEqual(result['report']['new_evidence'], 0)
        self.assertEqual(current['observation_revision'], 3)
        self.assertEqual(current['review']['decision'], 'remediated')
        self.assertTrue(current['needs_review'])
        self.assertTrue(all(c['kind'] == 'reappeared' for c in self.service.execute('code.changes')['items'][-2:]))
        with self.assertRaises(CodeExposureError):
            self.service.execute('code.review', **{**values, 'expected_revision': 1, 'idempotency_key': 'stale-observation'})
        # Long decision history remains paged and the original immutable evidence is addressable.
        for revision in range(1, 22):
            self.service.execute('code.review', **{**values, 'expected_revision': revision,
                'expected_observation_revision': 3, 'idempotency_key': f'review-{revision}'})
        detail = self.service.execute('code.finding.show', identifier=finding['id'])
        self.assertEqual(len(detail['reviews']), 20); self.assertTrue(detail['older_reviews_available'])
        page = self.service.execute('code.reviews', identifier=finding['id'], limit=20)
        last = self.service.execute('code.reviews', identifier=finding['id'], after=page['next_after'])
        self.assertEqual(len(last['items']), 2)
        self.assertEqual(self.service.execute('code.evidence.show', identifier=finding['evidence_id']), finding['evidence'])

    def test_pagination_and_company_boundary(self):
        self.run_collection()
        first = self.service.execute('code.findings', limit=1)
        second = self.service.execute('code.findings', limit=1, after=first['next_after'])
        self.assertNotEqual(first['items'][0]['id'], second['items'][0]['id'])
        path = Path(self.temp.name) / 'other.db'; SQLiteAssetRepository(path).initialize()
        with self.assertRaises(CodeExposureError):
            SQLiteCodeRepository(path).read('code.finding.show', {'identifier': first['items'][0]['id']})

    def test_failed_atomic_finish_keeps_old_snapshot_and_run_can_be_recovered(self):
        self.run_collection()
        before = self.findings()
        self.source.documents = [replace(self.source.documents[0], content='example.com\nsynthetic-secret\nchanged')]
        with patch('xti.adapters.sqlite_notification_sequence.next_notification_sequence', side_effect=RuntimeError('disk fixture')):
            with self.assertRaises(RuntimeError): self.run_collection('failure')
        self.assertEqual(self.findings(), before)
        self.assertEqual(self.inbox.list().total_count, 0)
        self.assertEqual(self.service.execute('code.runs')['items'][-1]['status'], 'running')

    def test_terminal_followups_keep_the_selected_workspace(self):
        import shlex
        from xti.interfaces.code_exposure import code_lines
        from xti.interfaces.inbox import detail_lines, page_lines
        self.run_collection()
        self.source.documents = [replace(self.source.documents[0], content='example.com\nsynthetic-secret\nchanged')]
        run = self.run_collection('change')
        page = self.inbox.list()
        for lines in (code_lines(run, data_dir=self.path.parent),
                      page_lines(page, status='all', next_command=None, data_dir=self.path.parent),
                      detail_lines(self.inbox.get(page.items[0].notification.id), data_dir=self.path.parent)):
            command = next(line.split('./xti', 1)[1] for line in lines if './xti' in line)
            self.assertEqual(shlex.split('./xti' + command)[1:3], ['--data-dir', str(self.path.parent)])


class CodeSourceTests(unittest.TestCase):
    def test_missing_keys_are_not_empty_success_and_are_not_requested(self):
        source = PublicCodeSources(transport=lambda *a: self.fail('network called'), credentials=lambda _: None)
        result = source.collect(scope({'domain': 'example.com', 'sources': ['github-code', 'gitlab-code']}), {}, lambda _: None)
        self.assertEqual([s['status'] for s in result['sources']], ['missing_credentials'] * 2)
        self.assertEqual(result['requests'], 0)

    def test_public_github_fixture_reaches_actual_blob_with_no_credentials(self):
        requests, docs = [], []
        def transport(host, path, token, timeout):
            requests.append(path); self.assertIsNone(token); self.assertEqual(host, 'api.github.com')
            payload = ({'items': [{'private': False, 'full_name': 'example/project'}], 'total_count': 1, 'incomplete_results': False}
                if path.startswith('/search/') else {'private': False} if path == '/repos/example/project'
                else [{'commit': {'tree': {'sha': '1' * 40}}}] if '/commits?' in path
                else {'tree': [{'type': 'blob', 'mode': '100644', 'path': 'README.md', 'size': 11, 'sha': '2' * 40}], 'truncated': False} if '/trees/' in path
                else {'encoding': 'base64', 'size': 11, 'content': base64.b64encode(b'example.com').decode()})
            return 200, {'content-type': 'application/json'}, json.dumps(payload).encode()
        result = PublicCodeSources(transport, lambda _: None).collect(scope({'domain': 'example.com', 'sources': ['github-repositories']}), {}, docs.append)
        self.assertEqual(len(docs), 1); self.assertEqual(docs[0].content, 'example.com')
        self.assertEqual(result['requests'], 5)
        self.assertEqual(result['sources'][0]['status'], 'complete')

    def test_rate_limit_stores_retry_and_cooldown_makes_no_request(self):
        calls = []
        def transport(*a): calls.append(a); return 429, {'retry-after': '90'}, b''
        adapter = PublicCodeSources(transport, lambda _: None, wall=lambda: 1000)
        selected = scope({'domain': 'example.com', 'sources': ['github-repositories']})
        result = adapter.collect(selected, {}, lambda _: None)['sources'][0]
        self.assertEqual(result['retry_at'], 1090)
        again = adapter.collect(selected, {'github-repositories': result}, lambda _: None)
        self.assertEqual(again['sources'][0]['status'], 'cooldown'); self.assertEqual(len(calls), 1)

    def test_invalid_untrusted_response_does_not_leak_body(self):
        adapter = PublicCodeSources(lambda *a: (200, {'content-type': 'application/json'}, b'{bad private value'), lambda _: None)
        result = adapter.collect(scope({'domain': 'example.com', 'sources': ['github-repositories']}), {}, lambda _: None)
        self.assertEqual(result['sources'][0]['status'], 'invalid_response')
        self.assertNotIn('private value', json.dumps(result))

    def test_request_budget_and_per_source_fairness(self):
        calls = []
        def transport(host, path, *args):
            calls.append(host)
            return 200, {'content-type': 'application/json'}, json.dumps({'items': [{'private': False, 'full_name': 'example/project'}]} if host == 'api.github.com' else []).encode()
        result = PublicCodeSources(transport, lambda _: None).collect(scope({'domain': 'example.com', 'max_requests': 2}), {}, lambda _: None)
        self.assertEqual(calls, ['api.github.com', 'gitlab.com'])
        self.assertEqual(result['requests'], 2)

    def test_gitlab_tree_resumes_file_then_next_page_without_authenticated_content(self):
        docs = []
        def transport(host, path, token, timeout):
            self.assertEqual(host, 'gitlab.com')
            if '/blobs/' in path:
                self.assertIsNone(token)
                return 200, {}, b'example.com'
            self.assertEqual(token, 'fixture-key-no-network')
            if path.startswith('/api/v4/projects?'): payload = [{'id': 123, 'visibility': 'public', 'web_url': 'https://gitlab.com/example/repo'}]
            elif path.endswith('/123'): payload = {'visibility': 'public'}
            elif '/commits?' in path: payload = [{'id': '1' * 40}]
            else:
                page = parse_qs(urlsplit(path).query)['page'][0]
                payload = ([{'type': 'blob', 'path': f'file{i}', 'mode': '100644', 'id': str(i) * 40} for i in (2, 3)] +
                           [{'type': 'tree'}] * 98 if page == '1' else
                           [{'type': 'blob', 'path': 'file4', 'mode': '100644', 'id': '4' * 40}])
            return 200, {'content-type': 'application/json'}, json.dumps(payload).encode()
        adapter = PublicCodeSources(transport, lambda _: 'fixture-key-no-network')
        selected = scope({'domain': 'example.com', 'sources': ['gitlab-projects'], 'max_files': 1})
        checkpoint = {}
        for _ in range(3):
            result = adapter.collect(selected, checkpoint, docs.append)
            checkpoint = {'gitlab-projects': result['sources'][0]}
        self.assertEqual([doc.path for doc in docs], ['file2', 'file3', 'file4'])
        self.assertEqual(result['sources'][0]['status'], 'complete')

    def test_paste_window_only_retains_company_matches_and_explicit_access_failure(self):
        docs = []
        def transport(host, path, token, timeout):
            self.assertIsNone(token)
            if path.startswith('/api_scraping.php'):
                return 200, {'content-type': 'application/json'}, b'[{"key":"abcd1234"},{"key":"efgh5678"}]'
            return 200, {}, b'example.com synthetic-secret' if 'abcd1234' in path else b'unrelated synthetic-secret'
        selected = scope({'domain': 'example.com', 'sources': ['pastebin']})
        result = PublicCodeSources(transport, lambda _: None).collect(selected, {}, docs.append)
        self.assertEqual(result['sources'][0]['coverage'], 'recent_public_pastes')
        self.assertEqual(result['sources'][0]['status'], 'complete')
        self.assertEqual(len(observations(docs[0], selected, Scanner().scan(docs[0].content, seconds=1))), 2)
        self.assertEqual(observations(docs[1], selected, Scanner().scan(docs[1].content, seconds=1)), [])
        denied = PublicCodeSources(lambda *a: (403, {}, b''), lambda _: None).collect(selected, {}, docs.append)
        self.assertEqual(denied['sources'][0]['status'], 'access_denied')

    def test_cancel_before_request_and_authenticated_search_without_access(self):
        selected = scope({'domain': 'example.com', 'sources': ['github-code', 'gitlab-code']})
        adapter = PublicCodeSources(lambda *a: self.fail('network called'), lambda _: 'key', cancelled=lambda: True)
        result = adapter.collect(selected, {}, lambda _: None)
        self.assertEqual(result['requests'], 0)
        self.assertTrue(all(s['status'] == 'cancelled' for s in result['sources']))
        result = PublicCodeSources(lambda *a: (401, {}, b''), lambda _: 'key').collect(selected, {}, lambda _: None)
        self.assertTrue(all(s['status'] == 'authentication_required' for s in result['sources']))


class CodeContractTests(unittest.TestCase):
    def test_parameters_reject_secrets_unknown_fields_and_paths(self):
        for values in ({'domain': 'example.com', 'token': 'hidden'}, {'domain': 'example.com', 'max_requests': True},
                       {'domain': 'example.com', 'repositories': ['https://evil.example/repo']},
                       {'domain': 'example.com', 'aliases': ['ab']}):
            with self.assertRaises(ValidationError): scope(values)
        with self.assertRaises(ValidationError): parameters('code.watch.add', {'domain': 'example.com'})

    def test_company_match_boundaries_and_no_raw_line_storage(self):
        selected = scope({'domain': 'example.com'})
        document = Document('pastebin', 'pastebin:abcd1234', 'https://pastebin.com/abcd1234', '', 'abcd1234', 'abcd1234',
                            'example.com.attacker.net', 'public_window')
        self.assertEqual(observations(document, selected, []), [])
        document = replace(document, content='example.com\nprivate-token-that-must-not-escape')
        rows = observations(document, selected, [{'rule': 'example', 'line': 2}])
        self.assertEqual(len(rows), 2)
        self.assertNotIn('private-token', json.dumps(rows))

    def test_engine_and_platform_describe_new_operations(self):
        from xti.interfaces.engine import engine_manifest
        from xti.interfaces.platform_engine import platform_manifest
        self.assertIn('code.findings', engine_manifest()['operations'])
        self.assertNotIn('code.run', engine_manifest()['operations'])
        self.assertIn('code.run', platform_manifest()['request_network_operations'])

    def test_multilingual_boundary_subdomain_and_copied_content_group(self):
        selected = scope({'domain': 'example.com', 'aliases': ['Örnek Şirket', '示例公司']} )
        doc = Document('github-repositories', 'first:readme', 'https://github.com/a/b', 'https://github.com/a/b',
                       'README', '1' * 40, 'mail.example.com ÖRNEK ŞİRKET 示例公司', 'repository_search')
        first = observations(doc, selected, [])
        second = observations(replace(doc, provider='gitlab-projects', locator='second:readme', url='https://gitlab.com/a/b'), selected, [])
        self.assertIn('example.com', first[0]['matched_terms'])
        self.assertIn('示例公司', first[0]['matched_terms'])
        self.assertEqual(first[0]['content_group'], second[0]['content_group'])
        self.assertNotEqual(first[0]['identity'], second[0]['identity'])
        for content in ('notexample.com', 'example.com.attacker.org', 'otherexample.com'):
            self.assertEqual(observations(replace(doc, content=content, basis='public_window'), selected, []), [])


if __name__ == '__main__': unittest.main()

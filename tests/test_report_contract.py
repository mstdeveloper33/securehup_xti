"""Real CLI JSON and company routing, optimistic fences, restore and no network."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
from xti.adapters.sqlite_mentions import SQLiteMentionRepository
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.cti_indicators import CtiIndicatorService
from xti.interfaces.cli import main
from xti.interfaces.reports import make_report_service
from tests import test_news_storage as news
from tests import test_platform_isolation as companies


class ReportContractTests(unittest.TestCase):
    def setUp(self):
        self.f = news.NewsStorageTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.apply(news.article(summary='192.0.2.10 observed in a document'))
        self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No network')))

    def invoke(self, args, request=None):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', StringIO(json.dumps(request))):
            code = main(['--data-dir', str(self.f.path.parent), *args])
        return code, out.getvalue(), err.getvalue()

    def request(self, operation, **parameters):
        return {'contract_version': 1, 'request_id': 'contract', 'operation': operation, 'parameters': parameters}

    def test_capture_show_observations_cli_and_engine_share_exact_model(self):
        code, out, err = self.invoke(['--json', 'reports', 'capture', '--source', 'news', news.article().id, '--idempotency-key', 'capture'])
        self.assertEqual((code, err), (0, ''))
        rid = json.loads(out)['data']['record']['id']
        code, out, err = self.invoke(['--json', 'reports', 'show', rid])
        self.assertEqual((code, err), (0, ''))
        terminal = json.loads(out)['data']
        code, out, err = self.invoke(['engine'], self.request('reports.show', identifier=rid))
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(json.loads(out)['data'], terminal)
        code, out, err = self.invoke(['observations', 'ipv4', '192.0.2.10'])
        self.assertEqual((code, err), (0, ''))
        self.assertIn('Metinde geçme', out)
        self.assertIn('Olay zamanı: bilinmiyor', out)

    def test_engine_is_read_only_missing_report_is_not_found_and_invalid_requests_are_rejected(self):
        cases = [('reports.capture', {'source': 'news', 'identifier': news.article().id, 'idempotency_key': 'k'}, 'unsupported_operation', 2),
            ('reports.show', {'identifier': str(uuid4())}, 'not_found', 3),
            ('reports.show', {'identifier': str(uuid4()), 'document_revision': True}, 'invalid_parameters', 2),
            ('reports.list', {'limit': False}, 'invalid_parameters', 2),
            ('reports.list', {'source': []}, 'invalid_parameters', 2),
            ('observations.list', {'indicator_type': [], 'value': 'x'}, 'invalid_parameters', 2),
            ('observations.list', {'indicator_type': 'ipv4', 'value': '192.0.2.10', 'path': '/other'}, 'invalid_parameters', 2)]
        before = self.f.path.read_bytes()
        for operation, values, error, expected_code in cases:
            with self.subTest(operation=operation, values=values):
                code, out, err = self.invoke(['engine'], self.request(operation, **values))
                self.assertEqual((code, err), (expected_code, ''))
                self.assertEqual(json.loads(out)['error']['code'], error)
        self.assertEqual(self.f.path.read_bytes(), before)

    def test_terminal_and_manifest_explain_summary_and_revision_scope(self):
        data = make_report_service(self.f.path).execute('reports.capture', source='news', identifier=news.article().id, idempotency_key='captured')
        code, out, err = self.invoke(['reports', 'show', data['record']['id']])
        self.assertEqual((code, err), (0, ''))
        self.assertIn('Kaynakta alınma:', out)
        self.assertIn('Rapora kayıt:', out)
        code, out, err = self.invoke(['engine', '--describe'])
        manifest = json.loads(out)['data']['reports']
        self.assertTrue(manifest['full_article_fetch'])
        self.assertEqual(manifest['publishers'], ['cert-fr', 'ncsc'])


class ReportCompanyTests(unittest.TestCase):
    def setUp(self):
        self.f = companies.PlatformIsolationTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.sources = {company: SQLiteMentionRepository(context.database).catalog().records[0].id
                        for company, context in self.f.contexts.items()}

    def capture_request(self, selected_company, **changes):
        return self.f.request('reports.capture', {'source': 'mentions', 'identifier': self.sources[selected_company],
            'idempotency_key': 'same-key', 'expected_workspace_id': self.f.contexts[selected_company].workspace_id, **changes})

    def test_company_capture_same_key_and_observations_never_use_other_workspace(self):
        results = {company: self.f.complete(company, self.capture_request(company)) for company in ('alpha', 'beta')}
        self.assertNotEqual(results['alpha']['record']['id'], results['beta']['record']['id'])
        for company, other in (('alpha', 'beta'), ('beta', 'alpha')):
            rid = results[company]['record']['id']
            value = self.f.complete(company, self.f.request('reports.show', {'identifier': rid}))
            self.assertNotIn(other + ' private', json.dumps(value))
            self.f.rejected(other, self.f.request('reports.show', {'identifier': rid}), error='not_found')
            self.f.rejected(other, self.capture_request(other, identifier=self.sources[company], idempotency_key='other-source'), error='not_found')

    def test_workspace_fence_writer_lock_and_hostile_fields_prevent_writes(self):
        # Creating the operator's lock file is expected; rejected requests
        # must preserve the already provisioned evidence and journal.
        with LocalExecutionLock(self.f.contexts['alpha'].database).acquire():
            pass
        before = self.f.files()
        self.f.rejected('alpha', self.capture_request('alpha', expected_workspace_id=str(uuid4())), error='scope_mismatch')
        self.f.rejected('alpha', self.capture_request('alpha', company='beta'), error='invalid_parameters')
        self.f.rejected('missing', self.capture_request('alpha'))
        with LocalExecutionLock(self.f.contexts['alpha'].database).acquire():
            self.f.rejected('alpha', self.capture_request('alpha'), error='busy')
        self.assertEqual(self.f.files(), before)

    def test_explicit_ioc_link_rejects_other_company_and_keeps_source_confidence(self):
        def add(company):
            return CtiIndicatorService(SQLiteCtiIndicatorRepository(self.f.contexts[company].database)).add(
                'ipv4', '192.0.2.10', source_name='fixture', source_reference='https://source.example/' + company,
                confidence=45, description='Explicit test evidence')
        owned, foreign = add('alpha'), add('beta')
        report = self.f.complete('alpha', self.capture_request('alpha'))['record']
        params = {'identifier': report['id'], 'target_kind': 'indicator', 'target_id': foreign.indicator.id,
            'expected_revision': 1, 'state': 'linked', 'reason': 'Analyst evidence link',
            'idempotency_key': 'link', 'expected_workspace_id': self.f.contexts['alpha'].workspace_id}
        self.f.rejected('alpha', self.f.request('reports.link', params), error='not_found')
        params['target_id'] = owned.indicator.id
        result = self.f.complete('alpha', self.f.request('reports.link', params))
        self.assertEqual(result['record']['links'][0]['target']['id'], owned.indicator.id)
        self.assertEqual(result['record']['links'][0]['relationship'], 'reports-on')
        before = self.f.files()
        self.f.complete('alpha', self.f.request('observations.list', {'indicator_type': 'ipv4', 'value': '192.0.2.10'}))
        self.assertEqual(self.f.files(), before)
        self.f.rejected('alpha', self.f.request('reports.link', {**params, 'idempotency_key': 'stale-revision'}), error='revision_changed')

    def test_platform_backup_restore_preserves_report_history_and_rejects_previous_workspace(self):
        result = self.f.complete('alpha', self.capture_request('alpha'))['record']
        context = self.f.contexts['alpha']
        backup = backup_platform_workspace(context, self.f.base / 'backup')
        restored = restore_platform_workspace(self.f.base / 'restored', 'alpha', backup)
        after = make_report_service(restored.database).execute('reports.show', identifier=result['id'])
        self.assertEqual(after['record'], result)
        old_request = self.capture_request('alpha')
        self.f.root = self.f.base / 'restored'
        self.f.rejected('alpha', old_request, error='scope_mismatch')

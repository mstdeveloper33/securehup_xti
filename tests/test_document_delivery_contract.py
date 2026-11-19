"""Real CLI/JSON transport, company isolation, managed install and frozen references."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import sys
import tomllib
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
from xti.adapters.sqlite_reports import SQLiteReportRepository
from xti.application.reports import ReportService
from xti.domain.engine import parse_engine_request, EngineContractError
from xti.interfaces.cli import main
from xti.interfaces.journal_storage import make_journal_service
from xti.interfaces.reports import make_report_service
from tests import test_platform_isolation as companies
from tests import test_report_contract as contracts
from tests import test_reports as reports
from tests.test_publisher_documents import document, URL, HTML


class DocumentTransportTests(unittest.TestCase):
    def setUp(self):
        self.f = contracts.ReportContractTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def test_fetch_cli_stored_views_and_engine_read_boundary(self):
        with patch('xti.adapters.publisher_documents.PublisherDocumentSource.fetch', return_value=document()):
            code, out, err = self.f.invoke(['--json', 'reports', 'fetch', URL, '--provider', 'cert-fr', '--idempotency-key', 'fetch-cli'])
        self.assertEqual((code, err), (0, ''))
        record = json.loads(out)['data']['record']
        for arguments in (['reports', 'show', record['id']], ['reports', 'fetches'], ['reports', 'publishers'], ['journals', 'status'],
                ['journals', 'archive-plan'], ['relationships', 'queue']):
            with self.subTest(args=arguments):
                code, out, err = self.f.invoke(arguments)
                self.assertEqual((code, err), (0, ''))
                self.assertTrue(out)
        for operation, options in (('reports.fetches', {}), ('reports.publishers', {}), ('journals.status', {}),
                ('journals.archive-plan', {}), ('relationships.queue', {})):
            code, out, err = self.f.invoke(['engine'], self.f.request(operation, **options))
            self.assertEqual((code, err), (0, ''))
            self.assertEqual(json.loads(out)['status'], 'complete')
        for operation in ('reports.fetch', 'journals.archive-apply', 'journals.restore'):
            with self.assertRaises(EngineContractError):
                parse_engine_request(self.f.request(operation))

    def test_read_contract_rejects_paths_extra_fields_and_wrong_types(self):
        for operation, values in (('reports.fetches', {'limit': True}), ('journals.archive-plan', {'limit': 1001}),
                ('journals.status', {'path': '/tmp/other'}), ('relationships.queue', {'indicator_type': 'ipv4'}),
                ('reports.publishers', {'provider': 'other'})):
            code, out, err = self.f.invoke(['engine'], self.f.request(operation, **values))
            self.assertEqual((code, err), (2, ''))
            self.assertEqual(json.loads(out)['error']['code'], 'invalid_parameters')


class DocumentCompanyTests(unittest.TestCase):
    def setUp(self):
        self.f = companies.PlatformIsolationTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def fetch_request(self, company, **options):
        return self.f.request('reports.fetch', {'provider': 'cert-fr', 'url': URL, 'idempotency_key': 'same-publisher-key',
            'expected_workspace_id': self.f.contexts[company].workspace_id, **options})

    def test_same_key_fetches_are_company_local_and_wrong_fence_cannot_fetch(self):
        with patch('xti.adapters.publisher_documents.PublisherDocumentSource.fetch', return_value=document()) as source:
            self.f.rejected('alpha', self.fetch_request('alpha', expected_workspace_id=self.f.contexts['beta'].workspace_id), error='scope_mismatch')
            source.assert_not_called()
            a = self.f.complete('alpha', self.fetch_request('alpha'))
            b = self.f.complete('beta', self.fetch_request('beta'))
            self.assertNotEqual(a['record']['id'], b['record']['id'])
            self.f.complete('alpha', self.fetch_request('alpha'))
            self.assertEqual(source.call_count, 2)
        self.f.rejected('beta', self.f.request('reports.fetch-show', {'identifier': a['run']['id']}), error='not_found')
        self.f.rejected('beta', self.f.request('reports.show', {'identifier': a['record']['id']}), error='not_found')

    def test_company_archive_restore_and_workspace_backup_preserve_publisher_receipts(self):
        context = self.f.contexts['alpha']
        at = reports.NOW - timedelta(days=100)
        source = Mock(fetch=Mock(return_value=document(at=at)))
        service = ReportService(SQLiteReportRepository(context.database), publisher=source, clock=lambda: at)
        first = service.execute('reports.fetch', provider='cert-fr', url=URL, idempotency_key='old-first')
        source.fetch.return_value = document(HTML.replace(b'Public report', b'New public report'), at=at)
        service.execute('reports.fetch', provider='cert-fr', url=URL, idempotency_key='old-second')
        plan = self.f.complete('alpha', self.f.request('journals.archive-plan', {'older_than_days': 7}))
        self.assertEqual(plan['selected_count'], 1)
        params = {'older_than_days': 7, 'token': plan['token'], 'expected_workspace_id': context.workspace_id}
        self.f.rejected('beta', self.f.request('journals.archive-apply', params), error='scope_mismatch')
        self.f.rejected('beta', self.f.request('journals.archive-apply', {**params, 'expected_workspace_id': self.f.contexts['beta'].workspace_id}), error='snapshot_changed')
        result = self.f.complete('alpha', self.f.request('journals.archive-apply', params))
        self.assertEqual(result['changed_count'], 1)
        self.assertEqual(service.execute('reports.fetch', provider='cert-fr', url=URL, idempotency_key='old-first')['record'], first['record'])
        backup = backup_platform_workspace(context, self.f.base / 'publisher-backup')
        restored = restore_platform_workspace(self.f.base / 'publisher-restore', 'alpha', backup)
        self.assertEqual(make_report_service(restored.database).execute('reports.fetches')['total_count'], 2)
        self.assertEqual(make_journal_service(restored.database).execute('journals.status')['journals'][0]['cold_count'], 1)
        self.f.root = self.f.base / 'publisher-restore'
        self.f.rejected('alpha', self.f.request('journals.restore', {'identifier': result['event']['id'], 'expected_workspace_id': context.workspace_id}), error='scope_mismatch')
        self.f.contexts['alpha'] = restored
        after = self.f.complete('alpha', self.f.request('journals.restore', {'identifier': result['event']['id'], 'expected_workspace_id': restored.workspace_id}))
        self.assertEqual(after['changed_count'], 1)


class PdfInstallationTests(unittest.TestCase):
    def test_package_constraints_hashed_wheel_and_workflow_install_match(self):
        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads((root / 'pyproject.toml').read_text())['project']
        self.assertEqual(project['optional-dependencies']['reports'], ['pypdf==7.1.1'])
        self.assertIn('pypdf==7.1.1', (root / 'constraints/brand.txt').read_text().splitlines())
        self.assertIn('pypdf==7.1.1 --hash=sha256:04c5680d4b4cfa04ab505b09393fc949860c34a4dad6565284d11a2f5c3ce8b1', (root / 'requirements/reports.txt').read_text())
        for name in ('check', 'full-check', 'stabilization', 'brand-install', 'harvester-install'):
            self.assertIn('-r requirements/reports.txt', (root / '.github/workflows' / (name + '.yml')).read_text())
        from tests.test_news_installation import VERIFIER
        VERIFIER._verify_pdf_runtime(Path(sys.prefix))
        with patch.object(VERIFIER, 'distribution', side_effect=VERIFIER.PackageNotFoundError('pypdf')), self.assertRaises(VERIFIER.VerificationError):
            VERIFIER._verify_pdf_runtime(Path(sys.prefix))

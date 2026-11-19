"""Real PDF subprocess, untrusted HTTP boundaries, atomic evidence and replay."""
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from xti.adapters.publisher_documents import PublisherDocumentSource, html_text, pdf_text, _resolve
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_reports import SQLiteReportRepository
from xti.application.reports import ReportService
from xti.domain.assets import ValidationError
from xti.domain.publisher_documents import FetchedDocument, publisher_url
from xti.domain.reports import ReportError
from xti.ports.discovery import SourceError
from tests import test_reports as base

URL = 'https://cert.cyber.gouv.fr/cti/CERTFR-2026-CTI-001/'
HTML = b'<html><title>Public report</title><nav>ignore[.]example</nav><main><h1>Report</h1><p>192.0.2.10 and suspect[.]example.</p><script>bad[.]example</script></main></html>'


def document(body=HTML, *, at=base.NOW, url=URL):
    text, title = html_text(body)
    return FetchedDocument('cert-fr', url, url, (), 'text/html', body, text, title, 'xti-publisher-html-v1', None, at.isoformat())


def pdf(*, encrypted=False, blank=False):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if not blank:
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 40 700 Td (Indicator 192.0.2.10 and suspect[.]example.) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
    writer.add_metadata({'/Title': 'Controlled PDF'})
    if encrypted:
        writer.encrypt('fixture-password')
    output = BytesIO(); writer.write(output)
    return output.getvalue()


class PublisherTransportTests(unittest.TestCase):
    def test_html_main_text_discards_navigation_and_active_markup(self):
        text, title = html_text(HTML)
        self.assertEqual(title, 'Public report')
        self.assertEqual(html_text(HTML.replace(b'</main>', b'<svg><title>icon label</title></svg></main>'))[1], 'Public report')
        self.assertIn('192.0.2.10', text)
        self.assertNotIn('bad', text); self.assertNotIn('ignore', text)
        with self.assertRaises(SourceError):
            html_text(b'<html><nav>No article</nav></html>')
        with self.assertRaises(SourceError):
            html_text(b'<main>' + b'x' * 65537 + b'</main>')

    def test_real_pdf_worker_extracts_text_and_rejects_encrypted_scanned_and_corrupt_input(self):
        text, title, pages = pdf_text(pdf())
        self.assertIn('192.0.2.10', text)
        self.assertEqual((title, pages), ('Controlled PDF', 1))
        for body in (pdf(blank=True), pdf(encrypted=True), b'%PDF-not a document'):
            with self.subTest(size=len(body)), self.assertRaises(SourceError):
                pdf_text(body)

    def test_pdf_timeout_and_wrong_dependency_are_controlled_errors(self):
        import subprocess
        with patch('xti.adapters.publisher_documents.subprocess.run', side_effect=subprocess.TimeoutExpired('pdf', 18)), self.assertRaises(SourceError):
            pdf_text(pdf())
        with patch('xti.adapters.publisher_documents.importlib.metadata.version', return_value='wrong'), self.assertRaises(SourceError):
            pdf_text(b'%PDF-')

    def test_url_and_dns_scope_fail_before_connection(self):
        for value in ('http://cert.cyber.gouv.fr/cti/a', 'https://cert.cyber.gouv.fr.evil.example/cti/a',
                      'https://127.0.0.1/cti/a', 'https://cert.cyber.gouv.fr/cti/%2e%2e/a',
                      'https://cert.cyber.gouv.fr/cti/a?next=evil', 'https://x@cert.cyber.gouv.fr/cti/a',
                      'https://cert.cyber.gouv.fr:444/cti/a', 'https://cert.cyber.gouv.fr/cti/%252e%252e/a'):
            with self.subTest(url=value), self.assertRaises(ValidationError):
                publisher_url('cert-fr', value)
        with patch('xti.adapters.publisher_documents.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=b'["127.0.0.1"]')), self.assertRaises(SourceError):
            _resolve('cert.cyber.gouv.fr')

    def fetcher(self, responses):
        connections = []
        for status, headers, body in responses:
            response = SimpleNamespace(status=status, getheader=lambda key, default=None, h=headers: h.get(key, default), read1=BytesIO(body).read1)
            connections.append(Mock(sock=None, getresponse=Mock(return_value=response)))
        connect = Mock(side_effect=connections)
        return PublisherDocumentSource(resolve=Mock(return_value='1.1.1.1'), connect=connect, clock=lambda: base.NOW), connect, connections

    def test_approved_redirect_and_pdf_keep_complete_acquisition_chain(self):
        source, connect, connections = self.fetcher([(302, {'Location': URL}, b''), (200, {'Content-Type': 'text/html; charset=utf-8'}, HTML)])
        old = 'https://www.cert.ssi.gouv.fr/cti/CERTFR-2026-CTI-001/'
        result = source.fetch('cert-fr', old)
        self.assertEqual((result.url, result.final_url, result.redirects), (old, URL, (URL,)))
        self.assertEqual(connect.call_args_list[0].args[:2], ('www.cert.ssi.gouv.fr', '1.1.1.1'))
        self.assertTrue(all(c.close.called for c in connections))
        source, _, _ = self.fetcher([(200, {'Content-Type': 'application/pdf'}, pdf())])
        result = source.fetch('cert-fr', URL)
        self.assertEqual((result.parser, result.page_count), ('pypdf/7.1.1', 1))

    def test_redirect_mime_compression_truncation_and_http_errors_preserve_failure(self):
        for response in ((302, {'Location': 'https://127.0.0.1/cti/a'}, b''),
                         (200, {'Content-Type': 'text/html', 'Content-Encoding': 'gzip'}, HTML),
                         (200, {'Content-Type': 'text/html', 'Content-Length': str(len(HTML) + 1)}, HTML),
                         (200, {'Content-Type': 'application/octet-stream'}, HTML),
                         (200, {'Content-Type': 'application/pdf'}, HTML),
                         (429, {}, b''), (503, {}, b'')):
            source, connect, _ = self.fetcher([response])
            with self.subTest(response=response[:2]), self.assertRaises(SourceError):
                source.fetch('cert-fr', URL)
            self.assertEqual(connect.call_count, 1)


class PublisherStorageTests(unittest.TestCase):
    def setUp(self):
        self.f = base.ReportTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.source = Mock(fetch=Mock(return_value=document()))
        self.service = ReportService(self.f.repo, publisher=self.source, clock=lambda: base.NOW)

    def fetch(self, key='fetch-1', **options):
        return self.service.execute('reports.fetch', provider='cert-fr', url=URL, idempotency_key=key, **options)

    def test_full_document_and_raw_object_survive_revision_and_earliest_replay(self):
        first = self.fetch()
        rid = first['record']['id']
        self.assertEqual(first['record']['document']['model_version'], 2)
        self.assertEqual(first['record']['document']['source_run_id'], first['run']['id'])
        self.assertEqual(self.f.observe()['records'][0]['report_id'], rid)
        self.source.fetch.return_value = document(HTML.replace(b'Public report', b'Changed report'))
        updated = self.fetch('fetch-2')
        self.assertEqual(updated['record']['document_revision'], 2)
        again = self.fetch()
        self.assertTrue(again['replayed'])
        self.assertEqual(again['record'], first['record'])
        self.assertEqual(self.source.fetch.call_count, 2)
        unchanged = self.fetch('fetch-3')
        self.assertEqual(unchanged['action'], 'unchanged')
        self.assertEqual(unchanged['record'], updated['record'])
        self.assertEqual(len(self.f.repo.fetches()), 3)
        self.assertEqual(self.f.show(rid, document_revision=1), {**first['record'], 'revision': 2,
            'current_document_revision': 2, 'history': updated['record']['history'], 'state_sha256': updated['record']['state_sha256']})

    def test_failure_is_recorded_without_losing_success_and_same_key_does_not_refetch(self):
        success = self.fetch()['record']
        self.source.fetch.side_effect = SourceError('Publisher HTTP 503')
        for _ in range(2):
            with self.assertRaisesRegex(SourceError, '503'):
                self.fetch('failed')
        self.assertEqual(self.source.fetch.call_count, 2)
        self.assertEqual(self.f.show(success['id']), success)
        rows = self.service.execute('reports.fetches')['records']
        self.assertEqual([row['status'] for row in rows], ['failed', 'complete'])
        self.assertEqual(self.service.execute('reports.fetch-show', identifier=rows[0]['id'])['run'], rows[0])

    def test_cross_operation_keys_and_conflicting_fetch_reject_before_network(self):
        self.fetch()
        with self.assertRaises(ReportError):
            self.f.capture(key='fetch-1')
        with self.assertRaises(ReportError):
            self.service.execute('reports.fetch', provider='cert-fr', url=URL + 'other', idempotency_key='fetch-1')
        self.assertEqual(self.source.fetch.call_count, 1)
        self.f.capture('old-capture')
        with self.assertRaises(ReportError):
            self.fetch('old-capture')
        self.assertEqual(self.source.fetch.call_count, 1)

    def test_failed_commit_rolls_back_raw_document_and_receipt_together(self):
        before = self.f.path.read_bytes()
        with patch.object(self.f.repo, '_mutate_in', side_effect=StorageError('Controlled commit failure')), self.assertRaises(StorageError):
            self.fetch()
        self.assertEqual(self.f.path.read_bytes(), before)
        self.assertEqual(self.f.repo.fetches(), [])

    def test_tampered_raw_object_fails_reads_and_backup_restore_keeps_full_evidence(self):
        record = self.fetch()['record']
        backup = self.f.repo.storage.backup(self.f.path.parent / 'publisher-backup.db')
        restored = self.f.path.parent / 'publisher-restored.db'
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(ReportService(SQLiteReportRepository(restored)).execute('reports.show', identifier=record['id'])['record'], record)
        with self.f.repo.storage._connection() as c, c:
            c.execute("UPDATE publisher_objects SET body=x'00'")
        with self.assertRaises(StorageError):
            self.f.show(record['id'])

    def test_future_collection_or_wrong_scope_has_no_partial_storage(self):
        for value in (replace(document(), fetched_at=(base.NOW + timedelta(days=1)).isoformat()),
                      replace(document(), url=URL + 'other', final_url=URL + 'other')):
            self.source.fetch.return_value = value
            before = self.f.path.read_bytes()
            with self.assertRaises(ValidationError):
                self.fetch()
            self.assertEqual(self.f.path.read_bytes(), before)

    def test_missing_publisher_receipt_rejects_report_reads_as_well_as_run_listing(self):
        record = self.fetch()['record']
        with self.f.repo.storage._connection() as c, c:
            c.execute('DELETE FROM publisher_fetch_runs')
        for read in (lambda: self.f.show(record['id']), self.f.repo.fetches):
            with self.assertRaises(StorageError):
                read()

    def test_later_install_pin_or_publisher_scope_does_not_reinterpret_old_documents(self):
        from xti.domain.publisher_documents import full_document, validate_full_document
        from uuid import uuid4
        body = pdf(); text, title, pages = pdf_text(body)
        stored = full_document(FetchedDocument('cert-fr', URL, URL, (), 'application/pdf', body, text, title,
            'pypdf/7.1.1', pages, base.NOW.isoformat()), str(uuid4()))
        record = self.fetch()['record']
        with patch('xti.domain.publisher_documents.PDF_VERSION', 'future-version'), \
                patch('xti.domain.publisher_documents.POLICY_VERSION', 'publisher-future'), \
                patch('xti.domain.publisher_documents.PUBLISHERS', {}):
            validate_full_document(stored)
            self.assertEqual(self.f.show(record['id']), record)
            self.assertEqual(len(self.f.repo.fetches()), 1)

    def test_full_text_engine_model_and_graph_preserve_existing_summary_policy(self):
        record = self.fetch()['record']
        from xti.interfaces.engine import make_engine_service
        from xti.domain.engine import parse_engine_request
        request = parse_engine_request({'contract_version': 1, 'request_id': 'fetches', 'operation': 'reports.fetches', 'parameters': {}})
        self.assertEqual(make_engine_service(self.f.path, operation=request.operation).execute(request)['total_count'], 1)
        from xti.domain.research_reports import document_node
        node = document_node(self.f.repo.read()[record['id']], 1)
        self.assertIn('HTML/PDF', node.evidence[0].description)
        self.assertNotIn('tam makale değildir', node.evidence[0].description)

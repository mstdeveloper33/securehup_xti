"""Company-scoped report research and drilldown through the real JSON dispatcher."""

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_mentions import SQLiteMentionRepository
from xti.application.cti_indicators import CtiIndicatorService
from xti.application.research import ResearchService
from xti.domain.mentions import company_target, MentionRequest, MentionHit, MentionResponse, build_query
from tests import test_report_contract as reports


class ResearchReportContractTests(unittest.TestCase):
    def setUp(self):
        self.h = reports.ReportCompanyTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.f = self.h.f
        self.at = datetime.now(timezone.utc).isoformat()
        self.enterContext(patch.object(ResearchService, '_now', return_value=self.at))

    def graph(self, company='alpha', value='192.0.2.10', kind='ipv4'):
        return self.f.complete(company, self.f.request('research.show', {'indicator_type': kind, 'value': value}))

    def linked_report(self, company):
        path = self.f.contexts[company].database
        ioc = CtiIndicatorService(SQLiteCtiIndicatorRepository(path)).add('ipv4', '192.0.2.10',
            source_name='analyst', source_reference='https://source.example/' + company,
            confidence=31, description=company + ' evidence')
        report = self.f.complete(company, self.h.capture_request(company))['record']
        self.f.complete(company, self.f.request('reports.link', {'identifier': report['id'],
            'target_kind': 'indicator', 'target_id': ioc.indicator.id, 'expected_revision': 1,
            'state': 'linked', 'reason': company + ' reviewed the selected document', 'idempotency_key': 'link',
            'expected_workspace_id': self.f.contexts[company].workspace_id}))
        return report, ioc

    def test_explicit_ioc_link_works_without_text_match_and_never_crosses_company(self):
        owned = {name: self.linked_report(name) for name in ('alpha', 'beta')}
        before = self.f.files()
        for company, other in (('alpha', 'beta'), ('beta', 'alpha')):
            with self.subTest(company=company):
                report, ioc = owned[company]
                graph = self.graph(company)
                docs = [row for row in graph['nodes'] if row['kind'] == 'report_document']
                self.assertEqual([row['value'] for row in docs], [report['id'] + ':1'])
                self.assertFalse(any(row['relationship_type'] == 'report_text_mention' for row in graph['edges']))
                reference = docs[0]['references'][0]
                detail = self.f.complete(company, self.f.request('record.get', {'reference': reference, 'limit': 1}))
                self.assertEqual(detail['record']['document_revision'], 1)
                self.assertEqual(detail['sections']['history']['total_count'], 2)
                self.assertTrue(detail['sections']['history']['has_more'])
                self.f.rejected(other, self.f.request('record.get', {'reference': reference}), error='not_found')
                root = next(row for row in graph['nodes'] if row['value'] == '192.0.2.10')
                self.assertEqual(root['evidence'][0]['confidence'], 31)
                self.assertEqual(root['evidence'][0]['assertion_id'], ioc.assertion.id)
                self.assertNotIn(owned[other][0]['id'], str(graph))
        self.assertEqual(self.f.files(), before)

    def test_original_search_domain_is_separate_from_a_text_mention(self):
        target = company_target('Controlled company', ('scope.example',))
        request = MentionRequest(target, 'news', 10)
        hit = MentionHit('https://publisher.example/controlled', 'Company release', 'No indicator here', '2026-11-16', .8)
        repo = SQLiteMentionRepository(self.f.contexts['alpha'].database)
        repo.apply(request, MentionResponse(build_query(target), None, (hit,), 1), started_at=self.at, finished_at=self.at)
        source = next(row for row in repo.catalog().records if row.hit == hit)
        captured = self.f.complete('alpha', self.h.capture_request('alpha', identifier=source.id,
            idempotency_key='scope'))['record']
        graph = self.graph(value='scope.example', kind='domain')
        doc = next(row for row in graph['nodes'] if row['value'] == captured['id'] + ':1')
        edges = [row for row in graph['edges'] if row['source_id'] == doc['id']]
        self.assertEqual([row['relationship_type'] for row in edges], ['report_search_scope'])
        self.assertEqual(edges[0]['evidence'][0]['record_type'], 'report_search_scope')
        self.assertFalse(any(row['kind'] == 'report_document' for row in self.graph('beta', 'scope.example', 'domain')['nodes']))

    def test_backup_restore_preserves_graph_ids_old_revision_reference_and_frozen_review(self):
        report, _ = self.linked_report('alpha')
        context = self.f.contexts['alpha']
        before = self.graph()
        review = self.f.complete('alpha', self.f.request('research.review.record', {
            'indicator_type': 'ipv4', 'value': '192.0.2.10', 'idempotency_key': 'record-review',
            'expected_workspace_id': context.workspace_id}))
        old_review = self.f.complete('alpha', self.f.request('research.review.get', {
            'review_id': review['review']['id'], 'view': 'items'}))
        backup = backup_platform_workspace(context, self.f.base / 'research-backup')
        restored = restore_platform_workspace(self.f.base / 'restored', 'alpha', backup)
        self.f.root = self.f.base / 'restored'
        self.f.contexts['alpha'] = restored
        self.assertEqual(self.graph(), before)
        after = self.f.complete('alpha', self.f.request('research.review.get', {
            'review_id': review['review']['id'], 'view': 'items'}))
        self.assertEqual(after, old_review)
        doc = next(row for row in before['nodes'] if row['kind'] == 'report_document')
        detail = self.f.complete('alpha', self.f.request('record.get', {'reference': doc['references'][0]}))
        self.assertEqual(detail['record']['id'], report['id'])

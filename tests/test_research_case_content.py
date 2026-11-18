"""Existing decisions remain attributable and never become source verdicts."""

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_research import SQLiteResearchRepository
from xti.application.research import ResearchService, research_data, priority_data
from xti.domain.research_history import freeze
from tests import test_cases as case_fixtures
from tests import test_brand_username_reviews as social_fixtures
github = social_fixtures.github
from tests import test_organization_content_report as content_fixtures


class ResearchCaseContentTests(unittest.TestCase):
    def fixture(self, cls):
        fixture = cls()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.path = fixture.path
        self.research = ResearchService(SQLiteResearchRepository(self.path),
            clock=lambda: datetime(2026, 11, 18, tzinfo=timezone.utc))
        return fixture

    def graph(self, value='example.com', kind='domain'):
        return research_data(self.research.show(indicator_type=kind, value=value))

    def test_case_close_and_link_removal_preserve_original_source_and_human_reason(self):
        fixture = self.fixture(case_fixtures.CaseTests)
        case, finding = fixture.create_case(), fixture.insert_finding()
        link = fixture.service.add_evidence(case.id, 'finding', finding, reason='Original analyst link')
        data = self.graph()
        self.assertTrue(any(row['record_type'] == 'case' for row in data['nodes']))
        fixture.service.remove_evidence(case.id, link.evidence.id, reason='Evidence removed from this case')
        fixture.service.set_status(case.id, 'closed', reason='Review completed', resolution='Controlled fixture conclusion')
        data = self.graph()
        evidence = [e for item in [*data['nodes'], *data['edges']] for e in item['evidence']]
        self.assertTrue(any(e['status'] == 'closed' and e['current'] for e in evidence))
        self.assertTrue(any(e['status'] == 'removed' and e['kind'] == 'human_decision' for e in evidence))
        self.assertFalse(any(e['kind'] == 'source_claim' for e in evidence))
        freeze(priority_data(self.research.priorities(indicator_type='domain', value='example.com')))

    def test_case_corruption_is_rejected(self):
        fixture = self.fixture(case_fixtures.CaseTests)
        case = fixture.create_case()
        fixture.service.add_evidence(case.id, 'finding', fixture.insert_finding(), reason='Original link')
        with fixture.storage._connection() as connection, connection:
            connection.execute("UPDATE cases SET title='Tampered valid title' WHERE id=?", (case.id,))
        with self.assertRaises(StorageError):
            self.graph()

    def test_case_budget_is_explicit_partial_without_decoding(self):
        fixture = self.fixture(case_fixtures.CaseTests)
        case = fixture.create_case()
        fixture.service.add_evidence(case.id, 'finding', fixture.insert_finding(), reason='Original link')
        with patch('xti.adapters.sqlite_research_cases.ResearchReadBudget.admit', return_value=False):
            self.assertFalse(any(row['record_type'] == 'case' for row in self.graph()['nodes']))

    def test_social_url_and_exact_state_decision_are_visible_and_frozen(self):
        fixture = self.fixture(social_fixtures.BrandUsernameReviewTests)
        _, watch, _ = fixture.create_found({'GitHub': github()})
        fixture.review_service().decide(watch.id, 'GitHub', decision='possible_impersonation', reason='Controlled profile review')
        data = self.graph(github(), 'url')
        profile = next(row for row in data['nodes'] if row['record_type'] == 'social_profile')
        self.assertTrue(any(e['status'] == 'possible_impersonation' for e in profile['evidence']))
        freeze(priority_data(self.research.priorities(indicator_type='url', value=github())))

    def test_source_failure_keeps_previous_social_evidence_and_reports_last_attempt(self):
        from xti.ports.discovery import SourceError
        fixture = self.fixture(social_fixtures.BrandUsernameReviewTests)
        service, watch, _ = fixture.create_found({'GitHub': github()}, SourceError('Controlled outage'))
        service.run(watch.id)
        data = self.graph(github(), 'url')
        profile = next(row for row in data['nodes'] if row['record_type'] == 'social_profile')
        self.assertTrue(any(e['status'] == 'found_unverified' and e['current'] for e in profile['evidence']))
        self.assertTrue(any(e['record_type'] == 'social_watch_run' and e['status'] == 'failed' for e in profile['evidence']))

    def test_public_notice_case_links_only_original_metadata_domain(self):
        from tests import test_public_notice_cases as public_fixtures
        fixture = self.fixture(public_fixtures.PublicNoticeCaseTests)
        baseline = fixture.w.apply()
        fixture.add(baseline.run.id)
        data = self.graph()
        self.assertTrue(any(node['record_type'] == 'case' for node in data['nodes']))
        self.assertFalse(any(node['record_type'] == 'case' for node in self.graph('unrelated.example')['nodes']))

    def test_ransomware_case_domain_does_not_infer_ransomlook_ownership(self):
        fixture = self.fixture(case_fixtures.CaseTests)
        fixture.test_both_ransomware_sources_remain_separate_unverified_evidence()
        data = self.graph('www.example.com')
        self.assertTrue(any(node['record_type'] == 'case' for node in data['nodes']))
        self.assertFalse(any(node['record_type'] == 'case' for node in self.graph('holding.example')['nodes']))

    def test_original_search_domain_and_url_link_without_network_or_name_guess(self):
        from dataclasses import replace
        fixture = self.fixture(content_fixtures.OrganizationContentReportTests)
        request = fixture.request()
        request = replace(request, target=replace(request.target, domains=('example.com',)))
        fixture.apply(fixture.hit(), request=request)
        data = self.graph()
        content = next(row for row in data['nodes'] if row['record_type'] == 'company_content')
        self.assertEqual(content['evidence'][0]['source'], 'tavily')
        self.assertFalse(any(row['record_type'] == 'company_content' for row in self.graph('unrelated.example')['nodes']))
        freeze(priority_data(self.research.priorities(indicator_type='domain', value='example.com')))

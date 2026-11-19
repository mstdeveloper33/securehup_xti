"""Identity reversibility, original report spans, migration, isolation and contracts."""

from datetime import timedelta
import json
import unittest
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_investigation import SQLiteInvestigationRepository
from xti.application.investigation import InvestigationService
from xti.domain.assets import ValidationError
from xti.domain.investigation import identity_proposal
from xti.domain.report_extraction import extract, report_proposal
from xti.domain.engine import parse_engine_request
from xti.domain.platform_engine import parse_platform_request
from xti.interfaces.company_review import make_company_review_service
from xti.interfaces.research_history import make_history_service
from tests.test_research import ResearchFixture


class InvestigationTests(ResearchFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repository = SQLiteInvestigationRepository(self.path)
        self.reviews = InvestigationService(self.repository, clock=lambda: self.at)

    def proposal(self):
        left, right = self.entity('Actor One'), self.entity('Actor Alternative')
        return self.reviews.propose({'kind': 'entity', 'id': left.entity.id}, {'kind': 'entity', 'id': right.entity.id},
            ['https://publisher.example/report'], 'Two independently reviewed source records', 'identity-proposal')

    def test_identity_reversible_idempotent_stale_revision_and_original_ids(self):
        first = self.proposal()['record']
        self.assertEqual(first['decision'], 'pending')
        kwargs = dict(identifier=first['id'], decision='accepted', reason='Source evidence reviewed', expected_revision=1,
                      idempotency_key='identity-accept')
        accepted = self.reviews.decide(**kwargs)['record']
        self.assertEqual(accepted['revision'], 2)
        withdrawn = self.reviews.decide(first['id'], 'withdrawn', 'New source contradicts mapping', 2, 'identity-withdraw')['record']
        self.assertEqual(withdrawn['decision'], 'withdrawn')
        replay = self.reviews.decide(**kwargs)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['record'], accepted)
        with self.assertRaises(ValidationError):
            self.reviews.decide(**{**kwargs, 'expected_revision': 2})
        with self.assertRaises(ValidationError):
            self.reviews.decide(first['id'], 'rejected', 'Stale client decision', 1, 'stale-revision')
        with self.repository.storage._connection(readonly=True) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM cti_entities').fetchone()[0], 2)

    def test_missing_and_other_workspace_identity_fail_without_journal_write(self):
        entity = self.entity()
        with self.assertRaises(ValidationError):
            self.reviews.propose({'kind': 'entity', 'id': entity.entity.id}, {'kind': 'entity', 'id': str(uuid4())},
                ['source:unrelated'], 'Unknown identity must fail', 'unknown-identity')
        self.assertFalse(self.repository.catalog())

    def test_different_cti_types_cannot_be_identity_equivalent(self):
        actor = self.entity('Actor')
        malware = self.cti.add_entity('malware', 'Malware', source_name='fixture', source_reference='report:malware',
                                    confidence=50, description='Controlled malware')
        with self.assertRaises(ValidationError):
            self.reviews.propose({'kind': 'entity', 'id': actor.entity.id}, {'kind': 'entity', 'id': malware.entity.id},
                ['report:malware'], 'Different entity types are not equivalent', 'wrong-types')
        self.assertFalse(self.repository.catalog())

    def test_deleted_journal_tail_fails_closed(self):
        record = self.proposal()['record']
        self.reviews.decide(record['id'], 'uncertain', 'Need another source', 1, 'uncertain')
        with self.repository.storage._connection() as connection, connection:
            connection.execute('DELETE FROM investigation_events WHERE sequence=2')
        with self.assertRaises(StorageError):
            self.reviews.list()

    def test_alias_candidates_are_exact_not_substring_and_do_not_merge(self):
        entity = self.cti.add_entity('threat-actor', 'Original actor', source_name='fixture', source_reference='report:alias',
            confidence=50, aliases=('Alternative name',), description='Controlled name alias')
        result = self.reviews.candidates('Alternative name')
        self.assertEqual(result['candidates'][0]['id'], entity.entity.id)
        self.assertFalse(self.reviews.candidates('Alternative')['candidates'])
        self.assertFalse(self.repository.catalog())

    def test_report_spans_refanging_and_not_automatically_iocs(self):
        text = 'Report: hxxps://evil[.]example/path and 192[.]0[.]2[.]10; SHA256 ' + 'a' * 64
        proposal = report_proposal(source='news', source_reference='https://publisher.example/report',
            source_record_id='source-record', source_run_id=str(uuid4()), text=text,
            source_sha256='b' * 64, observed_at=self.at.isoformat(), scope=['example.com'])
        result = self.repository.propose(proposal, key='report-extract', at=self.at.isoformat())['record']
        for candidate in proposal['candidates']:
            self.assertEqual(text[candidate['start']:candidate['end']], candidate['original'])
        self.assertIn(('url', 'https://evil.example/path'), [(row['indicator_type'], row['value']) for row in proposal['candidates']])
        graph = self.graph()
        self.assertTrue(any(node['record_type'] == 'report_candidate' for node in graph['nodes']))
        self.assertFalse(any(e['kind'] == 'source_claim' for node in graph['nodes'] for e in node['evidence']))
        with self.repository.storage._connection(readonly=True) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM cti_indicators').fetchone()[0], 0)
        make_history_service(self.path).record(indicator_type='domain', value='example.com', idempotency_key='report-review')
        self.assertEqual(self.reviews.show(result['id'])['record']['proposal'], proposal)

    def test_report_limits_reject_without_silent_truncation(self):
        for text in ('x' * 65537, ' '.join(f'{i % 250}.0.{i // 250}.1' for i in range(201))):
            with self.assertRaises(ValidationError):
                extract(text)

    def test_company_queue_includes_unlinked_cases_and_keeps_source_states(self):
        self.dns()
        self.ioc()
        service = make_company_review_service(self.path)
        data = service.show(limit=1)
        self.assertTrue(data['items'])
        self.assertTrue(data['has_more'])
        service.show(limit=1, offset=1, expected_snapshot=data['snapshot_id'])
        self.ioc(value='93.184.216.35')
        with self.assertRaises(ValidationError):
            service.show(limit=1, offset=1, expected_snapshot=data['snapshot_id'])

    def test_pending_identity_is_explainable_review_work(self):
        self.proposal()
        data = make_company_review_service(self.path).show()
        self.assertTrue(any(reason['code'] == 'investigation_pending'
                            for item in data['items'] for reason in item['reasons']))

    def test_contract_and_terminal_read_surfaces(self):
        self.proposal()
        for operation, parameters in [('investigation.list', {}), ('investigation.candidates', {'query': 'Actor One'}),
                                       ('company.review', {})]:
            request = {'contract_version': 1, 'request_id': 'review-test', 'operation': operation, 'parameters': parameters}
            parse_engine_request(request)
            parse_platform_request(request)
            code, out, err = self.invoke(['--data-dir', str(self.data), 'engine'], request)
            self.assertEqual(code, 0, err)
            self.assertIsNone(json.loads(out)['error'])
        code, out, err = self.invoke(['--data-dir', str(self.data), '--json', 'investigate', 'list'])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)['data']['total_count'], 1)

    def test_schema_75_upgrade_has_backup_and_retains_original_data(self):
        self.dns()
        with self.repository.storage._connection() as connection, connection:
            connection.execute('DROP TABLE investigation_events')
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(connection)
            connection.execute('PRAGMA user_version=75')
        migration = self.repository.storage.migrate()
        self.assertEqual((migration['from_version'], migration['to_version']), (75, 80))
        self.assertTrue(migration['backup'])
        self.assertTrue(self.graph()['nodes'])

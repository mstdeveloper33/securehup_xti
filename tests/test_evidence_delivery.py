"""Evidence preservation, stale decisions, company fences and real transport paths."""
from dataclasses import replace
from datetime import timedelta
from contextlib import closing
import json
import sqlite3
import unittest
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_evidence import SQLiteEvidenceRepository
from xti.application.evidence import EvidenceService
from xti.domain.assets import ValidationError
from xti.domain.reports import ReportError
from xti.interfaces.research import make_research_service
from xti.application.research import research_data
from tests import test_reports as reports
from tests import test_investigation as investigations
from tests import test_platform_isolation as companies

ROOT = dict(indicator_type='ipv4', value='192.0.2.10')


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.f = reports.ReportTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.repo = SQLiteEvidenceRepository(self.f.path)
        self.service = EvidenceService(self.repo, clock=lambda: reports.NOW)

    def sight(self, **options):
        return self.service.execute('sightings.record', **{**ROOT, 'source': 'customer-edr', 'sensor': 'gateway-a',
            'source_event_id': 'event-1', 'observed_at': (reports.NOW - timedelta(days=3)).isoformat(),
            'reference': 'sensor:event-1', 'idempotency_key': 'sight-1', **options})

    def test_sighting_is_separate_from_reports_and_ioc_claims_replays_and_revokes(self):
        before = self.f.observe()['total_count']
        record = self.sight()['record']
        self.assertEqual(record['observation']['observed_at'], (reports.NOW - timedelta(days=3)).isoformat())
        self.assertEqual(self.sight()['record'], record)
        duplicate = self.sight(idempotency_key='new-request')['record']
        self.assertEqual(duplicate['id'], record['id'])
        rows = self.service.execute('sightings.list', **ROOT)
        self.assertEqual(rows['total_count'], 1)
        self.assertEqual(self.f.observe()['total_count'], before)
        with self.repo.storage._connection(readonly=True) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM cti_indicators').fetchone()[0], 0)
        revoked = self.service.execute('sightings.revoke', identifier=record['id'], expected_revision=2,
            reason='Faulty sensor mapping', idempotency_key='revoke')['record']
        self.assertEqual(revoked['state'], 'revoked')
        self.assertEqual(self.sight()['record'], record)  # original receipt, not the latest state
        graph = research_data(make_research_service(self.f.path).show(**ROOT))
        evidence = [e for n in graph['nodes'] for e in n['evidence'] if e['record_type'] == 'local_sighting']
        self.assertEqual(len(evidence), 1)
        self.assertFalse(evidence[0]['current'])
        self.assertEqual(evidence[0]['time_basis'], 'sensor_reported_observation')

    def test_conflict_future_time_and_stale_revision_leave_bytes_unchanged(self):
        record = self.sight()['record']
        before = self.f.path.read_bytes()
        for options in ({'value': '192.0.2.11'}, {'value': '192.0.2.11', 'idempotency_key': 'different'},
                        {'observed_at': (reports.NOW + timedelta(days=1)).isoformat(), 'source_event_id': 'future', 'idempotency_key': 'future'}):
            with self.subTest(options=options), self.assertRaises((ReportError, ValidationError)):
                self.sight(**options)
            self.assertEqual(self.f.path.read_bytes(), before)
        with self.assertRaises(ReportError):
            self.service.execute('sightings.revoke', identifier=record['id'], expected_revision=2,
                reason='Stale client revision', idempotency_key='stale')
        self.assertEqual(self.f.path.read_bytes(), before)

    def candidate(self):
        self.f.capture()
        rows = self.service.execute('relationships.candidates', **ROOT)['records']
        return next(row for row in rows if row['rule'] == 'shared_report')

    def review(self, row, **options):
        return self.service.execute('relationships.review', **{**ROOT, 'identifier': row['id'],
            'evidence_sha256': row['evidence_sha256'], 'expected_revision': 0, 'decision': 'accepted',
            'reason': 'Same report reviewed, attribution not asserted', 'idempotency_key': 'review-1', **options})

    def test_report_cooccurrence_requires_separate_review_and_never_creates_cti_link(self):
        row = self.candidate()
        self.assertEqual(row['target'], ['domain', 'suspect.example'])
        self.assertIsNone(row['review'])
        record = self.review(row)['record']
        self.assertEqual(self.review(row)['record'], record)
        current = self.service.execute('relationships.candidates', **ROOT)['records'][0]
        self.assertTrue(current['review']['evidence_current'])
        with self.repo.storage._connection(readonly=True) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM cti_relationships').fetchone()[0], 0)
        self.review(row, decision='withdrawn', expected_revision=1, idempotency_key='withdraw')
        history = self.service.execute('relationships.show', identifier=row['id'])['record']['history']
        self.assertEqual([r['request']['decision'] for r in history], ['accepted', 'withdrawn'])

    def test_report_to_human_link_is_a_separate_context_rule(self):
        report = self.f.capture()['record']
        entity = self.f.entity()
        self.f.link(report['id'], entity)
        row = next(row for row in self.service.execute('relationships.candidates', **ROOT)['records']
                   if row['rule'] == 'report_review_context')
        self.assertEqual(row['target'], ['entity', entity])
        self.assertTrue(any(e['kind'] == 'human_decision' for edge in row['evidence'] for e in edge['evidence']))
        self.assertEqual(self.review(row)['record']['decision'], 'accepted')

    def test_changed_report_marks_previous_review_stale_and_rejects_old_proof(self):
        row = self.candidate(); self.review(row)
        self.f.f.apply(replace(self.f.item, summary='Updated report mentions 192.0.2.10 and suspect[.]example'))
        self.f.capture('capture-v2')
        current = next(r for r in self.service.execute('relationships.candidates', **ROOT)['records'] if r['id'] == row['id'])
        self.assertEqual(current['evidence_scope'], 'historical_or_withdrawn')
        self.assertFalse(current['review']['evidence_current'])
        with self.assertRaises(ReportError) as caught:
            self.review(row, expected_revision=1, idempotency_key='stale-proof')
        self.assertEqual(caught.exception.code, 'source_changed')
        self.assertEqual(self.review(row)['record']['revision'], 1)

    def test_pagination_snapshot_changes_on_revocation_and_read_only_bytes(self):
        record = self.sight()['record']
        self.sight(source_event_id='event-2', idempotency_key='sight-2')
        before = self.f.path.read_bytes()
        first = self.service.execute('sightings.list', **ROOT, limit=1)
        second = self.service.execute('sightings.list', **ROOT, offset=1, limit=1, expected_snapshot=first['snapshot_id'])
        self.assertNotEqual(first['records'][0]['id'], second['records'][0]['id'])
        self.assertEqual(before, self.f.path.read_bytes())
        self.service.execute('sightings.revoke', identifier=record['id'], expected_revision=1,
            reason='Sensor reviewed as incorrect', idempotency_key='revoke')
        with self.assertRaises(ReportError):
            self.service.execute('sightings.list', **ROOT, offset=1, expected_snapshot=first['snapshot_id'])

    def test_deleted_tail_and_wrong_metadata_fail_closed(self):
        self.sight(); self.sight(source_event_id='event-2', idempotency_key='sight-2')
        with self.repo.storage._connection() as c, c:
            c.execute('DELETE FROM evidence_journal WHERE sequence=2')
        with self.assertRaises(StorageError):
            self.service.execute('sightings.list', **ROOT)

    def test_core77_migration_keeps_reports_and_has_original_backup(self):
        rid = self.f.capture()['record']['id']
        with self.repo.storage._connection() as c, c:
            c.execute('DROP TABLE evidence_journal')
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(c)
            c.execute('PRAGMA user_version=77')
        before = self.f.path.read_bytes()
        result = self.repo.storage.migrate()
        self.assertEqual(result['from_version'], 77)
        from xti.adapters.schema import SCHEMA_VERSION
        self.assertEqual(result['to_version'], SCHEMA_VERSION)
        from pathlib import Path
        with closing(sqlite3.connect(result['backup'])) as backup, closing(sqlite3.connect(self.f.path)) as current:
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 77)
            self.assertEqual(backup.execute('SELECT payload_json FROM report_journal').fetchall(),
                current.execute('SELECT payload_json FROM report_journal').fetchall())
        self.assertEqual(self.f.show(rid)['document']['summary'], self.f.item.summary)
        self.assertEqual(self.service.execute('sightings.list', **ROOT)['total_count'], 0)

    def test_compare_does_not_invent_source_claim_from_customer_sighting(self):
        self.sight()
        compared = self.service.execute('ioc.compare', **ROOT)
        self.assertEqual(compared['total_count'], 0)
        self.assertEqual(compared['local_sightings']['active_count'], 1)
        self.assertFalse(compared['different_claim_states'])

    def test_sighting_only_root_appears_in_company_review_and_frozen_history(self):
        self.sight()
        from xti.interfaces.company_review import make_company_review_service
        from xti.interfaces.research_history import make_history_service
        review = make_company_review_service(self.f.path).show()
        self.assertEqual(review['root_total_count'], 1)
        self.assertTrue(any(i['source_comparison']['local_sighting_count_in_view'] == 1 for i in review['items']))
        capture = make_history_service(self.f.path).record(**ROOT, idempotency_key='sighting-history')
        self.assertEqual(capture['review']['query']['value'], ROOT['value'])

    def test_sighting_read_budget_is_explicit_and_does_not_create_empty_success(self):
        self.sight()
        from unittest.mock import patch
        with patch('xti.adapters.sqlite_evidence.MAX_ENTRIES', 0), self.assertRaises(StorageError):
            self.service.execute('sightings.list', **ROOT)

    def test_record_byte_capacity_rejects_before_commit_and_preserves_prior_observation(self):
        self.sight()
        from unittest.mock import patch
        from xti.domain.engine_jobs import canonical_json
        record = self.service.execute('sightings.list', **ROOT)['records'][0]
        size = len(canonical_json(record['history'][0]).encode('ascii'))
        before = self.f.path.read_bytes()
        with patch('xti.domain.evidence_ledger.MAX_RECORD_BYTES', size + 10), self.assertRaises(ValidationError):
            self.sight(idempotency_key='would-exceed-record-size')
        self.assertEqual(self.f.path.read_bytes(), before)
        self.assertEqual(self.service.execute('sightings.list', **ROOT)['records'][0], record)

    def test_distinct_source_claim_states_are_compared_without_a_vote(self):
        from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
        from xti.application.cti_indicators import CtiIndicatorService
        service = CtiIndicatorService(SQLiteCtiIndicatorRepository(self.f.path), clock=lambda: reports.NOW)
        for name, until in (('first-source', None), ('expired-source', reports.NOW.isoformat())):
            service.add('ipv4', ROOT['value'], source_name=name, source_reference='https://source.example/' + name,
                confidence=90, description='Controlled statement', observed_at=(reports.NOW - timedelta(days=1)).isoformat(),
                valid_until=until)
        compared = self.service.execute('ioc.compare', **ROOT)
        self.assertTrue(compared['different_claim_states'])
        self.assertEqual(compared['claim_states'], ['active', 'expired'])
        self.assertEqual(compared['total_count'], 2)
        self.assertNotIn('risk_score', compared)
        self.assertEqual([r['claims'][0]['confidence'] for r in compared['records']], [90, 90])

    def test_unknown_clock_and_parameter_types_reject_before_mutation(self):
        from xti.domain.evidence_contract import parameters
        from xti.domain.evidence_ledger import validate_candidate
        for options in ({'limit': True}, {'offset': -1}, {'expected_snapshot': []}, {'path': '/other'}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                parameters('sightings.list', {**ROOT, **options})
        service = EvidenceService(self.repo, clock=lambda: reports.NOW.replace(tzinfo=None))
        with self.assertRaises(ValidationError):
            service.execute('sightings.list', **ROOT)
        row = self.candidate()
        row.pop('review')
        row['target'] = row['root']
        with self.assertRaises(ValidationError):
            validate_candidate(row)


class IdentityViewTests(unittest.TestCase):
    def setUp(self):
        self.f = investigations.InvestigationTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.service = EvidenceService(SQLiteEvidenceRepository(self.f.path), clock=lambda: self.f.at)

    def test_pending_and_withdrawn_do_not_join_accepted_chain_or_mutate_originals(self):
        proposal = self.f.proposal()['record']
        root = proposal['proposal']['left']['id']
        read = lambda: self.service.execute('identity.view', kind='entity', identifier=root)
        self.assertEqual(len(read()['members']), 1)
        self.f.reviews.decide(proposal['id'], 'accepted', 'Reviewed exact identities', 1, 'accept')
        view = read()
        self.assertEqual(len(view['members']), 2)
        self.assertFalse(view['physical_merge'])
        self.assertTrue(all(row['source_assertions'] for row in view['members']))
        self.f.reviews.decide(proposal['id'], 'withdrawn', 'Mapping is no longer valid', 2, 'withdraw')
        self.assertEqual(len(read()['members']), 1)
        with self.f.repository.storage._connection(readonly=True) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM cti_entities').fetchone()[0], 2)

    def test_accepted_cycle_has_no_duplicates_and_alternative_path_survives_withdrawal(self):
        ids = [self.f.entity(name).entity.id for name in ('Identity A', 'Identity B', 'Identity C')]
        links = []
        for index, (left, right) in enumerate(((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0]))):
            proposed = self.f.reviews.propose({'kind': 'entity', 'id': left}, {'kind': 'entity', 'id': right},
                ['fixture:reviewed'], 'Controlled equivalence', 'propose-' + str(index))['record']
            links.append(proposed['id'])
            self.f.reviews.decide(proposed['id'], 'accepted', 'Controlled reviewed names', 1, 'accept-' + str(index))
        read = lambda: self.service.execute('identity.view', kind='entity', identifier=ids[0])
        self.assertEqual({row['id'] for row in read()['members']}, set(ids))
        self.f.reviews.decide(links[0], 'withdrawn', 'Withdraw first connection', 2, 'withdraw-ab')
        self.assertEqual({row['id'] for row in read()['members']}, set(ids))
        self.f.reviews.decide(links[2], 'withdrawn', 'Withdraw alternative connection', 2, 'withdraw-ca')
        self.assertEqual([row['id'] for row in read()['members']], [ids[0]])


class InfrastructureCandidateTests(unittest.TestCase):
    def setUp(self):
        from tests.test_research_surface import SurfaceResearchTests
        self.f = SurfaceResearchTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.service = EvidenceService(SQLiteEvidenceRepository(self.f.path), clock=lambda: self.f.at)

    def test_shared_dns_address_keeps_two_original_checks_without_attribution(self):
        first, second = self.f.dns('first.example'), self.f.dns('second.example')
        rows = self.service.execute('relationships.candidates', indicator_type='domain', value='first.example')['records']
        row = next(r for r in rows if r['rule'] == 'shared_dns_address')
        self.assertEqual(row['target'], ['domain', 'second.example'])
        self.assertEqual({e['record_id'] for edge in row['evidence'] for e in edge['evidence']}, {first.id, second.id})
        self.assertIsNone(row['review'])

    def test_shared_certificate_requires_observed_presentation_not_san_names(self):
        self.f.tls('first.example', ip='192.0.2.10')
        self.f.tls('second.example', ip='192.0.2.11')
        rows = self.service.execute('relationships.candidates', indicator_type='domain', value='first.example')['records']
        row = next(r for r in rows if r['rule'] == 'shared_certificate')
        self.assertEqual(row['target'], ['domain', 'second.example'])
        self.assertFalse(any('san-only.example' in r['target'] for r in rows))


class EvidenceCompanyTests(unittest.TestCase):
    def setUp(self):
        self.f = companies.PlatformIsolationTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def record(self, company, **options):
        return self.f.request('sightings.record', {**ROOT, 'source': 'sensor', 'sensor': 'gateway',
            'source_event_id': 'same-event', 'observed_at': reports.NOW.isoformat(), 'reference': 'sensor:evt',
            'idempotency_key': 'same-key', 'expected_workspace_id': self.f.contexts[company].workspace_id, **options})

    def test_same_external_event_and_request_keys_are_company_scoped(self):
        a = self.f.complete('alpha', self.record('alpha'))['record']
        b = self.f.complete('beta', self.record('beta'))['record']
        self.assertNotEqual(a['id'], b['id'])
        self.f.rejected('beta', self.f.request('sightings.show', {'identifier': a['id']}), error='not_found')
        self.f.rejected('alpha', self.record('alpha', expected_workspace_id=self.f.contexts['beta'].workspace_id), error='scope_mismatch')
        read = self.f.complete('alpha', self.f.request('sightings.list', ROOT))
        self.assertEqual(read['total_count'], 1)
        self.assertEqual(read['records'][0]['id'], a['id'])

    def test_strict_field_contract_and_no_engine_write_surface(self):
        from xti.domain.engine import parse_engine_request, EngineContractError
        from xti.domain.platform_engine import parse_platform_request
        for options in ({'path': '/outside'}, {'observed_at': 'yesterday'}, {'expected_workspace_id': None}):
            with self.subTest(options=options), self.assertRaises(EngineContractError):
                parse_platform_request(self.record('alpha', **options))
        with self.assertRaises(EngineContractError):
            parse_engine_request(self.record('alpha'))

    def test_local_mentions_report_step_reads_only_selected_company_without_tavily(self):
        from xti.adapters.source_job_reports import VersionedReportStep
        from xti.domain.source_jobs import source_plan
        from xti.interfaces.reports import make_report_service
        plan = source_plan(**ROOT, sources=['report-capture'], capture_source='mentions')
        receipts = {}
        for company, context in self.f.contexts.items():
            step = VersionedReportStep(context.database)
            receipts[company] = step.execute(plan, str(uuid4()))
            step.verify(receipts[company], plan)
            self.assertTrue(receipts[company]['records'])
        identifier = receipts['alpha']['records'][0]['id']
        with self.assertRaises(ReportError):
            make_report_service(self.f.contexts['beta'].database).execute('reports.show', identifier=identifier)

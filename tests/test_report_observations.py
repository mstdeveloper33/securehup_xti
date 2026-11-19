"""Provider observations, list versions and legacy assertion time stay separate."""

from dataclasses import replace
from datetime import timedelta
import unittest

from xti.application.reports import ReportService
from xti.adapters.sqlite_reports import SQLiteReportRepository
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository
from xti.adapters.certpl_warning import parse_certpl_warning_response
from xti.domain.cti_feeds import CERTPL_POLICY
from tests import test_ioc_lifecycle as lifecycle
from tests import test_mentions_storage as mentions


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.f = lifecycle.IocLifecycleTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.service = ReportService(SQLiteReportRepository(self.f.path), clock=lambda: self.f.now)

    def show(self, kind='ipv4', value=lifecycle.VALUE):
        return self.service.execute('observations.list', indicator_type=kind, value=value)

    def test_provider_repeat_new_observation_and_revocation_do_not_mean_customer_sighting(self):
        self.f.apply()
        first = self.show()
        row = first['records'][0]
        self.assertEqual(row['kind'], 'provider_observation')
        self.assertIsNotNone(row['observed_at'])
        self.assertIsNone(row['collected_at'])
        self.f.apply(at=lifecycle.NOW + timedelta(days=1))
        self.assertEqual(self.show(), first)
        self.f.apply(lifecycle.feed_snapshot(last='2026-11-19'), at=lifecycle.NOW + timedelta(days=2))
        self.assertEqual(self.show()['total_count'], 2)
        self.f.apply(lifecycle.parse_feodo_response(b'[]'), at=lifecycle.NOW + timedelta(days=3))
        self.assertEqual(self.show()['total_count'], 2)
        self.assertTrue(all(not r['assertion_active'] for r in self.show()['records']))

    def test_certpl_list_timestamp_is_never_reported_as_attack_time(self):
        repo = SQLiteCtiFeedRepository(self.f.path, CERTPL_POLICY)
        snapshot = parse_certpl_warning_response(lifecycle.content('example.test', version='202611181200'), fetched_at=lifecycle.NOW)
        self.f.apply(snapshot, repository=repo)
        row = self.show('domain', 'example.test')['records'][0]
        self.assertEqual(row['kind'], 'feed_membership')
        self.assertEqual(row['time_semantics'], 'provider_list_version')
        self.assertIsNone(row['observed_at'])
        before = self.show('domain', 'example.test')
        self.f.apply(snapshot, repository=repo, at=lifecycle.NOW + timedelta(days=1))
        self.assertEqual(before, self.show('domain', 'example.test'))

    def test_manual_assertion_does_not_invent_observation_and_same_time_correction_deduplicates(self):
        original = self.f.add()
        row = self.show()['records'][0]
        self.assertEqual(row['kind'], 'source_assertion')
        self.assertIsNone(row['observed_at'])
        self.assertEqual(row['time_semantics'], 'unspecified_assertion_time')
        self.f.add(confidence=70)
        rows = self.show()['records']
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]['event_ids']), 2)
        result = self.service.execute('reports.list')
        self.assertEqual(result['total_count'], 0)


class MentionReportTests(unittest.TestCase):
    def test_mention_scope_raw_publication_and_changed_score_do_not_fabricate_report_event(self):
        f = mentions.MentionStorageTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        # Use the established source fixture, never a real API key or network.
        request = mentions.request()
        hit = replace(mentions.hit(), summary='192.0.2.10 reported in article', published_at='2026-11-14')
        f.apply(hit, scope=request)
        stored = f.repo.catalog().records[0]
        service = ReportService(SQLiteReportRepository(f.path), clock=lambda: lifecycle.NOW)
        old = service.execute('reports.capture', source='mentions', identifier=stored.id, idempotency_key='capture')
        doc = old['record']['document']
        self.assertEqual(doc['scope'], list(request.target.domains))
        self.assertEqual(doc['publication']['precision'], 'date')
        f.apply(replace(hit, score=0.9), scope=request)
        new = service.execute('reports.capture', source='mentions', identifier=stored.id, idempotency_key='repeat')
        self.assertEqual(new['action'], 'unchanged')
        self.assertEqual(new['record'], old['record'])

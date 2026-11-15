"""Cross-module local search preserves scope, source history and read snapshots."""
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_global_search import SQLiteGlobalSearchRepository, _SearchReader
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.application.cti_indicators import CtiIndicatorService
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.application.global_search import GlobalSearchService
from xti.application.suppliers import SupplierService
from xti.domain.assets import ValidationError
from xti.domain.global_search import GLOBAL_SEARCH_KINDS
from xti.domain.public_notices import PublicNotice, PublicNoticeFeed
from xti.interfaces.cli import build_parser
from xti.interfaces.global_search import global_search_lines
from xti.ports.discovery import SourceError
from tests import test_collection_watch_cli as fixtures
from tests.test_discovery import batch, document


# The historical fixture intentionally contains no post-schema65 news rows;
# older migration fixtures reuse it and may discard only empty new tables.
LEGACY_SEARCH_KINDS = ('domain', 'finding', 'social', 'ransomware', 'public-notice',
                       'case', 'supplier', 'organization', 'cti', 'indicator')


class GlobalSearchTests(unittest.TestCase):
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files
    add_social = fixtures.CollectionWatchCLITests.add_social

    def setUp(self):
        fixtures.CollectionWatchCLITests.setUp(self)
        self.now = datetime.now(timezone.utc)
        self.service = GlobalSearchService(SQLiteGlobalSearchRepository(self.database), clock=lambda: self.now)
        self.knowledge = CtiKnowledgeService(SQLiteCtiKnowledgeRepository(self.database), clock=lambda: self.now)
        self.iocs = CtiIndicatorService(SQLiteCtiIndicatorRepository(self.database), clock=lambda: self.now)
        self.suppliers = SupplierService(SQLiteSupplierRepository(self.database), clock=lambda: self.now)
        self.notices = SQLitePublicNoticeRepository(self.database)

    def collect(self):
        self.crt.responses['%example%'] = batch(document('example-support.net', 1), document('example-help.net', 2))
        self.crt.responses['%.example.com'] = batch(document('portal.example.com', 3))
        return self.result('collect', 'example.com')

    def notice(self, identifier='ExampleIncident', domain='example.com'):
        return PublicNotice(identifier, identifier, domain, '2025-01-02',
                            '2025-02-03T00:00:00+00:00', '2025-02-03T00:00:00+00:00', 42,
                            ('Email addresses',), False, True, False, False, False, False, True,
                            'Public contributor', f'https://haveibeenpwned.com/api/v3/breach/{identifier}')

    def save_notices(self, records):
        self.now += timedelta(seconds=1)
        at = self.now.isoformat()
        return self.notices.apply(PublicNoticeFeed(at, 'a' * 64, tuple(records)), started_at=at, finished_at=at)

    def entity(self, name, *, aliases=()):
        return self.knowledge.add_entity('threat-actor', name, aliases=aliases,
            source_name='manual', source_reference='local:' + name,
            confidence=70, description='Yerel örnek kaynak iddiası.')

    def ioc(self, value, **options):
        return self.iocs.add('domain', value, source_name='manual', source_reference='local:' + value,
            confidence=60, description='Yerel örnek kaynak iddiası.', **options)

    def supplier(self, name='Example Supplier'):
        return self.suppliers.add(name, domain='vendor.example', relationship_type='cloud',
                                  criticality='high', reason='Kullanıcının kayıtlı hizmet sağlayıcısı.').supplier

    def save_claims(self):
        at = datetime.now(timezone.utc).isoformat()
        tc = self.tc_claims.apply(self.threatcluster.value, started_at=at, finished_at=at, item_limit=100)
        rl = self.rl_claims.apply(self.ransomlook.value, started_at=at, finished_at=at, item_limit=100)
        return tc, rl

    def create_case(self, title='Example investigation'):
        return SQLiteCaseRepository(self.database).create(title=title, summary='Yerel araştırma kaydı.',
            priority='high', reason='Kanıtları birlikte incelemek için.', recorded_at=self.now.isoformat()).case

    def test_all_ten_families_share_real_totals_safe_navigation_and_no_collection(self):
        self.collect()
        watch = self.social.add('Example social watch', 'example', platforms=('GitHub', 'Reddit')).watch
        self.maigret.responses.append({'GitHub': fixtures.github('example')})
        self.social.run(watch.id)
        self.save_claims()
        self.save_notices((self.notice(),))
        self.supplier()
        self.create_case()
        self.result('organizations', 'add', 'Example organization')
        self.entity('Example actor')
        self.ioc('example-malware.net')
        before, calls = self.files(), tuple(self.maigret.calls)
        with patch.object(SQLiteAssetRepository, 'initialize', side_effect=AssertionError('No initialization')):
            report = self.service.search('example')
        self.assertEqual({item.kind for item in report.results}, set(LEGACY_SEARCH_KINDS))
        self.assertEqual({item.kind for item in report.coverage}, set(GLOBAL_SEARCH_KINDS))
        self.assertEqual([item.source for item in report.results if item.kind == 'ransomware'],
                         ['ransomlook', 'threatcluster'])
        self.assertEqual(report.total_match_count, sum(item.matched_count for item in report.coverage))
        self.assertEqual(self.files(), before)
        self.assertEqual(tuple(self.maigret.calls), calls)
        parser = build_parser()
        for result in report.results:
            self.assertTrue(result.source)
            self.assertTrue(result.recorded_at)
            for navigation in result.navigation:
                parser.parse_args(list(navigation.arguments))
        social = [item for item in report.results if item.record_type == 'social_profile']
        self.assertEqual({item.status for item in social}, {'found_unverified', 'unreported'})
        notices = next(item for item in report.results if item.kind == 'public-notice')
        self.assertIn('is_fabricated=True', ' '.join(notices.details))
        self.assertIn('CC BY 4.0', ' '.join(notices.details))

    def test_exact_prefix_contains_ranking_and_disjoint_global_pages(self):
        exact = self.entity('example')
        prefix = self.entity('Example Crew')
        contains = self.entity('The example actor')
        full = self.service.search('example', kinds=('cti', 'domain'))
        self.assertEqual([item.match_type for item in full.results], ['exact', 'prefix', 'prefix', 'contains'])
        self.assertEqual(full.results[0].record_id, exact.entity.id)
        pages = [self.service.search('example', kinds=('domain', 'cti'), offset=index, limit=1) for index in range(5)]
        self.assertEqual([p.results[0] for p in pages[:4]], list(full.results))
        self.assertEqual([p.total_match_count for p in pages], [4] * 5)
        self.assertEqual([p.has_more for p in pages], [True, True, True, False, False])
        self.assertEqual(pages[-1].results, ())
        self.assertEqual({prefix.entity.id, contains.entity.id} - {r.record_id for r in full.results}, set())

    def test_source_failure_last_success_and_never_collected_are_distinct(self):
        never = self.service.search('example', kinds=('public-notice', 'ransomware'))
        self.assertTrue(all(item.latest_run_id is None for item in never.coverage))
        self.assertIn('Henüz', ' '.join(never.coverage[0].notes))
        saved = self.save_notices((self.notice(),))
        self.now += timedelta(seconds=1)
        failed = self.notices.record_failure(started_at=self.now.isoformat(), finished_at=self.now.isoformat(), error='Kaynak geçici olarak erişilemiyor.')
        before = self.files()
        report = self.service.search('example', kinds=('public-notice',))
        self.assertEqual(report.total_match_count, 1)
        scope = report.coverage[0]
        self.assertEqual((scope.latest_run_id, scope.latest_run_status, scope.latest_success_run_id), (failed.id, 'failed', saved.run.id))
        self.assertEqual(report.results[0].source_run_id, saved.run.id)
        self.assertIn('Kaynak geçici', ' '.join(scope.notes))
        self.assertEqual(self.files(), before)

    def test_all_includes_withdrawn_catalog_identity_once_and_latest_version_only(self):
        notice = self.notice()
        first = self.save_notices((notice,))
        changed = replace(notice, title='Changed Example', modified_at='2025-02-04T00:00:00+00:00')
        self.save_notices((changed,))
        removal = self.save_notices((self.notice('UnrelatedIncident', 'other.test'),))
        self.assertEqual(self.service.search('example', kinds=('public-notice',)).total_match_count, 0)
        report = self.service.search('example', kinds=('public-notice',), include_inactive=True)
        self.assertEqual(report.total_match_count, 1)
        result = report.results[0]
        self.assertEqual((result.display_value, result.status, result.current, result.source_run_id),
                         ('Changed Example', 'withdrawn_from_catalog', False, removal.run.id))
        self.assertNotEqual(first.run.id, result.source_run_id)
        self.assertIn('--all tüm sürüm arşivi değildir', ' '.join(report.notes))

    def test_ransomware_sources_keep_independent_failures_and_removed_claims(self):
        baseline, _ = self.save_claims()
        at = datetime.now(timezone.utc).isoformat()
        failure = self.tc_claims.record_failure(started_at=at, finished_at=at, error='ThreatCluster geçici kesinti.')
        feed = fixtures.ransomlook_feed([fixtures.post('Unrelated Company', group='other-group')])
        at = datetime.now(timezone.utc).isoformat()
        removed = self.rl_claims.apply(feed, started_at=at, finished_at=at, item_limit=100)
        report = self.service.search('Example Holding', kinds=('ransomware',))
        self.assertEqual([item.source for item in report.results], ['threatcluster'])
        scope = next(item for item in report.coverage if item.source == 'threatcluster')
        self.assertEqual((scope.latest_run_id, scope.latest_success_run_id), (failure.id, baseline.run.id))
        history = self.service.search('Example Holding', kinds=('ransomware',), include_inactive=True)
        result = next(item for item in history.results if item.source == 'ransomlook')
        self.assertEqual((result.current, result.source_run_id), (False, removed.run.id))
        self.assertEqual(result.status, 'withdrawn_from_catalog')

    def test_social_current_definition_old_failure_and_human_decision_are_preserved(self):
        watch = self.add_social()
        self.maigret.responses.extend(({'GitHub': fixtures.github()}, SourceError('Kaynak bekleme sınırı.')))
        first = self.social.run(watch.id)
        self.result('brand', 'watch-review', watch.id, 'GitHub', '--decision', 'possible_impersonation', '--reason', 'İnsan değerlendirmesi kaydı.')
        self.social.run(watch.id)
        report = self.service.search('samplebrand', kinds=('social',))
        self.assertEqual(report.coverage[0].latest_run_status, 'failed')
        self.assertEqual(report.coverage[0].latest_success_run_id, first.run.id)
        profile = next(item for item in report.results if item.status == 'found_unverified')
        self.assertIn('İnsan kararı: possible_impersonation', profile.details)
        for navigation in profile.navigation:
            build_parser().parse_args(list(navigation.arguments))
        self.social.add(watch.display_name, 'changedbrand', platforms=watch.platforms)
        self.assertEqual(self.service.search('samplebrand', kinds=('social',)).total_match_count, 0)
        history = self.service.search('samplebrand', kinds=('social',), include_inactive=True)
        self.assertEqual(len(history.results), 2)
        self.assertTrue(all(not value.current and value.source_run_id == first.run.id for value in history.results))
        self.assertIsNone(history.coverage[0].latest_success_run_id)

    def test_inactive_suppliers_organizations_cti_and_expired_ioc_require_all(self):
        supplier = self.supplier()
        self.suppliers.revoke(supplier.id, reason='Hizmet ilişkisi sona erdi.')
        organization = self.result('organizations', 'add', 'Example organization')['organization']
        self.result('organizations', 'revoke', organization['id'], '--reason', 'Grup artık kullanılmıyor.')
        actor = self.entity('Example retired actor')
        self.knowledge.revoke_entity(actor.assertion.id, reason='Kaynak geri çekildi.')
        self.ioc('example-expired.net', valid_until=(self.now - timedelta(minutes=1)).isoformat())
        kinds = ('supplier', 'organization', 'cti', 'indicator')
        self.assertEqual(self.service.search('example', kinds=kinds).total_match_count, 0)
        report = self.service.search('example', kinds=kinds, include_inactive=True)
        self.assertEqual({item.kind for item in report.results}, set(kinds))
        self.assertTrue(all(not item.current for item in report.results))

    def test_case_link_search_keeps_case_state_and_removed_link_explicit(self):
        self.collect()
        finding = self.result('findings', 'list')['findings'][0]
        self.result('findings', 'review', finding['id'], '--decision', 'dismissed', '--reason', 'Meşru adres olarak incelendi.')
        case = self.create_case(title='Unrelated human case')
        link = self.result('cases', 'evidence-add', case.id, '--type', 'finding', '--evidence-id', finding['id'], '--reason', 'Açık insan kanıt bağlantısı.')['evidence']
        report = self.service.search(finding['domain'], kinds=('case', 'finding'))
        result = next(item for item in report.results if item.kind == 'case')
        self.assertEqual((result.record_id, result.matched_field, result.status), (case.id, 'linked_evidence', 'open'))
        self.assertEqual(next(item.status for item in report.results if item.kind == 'finding'), 'dismissed')
        self.result('cases', 'evidence-remove', case.id, link['id'], '--reason', 'İlgisiz kanıt bağlantısı kaldırıldı.')
        self.assertEqual(self.service.search(finding['domain'], kinds=('case',)).total_match_count, 0)
        removed = self.service.search(finding['domain'], kinds=('case',), include_inactive=True).results[0]
        self.assertEqual(removed.matched_field, 'removed_evidence')
        self.assertIn('etkin=False', ' '.join(removed.details))

    def test_nonmatching_corruption_fails_selected_scope_without_writes(self):
        self.entity('Visible Example')
        hidden = self.entity('Unrelated actor')
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE cti_entity_assertion_events SET aliases_json='[] ' WHERE assertion_id=?", (hidden.assertion.id,))
        before = self.files()
        with self.assertRaises(StorageError):
            self.service.search('visible', kinds=('cti',))
        # Explicit selection of another family does not silently claim the CTI scope.
        other = self.service.search('example', kinds=('domain',))
        self.assertEqual(other.kinds, ('domain',))
        self.assertEqual({scope.kind for scope in other.coverage}, {'domain'})
        self.assertEqual(self.files(), before)

    def test_case_current_state_tampering_fails_even_for_nonmatching_query(self):
        case = self.create_case()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE cases SET title='Unrelated forged title' WHERE id=?", (case.id,))
        before = self.files()
        with self.assertRaises(StorageError):
            self.service.search('no-match', kinds=('case',))
        self.assertEqual(self.files(), before)

    def test_case_last_activity_does_not_replace_state_time_or_search_private_note_body(self):
        case = self.create_case()
        later = (self.now + timedelta(minutes=1)).isoformat()
        SQLiteCaseRepository(self.database).add_note(case.id, kind='observation',
            body='Private note only unique phrase.', recorded_at=later)
        result = self.service.search('example', kinds=('case',)).results[0]
        self.assertEqual(result.recorded_at, case.updated_at)
        self.assertIn('Son vaka etkinliği: ' + later, result.details)
        self.assertEqual(self.service.search('unique phrase', kinds=('case',)).total_match_count, 0)

    def test_capacity_overflow_is_explicit_and_never_returns_a_partial_scope(self):
        SQLiteAssetRepository(self.database).add('second.example')
        before = self.files()
        with patch('xti.adapters.sqlite_global_search.MAX_SEARCH_ROWS', 1):
            with self.assertRaisesRegex(StorageError, 'kısmi sonuç üretilmedi'):
                self.service.search('example', kinds=('domain',))
        self.assertEqual(self.files(), before)

    def test_literal_unicode_validation_and_no_payload_search(self):
        self.entity('Example fullwidth')
        self.assertEqual(self.service.search('ＥＸＡＭＰＬＥ', kinds=('cti',)).total_match_count, 1)
        self.assertEqual(self.service.search('%_', kinds=('domain', 'cti')).total_match_count, 0)
        self.assertEqual(self.service.search('Yerel örnek kaynak', kinds=('cti',)).total_match_count, 0)
        for query, options in [('x', {}), ('bad\ninput', {}), ('example', {'kinds': []}),
                               ('example', {'kinds': ('unknown',)}), ('example', {'offset': -1}),
                               ('example', {'limit': 501}), ('example', {'include_inactive': 1})]:
            with self.assertRaises(ValidationError):
                self.service.search(query, **options)

    def test_single_read_snapshot_survives_concurrent_write(self):
        self.collect()
        finding = self.result('findings', 'list')['findings'][0]
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        reads, statements = [], []
        original_connection = self.service.repository._storage._connection
        original_domains = _SearchReader.domains
        @contextmanager
        def tracked_connection(*, readonly=False):
            reads.append(readonly)
            with original_connection(readonly=readonly) as connection:
                connection.set_trace_callback(statements.append)
                yield connection
        def write_after_first_family(reader):
            original_domains(reader)
            with closing(sqlite3.connect(self.database)) as writer, writer:
                writer.execute("UPDATE findings SET status='dismissed' WHERE id=?", (finding['id'],))
        with patch.object(self.service.repository._storage, '_connection', tracked_connection), patch.object(_SearchReader, 'domains', write_after_first_family):
            report = self.service.search('example', kinds=('domain', 'finding'))
        selected = next(item for item in report.results if item.record_id == finding['id'])
        self.assertEqual(selected.status, finding['status'])
        self.assertEqual(reads, [True])
        self.assertEqual(statements.count('BEGIN'), 1)
        self.assertFalse(any(query.lstrip().split()[0].upper() in {'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER'} for query in statements))

    def test_cli_json_pagination_missing_database_and_terminal_escaping(self):
        self.entity('Example actor')
        before = self.files()
        result = self.result('search', 'example', '--kind', 'cti', '--kind', 'domain', '--limit', '1')
        self.assertEqual((result['total_match_count'], result['has_more']), (2, True))
        self.assertEqual(self.files(), before)
        report = self.service.search('example', kinds=('domain',), limit=1)
        escaped = replace(report, query='text\x1b[31m\ncontrol', results=(replace(report.results[0], display_value='name\x1b[31m\ncontrol'),))
        rendered = '\n'.join(global_search_lines(escaped))
        self.assertNotIn('\x1b', rendered)
        self.assertIn('\\u001b[31m\\u000a', rendered)
        missing = self.data.parent / 'missing'
        code, out, error = self.invoke('--data-dir', str(missing), 'search', 'example')
        self.assertNotEqual(code, 0)
        self.assertEqual(out, '')
        self.assertIn('Veritabanı bulunamadı', json.loads(error)['error']['message'])
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()

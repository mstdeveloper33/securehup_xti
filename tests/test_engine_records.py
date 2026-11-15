"""Real stored evidence round-trips through the engine record read boundary."""

from contextlib import closing
from dataclasses import fields, make_dataclass, replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.engine_records import SQLiteEngineRecordRepository
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.engine import EngineContractError, EngineRecordReference, reference_for_result
from xti.domain.global_search import GLOBAL_SEARCH_KINDS
from tests import test_collection_watch_cli as fixtures
from tests import test_global_search as global_fixtures


class EngineRecordTests(unittest.TestCase):
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files
    add_social = fixtures.CollectionWatchCLITests.add_social
    collect = global_fixtures.GlobalSearchTests.collect
    notice = global_fixtures.GlobalSearchTests.notice
    save_notices = global_fixtures.GlobalSearchTests.save_notices
    save_claims = global_fixtures.GlobalSearchTests.save_claims
    entity = global_fixtures.GlobalSearchTests.entity
    ioc = global_fixtures.GlobalSearchTests.ioc
    supplier = global_fixtures.GlobalSearchTests.supplier
    create_case = global_fixtures.GlobalSearchTests.create_case

    def setUp(self):
        global_fixtures.GlobalSearchTests.setUp(self)
        self.records = SQLiteEngineRecordRepository(self.database)

    def seed_all(self):
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
        return self.service.search('example').results

    def test_every_search_family_and_subtype_resolves_structured_evidence_without_writes(self):
        hits = self.seed_all()
        self.assertEqual({hit.kind for hit in hits}, set(GLOBAL_SEARCH_KINDS))
        self.assertTrue({'registered_domain', 'surface_candidate', 'username_watch', 'social_profile'} <= {hit.record_type for hit in hits})
        before, calls = self.files(), (len(self.maigret.calls), self.threatcluster.calls, self.ransomlook.calls)
        with patch.object(SQLiteAssetRepository, 'initialize', side_effect=AssertionError('Read must not initialize')):
            for hit in hits:
                with self.subTest(kind=hit.kind, record_type=hit.record_type, namespace=hit.source):
                    reference = reference_for_result(hit)
                    detail = self.records.get(reference, limit=1)
                    self.assertEqual(detail['reference'], reference.to_dict())
                    self.assertEqual(detail['record']['id'], hit.record_id)
                    self.assertNotIn('matched_field', detail['record'])
                    self.assertTrue(detail['provenance']['source'])
                    self.assertTrue(detail['notes'])
                    json.dumps(detail, allow_nan=False)
                    for page in detail['sections'].values():
                        self.assertLessEqual(len(page['items']), 1)
                        self.assertEqual(page['has_more'], page['total_count'] > 1)
        self.assertEqual(self.files(), before)
        self.assertEqual((len(self.maigret.calls), self.threatcluster.calls, self.ransomlook.calls), calls)

    def test_ransomware_same_identity_stays_in_its_source_namespace(self):
        tc, rl = self.save_claims()
        hits = self.service.search('Example Holding', kinds=('ransomware',)).results
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].record_id, hits[1].record_id)
        details = {hit.source: self.records.get(reference_for_result(hit)) for hit in hits}
        self.assertEqual(details['threatcluster']['record']['website'], 'example.com')
        self.assertNotIn('website', details['ransomlook']['record'])
        self.assertEqual(details['threatcluster']['provenance']['record_run_id'], tc.run.id)
        self.assertEqual(details['ransomlook']['provenance']['record_run_id'], rl.run.id)
        for source, detail in details.items():
            self.assertIn(source.casefold(), detail['provenance']['source'].casefold())
            self.assertIn('4.0', detail['provenance']['license'])

    def test_catalog_failure_preserves_current_record_and_last_success(self):
        baseline, _ = self.save_claims()
        at = datetime.now(timezone.utc).isoformat()
        failed = self.tc_claims.record_failure(started_at=at, finished_at=at, error='Kaynak geçici kesinti.')
        hit = next(hit for hit in self.service.search('Example Holding', kinds=('ransomware',)).results if hit.source == 'threatcluster')
        detail = self.records.get(reference_for_result(hit))
        self.assertTrue(detail['provenance']['current'])
        self.assertEqual(detail['provenance']['latest_run']['id'], failed.id)
        self.assertEqual(detail['provenance']['latest_run']['error'], 'Kaynak geçici kesinti.')
        self.assertEqual(detail['provenance']['latest_complete_run']['id'], baseline.run.id)
        self.assertEqual(detail['provenance']['record_run_id'], baseline.run.id)

    def test_removed_public_notice_keeps_changed_payload_and_paged_history(self):
        initial = self.save_notices((self.notice(),))
        changed = replace(self.notice(), title='Changed Example', modified_at='2025-02-04T00:00:00+00:00')
        self.save_notices((changed,))
        removed = self.save_notices((self.notice('OtherIncident', 'other.test'),))
        hit = self.service.search('example', kinds=('public-notice',), include_inactive=True).results[0]
        ref = reference_for_result(hit)
        full = self.records.get(ref)
        self.assertEqual(full['record']['title'], changed.title)
        self.assertFalse(full['provenance']['current'])
        self.assertEqual(full['provenance']['record_run_id'], removed.run.id)
        self.assertIn('Have I Been Pwned', full['provenance']['attribution'])
        self.assertEqual(full['sections']['changes']['total_count'], 3)
        pages = [self.records.get(ref, offset=index, limit=1)['sections']['changes'] for index in range(4)]
        self.assertEqual([page['has_more'] for page in pages], [True, True, False, False])
        self.assertEqual(pages[-1]['items'], [])
        self.assertEqual([page['items'][0]['change']['action'] for page in pages[:3]], ['added', 'updated', 'removed'])
        self.assertEqual(pages[0]['items'][0]['run']['id'], initial.run.id)
        self.assertEqual([page['items'][0] for page in pages[:3]], full['sections']['changes']['items'])

    def test_removed_ransomlook_record_remains_readable(self):
        self.save_claims()
        hit = next(hit for hit in self.service.search('Example Holding', kinds=('ransomware',)).results if hit.source == 'ransomlook')
        feed = fixtures.ransomlook_feed([fixtures.post('Another Company', group='other-group')])
        at = datetime.now(timezone.utc).isoformat()
        removed = self.rl_claims.apply(feed, started_at=at, finished_at=at, item_limit=100)
        detail = self.records.get(reference_for_result(hit))
        self.assertFalse(detail['provenance']['current'])
        self.assertEqual(detail['provenance']['record_run_id'], removed.run.id)
        self.assertEqual(detail['record']['victim'], 'Example Holding')

    def test_historical_social_item_keeps_original_definition_and_human_review(self):
        watch = self.add_social()
        self.maigret.responses.append({'GitHub': fixtures.github()})
        run = self.social.run(watch.id)
        self.result('brand', 'watch-review', watch.id, 'GitHub', '--decision', 'possible_impersonation', '--reason', 'İnsan incelemesi kanıtı.')
        hit = next(hit for hit in self.service.search('samplebrand', kinds=('social',)).results if hit.status == 'found_unverified')
        self.social.add(watch.display_name, 'changedbrand', platforms=watch.platforms)
        detail = self.records.get(reference_for_result(hit))
        self.assertEqual(detail['record']['run_id'], run.run.id)
        self.assertEqual(detail['provenance']['run']['username'], 'samplebrand')
        self.assertFalse(detail['provenance']['current'])
        self.assertEqual(detail['provenance']['current_review']['decision'], 'possible_impersonation')
        self.assertNotIn('current_review', detail['record'])
        self.assertEqual(detail['sections']['review_events']['total_count'], 1)

    def test_human_review_updates_provenance_without_rewriting_historical_source_item(self):
        watch = self.add_social()
        self.maigret.responses.append({'GitHub': fixtures.github()})
        self.social.run(watch.id)
        hit = next(hit for hit in self.service.search('samplebrand', kinds=('social',)).results
                   if hit.status == 'found_unverified')
        reference = reference_for_result(hit)
        before = self.records.get(reference)
        self.assertIsNone(before['provenance']['current_review'])
        self.assertNotIn('current_review', before['record'])
        self.result('brand', 'watch-review', watch.id, 'GitHub', '--decision',
                    'possible_impersonation', '--reason', 'İnsan değerlendirmesi yapıldı.')
        after = self.records.get(reference)
        self.assertEqual(after['record'], before['record'])
        self.assertNotIn('current_review', after['record'])
        self.assertEqual(after['provenance']['current_review']['decision'], 'possible_impersonation')
        self.assertEqual(after['sections']['review_events']['total_count'], 1)

    def test_inactive_local_and_intelligence_records_keep_source_history(self):
        supplier = self.supplier()
        self.suppliers.revoke(supplier.id, reason='Hizmet ilişkisi sona erdi.')
        actor = self.entity('Example old actor')
        self.knowledge.revoke_entity(actor.assertion.id, reason='Kaynak geri çekildi.')
        self.ioc('example-expired.net', valid_until=(self.now - timedelta(minutes=1)).isoformat())
        for hit in self.service.search('example', kinds=('supplier', 'cti', 'indicator'), include_inactive=True).results:
            detail = self.records.get(reference_for_result(hit))
            self.assertEqual(detail['record']['id'], hit.record_id)
            if hit.kind == 'supplier':
                self.assertFalse(detail['record']['active'])
                self.assertEqual(detail['sections']['events']['total_count'], 2)
            else:
                self.assertEqual(detail['sections']['assertions']['total_count'], 1)

    def test_case_evidence_and_organization_links_are_structured_and_paged(self):
        self.collect()
        finding = self.result('findings', 'list')['findings'][0]
        case = self.create_case()
        self.result('cases', 'evidence-add', case.id, '--type', 'finding',
                    '--evidence-id', finding['id'], '--reason', 'Açık kanıt bağlantısı.')
        detail = self.records.get(EngineRecordReference('case', 'case', 'local-case-management', case.id), limit=1)
        evidence = detail['sections']['evidence']['items'][0]
        self.assertEqual(evidence['evidence_id'], finding['id'])
        self.assertIsInstance(json.loads(evidence['snapshot_json']), dict)
        self.assertTrue(detail['sections']['activities']['has_more'])
        organization = self.result('organizations', 'add', 'Example group')['organization']
        self.result('organizations', 'link', organization['id'], '--kind', 'domain', '--value', 'example.com')
        ref = EngineRecordReference('organization', 'organization', 'local-organizations', organization['id'])
        detail = self.records.get(ref)
        link = detail['sections']['links']['items'][0]
        self.assertEqual(link['target']['reference'], {'kind': 'domain', 'value': 'example.com'})
        self.assertEqual(detail['sections']['link_events']['total_count'], 1)
        beyond = self.records.get(ref, offset=5, limit=1)
        self.assertTrue(all(section['items'] == [] and not section['has_more'] for section in beyond['sections'].values()))

    def test_wrong_namespace_subtype_and_missing_record_are_not_found(self):
        actor = self.entity('Example actor')
        for ref in (
            EngineRecordReference('cti', 'threat-actor', 'local-ioc', actor.entity.id),
            EngineRecordReference('cti', 'campaign', 'local-cti', actor.entity.id),
            EngineRecordReference('cti', 'threat-actor', 'local-cti', str(uuid4())),
            EngineRecordReference('domain', 'registered_domain', 'local-assets', str(uuid4())),
        ):
            with self.subTest(reference=ref), self.assertRaises(EngineContractError) as caught:
                self.records.get(ref)
            self.assertEqual(caught.exception.code, 'not_found')

    def test_corrupted_case_and_cti_current_state_fail_without_repair(self):
        case = self.create_case()
        actor = self.entity('Example actor')
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute('UPDATE cases SET title=? WHERE id=?', ('Changed without history', case.id))
            connection.execute('UPDATE cti_entity_assertions SET confidence=5 WHERE id=?', (actor.assertion.id,))
            connection.commit()
        before = self.files()
        for ref in (
            EngineRecordReference('case', 'case', 'local-case-management', case.id),
            EngineRecordReference('cti', 'threat-actor', 'local-cti', actor.entity.id),
        ):
            with self.subTest(reference=ref), self.assertRaises(StorageError):
                self.records.get(ref)
        self.assertEqual(self.files(), before)

    def test_missing_storage_and_capacity_overflow_never_create_or_truncate(self):
        missing = self.data / 'absent' / 'xti.db'
        with self.assertRaises(StorageError):
            SQLiteEngineRecordRepository(missing).get(EngineRecordReference('case', 'case', 'local-case-management', str(uuid4())))
        self.assertFalse(missing.parent.exists())
        case = self.create_case()
        before = self.files()
        with patch('xti.adapters.engine_records.MAX_DETAIL_ROWS', 0), self.assertRaises(StorageError):
            self.records.get(EngineRecordReference('case', 'case', 'local-case-management', case.id))
        self.assertEqual(self.files(), before)

    def test_future_internal_fields_are_not_added_to_v1_record_or_nested_history(self):
        notice = self.notice()
        self.save_notices((notice,))
        hit = self.service.search('example', kinds=('public-notice',)).results[0]
        reference = reference_for_result(hit)
        ordinary = self.records.get(reference)
        extended_type = make_dataclass('PublicNotice',
            [(field.name, object) for field in fields(notice)] + [('internal_secret', str)])
        extended_type.__module__ = 'xti.domain.public_notices'
        extended = extended_type(**{field.name: getattr(notice, field.name) for field in fields(notice)},
                                 internal_secret='must-stay-internal')
        reader = self.records._catalog

        def with_future_field(connection, ref):
            record, sections, provenance, notes = reader(connection, ref)
            changes = tuple({'change': replace(item['change'], notice=extended), 'run': item['run']}
                            for item in sections['changes'])
            return extended, {'changes': changes}, provenance, notes

        with patch.object(self.records, '_catalog', side_effect=with_future_field):
            projected = self.records.get(reference)
        self.assertEqual(projected, ordinary)
        self.assertNotIn('must-stay-internal', json.dumps(projected))


if __name__ == '__main__':
    unittest.main()

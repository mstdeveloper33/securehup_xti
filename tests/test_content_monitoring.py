from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_content_monitoring import SQLiteContentRepository
from xti.application.content_monitoring import ContentMonitoringService
from xti.domain.content_monitoring import ContentDocument, ContentError, match_terms, scope, source_definition
from xti.domain.assets import ValidationError


class Scanner:
    def status(self): return {'state': 'ready'}
    def scan(self, content, *, seconds):
        return [{'rule': 'controlled-test', 'line': index + 1} for index, line in enumerate(content.splitlines()) if 'synthetic-secret' in line]


class Sources:
    def __init__(self):
        self.calls = 0
        self.documents = [ContentDocument('1', 'https://news.example.com/1', 'Example Corp update', 'example.com released a report.')]
        self.state = 'complete'
    def status(self): return []
    def collect(self, source, checkpoint, budget, consume, *, targets=()):
        self.calls += 1
        self.targets = targets
        for document in self.documents: consume(document)
        return {'status': self.state, 'items': len(self.documents), 'operations': 1,
                'checkpoint': {'baseline_complete': True} if self.state == 'complete' else None}


class Targets:
    def resolve(self, kind, identifier): raise AssertionError('No inventory resolution expected')


class ContentFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'xti.db'
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteContentRepository(self.path); self.sources = Sources()
        self.at = datetime(2026, 11, 21, tzinfo=timezone.utc)
        self.service = ContentMonitoringService(self.repository, self.sources, Targets(), Scanner(), now=lambda: self.at.isoformat())
        self.source = self.service.execute('content.source.add', provider='rss', locator='https://news.example.com/rss', idempotency_key='source')
        self.watch = self.service.execute('content.watch.add', sources=[self.source['id']],
            targets=[{'kind': 'company', 'name': 'Example Corp', 'domains': ['example.com']}], idempotency_key='watch')

    def run_content(self, key='run'):
        self.at += timedelta(days=1)
        return self.service.execute('content.run', identifier=self.watch['id'], expected_revision=self.watch['revision'], idempotency_key=key)

    def matches(self): return self.service.execute('content.matches')['items']

    def test_baseline_masking_replay_and_unchanged_do_not_duplicate(self):
        self.sources.documents[0] = replace(self.sources.documents[0], content='example.com\nsynthetic-secret')
        first = self.run_content()
        self.assertEqual(first['status'], 'complete'); self.assertEqual(first['report']['new_matches'], 1)
        self.assertEqual(first['report']['changes'], 0)
        evidence = self.matches()[0]['evidence']['body']
        self.assertIn('MASKELENDİ', evidence['excerpt'])
        self.assertNotIn(b'synthetic-secret', self.path.read_bytes())
        replay = self.run_content(); self.assertTrue(replay['replayed']); self.assertEqual(self.sources.calls, 1)
        second = self.run_content('unchanged'); self.assertEqual(second['report']['new_evidence'], 0)
        self.assertEqual(second['report']['changes'], 0)
        with closing(sqlite3.connect(self.path)) as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM content_evidence').fetchone()[0], 1)

    def test_content_changes_preserve_review_and_require_new_decision(self):
        self.run_content(); current = self.matches()[0]
        review = self.service.execute('content.review', identifier=current['id'], evidence_id=current['evidence_id'],
            expected_revision=0, expected_observation_revision=1, decision='ordinary_news', reason='Controlled public update', idempotency_key='review')
        self.assertFalse(self.matches()[0]['needs_review'])
        self.sources.documents[0] = replace(self.sources.documents[0], content='example.com changed its report.')
        changed = self.run_content('change')
        current2 = self.matches()[0]
        self.assertEqual(changed['report']['changes'], 1); self.assertTrue(current2['needs_review'])
        self.assertEqual(current2['review']['id'], review['id'])
        self.assertEqual(current2['observation_revision'], 2)
        self.assertEqual(self.service.execute('content.evidence.show', identifier=current['evidence_id'])['body']['excerpt'], 'example.com released a report.')
        with self.assertRaises(ContentError):
            self.service.execute('content.review', identifier=current['id'], evidence_id=current['evidence_id'],
                expected_revision=1, expected_observation_revision=1, decision='ordinary_news', reason='Stale review', idempotency_key='stale')
        # Returning to the earlier text must not revive its old review automatically.
        self.sources.documents[0] = replace(self.sources.documents[0], content='example.com released a report.')
        self.run_content('return'); self.assertTrue(self.matches()[0]['needs_review'])

    def test_failure_empty_success_and_absence_never_delete_previous_content(self):
        self.run_content(); identifier = self.matches()[0]['id']
        self.sources.documents = []; self.sources.state = 'unavailable'
        failed = self.run_content('failed'); self.assertEqual(failed['status'], 'failed')
        self.sources.state = 'complete'; empty = self.run_content('empty'); self.assertEqual(empty['status'], 'complete')
        self.assertEqual(self.matches()[0]['id'], identifier)
        self.assertEqual(empty['report']['changes'], 0)

    def test_same_body_across_two_targets_stored_once(self):
        self.watch = self.service.execute('content.watch.update', identifier=self.watch['id'], expected_revision=1,
            targets=[{'name': 'Example Corp', 'domains': ['example.com']}, {'name': 'Example Partner', 'domains': ['example.com']}], idempotency_key='two')
        run = self.run_content(); self.assertEqual(len(self.matches()), 2)
        self.assertEqual(run['report']['new_evidence'], 1)
        self.assertEqual(len({m['evidence_id'] for m in self.matches()}), 1)

    def test_source_revision_change_requires_explicit_watch_update_and_replay_still_works(self):
        self.run_content()
        self.service.execute('content.source.update', identifier=self.source['id'], expected_revision=1, name='Updated name', idempotency_key='source-change')
        self.assertTrue(self.run_content()['replayed'])
        with self.assertRaises(ContentError) as error: self.run_content('new')
        self.assertEqual(error.exception.code, 'scope_changed'); self.assertEqual(self.sources.calls, 1)
        self.watch = self.service.execute('content.watch.update', identifier=self.watch['id'], expected_revision=1, enabled=True, idempotency_key='rebind')
        self.assertEqual(self.run_content('bound')['status'], 'complete')
        # A disabled source must never prevent the user from stopping its watch.
        self.service.execute('content.source.update', identifier=self.source['id'], expected_revision=2,
            enabled=False, idempotency_key='source-stop')
        stop = dict(identifier=self.watch['id'], expected_revision=2, enabled=False, idempotency_key='watch-stop')
        stopped = self.service.execute('content.watch.update', **stop)
        self.assertFalse(stopped['enabled'])
        self.assertEqual(stopped['bindings'], self.watch['bindings'])
        self.assertTrue(self.service.execute('content.watch.update', **stop)['replayed'])
        with self.assertRaises(ContentError) as unavailable:
            self.service.execute('content.watch.update', identifier=stopped['id'], expected_revision=3,
                enabled=True, idempotency_key='restart')
        self.assertEqual(unavailable.exception.code, 'source_disabled')
        self.assertEqual(self.sources.calls, 2)

    def test_interrupted_reservation_requires_recovery_and_never_repeats_http(self):
        values = {'identifier': self.watch['id'], 'expected_revision': 1, 'idempotency_key': 'crash'}
        run, _ = self.repository.reserve(values, self.at.isoformat(), bindings=self.watch['bindings'])
        result = self.service.execute('content.run', **values)
        self.assertTrue(result['replayed']); self.assertEqual(self.sources.calls, 0)
        recovered = self.service.execute('content.recover', identifier=run['id'], idempotency_key='recover')
        self.assertEqual(recovered['status'], 'interrupted')
        self.assertEqual(self.sources.calls, 0)
        self.assertEqual(self.run_content('fresh')['status'], 'complete')

    def test_scope_and_pagination_are_explicit(self):
        self.sources.documents = [replace(self.sources.documents[0], native_id=str(i), url=f'https://news.example.com/{i}') for i in range(5)]
        self.run_content()
        page = self.service.execute('content.matches', limit=2, domain='example.com')
        second = self.service.execute('content.matches', limit=2, domain='example.com', after=page['next_after'])
        third = self.service.execute('content.matches', limit=2, domain='example.com', after=second['next_after'])
        self.assertEqual(len({v['id'] for p in (page, second, third) for v in p['items']}), 5)
        self.assertIsNone(third['next_after'])
        self.assertEqual(self.service.execute('content.report', domain='other.example')['total_matches'], 0)
        self.assertEqual(self.service.execute('content.report', domain='example.com')['total_matches'], 5)

    def test_failed_scanner_preserves_only_metadata(self):
        self.service.scanner.status = lambda: {'state': 'not_installed'}
        self.sources.documents[0] = replace(self.sources.documents[0], title='example.com synthetic-secret')
        result = self.run_content()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(self.matches()[0]['evidence']['body']['excerpt'], '')
        self.assertNotIn(b'synthetic-secret', self.path.read_bytes())

    def test_inbox_and_case_keep_exact_old_evidence(self):
        from xti.adapters.sqlite_inbox import SQLiteInboxRepository
        from xti.adapters.sqlite_status import SQLiteStatusRepository
        from xti.interfaces.cli import make_case_service
        from xti.config import Settings
        self.run_content(); match = self.matches()[0]
        cases = make_case_service(Settings(data_dir=self.path.parent))
        case = cases.create('Content review', summary='Fixture', reason='Verification').case
        frozen = cases.add_evidence(case.id, 'content_match', match['id'], reason='Freeze proof').evidence
        self.sources.documents[0] = replace(self.sources.documents[0], content='example.com changed report')
        self.run_content('changed')
        inbox = SQLiteInboxRepository(self.path); page = inbox.list()
        self.assertEqual(page.total_count, 1)
        counts = SQLiteAssetRepository(self.path).inspect()
        status = SQLiteStatusRepository(self.path).snapshot(('crt.sh',), None, 10)
        self.assertEqual((counts['notification_count'], counts['unread_notification_count']), (1, 1))
        self.assertEqual((status.notification_count, status.unread_notification_count), (1, 1))
        notice = page.items[0].notification.id
        details = inbox.get(notice).content_change
        self.assertEqual(details['before']['body']['excerpt'], 'example.com released a report.')
        self.assertEqual(details['after']['body']['excerpt'], 'example.com changed report')
        inbox.mark([notice], True, self.at.isoformat())
        self.assertEqual(inbox.list().unread_count, 0)
        counts = SQLiteAssetRepository(self.path).inspect()
        status = SQLiteStatusRepository(self.path).snapshot(('crt.sh',), None, 10)
        self.assertEqual((counts['notification_count'], counts['unread_notification_count']), (1, 0))
        self.assertEqual((status.notification_count, status.unread_notification_count), (1, 0))
        self.assertIn('released a report', frozen.snapshot_json)
        self.assertNotIn('changed report', frozen.snapshot_json)

    def test_changed_text_that_no_longer_mentions_target_reopens_review(self):
        self.run_content(); before = self.matches()[0]
        self.service.execute('content.review', identifier=before['id'], evidence_id=before['evidence_id'],
            expected_revision=0, expected_observation_revision=1, decision='ordinary_news', reason='First review', idempotency_key='old-review')
        self.sources.documents[0] = replace(self.sources.documents[0], url='https://publisher.test/1', title='A corrected article', content='A different company was involved.')
        self.run_content('corrected')
        current = self.matches()[0]
        self.assertEqual(current['match']['kind'], 'previous_match_not_in_current_text')
        self.assertTrue(current['needs_review']); self.assertEqual(current['observation_revision'], 2)

    def test_atomic_failure_does_not_publish_half_a_change(self):
        self.run_content(); original = self.matches()
        self.sources.documents[0] = replace(self.sources.documents[0], content='example.com updated')
        with patch('xti.adapters.sqlite_notification_sequence.next_notification_sequence', side_effect=RuntimeError('disk fixture')):
            with self.assertRaises(RuntimeError): self.run_content('disk-failure')
        self.assertEqual(self.matches(), original)
        self.assertEqual(self.service.execute('content.changes')['items'], [])
        self.assertEqual(self.service.execute('content.runs')['items'][-1]['status'], 'running')

    def test_company_view_includes_explicit_supplier_and_excludes_other_company(self):
        from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
        from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
        from xti.adapters.sqlite_mention_targets import SQLiteMentionTargetRepository
        from xti.adapters.sqlite_company_content import SQLiteCompanyContentRepository
        from xti.application.company_content import CompanyContentService
        organizations = SQLiteOrganizationRepository(self.path)
        company = organizations.add(name_key='example corp', display_name='Example Corp', reason='Fixture', recorded_at=self.at.isoformat()).organization
        other = organizations.add(name_key='another company', display_name='Another company', reason='Fixture', recorded_at=self.at.isoformat()).organization
        supplier = SQLiteSupplierRepository(self.path).add(name_key='example supplier', display_name='Example Supplier', primary_domain='supplier.test',
            relationship_type='software', criticality='high', reason='Fixture', recorded_at=self.at.isoformat()).supplier
        self.service.targets = SQLiteMentionTargetRepository(self.path)
        self.watch = self.service.execute('content.watch.update', identifier=self.watch['id'], expected_revision=1,
            targets=[{'kind': 'organization', 'id': company.id}, {'kind': 'supplier', 'id': supplier.id}], idempotency_key='company-watch')
        self.sources.documents.append(ContentDocument('2', 'https://news.example.com/2', 'Example Supplier news', 'supplier.test announced an update.'))
        self.run_content()
        view = CompanyContentService(SQLiteCompanyContentRepository(self.path), clock=lambda: self.at)
        report = view.show(company.id)
        # Stored feed matches do not turn the still-unchecked web search into success.
        self.assertEqual(report['state'], 'partial')
        self.assertEqual(report['monitored_content']['watches'][0]['latest_run']['status'], 'complete')
        self.assertEqual(report['monitored_content']['total_count'], 2)
        self.assertEqual({r['target']['kind'] for r in report['monitored_content']['items']}, {'organization', 'supplier'})
        self.assertEqual(view.show(other.id)['monitored_content']['items'], [])

    def test_replayed_watch_update_survives_later_source_disable(self):
        request = dict(identifier=self.watch['id'], expected_revision=1, name='Updated', idempotency_key='update')
        changed = self.service.execute('content.watch.update', **request)
        self.service.execute('content.source.update', identifier=self.source['id'], expected_revision=1,
                             enabled=False, idempotency_key='disable')
        replay = self.service.execute('content.watch.update', **request)
        self.assertTrue(replay['replayed']); self.assertEqual(changed['id'], replay['id'])

    def test_url_secrets_and_native_identifiers_never_enter_evidence(self):
        self.sources.documents = [ContentDocument('synthetic-secret-native', 'https://publisher.test/synthetic-secret-url',
                                                 'Example Corp', 'example.com update')]
        self.run_content()
        body = self.matches()[0]['evidence']['body']
        self.assertEqual(body['url'], ''); self.assertEqual(len(body['native_id']), 64)
        self.assertNotIn(b'synthetic-secret', self.path.read_bytes())

    def test_history_is_recorded_without_new_alarm_but_newest_message_alerts(self):
        self.run_content()
        self.sources.documents = [ContentDocument('old', '', 'Example Corp old report', '', historical=True),
                                  ContentDocument('new', '', 'Example Corp current update', '')]
        result = self.run_content('history-and-new')
        self.assertEqual(result['report']['new_matches'], 2)
        self.assertEqual(result['report']['changes'], 1)

    def test_tampered_evidence_schema_is_rejected_even_with_recomputed_hash(self):
        from xti.domain.content_monitoring import canonical, digest
        from xti.adapters.sqlite import StorageError
        self.run_content(); row = self.matches()[0]['evidence']; body = row['body']
        body['unexpected_raw_content'] = 'should not be returned'
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE content_evidence SET body_json=?,body_sha256=? WHERE id=?', (canonical(body), digest(body), row['id']))
        with self.assertRaises(StorageError): self.matches()


class UnicodeContentTests(unittest.TestCase):
    def test_forty_independently_labelled_multilingual_examples(self):
        cases = {
            'tr': ('İleri Teknoloji', ['Ileri Teknoloji'], [
                ('İLERİ TEKNOLOJİ duyurusu', 'name_candidate'), ('İleri Teknoloji: faaliyet raporu', 'name_candidate'),
                ('Ileri Teknoloji bir hizmet sağlayıcıdır', 'name_candidate'), ('ileri.example hizmeti güncellendi', 'domain_match'),
                ('Yeni teknolojileri takip ediyoruz', None), ('İleri Teknolojiler hakkında', None),
                ('sahteileri.example sitesi', None), ('İleri Teknoloji adlı başka bir kuruluş', 'name_candidate')]),
            'ru': ('Север Банк', [], [
                ('СЕВЕР БАНК опубликовал отчёт', 'name_candidate'), ('«Север Банк» новости', 'name_candidate'),
                ('Север Банк: результаты', 'name_candidate'), ('ileri.example обновлён', 'domain_match'),
                ('Северные банки', None), ('Север Банковский отчёт', None), ('ileri.example.evil.test', None),
                ('Другой Север Банк', 'name_candidate')]),
            'zh': ('华星科技', [], [
                ('华星科技发布公告', 'name_candidate'), ('关于华星科技的新闻', 'name_candidate'),
                ('华星科技：年度报告', 'name_candidate'), ('网站ileri.example更新', None),
                ('ileri.example 发布消息', 'domain_match'), ('华兴科技发布消息', None),
                ('其他公司的公告', None), ('另一个华星科技', 'name_candidate')]),
            'ar': ('شركة النور', [], [
                ('أعلنت شركة النور تقريرها', 'name_candidate'), ('شركة النور: أخبار', 'name_candidate'),
                ('«شركة النور»', 'name_candidate'), ('تحديث ileri.example', 'domain_match'),
                ('شركة الأنوار', None), ('شركات النور', None), ('ileri.example.evil.test', None),
                ('شركة النور أخرى بنفس الاسم', 'name_candidate')]),
            'pt': ('Árvore Digital', [], [
                ('ÁRVORE DIGITAL publicou novidades', 'name_candidate'), ('Árvore Digital publicou relatório', 'name_candidate'),
                ('“Árvore Digital”', 'name_candidate'), ('Notícias de ileri.example', 'domain_match'),
                ('Arvores digitais', None), ('Árvore Digitals', None), ('falsoileri.example', None),
                ('Outra Árvore Digital, sem vínculo', 'name_candidate')]),
        }
        count = 0
        for language, (name, aliases, examples) in cases.items():
            for content, expected in examples:
                with self.subTest(language=language, content=content):
                    match = match_terms(ContentDocument('1', '', '', content), {'name': name, 'aliases': aliases, 'domains': ['ileri.example']})
                    self.assertEqual(match['kind'] if match else None, expected)
                    if match: self.assertFalse(match['identity_confirmed']); self.assertFalse(match['threat_confirmed'])
                    count += 1
        self.assertEqual(count, 40)

    def test_source_configuration_never_accepts_credentials_or_private_channel_invites(self):
        for provider, locator in [('rss', 'http://example.com/rss'), ('rss', 'https://user:password@example.com/'),
                                  ('bluesky', 'https://example.com/search'),
                                  ('telegram', 'https://t.me/+invite'), ('discord', '@me/12345'), ('irc', 'ircs://example.com/#chan')]:
            with self.subTest(provider=provider, locator=locator), self.assertRaises(ValidationError):
                source_definition({'provider': provider, 'locator': locator})

    def test_bluesky_source_is_fixed_to_public_appview(self):
        source = source_definition({'provider': 'bluesky'})
        self.assertEqual(source['locator'], 'https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts')
        self.assertEqual(source['category'], 'channel')


if __name__ == '__main__': unittest.main()

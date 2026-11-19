"""Source revisions, frozen human links, replay and preservation of evidence."""

from dataclasses import replace
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_reports import SQLiteReportRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.application.reports import ReportService
from xti.domain.assets import ValidationError
from xti.domain.reports import ReportError, publication
from tests import test_news_storage as news

NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.f = news.NewsStorageTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.path = self.f.path
        self.repo = SQLiteReportRepository(self.path)
        self.service = ReportService(self.repo, clock=lambda: NOW)
        self.item = news.article(summary='Report mentions 192.0.2.10 and suspect[.]example')
        self.f.apply(self.item)
        self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No network')))
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network')))

    def capture(self, key='capture-one', identifier=None):
        return self.service.execute('reports.capture', source='news', identifier=identifier or self.item.id, idempotency_key=key)

    def show(self, identifier, **options):
        return self.service.execute('reports.show', identifier=identifier, **options)['record']

    def observe(self, **options):
        return self.service.execute('observations.list', indicator_type='ipv4', value='192.0.2.10', **options)

    def entity(self, kind='campaign'):
        return CtiKnowledgeService(SQLiteCtiKnowledgeRepository(self.path), clock=lambda: NOW).add_entity(
            kind, 'Controlled ' + kind, source_name='analyst', source_reference='https://source.example/cti',
            confidence=40, aliases=(), description='Controlled test evidence').entity.id

    def link(self, report_id, target_id, revision=1, key='link-one', **options):
        return self.service.execute('reports.link', identifier=report_id, target_kind='entity', target_id=target_id,
            expected_revision=revision, idempotency_key=key,
            **{'state': 'linked', 'reason': 'Analyst reviewed this exact text', **options})

    def test_capture_preserves_text_source_and_unknown_event_time_without_creating_ioc(self):
        record = self.capture()['record']
        doc = record['document']
        self.assertEqual(doc['summary'], self.item.summary)
        self.assertEqual(doc['text'], self.item.title + '\n' + self.item.summary)
        obs = self.observe()['records'][0]
        self.assertEqual(obs['kind'], 'text_mention')
        self.assertIsNone(obs['observed_at'])
        self.assertIsNone(obs['publication']['at'])
        self.assertEqual(obs['source_run_id'], doc['source_run_id'])
        self.assertLess(obs['collected_at'], obs['recorded_at'])
        self.assertEqual(doc['text'][obs['span']['start']:obs['span']['end']], obs['span']['original'])
        with self.f.storage._connection(readonly=True) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM cti_indicators').fetchone()[0], 0)

    def test_sentence_final_ip_is_a_candidate_without_reinterpreting_old_investigation_policy(self):
        from xti.domain.report_extraction import extract, extract_document, report_proposal, validate_report
        text = 'The report mentions 192.0.2.10.'
        self.assertEqual(extract(text), [])
        self.assertEqual(extract_document(text)[0]['value'], '192.0.2.10')
        for suffix in ('.5', '.example', 'abc', '..5'):
            self.assertFalse(extract_document('Address 192.0.2.10' + suffix))
        old = report_proposal(source='news', source_reference='https://source.example/report', source_record_id='legacy',
            source_run_id=str(uuid4()), text=text, observed_at=NOW.isoformat(), scope=[], source_sha256='a' * 64)
        self.assertEqual(validate_report(old)['candidates'], [])
        self.f.apply(replace(self.item, summary=text))
        record = self.capture()['record']
        self.assertEqual(record['document']['extraction_policy'], 'report-document-candidates-v2')
        self.assertEqual(self.observe()['total_count'], 1)

    def test_refresh_and_new_key_leave_revision_observation_and_page_snapshot_unchanged(self):
        old = self.capture()['record']
        obs = self.observe()
        self.f.apply(self.item)
        repeat = self.capture('another-request')
        self.assertEqual(repeat['action'], 'unchanged')
        self.assertEqual(repeat['record'], old)
        self.assertEqual(self.observe(), obs)
        self.assertEqual(len(self.repo.read()[old['id']]['history']), 1)

    def test_content_change_and_return_to_old_text_are_distinct_revisions(self):
        one = self.capture()['record']
        self.f.apply(replace(self.item, summary='No indicator in corrected summary'))
        two = self.capture('second')['record']
        self.assertEqual((two['id'], two['document_revision']), (one['id'], 2))
        self.assertEqual(self.show(one['id'], document_revision=1)['document'], one['document'])
        self.assertFalse(self.observe()['records'][0]['current_document'])
        self.f.apply(self.item)
        self.assertEqual(self.capture('third')['record']['document_revision'], 3)
        self.assertEqual(self.observe()['total_count'], 2)

    def test_same_request_replays_original_result_after_source_and_report_change(self):
        old = self.capture()
        self.f.apply(replace(self.item, title='Updated title'))
        self.capture('second')
        replay = self.capture()
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['record'], old['record'])
        with self.assertRaises(ReportError) as error:
            self.capture(identifier='different-source-id')
        self.assertEqual(error.exception.code, 'idempotency_conflict')

    def test_failed_source_refresh_does_not_delete_frozen_report(self):
        before = self.capture()['record']
        self.f.failure()
        self.assertEqual(self.capture('after-failure')['record'], before)
        self.assertEqual(self.show(before['id']), before)

    def test_publication_keeps_date_precision_unknown_timezone_and_raw_text(self):
        self.assertEqual(publication('2026-11-14'), {'at': None, 'date': '2026-11-14', 'precision': 'date', 'raw': '2026-11-14'})
        for raw in ('unknown', '2026-11-15T11:00:00', '2026-02-31'):
            self.assertEqual(publication(raw)['precision'], 'unknown')
        parsed = publication('Sat, 14 Nov 2026 12:00:00 +0300')
        self.assertEqual(parsed['at'], '2026-11-14T09:00:00+00:00')
        self.assertEqual(parsed['precision'], 'timestamp')

    def test_source_publication_and_truncation_are_preserved_separately_from_capture(self):
        self.item = replace(self.item, published_at='2026-11-14T09:00:00+00:00',
            published_raw='Sat, 14 Nov 2026 12:00:00 +0300', summary_truncated=True)
        self.f.apply(self.item)
        doc = self.capture()['record']['document']
        self.assertTrue(doc['summary_truncated'])
        self.assertEqual(doc['publication']['at'], self.item.published_at)
        self.assertNotEqual(doc['collected_at'], self.item.published_at)

    def test_human_link_belongs_to_exact_document_revision_and_withdrawal_keeps_history(self):
        rid = self.capture()['record']['id']
        target = self.entity()
        linked = self.link(rid, target)['record']
        self.assertEqual(linked['revision'], 2)
        withdrawn = self.link(rid, target, 2, 'withdraw', state='withdrawn')['record']
        self.assertEqual(withdrawn['links'][0]['state'], 'withdrawn')
        self.assertEqual(len(withdrawn['history']), 3)
        self.f.apply(replace(self.item, title='New source version'))
        current = self.capture('updated')['record']
        self.assertEqual(current['links'], [])
        self.assertEqual(self.show(rid, document_revision=1)['links'][0]['state'], 'withdrawn')

    def test_changed_revision_unknown_target_and_disallowed_entity_do_not_append(self):
        rid = self.capture()['record']['id']
        target = self.entity()
        self.link(rid, target)
        before = self.path.read_bytes()
        for identifier, revision in ((target, 1), (str(uuid4()), 2)):
            with self.assertRaises(ReportError):
                self.link(rid, identifier, revision, 'rejected-request')
        with self.assertRaises(ValidationError):
            self.link(rid, self.entity('report'), 2, 'disallowed-target')
        self.assertEqual(self.show(rid)['revision'], 2)
        self.assertEqual(len(self.repo.read()), 1)

    def test_old_document_link_can_be_withdrawn_after_a_new_source_version(self):
        rid = self.capture()['record']['id']
        target = self.entity()
        self.link(rid, target)
        self.f.apply(replace(self.item, title='A new document revision'))
        self.capture('new-document')
        current = self.link(rid, target, 3, 'old-link-withdraw', state='withdrawn', document_revision=1)['record']
        self.assertEqual(current['links'], [])
        self.assertEqual(current['history'][-1]['document_revision'], 1)
        self.assertEqual(self.show(rid, document_revision=1)['links'][0]['state'], 'withdrawn')

    def test_link_same_decision_noop_replay_and_all_allowed_entity_types(self):
        rid = self.capture()['record']['id']
        revision = 1
        for kind in ('threat-actor', 'campaign', 'malware'):
            target = self.entity(kind)
            first = self.link(rid, target, revision, 'link-' + kind)
            self.assertEqual(first['record']['links'][-1]['target']['type'], kind)
            revision += 1
            repeat = self.link(rid, target, revision, 'noop-' + kind)
            self.assertEqual(repeat['action'], 'unchanged')
            self.assertEqual(repeat['record'], first['record'])
            self.assertTrue(self.link(rid, target, revision - 1, 'link-' + kind)['replayed'])

    def test_unknown_report_version_and_missing_source_are_explicit_not_found(self):
        rid = self.capture()['record']['id']
        for request in (lambda: self.show(str(uuid4())), lambda: self.show(rid, document_revision=2),
                        lambda: self.capture('missing', 'missing')):
            with self.assertRaises(ReportError) as error:
                request()
            self.assertEqual(error.exception.code, 'not_found')

    def test_changed_page_guard_and_read_only_evidence(self):
        self.capture()
        first = self.service.execute('reports.list', limit=1)
        obs = self.observe(limit=1)
        before = self.path.read_bytes()
        self.observe(expected_snapshot=obs['snapshot_id'])
        self.service.execute('reports.list', expected_snapshot=first['snapshot_id'])
        self.assertEqual(self.path.read_bytes(), before)
        self.f.apply(replace(self.item, summary='192.0.2.10 changed source context'))
        self.capture('changed')
        for operation, options in (('reports.list', {'expected_snapshot': first['snapshot_id']}),
            ('observations.list', {'indicator_type': 'ipv4', 'value': '192.0.2.10', 'expected_snapshot': obs['snapshot_id']})):
            with self.assertRaises(ReportError) as error:
                self.service.execute(operation, **options)
            self.assertEqual(error.exception.code, 'snapshot_changed')

    def test_corrupt_payload_metadata_chain_and_deleted_tail_are_rejected(self):
        self.capture()
        original = self.path.read_bytes()
        for statement in ("UPDATE report_journal SET payload_json='{}'", "UPDATE report_journal SET operation='wrong'",
                          "UPDATE report_journal SET chain_sha256='bad'", 'DELETE FROM report_journal'):
            with self.subTest(statement=statement):
                self.path.write_bytes(original)
                with closing(sqlite3.connect(self.path)) as c, c:
                    c.execute(statement)
                with self.assertRaises(StorageError):
                    self.repo.read()
        self.path.write_bytes(original)

    def test_semantic_tampering_is_rejected_even_when_hash_chain_is_recomputed(self):
        from xti.domain.engine_jobs import canonical_json, digest
        from xti.domain.research import identity
        self.capture()
        with closing(sqlite3.connect(self.path)) as c, c:
            data = json.loads(c.execute('SELECT payload_json FROM report_journal').fetchone()[0])
            data['payload']['candidates'][0]['value'] = 'wrong.example'
            text = canonical_json(data)
            c.execute('UPDATE report_journal SET payload_json=?,payload_sha256=?,chain_sha256=?',
                      (text, digest(text), identity(None, digest(text))))
        with self.assertRaises(StorageError):
            self.repo.read()

    def test_capacity_read_and_write_budgets_fail_without_partial_mutation(self):
        self.capture()
        before = self.path.read_bytes()
        with patch('xti.adapters.sqlite_reports.MAX_ENTRIES', 1):
            with self.assertRaises(ValidationError):
                self.capture('over-limit')
        with patch('xti.adapters.sqlite_reports.MAX_BYTES', 1):
            with self.assertRaises(StorageError):
                self.repo.read()
        self.assertEqual(before, self.path.read_bytes())

    def test_source_corruption_fails_capture_but_frozen_document_remains_readable(self):
        old = self.capture()['record']
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute("UPDATE news_articles SET state_sha256=?", ('b' * 64,))
        with self.assertRaises(StorageError):
            self.capture('bad-source')
        self.assertEqual(self.show(old['id']), old)

    def test_schema76_requires_explicit_backed_up_migration_and_preserves_sources(self):
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute('DROP TABLE report_journal')
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(c)
            c.execute('PRAGMA user_version=76')
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.repo.read()
        self.assertEqual(self.path.read_bytes(), before)
        result = self.f.storage.migrate()
        self.assertEqual((result['from_version'], result['to_version']), (76, 80))
        with closing(sqlite3.connect(result['backup'])) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 76)
            self.assertFalse(c.execute("SELECT 1 FROM sqlite_schema WHERE name='report_journal'").fetchone())
        self.assertEqual(self.capture()['record']['document']['title'], self.item.title)
        self.assertFalse(self.f.storage.migrate()['changed'])

    def test_two_writers_capture_one_document_with_separate_idempotency_receipts(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.capture, ('writer-one', 'writer-two')))
        self.assertEqual({r['action'] for r in results}, {'changed', 'unchanged'})
        self.assertEqual(results[0]['record'], results[1]['record'])
        self.assertEqual(self.observe()['total_count'], 1)

    def test_response_capacity_is_rejected_before_a_successful_write_can_commit(self):
        before = self.path.read_bytes()
        with patch('xti.domain.reports.MAX_REPORT_BYTES', 256):
            with self.assertRaises(ValidationError):
                self.capture()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.service.execute('reports.list')['total_count'], 0)

    def test_report_and_ioc_observations_use_one_sqlite_snapshot_during_concurrent_write(self):
        from xti.adapters.sqlite_reports import read_reports
        from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
        from xti.application.cti_indicators import CtiIndicatorService
        self.capture()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        def after_report_read(connection):
            result = read_reports(connection)
            CtiIndicatorService(SQLiteCtiIndicatorRepository(self.path), clock=lambda: NOW).add(
                'ipv4', '192.0.2.10', source_name='concurrent', source_reference='https://source.example/new',
                confidence=50, description='Concurrent source assertion')
            return result
        with patch('xti.adapters.sqlite_reports.read_reports', side_effect=after_report_read):
            self.assertEqual(self.observe()['total_count'], 1)
        self.assertEqual(self.observe()['total_count'], 2)

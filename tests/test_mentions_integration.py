"""Persisted company search evidence joins local search, watches and engine reads."""

from contextlib import closing
from dataclasses import asdict, fields, make_dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.engine_records import SQLiteEngineRecordRepository
from xti.adapters.source_readiness import SQLiteSourceReadinessRepository
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
from xti.adapters.sqlite_global_search import SQLiteGlobalSearchRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_mentions import SQLiteMentionRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.global_saved_searches import GlobalSavedSearchService
from xti.application.global_search import GlobalSearchService
from xti.application.sources import SourceCatalogService
from xti.domain.engine import EngineContractError, parse_record_reference, reference_for_result
from xti.domain.global_search import GLOBAL_SEARCH_KINDS
from xti.domain.global_saved_searches import make_match, mention_semantic
from xti.domain.mentions import (
    MentionHit, MentionRequest, MentionResponse, MentionTarget, build_query, company_target, result_id,
)


NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
PRE_MENTION_KINDS = (
    'domain', 'finding', 'social', 'ransomware', 'public-notice', 'case',
    'supplier', 'organization', 'cti', 'indicator', 'news',
)


def request(*, name='Example Company', domains=('example.com',), kind='company', identifier=None):
    target = company_target(name, domains) if kind == 'company' else MentionTarget(kind, identifier or str(uuid4()), name, domains)
    return MentionRequest(target, 'general', 10)


def hit(**changes):
    return replace(MentionHit('https://publisher.example/article', 'Example Company announcement',
        'A report about example.com.', '2026-11-14', 0.8), **changes)


class MentionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'data' / 'xti.db'
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteMentionRepository(self.path)
        self.now = NOW
        self.search = GlobalSearchService(SQLiteGlobalSearchRepository(self.path), clock=lambda: self.now)
        self.watches = GlobalSavedSearchService(SQLiteGlobalSavedSearchRepository(self.path),
            LocalExecutionLock(self.path), clock=lambda: self.now)
        self.records = SQLiteEngineRecordRepository(self.path)
        self.readiness = SQLiteSourceReadinessRepository(self.path, self.root / 'project')
        self.addCleanup(patch.stopall)
        patch('socket.socket.connect', side_effect=AssertionError('Read must not use network')).start()
        patch('socket.getaddrinfo', side_effect=AssertionError('Read must not use DNS')).start()

    def tick(self):
        self.now += timedelta(seconds=1)
        return self.now.isoformat()

    def save(self, *hits, selected=None):
        selected = selected or request()
        at = self.tick()
        return self.repository.apply(selected, MentionResponse(build_query(selected.target),
            'provider-request', tuple(hits), 1), started_at=at, finished_at=at)

    def record_failure(self, *, selected=None):
        at = self.tick()
        return self.repository.record_failure(selected or request(), started_at=at,
            finished_at=at, error='Tavily sorgusu süre sınırına ulaştı.')

    def watch_run(self, identifier):
        self.tick()
        return self.watches.run(identifier)

    def test_empty_catalog_has_explicit_scope_and_no_credentials_or_network_reads(self):
        before = self.path.read_bytes()
        with patch.dict('os.environ', {'TAVILY_API_KEY': 'private-key-not-for-output'}):
            report = self.search.search('Example')
            self.assertEqual(report.kinds, GLOBAL_SEARCH_KINDS)
            coverage = next(item for item in report.coverage if item.kind == 'mention')
            self.assertEqual((coverage.source, coverage.examined_count, coverage.latest_run_id), ('tavily', 0, None))
            status = next(item for item in self.readiness.snapshot().sources if item.identifier == 'mentions:tavily')
            self.assertEqual((status.installation, status.latest_status, status.record_count), ('builtin', 'never', None))
            self.assertNotIn('private-key-not-for-output', str((report, status)))
        self.assertEqual(self.path.read_bytes(), before)

    def test_search_keeps_target_identity_and_paginates_without_losing_totals(self):
        company = request()
        supplier = request(kind='supplier')
        self.save(hit(), selected=company)
        self.save(hit(), selected=supplier)
        before = self.path.read_bytes()
        page = self.search.search('example.com', kinds=('mention',), limit=1)
        self.assertEqual((page.total_match_count, len(page.results), page.has_more), (2, 1, True))
        rows = self.search.search('example.com', kinds=('mention',)).results
        self.assertEqual(len({item.record_id for item in rows}), 2)
        self.assertTrue(all(item.status == 'search_candidate' and item.source == 'tavily' for item in rows))
        targets = {self.records.get(reference_for_result(item))['record']['request']['target']['kind'] for item in rows}
        self.assertTrue(all(self.records.get(reference_for_result(item))['record']['query'] == build_query(company.target)
                            for item in rows))
        self.assertEqual(targets, {'company', 'supplier'})
        self.assertEqual(self.path.read_bytes(), before)

    def test_engine_record_namespace_and_query_specific_source_history_are_frozen(self):
        selected = request(kind='organization')
        first = self.save(hit(), selected=selected)
        self.save(hit(title='A different company announcement'), selected=request(name='Another Company', domains=()))
        failure = self.record_failure(selected=selected)
        row = next(item for item in self.search.search('example.com', kinds=('mention',)).results
                   if item.record_id == result_id(selected, hit().url))
        reference = parse_record_reference(reference_for_result(row).to_dict())
        before = self.path.read_bytes()
        detail = self.records.get(reference)
        self.assertEqual(detail['record']['id'], row.record_id)
        self.assertEqual(detail['record']['request']['target']['id'], selected.target.id)
        self.assertEqual(detail['record']['hit']['url'], hit().url)
        self.assertEqual(detail['provenance']['latest_attempt']['id'], failure.id)
        self.assertEqual(detail['provenance']['latest_success']['id'], first.id)
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(EngineContractError):
            parse_record_reference({**reference.to_dict(), 'namespace': 'cisa'})
        with self.assertRaises(EngineContractError) as error:
            self.records.get(replace(reference, namespace='another-provider'))
        self.assertEqual(error.exception.code, 'not_found')

    def test_watch_ignores_ranking_refresh_absence_and_failure_but_reports_content_change(self):
        original = hit()
        self.save(original)
        watch = self.watches.add('Company content', 'example.com', kinds=('mention',)).saved_search
        baseline = self.watch_run(watch.id)
        self.assertIsNone(baseline.notification_id)
        self.save(replace(original, score=0.3))
        repeated = self.watch_run(watch.id)
        self.assertEqual((repeated.run.added_count, repeated.run.updated_count, repeated.run.unchanged_count), (0, 0, 1))
        self.assertIsNone(repeated.notification_id)
        self.save()
        self.record_failure()
        absent = self.watch_run(watch.id)
        self.assertEqual((absent.run.unchanged_count, absent.run.removed_count), (1, 0))
        self.assertIsNone(absent.notification_id)
        self.save(replace(original, summary='Updated statement about example.com.'))
        changed = self.watch_run(watch.id)
        self.assertEqual((changed.run.added_count, changed.run.updated_count), (0, 1))
        self.assertIsNotNone(changed.notification_id)
        self.save(replace(original, title='A later title'))
        self.assertEqual(self.watches.show_run(changed.run.id), changed)
        notice = SQLiteInboxRepository(self.path).get(changed.notification_id)
        self.assertEqual(notice.global_search_change.run.id, changed.run.id)

    def test_old_eleven_kind_watch_does_not_silently_expand(self):
        SQLiteAssetRepository(self.path).add('example.com')
        watch = self.watches.add('Before content search', 'example', kinds=PRE_MENTION_KINDS).saved_search
        baseline = self.watch_run(watch.id)
        self.save(hit())
        repeated = self.watch_run(watch.id)
        self.assertEqual(repeated.saved_search.kinds, PRE_MENTION_KINDS)
        self.assertEqual((repeated.run.added_count, repeated.run.updated_count), (0, 0))
        self.assertIsNone(repeated.notification_id)
        self.assertEqual(self.watches.show_run(baseline.run.id), baseline)
        self.tick()
        widened = self.watches.add('Before content search', 'example').saved_search
        self.assertEqual(widened.kinds, GLOBAL_SEARCH_KINDS)
        self.assertEqual(widened.revision, watch.revision + 1)
        changed_scope = self.watch_run(watch.id)
        self.assertIsNone(changed_scope.run.previous_run_id)
        self.assertIsNone(changed_scope.notification_id)
        self.assertEqual({item.after.result.kind for item in changed_scope.items}, {'domain', 'mention'})

    def test_watch_semantics_reject_false_identity_context_and_matching_reason(self):
        self.save(hit())
        stored = self.repository.catalog().records[0]
        row = self.search.search('example.com', kinds=('mention',)).results[0]
        reference = reference_for_result(row).to_dict()
        identity = tuple(value for key in sorted(reference) for value in (key, reference[key]))
        semantic = mention_semantic(stored)
        make_match(row, identity, semantic)
        for altered, result in (
            ({**semantic, 'matched_terms': ['A different company']}, row),
            ({**semantic, 'match_fields': []}, row),
            ({**semantic, 'source_key': 'cisa'}, row),
            ({**semantic, 'hit': {**semantic['hit'], 'score': 0.8}}, row),
            ({**semantic, 'record_id': 'a' * 64}, row),
            ({**semantic, 'request': {**semantic['request'], 'topic': 'news'}}, row),
            (semantic, replace(row, status='confirmed_breach')),
            (semantic, replace(row, display_value='A forged title')),
        ):
            with self.subTest(semantic=altered, result=result), self.assertRaises(ValueError):
                make_match(result, identity, altered)

    def test_readiness_distinguishes_empty_success_from_failed_search_and_retains_previous_records(self):
        empty = self.save()
        status = next(item for item in self.readiness.snapshot().sources if item.identifier == 'mentions:tavily')
        self.assertEqual((status.latest_status, status.record_count, status.last_success_at), ('complete', 0, empty.finished_at))
        success = self.save(hit())
        failure = self.record_failure()
        SQLiteAssetRepository(self.path).add('unrelated.example')
        before = self.path.read_bytes()
        status = next(item for item in self.readiness.snapshot(domain='unrelated.example').sources if item.identifier == 'mentions:tavily')
        self.assertEqual((status.latest_status, status.record_count), ('failed', 1))
        self.assertEqual(status.last_success_at, success.finished_at)
        self.assertIn('domain filtresinden bağımsız', status.scope)
        coverage = self.search.search('example', kinds=('mention',)).coverage[0]
        self.assertEqual((coverage.latest_run_id, coverage.latest_success_run_id), (failure.id, success.id))
        self.assertEqual(self.path.read_bytes(), before)

    def test_catalog_explains_free_credits_key_requirement_and_bounded_source(self):
        item = next(item for item in SourceCatalogService().list() if item.identifier == 'mentions:tavily')
        self.assertTrue(item.credential_required)
        self.assertFalse(item.paid_dependency)
        self.assertFalse(item.contacts_monitored_target)
        self.assertIn('Ücretsiz', item.access)
        self.assertIn('mentions search --supplier TEDARIKCI_KIMLIGI', item.commands)
        self.assertTrue(any('20' in note for note in item.limits))

    def test_engine_does_not_publish_added_internal_dataclass_fields(self):
        self.save(hit())
        catalog = self.repository.catalog()
        original = catalog.records[0].hit
        extended_type = make_dataclass('MentionHit', [(field.name, field.type) for field in fields(original)] + [('internal_secret', str)])
        extended_type.__module__ = 'xti.domain.mentions'
        extended = extended_type(**asdict(original), internal_secret='never-export-me')
        modified = replace(catalog, records=(replace(catalog.records[0], hit=extended),))
        row = self.search.search('example', kinds=('mention',)).results[0]
        with patch('xti.adapters.engine_records.read_mentions_catalog', return_value=modified):
            detail = self.records.get(reference_for_result(row))
        self.assertNotIn('internal_secret', detail['record']['hit'])
        self.assertNotIn('never-export-me', str(detail))

    def test_corrupt_source_evidence_fails_search_readiness_and_record_reads(self):
        self.save(hit())
        reference = reference_for_result(self.search.search('example', kinds=('mention',)).results[0])
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE mentions_runs SET payload_json='{}'")
            connection.commit()
        before = self.path.read_bytes()
        for read in (lambda: self.search.search('not-matching', kinds=('mention',)),
                     self.readiness.snapshot, lambda: self.records.get(reference)):
            with self.subTest(read=read), self.assertRaises(StorageError):
                read()
        self.assertEqual(self.path.read_bytes(), before)

    def test_backup_restore_preserves_content_watch_history_and_notification(self):
        self.save(hit())
        watch = self.watches.add('Restored content watch', 'example.com', kinds=('mention',)).saved_search
        self.watch_run(watch.id)
        self.save(hit(summary='A changed report about example.com.'))
        changed = self.watch_run(watch.id)
        inbox = SQLiteInboxRepository(self.path)
        inbox.mark((changed.notification_id,), True, self.tick())
        notification = inbox.get(changed.notification_id)
        catalog = self.repository.catalog()
        backup, restored = self.root / 'backup.db', self.root / 'restored' / 'xti.db'
        SQLiteAssetRepository(self.path).backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteMentionRepository(restored).catalog(), catalog)
        self.assertEqual(SQLiteInboxRepository(restored).get(changed.notification_id), notification)
        recovered = GlobalSavedSearchService(SQLiteGlobalSavedSearchRepository(restored),
            LocalExecutionLock(restored), clock=lambda: self.now)
        self.assertEqual(recovered.show_run(changed.run.id), changed)
        self.tick()
        repeated = recovered.run(watch.id)
        self.assertEqual((repeated.run.added_count, repeated.run.updated_count, repeated.run.unchanged_count), (0, 0, 1))
        self.assertIsNone(repeated.notification_id)


if __name__ == '__main__':
    unittest.main()

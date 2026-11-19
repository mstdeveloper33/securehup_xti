"""Company review, frozen cases and repeatable social change delivery acceptance."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout, redirect_stderr
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository
from xti.adapters.sqlite_social_tracking import SQLiteSocialTrackingRepository, case_snapshot
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.application.cases import CaseService, CaseEvidenceResolverService
from xti.application.social_discovery import SocialDiscoveryService
from xti.application.social_tracking import SocialTrackingService
from xti.application.social_tracking_monitor import monitor
from xti.domain.assets import ValidationError
from xti.domain.engine import EngineContractError, parse_engine_request
from xti.domain.platform_engine import parse_platform_request
from xti.domain.social_discovery import Page, SocialDiscoveryError
from xti.domain.social_tracking import case_id, compare, validate_case_snapshot, parameters
from xti.interfaces.entrypoint import main
from xti.interfaces.company_review import make_company_review_service
from xti.interfaces.social_tracking import review_lines
from tests.test_social_discovery import AT, IG, GH, SCOPE, Pages, Sources, page, profile
from tests.case_evidence_v82_fixture import case_evidence_layout_v82


class TrackingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.path = self.root / 'data' / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path); self.storage.initialize()
        self.at = AT; self.mode = 'normal'; self.pages = Pages(); self.sources = Sources()
        original = self.pages.fetch
        def fetch(url, **options):
            if url == IG and self.mode == 'timeout': return Page(url, url, None, self.at, error='timeout')
            if url == IG and self.mode == 'absent': return page(url, 'Not found', 404)
            if url == IG and self.mode == 'changed': return replace(profile(), description='Updated company description')
            if url == 'https://acme.example/' and self.mode == 'new':
                return page(url, f'<a href="{IG}">Main</a><a href="https://instagram.com/acme_support">Support</a>')
            if url == 'https://instagram.com/acme_support': return profile(url, 'acme_support')
            return original(url, **options)
        self.pages.fetch = fetch
        self.discovery_repo = SQLiteSocialDiscoveryRepository(self.path)
        self.discovery = SocialDiscoveryService(self.discovery_repo, pages=self.pages, sources=self.sources, clock=lambda: self.at)
        self.seed = self.discovery.execute('brand.discovery.run', **SCOPE, idempotency_key='seed')['record']
        self.repo = SQLiteSocialTrackingRepository(self.path)
        self.service = SocialTrackingService(self.repo, discovery=self.discovery, clock=lambda: self.at)
        self.inbox = SQLiteInboxRepository(self.path)
        self.cases = CaseService(SQLiteCaseRepository(self.path),
            CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.path)), clock=lambda: datetime.fromisoformat(self.at))

    def later(self, seconds=3600):
        self.at = (datetime.fromisoformat(self.at) + timedelta(seconds=seconds)).isoformat()

    def add(self, **options):
        return self.service.execute('brand.tracking.add', **{'discovery_id': self.seed['id'], 'name': 'Acme social',
            'interval_seconds': 300, 'idempotency_key': 'watch', **options})['record']

    def run_watch(self, watch, key='cycle', **options):
        return self.service.execute('brand.tracking.run', identifier=watch['id'], idempotency_key=key, **options)

    def decide(self, **options):
        return self.service.execute('brand.review.decide', **{'discovery_id': self.seed['id'], 'url': IG,
            'decision': 'official', 'reason': 'Confirmed by company representative', 'expected_revision': 0,
            'idempotency_key': 'review', **options})

    def test_company_review_contains_exact_profiles_and_human_decision_without_mutating_discovery(self):
        before = self.discovery_repo.show(self.seed['id'])
        decided = self.decide()['record']
        view = self.service.execute('brand.review.show', discovery_id=self.seed['id'], url=IG)['record']
        self.assertEqual(view['review'], decided); self.assertEqual(view['revision'], 1)
        self.assertEqual(view['profile']['state'], 'found'); self.assertEqual(view['provider_evidence'], [])
        self.assertEqual(self.discovery_repo.show(self.seed['id']), before)
        company = make_company_review_service(self.path).show()
        self.assertIn(IG, [r['profile']['url'] for r in company['social']['records']])
        self.assertIn('Resmî hesap', '\n'.join(review_lines(view)))

    def test_review_idempotency_revision_scope_and_history(self):
        first = self.decide(); before = self.path.read_bytes()
        self.assertTrue(self.decide()['replayed']); self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(SocialDiscoveryError) as conflict: self.decide(decision='unrelated')
        self.assertEqual(conflict.exception.code, 'idempotency_conflict')
        with self.assertRaises(SocialDiscoveryError) as revision: self.decide(idempotency_key='second')
        self.assertEqual(revision.exception.code, 'revision_conflict')
        self.decide(idempotency_key='second', expected_revision=1, decision='uncertain')
        self.assertEqual(self.service.execute('brand.review.show', discovery_id=self.seed['id'], url=IG)['record']['revision'], 2)
        with self.assertRaises(SocialDiscoveryError): self.decide(idempotency_key='bad', url='https://instagram.com/not_selected')

    def test_latest_company_discovery_keeps_old_decision_as_previous_evidence(self):
        self.decide(); self.later()
        latest = self.discovery.execute('brand.discovery.run', **SCOPE, idempotency_key='next')['record']
        view = self.service.execute('brand.review.list', limit=1)['records'][0]
        rows = self.service.execute('brand.review.list')['records']
        instagram = next(r for r in rows if r['profile']['url'] == IG)
        self.assertEqual(instagram['discovery_id'], latest['id'])
        self.assertFalse(instagram['review_matches_discovery'])
        self.assertEqual(instagram['review']['discovery_id'], self.seed['id'])
        self.assertEqual(self.service.execute('brand.review.list', domain='other.example')['records'], [])

    def test_first_run_silent_then_metadata_change_delivered_once_to_shared_inbox(self):
        watch = self.add(); first = self.run_watch(watch)['record']
        self.assertTrue(first['baseline']); self.assertEqual(first['changes'], [])
        self.later(); self.mode = 'changed'
        result = self.run_watch(watch, 'second'); run = result['record']
        self.assertFalse(run['baseline']); self.assertEqual([c['kind'] for c in run['changes']], ['profile_changed'])
        inbox = self.inbox.list(status='unread', limit=20, before=None)
        self.assertEqual((inbox.total_count, inbox.unread_count), (1, 1))
        notice = inbox.items[0].notification
        self.assertEqual(self.inbox.get(notice.id).social_change['change'], run['changes'][0])
        self.assertEqual(self.service.execute('brand.change.show', identifier=notice.id)['record']['run_id'], run['id'])
        with patch.object(self.discovery, '_collect', side_effect=AssertionError('no repeat network')):
            self.assertTrue(self.run_watch(watch, 'second')['replayed'])
        self.assertEqual(self.inbox.list(status='all', limit=20, before=None).total_count, 1)
        self.inbox.mark((notice.id,), read=True, now=self.at)
        self.assertEqual(self.inbox.list(status='read', limit=20, before=None).unread_count, 0)

    def test_timeout_and_missing_coverage_never_mean_account_removed_or_reset_baseline(self):
        watch = self.add(); self.run_watch(watch)
        self.later(); self.mode = 'timeout'
        unavailable = self.run_watch(watch, 'timeout')['record']
        self.assertEqual(unavailable['changes'], []); self.assertGreater(unavailable['unchecked_count'], 0)
        self.later(); self.mode = 'normal'
        self.assertEqual(self.run_watch(watch, 'recover')['record']['changes'], [])
        self.assertEqual(self.inbox.list(status='all', limit=20, before=None).total_count, 0)

    def test_direct_404_is_reported_as_unavailable_not_deleted_and_repeats_are_quiet(self):
        watch = self.add(); self.run_watch(watch)
        self.later(); self.mode = 'absent'
        changes = self.run_watch(watch, 'absent')['record']['changes']
        self.assertEqual([c['kind'] for c in changes], ['profile_unavailable'])
        self.later(); self.assertEqual(self.run_watch(watch, 'still-absent')['record']['changes'], [])

    def test_new_source_link_generates_new_profile_notice(self):
        watch = self.add(); self.run_watch(watch)
        self.later(); self.mode = 'new'
        changes = self.run_watch(watch, 'new')['record']['changes']
        self.assertEqual([(r['kind'], r['url']) for r in changes], [('new_profile', 'https://instagram.com/acme_support')])

    def test_due_time_pause_resume_and_force_are_explicit(self):
        watch = self.add(); self.run_watch(watch)
        with self.assertRaises(SocialDiscoveryError) as error: self.run_watch(watch, 'early')
        self.assertEqual(error.exception.code, 'not_due')
        self.run_watch(watch, 'manual', force=True)
        paused = self.service.execute('brand.tracking.set', identifier=watch['id'], enabled=False,
            expected_revision=1, idempotency_key='pause')['record']
        self.assertFalse(paused['enabled'])
        with self.assertRaises(SocialDiscoveryError): self.run_watch(watch, 'paused', force=True)
        self.service.execute('brand.tracking.set', identifier=watch['id'], enabled=True, expected_revision=2, idempotency_key='resume')
        self.later(); self.assertEqual(self.run_watch(watch, 'resumed')['record']['watch_id'], watch['id'])

    def test_committed_discovery_recovers_after_process_interruption_without_network_repeat(self):
        watch = self.add(); original = self.discovery_repo.finish
        def crash(*args, **kwargs): original(*args, **kwargs); raise KeyboardInterrupt()
        with patch.object(self.discovery_repo, 'finish', side_effect=crash), self.assertRaises(KeyboardInterrupt):
            self.run_watch(watch)
        with patch.object(self.discovery, '_collect', side_effect=AssertionError('no repeated collection')):
            recovered = self.run_watch(watch)['record']
        self.assertEqual(recovered['status'], 'partial'); self.assertTrue(recovered['baseline'])
        self.assertEqual(self.service.execute('brand.tracking.run.show', identifier=recovered['id'])['record'], recovered)

    def test_interrupted_uncommitted_discovery_has_explicit_outcome_and_no_automatic_repeat(self):
        watch = self.add()
        with patch.object(self.discovery, '_collect', side_effect=KeyboardInterrupt()), self.assertRaises(KeyboardInterrupt):
            self.run_watch(watch)
        with self.assertRaises(SocialDiscoveryError) as busy: self.run_watch(watch, 'another')
        self.assertEqual(busy.exception.code, 'busy')
        with patch.object(self.discovery, '_collect', side_effect=AssertionError('no repeat')):
            self.assertEqual(self.run_watch(watch)['record']['status'], 'interrupted')
        self.later(); self.assertTrue(self.run_watch(watch, 'new-cycle')['record']['baseline'])

    def test_two_concurrent_writers_share_one_run_for_same_key(self):
        watch = self.add()
        def reserve(_):
            return self.repo.write('brand.tracking.run', {'identifier': watch['id'], 'force': False, 'idempotency_key': 'parallel'}, self.at)
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(reserve, range(2)))
        self.assertEqual(results[0]['record'], results[1]['record'])
        self.assertEqual(sorted(r['replayed'] for r in results), [False, True])

    def test_frozen_case_keeps_original_discovery_and_decision_after_new_review(self):
        self.decide()
        case = self.cases.create('Social investigation', summary='Investigate the selected company profile', priority='medium', reason='Analyst selection').case
        link = self.cases.add_evidence(case.id, 'social_discovery', case_id(self.seed['id'], IG), reason='Preserve page evidence').evidence
        original = link.snapshot_json
        self.later(); self.decide(expected_revision=1, decision='uncertain', idempotency_key='change-review')
        self.assertEqual(self.cases.evidence_show(case.id, link.id).snapshot_json, original)
        payload = json.loads(original); self.assertEqual(payload['review_history'][-1]['decision'], 'official')
        forged = deepcopy(payload); forged['profile']['state'] = 'not_found'
        with self.assertRaises(ValidationError): validate_case_snapshot(forged)
        self.assertEqual(self.cases.add_evidence(case.id, 'social_discovery', case_id(self.seed['id'], IG), reason='Explicit refresh').action, 'refreshed')

    def test_other_workspace_cannot_read_review_watch_or_resolve_case_evidence(self):
        other = self.root / 'other' / 'xti.db'; SQLiteAssetRepository(other).initialize()
        service = SocialTrackingService(SQLiteSocialTrackingRepository(other))
        watch = self.add()
        for op, kwargs in [('brand.review.show', {'discovery_id': self.seed['id'], 'url': IG}),
                           ('brand.tracking.show', {'identifier': watch['id']})]:
            with self.subTest(operation=op), self.assertRaises(SocialDiscoveryError): service.execute(op, **kwargs)
        with self.assertRaises(SocialDiscoveryError): SQLiteCaseEvidenceSourceRepository(other).resolve('social_discovery', case_id(self.seed['id'], IG))

    def test_deleted_journal_tail_or_changed_source_fails_closed(self):
        self.decide()
        with self.storage._connection() as c, c: c.execute('DELETE FROM social_tracking_journal')
        with self.assertRaises(StorageError): self.service.execute('brand.review.list')

    def test_lost_notification_is_not_silently_regenerated(self):
        watch = self.add(); self.run_watch(watch); self.later(); self.mode = 'changed'; self.run_watch(watch, 'next')
        with self.storage._connection() as c, c: c.execute('DELETE FROM social_tracking_notifications')
        with self.assertRaises(StorageError): self.inbox.list(status='all', limit=20, before=None)
        with self.assertRaises(StorageError): self.run_watch(watch, 'next')

    def test_real_cli_and_engine_return_same_stored_review_without_network(self):
        self.decide()
        out, err = StringIO(), StringIO()
        with patch('socket.create_connection', side_effect=AssertionError('no network')), redirect_stdout(out), redirect_stderr(err):
            code = main(['--data-dir', str(self.path.parent), '--json', 'brand', 'review-show', self.seed['id'], '--url', IG])
        self.assertEqual((code, err.getvalue()), (0, ''))
        expected = json.loads(out.getvalue())['data']
        out, err = StringIO(), StringIO()
        request = {'contract_version': 1, 'request_id': 'read', 'operation': 'brand.review.show',
                   'parameters': {'discovery_id': self.seed['id'], 'url': IG}}
        with patch('sys.stdin', StringIO(json.dumps(request))), redirect_stdout(out), redirect_stderr(err):
            code = main(['--data-dir', str(self.path.parent), 'engine'])
        self.assertEqual((code, err.getvalue()), (0, '')); self.assertEqual(json.loads(out.getvalue())['data'], expected)

    def test_cli_case_add_show_and_inbox_show_render_complete_social_evidence(self):
        case = self.cases.create('Social investigation', summary='Investigate the selected company profile', priority='medium', reason='Analyst selection').case
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(['--data-dir', str(self.path.parent), '--json', 'cases', 'evidence-add', case.id,
                         '--type', 'social_discovery', '--evidence-id', case_id(self.seed['id'], IG), '--reason', 'Preserve selected evidence'])
        self.assertEqual((code, err.getvalue()), (0, ''), out.getvalue())
        link = json.loads(out.getvalue())['data']['evidence']['id']
        out = StringIO()
        with redirect_stdout(out):
            code = main(['--data-dir', str(self.path.parent), 'cases', 'evidence-show', case.id, link])
        self.assertEqual(code, 0); self.assertIn(IG, out.getvalue())
        watch = self.add(); self.run_watch(watch); self.later(); self.mode = 'changed'; self.run_watch(watch, 'changed')
        notice = self.inbox.list(status='unread', limit=20, before=None).items[0].notification
        out = StringIO()
        with redirect_stdout(out):
            code = main(['--data-dir', str(self.path.parent), 'inbox', 'show', notice.id])
        self.assertEqual(code, 0); self.assertIn('profile_changed', out.getvalue()); self.assertIn('social_discovery', out.getvalue())

    def test_review_pagination_is_explicit_in_company_coverage(self):
        service = make_company_review_service(self.path)
        first = service.show(social_limit=1)
        self.assertTrue(first['social']['has_more'])
        self.assertFalse(first['coverage_complete']); self.assertIn('company_social_window', first['limitations'])
        second = service.show(social_offset=1, social_limit=1)
        self.assertNotEqual(first['social']['records'][0]['profile']['url'], second['social']['records'][0]['profile']['url'])

    def test_source_receipt_corruption_stops_review_and_new_network(self):
        watch = self.add()
        with self.storage._connection() as c, c:
            c.execute('UPDATE social_discovery_runs SET report_sha256=? WHERE id=?', ('0' * 64, self.seed['id']))
        with patch.object(self.discovery, '_collect', side_effect=AssertionError('no network')), self.assertRaises(StorageError): self.run_watch(watch)

    def test_missing_profile_in_partial_collection_preserves_last_observation(self):
        known, _, _ = compare({}, self.seed, baseline=True, run_id=str(uuid4()))
        reduced = deepcopy(self.seed); reduced['report']['profiles'] = []
        after, changes, unchecked = compare(known, reduced, baseline=False, run_id=str(uuid4()))
        self.assertEqual(after, known); self.assertEqual(changes, []); self.assertEqual(unchecked, len(known))

    def test_saved_paid_seed_never_turns_recurring_paid_search_on(self):
        paid = self.discovery.execute('brand.discovery.run', **SCOPE, web_search=True, idempotency_key='paid-seed')['record']
        watch = self.add(discovery_id=paid['id'])
        self.assertFalse(watch['scope']['web_search'])
        with patch.object(self.sources, 'search', side_effect=AssertionError('No paid recurring source')):
            self.run_watch(watch)


class EnrichmentWorkflowTests(unittest.TestCase):
    def test_provider_evidence_remains_separate_and_case_freezes_pending_state(self):
        from tests.test_social_enrichment import EnrichmentTests, URL
        from tests.test_brightdata_social import AT as PROVIDER_AT
        f = EnrichmentTests(); f.setUp(); self.addCleanup(f.doCleanups)
        tracking = SocialTrackingService(SQLiteSocialTrackingRepository(f.path), clock=lambda: PROVIDER_AT)
        pending = f.run_enrichment()['record']
        view = tracking.execute('brand.review.show', discovery_id=f.discovery['id'], url=URL)['record']
        self.assertEqual(view['profile']['state'], 'candidate'); self.assertEqual(view['provider_evidence'][0]['status'], 'pending')
        with f.storage._connection(readonly=True) as c:
            frozen = case_snapshot(c, f.path, case_id(f.discovery['id'], URL))
        f.service.execute('brand.enrichment.refresh', identifier=pending['id'])
        current = tracking.execute('brand.review.show', discovery_id=f.discovery['id'], url=URL)['record']
        self.assertEqual(current['profile']['state'], 'candidate')
        self.assertEqual(current['provider_evidence'][0]['result']['state'], 'provider_supported')
        self.assertIsNone(current['review'])
        validate_case_snapshot(json.loads(frozen.snapshot_json))
        self.assertEqual(json.loads(frozen.snapshot_json)['provider_evidence'][0]['status'], 'pending')
        with f.storage._connection(readonly=True) as c:
            fresh = case_snapshot(c, f.path, case_id(f.discovery['id'], URL))
        validate_case_snapshot(json.loads(fresh.snapshot_json))
        self.assertNotEqual(frozen.snapshot_sha256, fresh.snapshot_sha256)


class PlatformWorkflowTests(unittest.TestCase):
    def test_company_json_review_tracking_fence_replay_and_foreign_record(self):
        from tests.test_platform_engine import PlatformEngineTests
        f = PlatformEngineTests(); f.setUp(); self.addCleanup(f.doCleanups)
        # The recording service uses UTC, and all network adapters below are controlled fixtures.
        from datetime import timezone
        discovery = SocialDiscoveryService(SQLiteSocialDiscoveryRepository(f.context.database), pages=Pages(), sources=Sources(),
                                            clock=lambda: datetime.now(timezone.utc).isoformat())
        seed = discovery.execute('brand.discovery.run', **SCOPE, idempotency_key='seed')['record']
        scope = {'expected_workspace_id': f.context.workspace_id, 'idempotency_key': 'save',
                 'discovery_id': seed['id'], 'name': 'Company social'}
        code, saved = f.invoke(request=f.request('brand.tracking.add', scope))
        self.assertEqual(code, 0, saved); watch = saved['data']['record']
        self.assertTrue(f.invoke(request=f.request('brand.tracking.add', scope))[1]['data']['replayed'])
        self.assertEqual(f.invoke(request=f.request('brand.review.list'))[0], 0)
        bad = {**scope, 'expected_workspace_id': str(uuid4()), 'idempotency_key': 'bad'}
        self.assertEqual(f.invoke(request=f.request('brand.tracking.add', bad))[1]['error']['code'], 'scope_mismatch')
        with patch('xti.interfaces.social_discovery.make_social_discovery_service', return_value=discovery):
            request = {'identifier': watch['id'], 'expected_workspace_id': f.context.workspace_id, 'idempotency_key': 'run'}
            code, result = f.invoke(request=f.request('brand.tracking.run', request))
        self.assertEqual(code, 0, result)
        self.assertEqual(result['data']['record']['status'], 'partial')
        request = {'discovery_id': seed['id'], 'url': IG, 'decision': 'uncertain', 'reason': 'Analyst review',
                   'expected_revision': 0, 'expected_workspace_id': f.context.workspace_id, 'idempotency_key': 'review'}
        self.assertEqual(f.invoke(request=f.request('brand.review.decide', request))[0], 0)
        code, missing = f.invoke(request=f.request('brand.tracking.show', {'identifier': str(uuid4())}))
        self.assertEqual((code, missing['error']['code']), (3, 'not_found'))


class MonitorTests(unittest.TestCase):
    def test_monitor_respects_due_time_and_duration_without_holding_one_long_writer(self):
        f = TrackingTests(); f.setUp(); self.addCleanup(f.doCleanups)
        watch = f.add(); tick = [0.0]; origin = datetime.fromisoformat(AT)
        def sleep(seconds):
            self.assertLessEqual(seconds, 1); tick[0] += seconds
            f.at = (origin + timedelta(seconds=tick[0])).isoformat()
        result = monitor(watch['id'], f.service.execute, max_cycles=3, max_duration_seconds=301,
            clock=lambda: datetime.fromisoformat(f.at), monotonic=lambda: tick[0], sleeper=sleep)
        self.assertEqual(result['completed_cycles'], 2); self.assertEqual(result['stop_reason'], 'duration')

    def test_monotonic_clock_regression_and_invalid_limits_fail_before_collection(self):
        with self.assertRaises(ValidationError): monitor(str(uuid4()), lambda *a, **k: None, max_cycles=True)
        ticks = iter([10.0, 9.0])
        with self.assertRaises(ValidationError): monitor(str(uuid4()), lambda *a, **k: None, monotonic=lambda: next(ticks))


class ContractTests(unittest.TestCase):
    def test_write_boundary_requires_workspace_fence_and_rejects_credentials_or_arbitrary_urls(self):
        base = {'contract_version': 1, 'request_id': 'write', 'operation': 'brand.tracking.run',
                'parameters': {'identifier': str(uuid4()), 'idempotency_key': 'run'}}
        with self.assertRaises(EngineContractError): parse_engine_request(base)
        with self.assertRaises(EngineContractError): parse_platform_request(base)
        base['parameters']['expected_workspace_id'] = str(uuid4())
        self.assertEqual(parse_platform_request(base).operation, 'brand.tracking.run')
        for extra in ({'api_key': 'secret'}, {'web_search': True}, {'interval_seconds': 0}, {'force': 'yes'}, {'company': 'other'}):
            with self.subTest(extra=extra), self.assertRaises(EngineContractError):
                parse_platform_request({**base, 'parameters': {**base['parameters'], **extra}})


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.f = TrackingTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        # Existing case rows, evidence and source receipts must survive the CHECK rebuild.
        from tests.test_cases import CaseTests
        self.old = CaseTests(); self.old.setUp(); self.addCleanup(self.old.doCleanups)
        case = self.old.create_case()
        self.link = self.old.service.add_evidence(case.id, 'finding', self.old.insert_finding(), reason='Preserve historical evidence').evidence
        self.path, self.storage = self.old.path, self.old.storage
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute('UPDATE case_evidence SET rowid=rowid+100')
            case_evidence_layout_v82(c); c.execute('PRAGMA user_version=82')
            self.assertEqual(validate_schema(c, allow_legacy=True), 82)
            self.before = self.manifest(c)

    @staticmethod
    def manifest(c): return {table: c.execute(f'SELECT rowid,* FROM {table} ORDER BY rowid').fetchall() for table in VERSION_TABLES[82]}

    def test_explicit_backed_up_upgrade_preserves_every_old_row_and_identity(self):
        with self.assertRaises(StorageError): self.old.service.show(self.link.case_id)
        result = self.storage.migrate(); self.assertEqual(result['to_version'], SCHEMA_VERSION)
        for path in (self.path, Path(result['backup'])):
            with closing(sqlite3.connect(path)) as c: self.assertEqual(self.manifest(c), self.before)
        self.assertEqual(self.old.service.evidence_show(self.link.case_id, self.link.id), self.link)
        self.assertFalse(self.storage.migrate()['changed'])

    def test_interrupted_copy_rolls_back_and_backup_remains_restorable(self):
        from xti.adapters.social_tracking_schema import create
        def interrupted(c): create(c); raise KeyboardInterrupt()
        with patch('xti.adapters.sqlite.create_social_tracking_schema', side_effect=interrupted), self.assertRaises(KeyboardInterrupt): self.storage.migrate()
        with closing(sqlite3.connect(self.path)) as c:
            self.assertEqual(validate_schema(c, allow_legacy=True), 82); self.assertEqual(self.manifest(c), self.before)
        backup = next((self.path.parent / 'backups').glob('*.db'))
        restored = self.path.parent / 'restored' / 'xti.db'; SQLiteAssetRepository.restore(backup, restored)
        SQLiteAssetRepository(restored).migrate()
        with closing(sqlite3.connect(restored)) as c: self.assertEqual(self.manifest(c), self.before)

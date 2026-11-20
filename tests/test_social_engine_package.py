"""Cross-feature acceptance for social research, profile jobs and cold receipts."""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_research import SQLiteResearchRepository
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_collection_social import SQLiteCollectionSocial
from xti.adapters.sqlite_journal_storage import SQLiteJournalStorageRepository
from xti.application.journal_storage import JournalStorageService
from xti.application.research import ResearchService, research_data, priority_data
from xti.domain.assets import ValidationError
from xti.domain.collection import CollectionPlan
from xti.domain.collection_history import freeze_collection_plan, parse_plan_json, canonical_plan_json
from xti.domain.collection_profiles import CollectionProfileDefinition, canonical_definition_json, parse_definition_json
from xti.domain.research_history import freeze
from xti.domain.source_comparison import comparisons
from xti.interfaces.cli import main
from tests.test_social_discovery import IG, HN, GH, SCOPE
from tests import test_social_tracking as fixtures


class SocialEngineTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.TrackingTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.path = self.f.path
        self.research = ResearchService(SQLiteResearchRepository(self.path), clock=lambda: datetime.fromisoformat(self.f.at))

    def graph(self, value='acme.example', kind='domain'):
        return research_data(self.research.show(value=value, indicator_type=kind))

    def invoke(self, *args):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(['--data-dir', str(self.path.parent), '--json', *args])
        return code, json.loads(out.getvalue() or err.getvalue())

    def frozen(self):
        watch = self.f.add()
        bridge = SQLiteCollectionSocial(self.path, self.f.service)
        definition = CollectionProfileDefinition('acme.example', task_ids=(), social_watch_ids=(watch['id'],))
        tasks = bridge.plan(definition.social_watch_ids, definition.asset_value)
        plan = freeze_collection_plan(definition, CollectionPlan('acme.example', False, tasks, ()),
            contracts={task.id: bridge.contract(task) for task in tasks})
        return bridge, plan, watch

    def start(self):
        bridge, plan, watch = self.frozen()
        history = SQLiteCollectionHistoryRepository(self.path)
        # A real registered asset, as required by collection preflight.
        self.assertEqual(self.invoke('assets', 'add', 'acme.example')[0], 0)
        details = history.begin(plan, started_at=self.f.at)
        token = history.start_step(details.session.id, details.steps[0].id, started_at=self.f.at)
        return bridge, plan, watch, history, details, token

    def test_research_links_domain_url_case_without_ownership_and_reads_without_network(self):
        before = self.path.read_bytes()
        with patch.object(self.f.discovery, '_collect', side_effect=AssertionError('offline research')):
            graph = self.graph()
            url_graph = self.graph(IG, 'url')
        self.assertEqual(before, self.path.read_bytes())
        social = [n for n in graph['nodes'] if n['record_type'] == 'social_profile']
        self.assertIn(IG, [n['label'] for n in social])
        self.assertTrue(any(n['kind'] == 'domain' and n['value'] == 'acme.example' for n in url_graph['nodes']))
        self.assertFalse(any(e['status'] in ('official', 'suspected_impersonation') for n in social for e in n['evidence']))
        case = self.f.cases.create('Social investigation', summary='Controlled scenario', reason='Review exact profile').case
        ref = self.f.service.execute('brand.review.show', discovery_id=self.f.seed['id'], url=IG)['record']['case_evidence_id']
        self.f.cases.add_evidence(case.id, 'social_discovery', ref, reason='Attach exact evidence')
        graph = self.graph(IG, 'url')
        self.assertTrue(any(n['record_type'] == 'case' for n in graph['nodes']))
        freeze(priority_data(self.research.full_priorities(value=IG, indicator_type='url')))

    def test_source_absence_is_not_access_failure_and_tool_claim_does_not_override_page(self):
        graph = self.graph()
        nodes = {n['label']: n for n in graph['nodes'] if n['record_type'] == 'social_profile'}
        self.assertEqual(nodes[HN]['source_comparisons'][0]['state'], 'different_observations')
        self.assertEqual(nodes[GH]['source_comparisons'][0]['state'], 'verification_gap')
        claims = nodes[HN]['source_comparisons'][0]['observations']
        self.assertEqual({c['value'] for c in claims}, {'absent', 'reported_present'})
        self.assertTrue(all(c['record_id'] and c['observed_at'] for c in claims))

    def test_review_stays_historical_after_next_discovery_and_old_snapshot_stays_identical(self):
        self.f.decide(decision='suspected_impersonation')
        first = priority_data(self.research.full_priorities(value=IG, indicator_type='url'))
        frozen = freeze(first)
        self.assertTrue(any(r['code'] == 'social_impersonation_review' for i in first['items'] for r in i['reasons']))
        self.f.later()
        self.f.discovery.execute('brand.discovery.run', **SCOPE, idempotency_key='new-round')
        second = priority_data(self.research.full_priorities(value=IG, indicator_type='url'))
        self.assertFalse(any(r['code'] == 'social_impersonation_review' for i in second['items'] for r in i['reasons']))
        self.assertTrue(any(r['code'] == 'social_review_outdated' for i in second['items'] for r in i['reasons']))
        self.assertEqual(freeze(first), frozen)

    def test_two_workspaces_do_not_share_profile_or_decision(self):
        self.f.decide()
        other = self.path.parent / 'other.db'
        SQLiteAssetRepository(other).initialize()
        result = research_data(ResearchService(SQLiteResearchRepository(other)).show(value=IG, indicator_type='url'))
        self.assertFalse(any(n['record_type'] == 'social_profile' for n in result['nodes']))

    def test_later_unclaimed_absence_is_kept_for_a_previously_found_profile(self):
        from tests.test_social_discovery import page
        old = self.f.pages.fetch
        def fetch(url, **options):
            if url == 'https://acme.example/': return page(url, '<title>Company</title>')
            if url == IG: return page(url, 'Not found', 404)
            return old(url, **options)
        self.f.pages.fetch = fetch
        self.f.later()
        new = self.f.discovery.execute('brand.discovery.run', **SCOPE, idempotency_key='no-longer-linked')['record']
        node = next(n for n in self.graph()['nodes'] if n['record_type'] == 'social_profile' and n['label'] == IG)
        latest = [e for e in node['evidence'] if e['record_type'] == 'social_page' and e['current']]
        self.assertEqual(len(latest), 1)
        self.assertEqual((latest[0]['record_id'], latest[0]['status']), (new['id'], 'not_found'))

    def test_old_profile_and_plan_encodings_remain_unchanged(self):
        old = '{"asset_value":"acme.example","finding_limit":10,"ransomlook_watch_ids":[],"ransomware_watch_ids":[],"stale_after_hours":24,"task_ids":["ioc-feodo"],"typos":false,"username_watch_ids":[],"version":1,"watch_item_limit":100}'
        self.assertEqual(canonical_definition_json(parse_definition_json(old)), old)
        _, plan, _ = self.frozen()
        text = canonical_plan_json(plan)
        self.assertEqual(json.loads(text)['version'], 3)
        self.assertEqual(parse_plan_json(text, plan.definition), plan)
        self.assertEqual(parse_definition_json(canonical_definition_json(plan.definition)), plan.definition)

    def test_collection_receipt_and_notices_commit_together_and_recover_does_not_repeat_network(self):
        bridge, plan, watch, history, details, token = self.start()
        result = bridge.run(bridge.plan((watch['id'],), 'acme.example')[0], token)
        saved = history.get(details.session.id)
        self.assertEqual(saved.receipts[0].result_kind, 'social_tracking_run')
        self.assertEqual(saved.receipts[0].result_id, result['record']['id'])
        self.f.later()
        with patch.object(self.f.discovery, '_collect', side_effect=AssertionError('offline recovery')):
            history.recover_interrupted(recorded_at=self.f.at)
        self.assertEqual(history.get(details.session.id).receipts, saved.receipts)

    def test_crash_after_discovery_commit_is_recovered_without_duplicate_observation(self):
        bridge, plan, watch, history, details, token = self.start()
        original = self.f.repo.write
        def fail_finish(op, *args, **kw):
            if op == 'brand.tracking.finish': raise KeyboardInterrupt('after discovery commit')
            return original(op, *args, **kw)
        with patch.object(self.f.repo, 'write', side_effect=fail_finish), self.assertRaises(KeyboardInterrupt):
            bridge.run(bridge.plan((watch['id'],), 'acme.example')[0], token)
        before = len(self.f.pages.calls)
        self.f.later()
        history.recover_interrupted(recorded_at=self.f.at)
        result = history.get(details.session.id)
        self.assertEqual(len(result.receipts), 1)
        self.assertEqual(len(self.f.pages.calls), before)
        self.assertEqual(len(self.f.service.execute('brand.tracking.list')['records']), 1)

    def test_crash_before_discovery_reservation_closes_without_network_and_allows_later_run(self):
        bridge, plan, watch, history, details, token = self.start()
        with patch.object(self.f.discovery, 'run_tracking', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            bridge.run(bridge.plan((watch['id'],), 'acme.example')[0], token)
        self.f.later()
        with patch.object(self.f.discovery, '_collect', side_effect=AssertionError('offline recovery')):
            history.recover_interrupted(recorded_at=self.f.at)
        self.assertEqual(history.get(details.session.id).receipts[0].result_status, 'interrupted')
        self.f.later()
        self.assertNotEqual(self.f.run_watch(watch, 'after-interruption')['record']['status'], 'running')

    def test_actual_killed_process_preserves_committed_discovery_and_recovers_once(self):
        import os, signal, subprocess, sys
        from dataclasses import asdict
        _, _, watch, history, details, token = self.start()
        program = '''
import json, os, signal, sys
from pathlib import Path
from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository
from xti.adapters.sqlite_social_tracking import SQLiteSocialTrackingRepository
from xti.application.social_discovery import SocialDiscoveryService
from xti.application.social_tracking import SocialTrackingService
from xti.domain.collection_history import CollectionOperationToken
from tests.test_social_discovery import Pages, Sources
path, watch, token, at = Path(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3]), sys.argv[4]
discovery = SocialDiscoveryService(SQLiteSocialDiscoveryRepository(path), pages=Pages(), sources=Sources(), clock=lambda: at)
repo = SQLiteSocialTrackingRepository(path)
original = repo.write
def write(operation, *args, **kwargs):
    if operation == 'brand.tracking.finish': os.kill(os.getpid(), signal.SIGKILL)
    return original(operation, *args, **kwargs)
repo.write = write
SocialTrackingService(repo, discovery=discovery, clock=lambda: at).execute_collection(watch, CollectionOperationToken(**token))
'''
        env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
        child = subprocess.run([sys.executable, '-c', program, str(self.path), watch['id'],
            json.dumps(asdict(token)), self.f.at], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(child.returncode, -signal.SIGKILL, child.stderr)
        self.assertEqual(child.stdout + child.stderr, '')
        self.assertEqual(self.f.discovery_repo.list()['total_count'], 2)
        self.f.later()
        with patch('socket.socket.connect', side_effect=AssertionError('recovery must stay offline')):
            history.recover_interrupted(recorded_at=self.f.at)
            history.recover_interrupted(recorded_at=self.f.at)
        recovered = history.get(details.session.id)
        self.assertEqual(len(recovered.receipts), 1)
        self.assertEqual(recovered.receipts[0].result_kind, 'social_tracking_run')
        self.assertEqual(self.f.discovery_repo.list()['total_count'], 2)

    def test_other_domain_and_changed_watch_are_rejected_before_network(self):
        bridge, plan, watch = self.frozen()
        with self.assertRaises(ValidationError): bridge.plan((watch['id'],), 'different.example')
        self.assertEqual(self.invoke('assets', 'add', 'acme.example')[0], 0)
        self.f.service.execute('brand.tracking.set', identifier=watch['id'], enabled=False,
            expected_revision=1, idempotency_key='pause')
        before = len(self.f.pages.calls)
        with self.assertRaises(ValidationError):
            SQLiteCollectionHistoryRepository(self.path).begin(plan, started_at=self.f.at)
        self.assertEqual(len(self.f.pages.calls), before)

    def test_cli_profile_save_plan_collect_skip_and_job_payload_use_same_social_scope(self):
        from xti.adapters.engine_job_collection import CollectionProfileJobRunner
        from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
        from xti.config import Settings
        from xti.interfaces.cli import make_collection_history_service
        watch = self.f.add()
        self.assertEqual(self.invoke('assets', 'add', 'acme.example')[0], 0)
        clock = lambda: datetime.now(timezone.utc).isoformat()
        self.f.service.clock = self.f.discovery.clock = clock
        with patch('xti.interfaces.social_tracking.make_social_tracking_service', return_value=self.f.service):
            code, saved = self.invoke('profiles', 'save', 'Daily social', 'acme.example', '--only-social', '--social-watch', watch['id'])
            self.assertEqual(code, 0, saved)
            before, calls = self.path.read_bytes(), len(self.f.pages.calls)
            code, plan = self.invoke('collect', '--profile', 'Daily social', '--plan')
            self.assertEqual(code, 0, plan)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(len(self.f.pages.calls), calls)
            runner = CollectionProfileJobRunner(SQLiteCollectionProfileRepository(self.path),
                lambda: make_collection_history_service(Settings(self.path.parent), self.f.storage))
            payload = runner.prepare('Daily social', 1)
            self.assertEqual(payload.frozen_plan.units[0].watch.revision, 1)
            sessions = []
            delivered = runner.run(payload, session_started=sessions.append)
            self.assertEqual(delivered['steps'][0]['receipt']['kind'], 'social_tracking_run')
            self.assertEqual(sessions, [delivered['collection_session_id']])
            code, result = self.invoke('collect', '--profile', 'Daily social', '--summary')
            self.assertIn(code, (0, 3), result)
            self.assertEqual(result['data']['steps'][0]['task']['kind'], 'social_tracking')
            calls = len(self.f.pages.calls)
            code, result = self.invoke('collect', '--profile', 'Daily social')
            self.assertEqual(result['data']['steps'][0]['social']['status'], 'not_due')
            self.assertEqual(len(self.f.pages.calls), calls)

    def test_archive_preserves_discovery_case_decision_replay_and_backup_restore(self):
        self.f.decide()
        before = self.f.discovery_repo.show(self.f.seed['id'])
        view = self.f.service.execute('brand.review.show', discovery_id=self.f.seed['id'], url=IG)
        self.f.later(86400 * 10)
        self.f.discovery.execute('brand.discovery.run', **SCOPE, idempotency_key='latest')
        archives = JournalStorageService(SQLiteJournalStorageRepository(self.path), clock=lambda: datetime.fromisoformat(self.f.at))
        plan = archives.execute('journals.archive-plan', older_than_days=7)
        self.assertEqual([r['journal'] for r in plan['items']], ['social_discovery_runs'])
        applied = archives.execute('journals.archive-apply', older_than_days=7, token=plan['token'])
        self.assertTrue(Path(applied['backup']).is_file())
        self.assertEqual(self.f.discovery_repo.show(self.f.seed['id']), before)
        self.assertEqual(self.f.service.execute('brand.review.show', discovery_id=self.f.seed['id'], url=IG), view)
        with patch.object(self.f.discovery, '_collect', side_effect=AssertionError('archive replay offline')):
            self.assertEqual(self.f.discovery.execute('brand.discovery.run', **SCOPE, idempotency_key='seed')['record'], before['record'])
        backup = self.f.storage.backup(self.path.parent / 'cold.db')
        restored = self.path.parent / 'restored.db'
        SQLiteAssetRepository.restore(backup, restored)
        from xti.adapters.sqlite_social_discovery import SQLiteSocialDiscoveryRepository
        self.assertEqual(SQLiteSocialDiscoveryRepository(restored).show(self.f.seed['id']), before)
        archives.execute('journals.restore', identifier=applied['event']['id'])
        self.assertEqual(self.f.discovery_repo.show(self.f.seed['id']), before)

    def test_archiving_cannot_bypass_logical_byte_limit_or_accept_corruption(self):
        self.f.later(86400 * 10)
        self.f.discovery.execute('brand.discovery.run', **SCOPE, idempotency_key='latest')
        archives = JournalStorageService(SQLiteJournalStorageRepository(self.path), clock=lambda: datetime.fromisoformat(self.f.at))
        plan = archives.execute('journals.archive-plan', older_than_days=7)
        archives.execute('journals.archive-apply', older_than_days=7, token=plan['token'])
        with patch('xti.adapters.sqlite_social_discovery.MAX_TOTAL_BYTES', 1000), self.assertRaises(StorageError):
            self.f.discovery_repo.show(self.f.seed['id'])
        with self.f.storage._connection() as c, c:
            c.execute("UPDATE journal_payload_archives SET body=? WHERE journal='social_discovery_runs'", (b'broken',))
        with self.assertRaises(StorageError): self.f.discovery_repo.show(self.f.seed['id'])


if __name__ == '__main__':
    unittest.main()

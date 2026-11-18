"""Independent attempts, retained evidence, frozen history and workspace scope."""

from copy import deepcopy
from datetime import timedelta
import json
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import provision_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_research import _Reader
from xti.adapters.sqlite_research_discovery_status import StoredDiscoveryStatuses
from xti.application.surface_discovery_status import SurfaceDiscoveryStatusService
from xti.domain.assets import ValidationError
from xti.domain.research import ResearchSnapshotChanged
from xti.domain.research_history import freeze, validate_snapshot
from xti.domain.surface import SurfaceDiscoveryRunRequest
from xti.interfaces.platform_jobs import initialize_jobs
from xti.interfaces.research import research_lines, priority_lines
from tests.test_research_discovery import DiscoveryResearchFixture


class ResearchDiscoveryStatusTests(DiscoveryResearchFixture, unittest.TestCase):
    def record(self, status='complete', *, provider='crt.sh', root='example.com', path=None, error=None):
        path = path or self.path
        asset, _ = SQLiteAssetRepository(path).add(root)
        stamp = self.at.isoformat()
        return self.repo(path).record_discovery(asset.id, root, (), SurfaceDiscoveryRunRequest(
            status, 'https://archive.example/search', stamp, stamp, 0, 0, 0,
            ('Partial fixture',) if status == 'partial' else (), 0,
            error or 'Fixture timeout' if status == 'failed' else None, provider))[1]

    def root_node(self, graph=None):
        return next(row for row in (graph or self.graph(limit=100))['nodes'] if row['value'] == 'example.com')

    def sources(self):
        return {row['provider']: row for row in self.root_node()['discovery']}

    def test_registered_never_checked_and_unregistered_domain_have_different_context(self):
        self.assertEqual(self.root_node()['discovery'], [])
        SQLiteAssetRepository(self.path).add('example.com')
        before = self.files()
        states = self.sources()
        self.assertEqual(set(states), {'crt.sh', 'theharvester'})
        for state in states.values():
            self.assertEqual(state['outcome'], 'never')
            self.assertIsNone(state['latest_run'])
            self.assertIsNone(state['successful_run'])
        self.assertFalse(self.root_node()['evidence'])
        self.assertEqual(self.files(), before)

    def test_success_partial_failure_empty_remain_distinct_and_match_existing_status(self):
        self.discover()
        assets = SQLiteAssetRepository(self.path)
        dedicated = SurfaceDiscoveryStatusService(assets, self.repo(), clock=lambda: self.at)
        for status in ('complete', 'partial', 'failed'):
            self.at += timedelta(minutes=1)
            run = self.record(status)
            state = self.sources()['crt.sh']
            self.assertEqual(state['outcome'], dedicated.show('example.com', provider='crt.sh').outcome)
            self.assertEqual(state['latest_run']['id'], run.id)
            self.assertEqual(state['previous_success_preserved'], status != 'complete')
            self.assertEqual(len(self.edges()), 1)
            codes = {reason['code'] for item in self.priorities()['items'] for reason in item['reasons']}
            self.assertIn({'complete': 'discovery_complete_empty', 'partial': 'discovery_query_partial',
                           'failed': 'discovery_query_failed'}[status], codes)
            if status != 'complete':
                self.assertNotIn('discovery_complete_empty', codes)

    def test_latest_partial_with_candidate_is_not_success_or_empty(self):
        item = self.discover()
        self.sql("UPDATE surface_discovery_runs SET status='partial',warnings='[\"limited\"]'")
        state = self.sources()['crt.sh']
        self.assertEqual(state['outcome'], 'partial_found')
        self.assertIsNone(state['successful_run'])
        self.assertEqual(self.edges()[0]['evidence'][0]['record_id'], item.candidate.id)

    def test_old_success_keeps_own_age_and_failed_run_has_original_identity(self):
        self.discover(observed=(self.at - timedelta(days=40)).isoformat())
        good = self.sources()['crt.sh']['latest_run']
        self.at += timedelta(days=3)
        failed = self.record('failed')
        state = self.sources()['crt.sh']
        self.assertEqual((state['latest_run']['freshness'], state['successful_run']['freshness']), ('fresh', 'stale'))
        self.assertEqual(state['successful_run']['id'], good['id'])
        row = next(e for e in self.root_node()['evidence'] if e['record_id'] == failed.id)
        self.assertEqual(row['source_run_id'], failed.id)
        self.assertEqual(row['time_basis'], 'response_received_at')
        self.assertEqual(row['observed_at'], failed.finished_at)
        self.assertTrue(all(row['source_run_id'] is None for row in self.edges()[0]['evidence']))

    def test_provider_failure_does_not_hide_other_provider_success(self):
        failure = self.record('failed')
        success = self.record(provider='theharvester')
        states = self.sources()
        self.assertEqual(states['crt.sh']['latest_run']['id'], failure.id)
        self.assertEqual(states['theharvester']['latest_run']['id'], success.id)
        self.assertEqual(states['theharvester']['outcome'], 'complete_empty')

    def test_sequence_survives_clock_rollback_and_future_dates_remain_visible(self):
        future = self.record()
        self.at -= timedelta(days=1)
        latest = self.record('failed')
        state = self.sources()['crt.sh']
        self.assertEqual(state['latest_run']['id'], latest.id)
        self.assertEqual(state['successful_run']['id'], future.id)
        self.assertEqual(state['successful_run']['freshness'], 'future')
        codes = {r['code'] for item in self.priorities()['items'] for r in item['reasons']}
        self.assertIn('future_evidence_time', codes)

    def test_read_budget_does_not_turn_unknown_context_into_never_or_empty(self):
        self.record()
        with patch('xti.adapters.sqlite_research_discovery_status.MAX_STATUS_BYTES', 1), \
             patch.object(type(self.repo()), '_run', side_effect=AssertionError('Decode before budget')):
            graph = self.graph()
        state = self.root_node(graph)['discovery'][0]
        self.assertEqual(state['outcome'], 'read_limited')
        self.assertFalse(state['read_complete'])
        self.assertIsNone(state['latest_run'])
        self.assertIn('discovery_status_read_budget', graph['limitations'])

    def test_large_stored_field_is_bounded_before_loading_or_decoding(self):
        run = self.record()
        self.sql('UPDATE surface_discovery_runs SET source_url=? WHERE id=?', ('x' * 10000, run.id))
        with patch('xti.adapters.sqlite_research_discovery_status.MAX_STATUS_BYTES', 5000):
            self.assertEqual(self.sources()['crt.sh']['outcome'], 'read_limited')

    def test_corrupt_selected_run_fails_closed_but_unrelated_root_is_not_loaded(self):
        self.record(root='unrelated.example')
        self.sql("UPDATE surface_discovery_runs SET warnings='not json'")
        self.record()
        self.assertEqual(self.sources()['crt.sh']['outcome'], 'complete_empty')
        self.sql("UPDATE surface_discovery_runs SET asset_value='other.example' WHERE asset_value='example.com'")
        with self.assertRaises(StorageError):
            self.graph()

    def test_selected_status_and_graph_share_one_read_snapshot(self):
        old = self.record()
        self.sql('PRAGMA journal_mode=WAL')
        original, inserted = StoredDiscoveryStatuses.read, []
        def change(reader, *args):
            if not inserted:
                inserted.append(self.record('failed'))
            return original(reader, *args)
        with patch.object(StoredDiscoveryStatuses, 'read', change):
            state = self.sources()['crt.sh']
        self.assertEqual(state['latest_run']['id'], old.id)
        self.assertEqual(self.sources()['crt.sh']['latest_run']['id'], inserted[0].id)

    def test_new_attempt_invalidates_page_and_saved_review_keeps_original_context(self):
        self.discover()
        graph = self.graph()
        history = self.history()
        old = history.record(indicator_type='domain', value='example.com')
        frozen = history.show(old['review']['id'], view='items', limit=100)
        self.record('failed')
        with self.assertRaises(ResearchSnapshotChanged):
            self.graph(expected_snapshot=graph['snapshot_id'])
        new = history.record(indicator_type='domain', value='example.com')
        changed = history.show(new['review']['id'])['changes']
        self.assertTrue(changed)
        self.assertEqual({item['origin'] for item in changed}, {'evidence_or_mixed'})
        self.assertTrue(all(not item['withdrawn_assertion_ids'] for item in changed))
        self.assertEqual(history.show(old['review']['id'], view='items', limit=100), frozen)

    def test_old_source_age_changes_are_time_only_in_saved_review(self):
        self.record()
        history = self.history()
        history.record(indicator_type='domain', value='example.com')
        self.at += timedelta(days=2)
        new = history.record(indicator_type='domain', value='example.com')
        changes = history.show(new['review']['id'])['changes']
        self.assertEqual({item['origin'] for item in changes}, {'time_only'})

    def test_frozen_model_checks_run_links_and_rejects_partial_as_completed(self):
        self.record('partial')
        data = freeze(self.priorities())
        for mutate in (
            lambda d: d['items'][0]['discovery'][0].update(outcome='complete_empty'),
            lambda d: d['items'][0]['discovery'][0]['latest_run'].update(id='wrong-run'),
            lambda d: d['items'][0]['discovery'][0].update(previous_success_preserved=True),
            lambda d: d['items'][0].update(discovery=[]),
            lambda d: d.update(model_version=2),
        ):
            damaged = deepcopy(data)
            mutate(damaged)
            with self.assertRaises(ValidationError):
                validate_snapshot(damaged)

    def test_priority_evidence_limit_retains_attempts_before_many_indicator_claims(self):
        self.dns()
        self.record()
        self.record('failed')
        for i in range(51):
            self.iocs.add('domain', 'example.com', source_name=f'fixture{i}', source_reference=f'report:{i}',
                          confidence=50, description='Fixture claim')
        data = freeze(self.priorities())
        root = next(item for item in data['items'] if item['value'] == 'example.com')
        self.assertEqual(len(root['evidence']), 52)
        self.assertGreater(root['evidence_total_count'], 52)
        self.assertEqual(len([e for e in root['evidence'] if e['record_type'] == 'surface_discovery_run']), 2)

    def test_two_company_platform_context_and_backup_preserve_original_run_ids(self):
        root = self.root / 'companies'
        runs = {}
        for company in ('first', 'second'):
            context = provision_company_workspace(root, company)
            SQLiteAssetRepository(context.database).initialize()
            initialize_jobs(context)
            runs[company] = self.record('failed', path=context.database, error=company + ' private failure')
        code, out, err = self.invoke(['platform', 'request', '--root', str(root), '--company', 'first'], self.request())
        self.assertEqual((code, err), (0, ''), out)
        self.assertIn(runs['first'].id, out)
        self.assertNotIn(runs['second'].id, out)
        self.assertNotIn('second private failure', out)
        self.record('failed')
        old = self.history().record(indicator_type='domain', value='example.com')
        backup = self.root / 'source-status-backup.db'
        SQLiteAssetRepository(self.path).backup(backup)
        self.assertEqual(self.history(backup).show(old['review']['id'], view='items'),
                         self.history().show(old['review']['id'], view='items'))

    def test_terminal_explains_no_attempt_and_preserved_success_without_network(self):
        self.record()
        self.record('failed')
        before = self.files()
        text = '\n'.join(research_lines(self.graph(), data_dir=self.data) + priority_lines(self.priorities(), data_dir=self.data))
        self.assertIn('henüz sorgulanmadı', text)
        self.assertIn('son sorgu başarısız', text)
        self.assertIn('Önceki tamamlanmış yanıt korunuyor', text)
        self.assertEqual(self.files(), before)

    def test_manifests_advertise_current_result_and_readable_frozen_models(self):
        from xti.interfaces.engine import engine_manifest
        from xti.interfaces.platform_engine import platform_manifest
        self.record()
        self.assertEqual(engine_manifest()['research']['model_version'], self.graph()['model_version'])
        self.assertEqual(platform_manifest()['research_history']['model_version'], self.graph()['model_version'])
        self.assertEqual(engine_manifest()['research_history']['readable_model_versions'], [1, 2, 3])

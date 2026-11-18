"""Stored supplier monitoring, honest source context and frozen comparisons."""

from contextlib import closing
from copy import deepcopy
from datetime import timedelta
import json
import shlex
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters import sqlite_research_supplier_context as context
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_supplier_watches import SQLiteSupplierWatchRepository, _audit
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.adapters.sqlite_research import SQLiteResearchRepository
from xti.adapters.sqlite_research_history import SQLiteResearchHistoryRepository
from xti.adapters.company_workspaces import provision_company_workspace
from xti.application.research import ResearchService, research_data
from xti.application.research_history import ResearchHistoryService
from xti.application.supplier_threat_events import SupplierThreatEventService
from xti.application.supplier_risk import SupplierRiskService
from xti.domain.research import research_query, build_research, ResearchSnapshotChanged
from xti.domain.research_history import capture_scope, freeze
from xti.interfaces.research import research_lines, priority_lines
from xti.interfaces.platform_jobs import initialize_jobs
from tests.test_public_notices import feed, item
from tests.test_threatcluster_ransomware import claim, content as threat_content
from tests.test_ransomlook_ransomware import post, content as ransom_content
from tests.test_research_suppliers import SupplierResearchFixture


class SupplierContextTests(SupplierResearchFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.watch_repo = SQLiteSupplierWatchRepository(self.path)
        self.threat = SQLiteRansomwareClaimRepository(self.path)
        self.ransom = SQLiteRansomLookClaimRepository(self.path)
        self.hibp = SQLitePublicNoticeRepository(self.path)

    def watch(self, supplier, source='threatcluster', enabled=True):
        return self.watch_repo.configure(supplier.id, source=source, enabled=enabled,
            reason='Explicit fixture monitoring choice', recorded_at=self.at.isoformat()).watch

    def apply_threat(self, *records, path=None):
        value = parse_threatcluster_ransomware_response(threat_content(list(records),
            generated_at=self.at.isoformat()), fetched_at=self.at)
        return (SQLiteRansomwareClaimRepository(path) if path else self.threat).apply(value,
            started_at=self.at.isoformat(), finished_at=self.at.isoformat(), item_limit=100)

    def apply_ransom(self, *records):
        value = parse_ransomlook_ransomware_response(ransom_content(list(records)), fetched_at=self.at)
        return self.ransom.apply(value, started_at=self.at.isoformat(), finished_at=self.at.isoformat(), item_limit=100)

    def apply_notice(self, *records):
        return self.hibp.apply(feed(*records), started_at=self.at.isoformat(), finished_at=self.at.isoformat())

    def nodes(self, kind, graph=None):
        return [node for node in (graph or self.graph(limit=100))['nodes'] if node['kind'] == kind]

    def event_service(self):
        return SupplierThreatEventService(self.suppliers.repository, self.threat, self.ransom)

    def test_unrelated_supplier_is_not_attached_and_no_network_or_writes(self):
        self.dns()
        supplier = self.supplier()
        self.apply_threat(claim(website=supplier.primary_domain))
        before = self.files()
        graph = self.graph(limit=100)
        self.assertFalse(self.nodes('supplier_event', graph))
        self.assertFalse(self.nodes('supplier_risk', graph))
        self.assertEqual(self.files(), before)

    def test_two_hops_keep_original_claim_and_derived_event_id_with_risk_parity(self):
        _, supplier = self.accepted()
        run = self.apply_threat(claim(website=supplier.primary_domain, victim=supplier.display_name))
        before = self.files()
        graph = self.graph(limit=100)
        event_node = self.nodes('supplier_event', graph)[0]
        event = self.event_service().evidence().events[0]
        row = event_node['evidence'][0]
        self.assertEqual((event_node['value'], row['record_id'], row['source_reference'], row['source_run_id']),
            (event.id, event.id, event.claim_id, run.run.id))
        self.assertEqual(row['observed_at'], event.discovered_at)
        self.assertEqual((row['kind'], row['status']), ('candidate_context', 'domain_match'))
        values = {node['id']: node['value'] for node in graph['nodes']}
        self.assertTrue(any([values[key] for key in path['node_ids']] ==
            ['example.com', supplier.id, event.id] for path in graph['paths']))
        card = SupplierRiskService(self.suppliers.repository, self.candidates.repository, self.event_service()).show(supplier.id).card
        risk = self.nodes('supplier_risk', graph)[0]['evidence'][0]
        self.assertEqual(risk['status'], card.attention)
        self.assertIn('güncel insan onaylı bağımlılık: 1', risk['description'])
        self.assertEqual(self.files(), before)

    def test_name_ambiguity_survives_filter_and_never_merges_supplier_nodes(self):
        _, supplier = self.accepted()
        other = self.supplier('other.example', supplier.display_name)
        self.apply_ransom(post(title=supplier.display_name, discovered=self.at.isoformat()))
        selected = self.event_service().list(supplier_id=supplier.id)
        self.assertEqual(selected.events[0].same_name_supplier_count, 2)
        graph = self.graph(limit=100)
        self.assertEqual(self.nodes('supplier_event', graph)[0]['evidence'][0]['status'], 'ambiguous_name')
        self.assertEqual(self.nodes('supplier_risk', graph)[0]['evidence'][0]['status'], 'identity_review')
        self.assertNotIn(other.id, {node['value'] for node in graph['nodes']})
        self.assertIn('supplier_identity_ambiguous', {r['code'] for n in self.priorities()['items'] for r in n['reasons']})

    def test_missing_failed_and_successful_empty_sources_are_distinct(self):
        self.accepted()
        initial = self.nodes('supplier_risk')[0]
        self.assertEqual(initial['evidence'][0]['status'], 'insufficient_data')
        self.assertEqual({row['status'] for row in initial['evidence'][1:]}, {'not_collected'})
        self.threat.record_failure(started_at=self.at.isoformat(), finished_at=self.at.isoformat(), error='Fixture outage')
        rows = self.nodes('supplier_risk')[0]['evidence']
        self.assertIn('unavailable', {row['status'] for row in rows})
        self.apply_threat()
        rows = self.nodes('supplier_risk')[0]['evidence']
        self.assertEqual(rows[0]['status'], 'no_current_match')
        self.assertIn('available', {row['status'] for row in rows})

    def test_old_inventory_without_sources_is_not_an_old_network_observation(self):
        self.accepted()
        self.at += timedelta(days=30)
        card = next(row for row in self.priorities()['items'] if
            row['subject_kind'] == 'node' and row['record_type'] == 'supplier_risk')
        codes = {reason['code'] for reason in card['reasons']}
        self.assertEqual(codes, {'supplier_source_missing'})
        self.assertTrue(all(row['time_basis'] in {'stored_context_updated_at', 'inventory_recorded_at'}
            for row in card['evidence']))

    def test_card_context_date_includes_later_human_dependency_decision(self):
        candidate, supplier = self.candidate(), self.supplier()
        self.at += timedelta(hours=2)
        self.review(candidate, 'accepted', supplier)
        card = self.nodes('supplier_risk')[0]['evidence'][0]
        self.assertEqual(card['recorded_at'], self.at.isoformat())
        self.assertEqual(card['time_basis'], 'stored_context_updated_at')

    def test_later_failure_preserves_success_claim_watch_and_original_dates(self):
        _, supplier = self.accepted(); self.watch(supplier)
        success = self.apply_threat(claim(website=supplier.primary_domain))
        self.at += timedelta(hours=1)
        failure = self.threat.record_failure(started_at=self.at.isoformat(), finished_at=self.at.isoformat(), error='Fixture outage')
        graph = self.graph(limit=100)
        row = self.nodes('supplier_event', graph)[0]['evidence'][0]
        self.assertEqual(row['source_run_id'], success.run.id)
        watches = self.nodes('supplier_watch', graph)
        coverage = next(row for row in watches[0]['evidence'] if row['record_type'] == 'supplier_source_coverage')
        self.assertEqual(coverage['status'], 'stale_after_failure')
        ids = {row['record_id'] for row in watches[0]['evidence'] if row['record_type'] == 'supplier_source_run'}
        self.assertEqual(ids, {success.run.id, failure.id})
        self.assertIn('supplier_source_degraded', {r['code'] for n in self.priorities()['items'] for r in n['reasons']})

    def test_watch_baseline_update_and_removed_keep_local_notification_and_source_hashes(self):
        _, supplier = self.accepted(); watch = self.watch(supplier, 'hibp')
        self.apply_notice(item(domain=supplier.primary_domain))
        run = self.watch_repo.show(watch.id).runs[0]
        self.assertEqual((run.baseline_count, run.added_count), (1, 0))
        rows = self.nodes('supplier_watch')[0]['evidence']
        original = next(row for row in rows if row['record_type'] == 'supplier_watch_run')
        self.assertEqual((original['status'], original['event_id']), ('baseline', None))
        self.apply_notice(item(domain=supplier.primary_domain, PwnCount=23456))
        report = self.watch_repo.run_show(self.watch_repo.show(watch.id).runs[0].id)
        rows = self.nodes('supplier_watch')[0]['evidence']
        original = next(row for row in rows if row['record_type'] == 'supplier_watch_run')
        change = next(row for row in rows if row['record_type'] == 'supplier_watch_item')
        self.assertEqual(original['event_id'], report.notification_id)
        self.assertEqual(change['status'], 'updated')
        self.assertIn('önceki kayıt özeti:', change['description'])
        self.apply_notice(item(domain='elsewhere.example'))
        rows = self.nodes('supplier_watch')[0]['evidence']
        change = next(row for row in rows if row['record_type'] == 'supplier_watch_item')
        self.assertEqual(change['status'], 'removed')
        self.assertFalse(change['current'])
        self.assertFalse(self.nodes('supplier_event'))  # HIBP metadata is not a ransomware claim.

    def test_identity_change_and_disable_retain_historical_watch_without_relabeling(self):
        _, supplier = self.accepted(); self.watch(supplier)
        self.apply_threat(claim(victim=supplier.display_name, website=None))
        self.suppliers.update(supplier.id, name='New Supplier Name', reason='Identity corrected')
        rows = self.nodes('supplier_watch')[0]['evidence']
        original = next(row for row in rows if row['record_type'] == 'supplier_watch_run')
        self.assertFalse(original['current'])
        self.assertEqual(original['status'], 'historical_scope')
        self.assertIn('tarihî tedarikçi: Fixture Supplier', original['description'])
        self.assertFalse(self.nodes('supplier_event'))
        self.watch(supplier, enabled=False)
        self.assertEqual(self.nodes('supplier_watch')[0]['evidence'][0]['status'], 'disabled')

    def test_revoked_supplier_keeps_watch_history_but_has_no_current_risk_card(self):
        _, supplier = self.accepted(); self.watch(supplier)
        self.apply_threat(claim(website=supplier.primary_domain))
        self.suppliers.revoke(supplier.id, reason='Relationship ended')
        graph = self.graph(limit=100)
        self.assertTrue(self.nodes('supplier_watch', graph))
        self.assertFalse(self.nodes('supplier_risk', graph))
        self.assertFalse(self.nodes('supplier_event', graph))
        run = next(row for row in self.nodes('supplier_watch', graph)[0]['evidence'] if row['record_type'] == 'supplier_watch_run')
        self.assertFalse(run['current'])

    def test_sources_remain_separate_even_for_same_supplier_name(self):
        _, supplier = self.accepted()
        for source in ('threatcluster', 'ransomlook', 'hibp'):
            self.watch(supplier, source)
        self.apply_threat(claim(victim=supplier.display_name, website=supplier.primary_domain))
        self.apply_ransom(post(title=supplier.display_name, discovered=self.at.isoformat()))
        self.apply_notice(item(domain=supplier.primary_domain))
        graph = self.graph(limit=100)
        self.assertEqual(len(self.nodes('supplier_watch', graph)), 3)
        events = self.nodes('supplier_event', graph)
        self.assertEqual({node['evidence'][0]['source'] for node in events}, {'threatcluster', 'ransomlook'})
        self.assertEqual(len({node['value'] for node in events}), 2)

    def test_unrun_watch_is_not_successful_empty_and_zero_match_reenable_is_baseline(self):
        _, supplier = self.accepted(); self.watch(supplier)
        rows = self.nodes('supplier_watch')[0]['evidence']
        self.assertIn('not_evaluated', {row['status'] for row in rows})
        self.apply_threat()
        self.watch(supplier, enabled=False); self.watch(supplier)
        self.apply_threat()
        row = next(row for row in self.nodes('supplier_watch')[0]['evidence'] if row['record_type'] == 'supplier_watch_run')
        self.assertEqual(row['status'], 'baseline')

    def test_domain_match_preserves_claim_name_ambiguity_counter_without_name_inference(self):
        _, supplier = self.accepted()
        self.supplier('same-one.example', 'Shared Name')
        self.supplier('same-two.example', 'Shared Name')
        self.apply_threat(claim(victim='Shared Name', website=supplier.primary_domain))
        event = self.event_service().list(supplier_id=supplier.id).events[0]
        self.assertEqual(event.same_name_supplier_count, 2)
        row = self.nodes('supplier_event')[0]['evidence'][0]
        self.assertEqual(row['status'], 'domain_match')
        self.assertIn('aynı adı taşıyan etkin tedarikçi: 2', row['description'])

    def test_work_budget_precedes_watch_replay_and_never_makes_partial_risk_card(self):
        _, supplier = self.accepted(); self.watch(supplier)
        self.apply_threat(claim(website=supplier.primary_domain))
        with patch.object(context, 'MAX_CONTEXT_WORK', 4), \
             patch.object(context, '_audit', side_effect=AssertionError('Bound before replay')):
            graph = self.graph(limit=100)
        self.assertFalse(self.nodes('supplier_watch', graph))
        self.assertIn('supplier_context_read_budget', graph['limitations'])

    def test_source_integrity_error_is_not_reported_as_successful_empty(self):
        _, supplier = self.accepted(); self.apply_threat(claim(website=supplier.primary_domain))
        self.sql('UPDATE ransomware_claim_run_items SET state_sha256=?', ('0' * 64,))
        with self.assertRaises(StorageError):
            self.graph()

    def test_two_company_platform_reads_and_backup_keep_source_and_watch_isolation(self):
        root = self.root / 'companies'
        contexts = [provision_company_workspace(root, name) for name in ('first', 'second')]
        for company in contexts:
            SQLiteAssetRepository(company.database).initialize(); initialize_jobs(company)
            candidate = self.candidate(path=company.database)
            supplier = self.supplier(name=company.company_id + ' Supplier', path=company.database)
            self.review(candidate, 'accepted', supplier, path=company.database)
            SQLiteSupplierWatchRepository(company.database).configure(supplier.id, source='threatcluster', enabled=True,
                reason='Company-local fixture watch', recorded_at=self.at.isoformat())
            self.apply_threat(claim(victim=company.company_id + ' CLAIM', website=supplier.primary_domain), path=company.database)
        before = self.files()
        code, out, err = self.invoke(['platform', 'request', '--root', str(root), '--company', 'first'], self.request(limit=100))
        self.assertEqual((code, err), (0, ''), out)
        self.assertIn('first CLAIM', out); self.assertNotIn('second CLAIM', out)
        self.assertIn('supplier_watch_run', out); self.assertIn('supplier_risk_context', out)
        self.assertEqual(self.files(), before)
        first = contexts[0]
        service = ResearchService(SQLiteResearchRepository(first.database), clock=lambda: self.at)
        history = ResearchHistoryService(SQLiteResearchHistoryRepository(first.database), service)
        record = history.record(indicator_type='domain', value='example.com')
        frozen = history.show(record['review']['id'], view='items', limit=100)
        backup = self.root / 'supplier-context-backup.db'
        SQLiteAssetRepository(first.database).backup(backup)
        restored = ResearchHistoryService(SQLiteResearchHistoryRepository(backup),
            ResearchService(SQLiteResearchRepository(backup), clock=lambda: self.at))
        self.assertEqual(restored.show(record['review']['id'], view='items', limit=100), frozen)

    def test_frozen_history_records_real_changes_and_keeps_earlier_snapshot(self):
        _, supplier = self.accepted(); self.watch(supplier)
        self.apply_threat(claim(website=supplier.primary_domain))
        first = self.history().record(indicator_type='domain', value='example.com')
        previous = deepcopy(self.history().show(first['review']['id'], view='items', limit=100))
        self.apply_threat(claim(website=supplier.primary_domain, status='delisted'))
        second = self.history().record(indicator_type='domain', value='example.com')
        self.assertEqual(second['review']['comparison']['state'], 'changed')
        self.assertEqual(self.history().show(first['review']['id'], view='items', limit=100), previous)
        self.assertNotEqual(first['review']['id'], second['review']['id'])

    def test_claim_leaving_source_is_visibility_change_not_withdrawn_assertion_or_resolved_incident(self):
        _, supplier = self.accepted(); self.watch(supplier)
        self.apply_threat(claim(website=supplier.primary_domain))
        self.history().record(indicator_type='domain', value='example.com')
        self.apply_threat()
        current = self.history().record(indicator_type='domain', value='example.com')
        changes = self.history().show(current['review']['id'], view='changes', limit=100)['changes']
        self.assertTrue(any(change['kind'] == 'not_in_current_view' for change in changes))
        self.assertTrue(all(not change['withdrawn_assertion_ids'] for change in changes))

    def test_policy_v5_snapshot_is_read_unchanged_and_v6_starts_baseline(self):
        self.accepted()
        from xti.application.research import priority_data
        data = freeze(priority_data(self.service.full_priorities(indicator_type='domain', value='example.com')))
        data['policy_version'] = 'research-priority-v5'
        repository = SQLiteResearchHistoryRepository(self.path)
        prior, _ = repository.append(capture_scope(indicator_type='domain', value='example.com'), data, 'fixture-v5', None)
        before = deepcopy(repository.show(prior.header.id))
        current = self.history().record(indicator_type='domain', value='example.com')
        self.assertEqual(current['review']['comparison']['state'], 'policy_baseline')
        self.assertEqual(repository.show(prior.header.id), before)

    def test_snapshot_guard_rejects_page_after_a_source_change(self):
        _, supplier = self.accepted(); self.apply_threat(claim(website=supplier.primary_domain))
        graph = self.graph(limit=1)
        self.apply_threat(claim(website=supplier.primary_domain, status='delisted'))
        with self.assertRaises(ResearchSnapshotChanged):
            self.graph(limit=1, offset=1, expected_snapshot=graph['snapshot_id'])

    def test_same_read_transaction_hides_concurrent_source_update_until_next_read(self):
        _, supplier = self.accepted(); self.apply_threat(claim(website=supplier.primary_domain))
        self.sql('PRAGMA journal_mode=WAL')
        query = research_query(indicator_type='domain', value='example.com', limit=100)
        with SQLiteResearchRepository(self.path).open(query, self.at.isoformat()) as reader:
            reader.node(('domain', 'example.com'))  # Establish snapshot before other connection commits.
            self.apply_threat(claim(website=supplier.primary_domain, status='delisted'))
            old = research_data(build_research(reader, query, self.at.isoformat()))
        old_evidence = self.nodes('supplier_event', old)[0]['evidence'][0]
        new_evidence = self.nodes('supplier_event')[0]['evidence'][0]
        self.assertIn('kaynak durumu: listed', old_evidence['description'])
        self.assertIn('kaynak durumu: delisted', new_evidence['description'])

    def test_byte_row_and_work_limits_keep_inventory_and_honest_partial_context(self):
        self.accepted()
        for constant in ('MAX_CONTEXT_ROWS', 'MAX_CONTEXT_BYTES', 'MAX_CONTEXT_WORK'):
            with self.subTest(constant=constant), patch.object(context, constant, 1):
                graph = self.graph(limit=100)
                self.assertEqual(graph['status'], 'partial')
                self.assertTrue(self.nodes('supplier', graph))
                self.assertFalse(self.nodes('supplier_risk', graph))
                self.assertIn('supplier_context_read_budget', graph['limitations'])

    def test_source_bytes_are_bounded_before_any_catalog_decode(self):
        _, supplier = self.accepted(); self.apply_threat(claim(website=supplier.primary_domain))
        self.sql("UPDATE ransomware_claim_runs SET source_name=?", ('x' * 50_000,))
        catalog = context._Catalog
        def bounded(connection, source):
            self.assertNotEqual(source, 'threatcluster', 'Oversized source must not be decoded')
            return catalog(connection, source)
        with patch.object(context, 'MAX_CONTEXT_BYTES', 10_000), \
             patch.object(context, '_Catalog', side_effect=bounded):
            graph = self.graph(limit=100)
        self.assertFalse(self.nodes('supplier_risk', graph))
        self.assertIn('supplier_context_read_budget', graph['limitations'])

    def test_event_window_keeps_full_card_count_and_marks_partial(self):
        _, supplier = self.accepted()
        self.apply_threat(*(claim(victim=f'Victim {i}', website=supplier.primary_domain) for i in range(4)))
        with patch.object(context, 'MAX_CONTEXT_EVENTS', 2):
            graph = self.graph(limit=100)
        self.assertEqual(len(self.nodes('supplier_event', graph)), 2)
        self.assertIn('aday: 4', self.nodes('supplier_risk', graph)[0]['evidence'][0]['description'])
        self.assertIn('supplier_context_event_limit', graph['limitations'])

    def test_watch_evidence_window_preserves_original_run_and_total_count(self):
        _, supplier = self.accepted(); self.watch(supplier, 'hibp')
        self.apply_notice(*(item(f'Record{i}', supplier.primary_domain) for i in range(60)))
        graph = self.graph(limit=100)
        node = self.nodes('supplier_watch', graph)[0]
        self.assertEqual(len(node['evidence']), 52)
        self.assertGreater(node['evidence_total_count'], 52)
        self.assertTrue(any(row['record_type'] == 'supplier_watch_run' for row in node['evidence']))
        self.assertIn('source_evidence_limit', graph['limitations'])
        self.history().record(indicator_type='domain', value='example.com')

    def test_corrupt_source_or_watch_binding_fails_without_writes(self):
        _, supplier = self.accepted(); self.watch(supplier)
        self.apply_threat(claim(website=supplier.primary_domain))
        self.sql('UPDATE supplier_watch_runs SET result_sha256=?', ('0' * 64,))
        before = self.files()
        with self.assertRaises(StorageError):
            self.graph()
        self.assertEqual(self.files(), before)

    def test_scoped_audit_validates_global_sequence_but_skips_unrelated_watch_payload(self):
        _, supplier = self.accepted(); self.watch(supplier)
        other = self.supplier('other.example', 'Other Supplier'); self.watch(other)
        self.apply_threat(claim(website=supplier.primary_domain))
        self.sql('UPDATE supplier_watch_runs SET scope_json=? WHERE supplier_id=?', ('x' * 30_000, other.id))
        self.assertTrue(self.nodes('supplier_watch'))
        with closing(sqlite3.connect(self.path)) as connection:
            with self.assertRaises(StorageError):
                _audit(connection)  # Full mutation audit still detects unrelated corruption.
        self.sql('UPDATE sqlite_sequence SET seq=seq+1 WHERE name=?', ('supplier_watch_runs',))
        with self.assertRaises(StorageError):
            self.graph()

    def test_cli_engine_and_every_generated_detail_command_use_selected_data(self):
        _, supplier = self.accepted(); self.watch(supplier); self.watch(supplier, 'hibp')
        self.apply_threat(claim(website=supplier.primary_domain)); self.apply_notice(item(domain=supplier.primary_domain))
        before = self.files()
        code, out, err = self.invoke(['--data-dir', str(self.data), 'engine'], self.request(limit=100))
        self.assertEqual((code, err), (0, ''), out)
        graph = json.loads(out)['data']
        lines = research_lines(graph, data_dir=self.data) + priority_lines(self.priorities(), data_dir=self.data)
        commands = {line.split('Ayrıntı: ', 1)[1] for line in lines if 'Ayrıntı: ' in line}
        self.assertTrue(any('watch-run-show' in command for command in commands))
        for command in commands:
            with self.subTest(command=command):
                code, out, err = self.invoke(shlex.split(command)[1:])
                self.assertEqual((code, err), (0, ''), out)
        self.assertEqual(self.files(), before)

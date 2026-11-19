"""Report revision paths, review history, bounded reads and actionable provenance."""

from contextlib import closing, redirect_stdout, redirect_stderr
from dataclasses import replace
from datetime import timedelta
from io import StringIO
import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.engine_records import SQLiteEngineRecordRepository
from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_research import SQLiteResearchRepository
from xti.adapters.sqlite_research_history import SQLiteResearchHistoryRepository
from xti.application.research import ResearchService, research_data, priority_data
from xti.application.research_history import ResearchHistoryService
from xti.domain.engine import EngineContractError, parse_record_reference
from xti.domain.research import ResearchSnapshotChanged, research_query
from xti.domain.research_history import freeze
from xti.interfaces.cli import main
from xti.interfaces.research import research_lines, priority_lines
from tests import test_reports as reports


class ResearchReportTests(unittest.TestCase):
    def setUp(self):
        self.f = reports.ReportTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.at = reports.NOW + timedelta(seconds=10)
        self.repository = SQLiteResearchRepository(self.f.path)
        self.service = ResearchService(self.repository, clock=lambda: self.at)
        self.history = ResearchHistoryService(SQLiteResearchHistoryRepository(self.f.path), self.service)

    def graph(self, value='192.0.2.10', kind='ipv4', **options):
        return research_data(self.service.show(indicator_type=kind, value=value, **options))

    def priority(self):
        return priority_data(self.service.full_priorities(indicator_type='ipv4', value='192.0.2.10'))

    def detail(self, node):
        return SQLiteEngineRecordRepository(self.f.path).get(parse_record_reference(node['references'][0]))

    def review(self):
        return self.history.record(indicator_type='ipv4', value='192.0.2.10')['review']['id']

    def test_capture_adds_two_hop_path_with_exact_document_and_human_provenance_without_new_claims(self):
        self.assertEqual(self.graph()['status'], 'not_recorded')
        report = self.f.capture()['record']
        actor = self.f.entity('threat-actor')
        self.f.link(report['id'], actor)
        before = self.f.path.read_bytes()
        graph = self.graph()
        by_type = {row['kind']: row for row in graph['nodes']}
        self.assertEqual(by_type['entity']['value'], actor)
        doc = by_type['report_document']
        self.assertTrue(any(path['hops'] == 2 and by_type['entity']['id'] in path['node_ids'] for path in graph['paths']))
        edge = next(row for row in graph['edges'] if row['relationship_type'] == 'report_reviewed_link')
        self.assertEqual(edge['kind'], 'human_decision')
        self.assertEqual(edge['evidence'][1]['status'], 'linked')
        self.assertTrue(edge['evidence'][1]['current'])
        self.assertNotEqual(edge['evidence'][0]['observed_at'], edge['evidence'][1]['observed_at'])
        self.assertEqual(edge['evidence'][0]['time_basis'], 'response_received_at')
        self.assertEqual(doc['evidence'][0]['source_run_id'], report['document']['source_run_id'])
        detail = self.detail(doc)
        self.assertEqual(detail['record']['document'], report['document'])
        self.assertIsNone(detail['provenance']['observed_at'])
        self.assertEqual(detail['sections']['links']['items'][0]['target']['id'], actor)
        self.assertEqual(self.f.path.read_bytes(), before)
        with self.f.f.storage._connection(readonly=True) as connection:
            for table in ('cti_indicators', 'cti_relationships'):
                self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0], 0)

    def test_domain_url_hash_and_ipv6_mentions_use_typed_nodes(self):
        values = [('domain', 'suspect.example'), ('url', 'https://suspect.example/login'),
                  ('ipv6', '2001:db8::123'), ('sha256', 'a' * 64)]
        self.f.f.apply(replace(self.f.item, summary='suspect[.]example ' + ' '.join(value for _, value in values[1:])))
        report = self.f.capture()['record']
        for kind, value in values:
            with self.subTest(kind=kind):
                graph = self.graph(value, kind)
                mentions = [edge for edge in graph['edges'] if edge['relationship_type'] == 'report_text_mention']
                self.assertTrue(mentions)
                self.assertTrue(any(row['value'] == report['id'] + ':1' for row in graph['nodes']))
                self.assertFalse(any(row['kind'] == 'source_claim' for edge in mentions for row in edge['evidence']))

    def test_new_document_does_not_inherit_link_and_old_withdrawal_preserves_both_decisions(self):
        rid = self.f.capture()['record']['id']
        target = self.f.entity()
        self.f.link(rid, target)
        self.f.f.apply(replace(self.f.item, title='Updated report'))
        self.f.capture('updated')
        before = self.graph()
        docs = {row['value']: row for row in before['nodes'] if row['kind'] == 'report_document'}
        self.assertEqual(set(docs), {rid + ':1', rid + ':2'})
        self.assertEqual(docs[rid + ':1']['evidence'][0]['status'], 'historical_document')
        links = [edge for edge in before['edges'] if edge['relationship_type'] == 'report_reviewed_link']
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['source_id'], docs[rid + ':1']['id'])
        self.f.link(rid, target, 3, 'withdraw-old', state='withdrawn', document_revision=1)
        graph = self.graph()
        edge = next(row for row in graph['edges'] if row['relationship_type'] == 'report_reviewed_link')
        decisions = [row for row in edge['evidence'] if row['kind'] == 'human_decision']
        self.assertEqual([(row['status'], row['current']) for row in decisions], [('withdrawn', True), ('linked', False)])
        reasons = {reason['code'] for item in self.priority()['items'] for reason in item['reasons']}
        self.assertIn('report_link_withdrawn', reasons)
        self.assertIn('report_document_historical', reasons)
        self.assertNotIn('report_linked', reasons)
        self.assertNotIn('active_indicator_claim', reasons)

    def test_noop_capture_and_failed_refresh_preserve_graph_snapshot_and_original_collection_time(self):
        self.f.capture()
        old = self.graph()
        self.f.f.failure()
        self.f.capture('same-content')
        self.assertEqual(self.graph()['snapshot_id'], old['snapshot_id'])
        self.assertEqual(self.graph()['nodes'], old['nodes'])
        self.f.f.apply(replace(self.f.item, summary='Correction removes the IP address'))
        self.f.capture('changed')
        with self.assertRaises(ResearchSnapshotChanged):
            self.graph(expected_snapshot=old['snapshot_id'])
        docs = [node for node in self.graph()['nodes'] if node['kind'] == 'report_document']
        self.assertEqual(len(docs), 1)
        self.assertFalse(docs[0]['evidence'][0]['current'])

    def test_frozen_reviews_keep_old_text_and_link_state_and_identify_evidence_changes(self):
        rid = self.f.capture()['record']['id']
        target = self.f.entity()
        self.f.link(rid, target)
        first = self.review()
        frozen = self.history.show(first, view='items', limit=100)
        self.f.link(rid, target, 2, 'withdraw', state='withdrawn')
        self.f.f.apply(replace(self.f.item, title='Corrected text'))
        self.f.capture('new-version')
        second = self.review()
        changes = self.history.show(second, limit=100)['changes']
        self.assertTrue(changes)
        self.assertTrue(any(row['origin'] == 'evidence_or_mixed' for row in changes))
        self.assertFalse(any(row['origin'] == 'time_only' for row in changes))
        self.assertEqual(self.history.show(first, view='items', limit=100), frozen)
        self.assertFalse(any(row['withdrawn_assertion_ids'] for row in changes))

    def test_priority_policy_change_starts_baseline_without_rewriting_v7_review(self):
        self.f.capture()
        with patch('xti.application.research.POLICY_VERSION', 'research-priority-v7'):
            old = self.review()
        frozen = self.history.show(old, view='items')
        new = self.review()
        self.assertEqual(self.history.show(new)['review']['comparison']['state'], 'policy_baseline')
        self.assertEqual(self.history.show(old, view='items'), frozen)

    def test_read_and_adjacency_limits_are_partial_not_empty_success_and_freezable(self):
        self.f.capture()
        with patch('xti.adapters.sqlite_research_reports.MAX_REPORT_READ_BYTES', 1):
            result = self.graph()
            self.assertEqual(result['status'], 'partial')
            self.assertIn('report_read_budget', result['limitations'])
            self.assertFalse(next(row for row in result['coverage'] if row['kind'] == 'report_documents')['complete'])
            freeze(self.priority())
        self.f.f.apply(reports.news.article('two', summary=self.f.item.summary))
        self.f.capture('two', identifier=reports.news.article('two').id)
        with patch('xti.adapters.sqlite_research_reports.MAX_REPORT_ADJACENCY', 1):
            result = self.graph()
            self.assertEqual(result['status'], 'partial')
            self.assertIn('report_adjacency_limit', result['limitations'])
            self.assertTrue(all(row['examined_count'] <= 1 for row in result['coverage'] if row['kind'] == 'report_links'))
            freeze(self.priority())
        with patch('xti.adapters.sqlite_research_reports.MAX_REPORT_BINDINGS', 1):
            result = self.graph()
            self.assertEqual(result['status'], 'partial')
            self.assertIn('report_work_budget', result['limitations'])
            freeze(self.priority())

    def test_tampered_report_journal_never_becomes_a_partial_or_clean_result(self):
        self.f.capture()
        with closing(sqlite3.connect(self.f.path)) as connection, connection:
            connection.execute("UPDATE report_journal SET payload_sha256=?", ('b' * 64,))
        with self.assertRaises(StorageError):
            self.graph()

    def test_many_decisions_keep_latest_state_with_explicit_omitted_evidence_count(self):
        rid = self.f.capture()['record']['id']
        target = self.f.entity()
        for index in range(53):
            self.f.link(rid, target, index + 1, f'link-{index}',
                state='linked' if index % 2 == 0 else 'withdrawn', reason=f'Analyst revision {index}')
        graph = self.graph()
        edge = next(row for row in graph['edges'] if row['relationship_type'] == 'report_reviewed_link')
        self.assertEqual((len(edge['evidence']), edge['evidence_total_count']), (52, 54))
        self.assertEqual((edge['evidence'][1]['status'], edge['evidence'][1]['current']), ('linked', True))
        self.assertIn('source_evidence_limit', graph['limitations'])
        freeze(self.priority())
        doc = next(row for row in graph['nodes'] if row['kind'] == 'report_document')
        self.assertEqual(self.detail(doc)['sections']['history']['total_count'], 54)

    def test_same_read_transaction_keeps_report_revision_before_concurrent_capture(self):
        rid = self.f.capture()['record']['id']
        with closing(sqlite3.connect(self.f.path)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        query = research_query(indicator_type='ipv4', value='192.0.2.10')
        with self.repository.open(query, self.at.isoformat()) as reader:
            reader.node(('ipv4', '192.0.2.10'))
            self.f.f.apply(replace(self.f.item, title='Concurrent version'))
            self.f.capture('concurrent')
            edges = reader.neighbors(('ipv4', '192.0.2.10'))
            keys = {edge.source for edge in edges if edge.relationship_type == 'report_text_mention'}
            self.assertEqual(keys, {('report_document', rid + ':1')})
        self.assertEqual(len([row for row in self.graph()['nodes'] if row['kind'] == 'report_document']), 2)

    def test_engine_reference_missing_revision_and_malformed_identity_return_not_found(self):
        self.f.capture()
        doc = next(row for row in self.graph()['nodes'] if row['kind'] == 'report_document')
        ref = doc['references'][0]
        for value in (str(uuid4()) + ':1', ref['record_id'][:-1] + '2', '../private:1', ref['record_id'][:-1] + '01'):
            with self.subTest(value=value), self.assertRaises(EngineContractError) as error:
                SQLiteEngineRecordRepository(self.f.path).get(parse_record_reference({**ref, 'record_id': value}))
            self.assertEqual(error.exception.code, 'not_found')

    def test_terminal_drilldown_and_cli_engine_json_agree_without_network_or_writes(self):
        self.f.capture()
        before = self.f.path.read_bytes()
        outputs = []
        for args, request in ((['--json', 'research', '192.0.2.10', '--type', 'ipv4'], None),
            (['engine'], {'contract_version': 1, 'request_id': 'report-research', 'operation': 'research.show',
                         'parameters': {'indicator_type': 'ipv4', 'value': '192.0.2.10'}})):
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', StringIO(json.dumps(request))), \
                patch.object(ResearchService, '_now', return_value=self.at.isoformat()):
                code = main(['--data-dir', str(self.f.path.parent), *args])
            self.assertEqual((code, err.getvalue()), (0, ''))
            outputs.append(json.loads(out.getvalue())['data'])
        for key in ('nodes', 'edges', 'paths', 'coverage'):
            self.assertEqual(outputs[0][key], outputs[1][key])
        for lines in (research_lines(outputs[0]), priority_lines(self.priority())):
            self.assertIn('--document-revision 1', '\n'.join(lines))
        self.assertIn('Yanıt alınma:', '\n'.join(research_lines(outputs[0])))
        self.assertEqual(self.f.path.read_bytes(), before)

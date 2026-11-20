"""Real local evidence, bounded grouping, immutable decisions and company fences."""
from copy import deepcopy
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_evidence import SQLiteEvidenceRepository
from xti.application.evidence import EvidenceService
from xti.domain.assets import ValidationError
from xti.domain.reports import ReportError
from xti.domain.research_groups import compose, validate_group, temporal
from xti.domain.group_ledger import project
from tests.test_research import ResearchFixture, NOW, IP

ROOT = dict(indicator_type='domain', value='example.com')


class GroupTests(ResearchFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.repo = SQLiteEvidenceRepository(self.path)
        self.groups = EvidenceService(self.repo, clock=lambda: self.at)

    def preview(self, **options):
        return self.groups.execute('groups.preview', **{**ROOT, **options})

    def row(self, **options):
        return {k: v for k, v in self.preview(**options)['records'][0].items() if k != 'saved'}

    def pair(self):
        self.dns(); self.dns('other.example')
        return self.row()

    def capture(self, row=None, key='capture'):
        row = row or self.row()
        return self.groups.execute('groups.capture', indicator_type=row['root'][0], value=row['root'][1],
            **row['scope'], identifier=row['id'], evidence_sha256=row['evidence_sha256'],
            expected_revision=0, idempotency_key=key)['record']

    def refresh(self, record, key='refresh'):
        return self.groups.execute('groups.refresh', identifier=record['id'],
            expected_revision=record['revision'], idempotency_key=key)['record']

    def review(self, record, **options):
        return self.groups.execute('groups.review', **{**dict(identifier=record['id'],
            evidence_sha256=record['group']['evidence_sha256'], expected_revision=record['revision'],
            decision='accepted', reason='Reviewed shared evidence, no actor attribution',
            idempotency_key='review'), **options})['record']

    def test_four_hops_and_cycles_preserve_bounds(self):
        self.dns(); first, second, third = self.entity('First'), self.entity('Second'), self.entity('Third')
        self.relation(first, indicator=self.ioc())
        self.relation(first, entity=second); self.relation(second, entity=third)
        self.relation(third, entity=first, ref='cycle')
        full = self.graph(max_hops=4)
        self.assertTrue(any(p['hops'] == 4 for p in full['paths']))
        self.assertTrue(all(len(p['node_ids']) == len(set(p['node_ids'])) for p in full['paths']))
        self.assertTrue(all(p['hops'] <= 2 for p in self.graph()['paths']))
        self.assertIn('node_limit', self.graph(max_hops=4, node_limit=2)['limitations'])

    def test_dns_group_keeps_exact_members_time_and_noise_without_attribution(self):
        row = self.pair()
        self.assertEqual({m['key'][1] for m in row['members']}, {'example.com', 'other.example'})
        self.assertEqual(row['temporal']['state'], 'near_observations')
        self.assertEqual(row['temporal']['observed_span_seconds'], 0)
        self.assertEqual(row['attribution'], 'not_assessed')
        self.assertEqual(row['noise_reasons'], ['shared_hosting_possible'])
        self.assertEqual(validate_group(row), row)
        with self.repo.storage._connection(readonly=True) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM cti_relationships').fetchone()[0], 0)

    def test_different_time_and_smallest_window_never_interpolate_activity(self):
        self.dns(observed=NOW-timedelta(days=3)); self.dns('other.example')
        row = self.row()
        self.assertEqual(row['temporal']['state'], 'separated_observations')
        self.assertEqual(row['temporal']['observed_span_seconds'], 3*86400)
        self.assertEqual(self.row(time_window_hours=100)['temporal']['state'], 'near_observations')
        self.dns(observed=NOW-timedelta(hours=1))
        self.assertEqual(self.row()['temporal']['observed_span_seconds'], 3600)
        # Ingest/publication dates must never substitute for actual observation.
        copied = deepcopy(self.row()['members'])
        for edge in copied[0]['edges']:
            for e in edge['evidence']:
                e['time_basis'] = 'response_received_at'
        self.assertEqual(temporal(copied, 24)['state'], 'unknown')

    def test_shared_star_not_transitive_and_names_alone_do_not_group(self):
        self.dns(); self.dns('other.example')
        self.dns('other.example', ip='93.184.216.35'); self.dns('third.example', ip='93.184.216.35')
        self.dns('examplle.com', ip='93.184.216.36')
        rows = self.preview(max_hops=4)['records']
        self.assertEqual(len(rows), 2)
        self.assertEqual({frozenset(m['key'][1] for m in r['members']) for r in rows},
            {frozenset(('example.com','other.example')), frozenset(('other.example','third.example'))})

    def test_revision_replay_proof_conflicts_and_change_history(self):
        row = self.pair(); first = self.capture(row); accepted = self.review(first)
        self.assertTrue(accepted['review_current'])
        self.dns('third.example')
        self.assertEqual(self.capture(row), first)  # original receipt survives changes
        before = self.path.read_bytes()
        with self.assertRaises(ReportError):
            self.review(accepted, idempotency_key='old-proof')
        self.assertEqual(self.path.read_bytes(), before)
        updated = self.refresh(accepted)
        self.assertFalse(updated['review_current'])
        self.assertEqual(updated['changes'][0]['added'], [['domain', 'third.example']])
        self.assertEqual(updated['id'], first['id'])
        self.assertEqual(updated['decision'], accepted['decision'])
        self.assertEqual(updated['history'][0]['snapshot'], row)
        with self.assertRaises(ReportError):
            self.refresh(first, 'stale-revision')
        self.assertEqual(self.refresh(accepted), updated)

    def test_partial_refresh_retains_last_complete_group_and_requires_new_review(self):
        first = self.capture(self.pair()); accepted = self.review(first)
        with patch('xti.adapters.sqlite_research.MAX_DNS_CHECKS', 1):
            partial = self.refresh(accepted)
        self.assertEqual(partial['status'], 'indeterminate')
        self.assertEqual(partial['group'], accepted['group'])
        self.assertFalse(partial['review_current'])
        self.assertFalse(partial['changes'])
        restored = self.refresh(partial, 'complete-again')
        self.assertEqual(restored['status'], 'current')
        self.assertTrue(restored['review_current'])  # identical frozen proof, no fabricated change
        self.assertFalse(restored['changes'])

    def test_absence_partial_absence_does_not_repeat_disappearance(self):
        first = self.capture(self.pair())
        # Controlled graph outcomes; ordinary DNS history is intentionally preserved.
        target = 'xti.adapters.sqlite_groups.preview_in'
        complete = {'coverage_complete': True, 'limitations': []}
        with patch(target, return_value=([], complete)):
            absent = self.refresh(first, 'absent')
        with patch(target, return_value=([], {'coverage_complete': False, 'limitations': ['dns_read_budget']})):
            partial = self.refresh(absent, 'partial')
        with patch(target, return_value=([], complete)):
            again = self.refresh(partial, 'again')
        self.assertEqual(again['status'], 'not_in_view')
        self.assertEqual(len(again['changes']), 1)
        self.assertEqual(again['group'], first['group'])
        returned = self.refresh(again, 'return')
        self.assertEqual(len(returned['changes']), 2)
        self.assertEqual(returned['status'], 'current')

    def test_partial_capture_never_accepts_as_complete(self):
        self.pair()
        with patch('xti.adapters.sqlite_research.MAX_SHOWN_SOURCES', 1):
            self.dns(); row = self.row(); record = self.capture(row)
            self.assertFalse(row['coverage_complete'])
            with self.assertRaises(ValidationError):
                self.review(record)

    def test_queue_compares_fresh_local_proof_and_reads_do_not_mutate(self):
        accepted = self.review(self.capture(self.pair()))
        before = self.files()
        self.assertEqual(self.groups.execute('groups.queue')['records'], [])
        self.assertEqual(self.files(), before)
        self.dns('third.example')
        row = self.groups.execute('groups.queue')['records'][0]
        self.assertEqual(row['queue_state'], 'changed')
        self.assertEqual(row['revision'], accepted['revision'])
        self.assertEqual(self.groups.execute('groups.show', identifier=accepted['id'])['record'], accepted)

    def test_limits_corruption_and_deleted_tail_fail_without_losing_prior_records(self):
        first = self.capture(self.pair())
        before = self.path.read_bytes()
        from xti.domain.engine_jobs import canonical_json
        budget = len(canonical_json(first['history'][0])) + 100
        with patch('xti.domain.group_ledger.MAX_RECORD_BYTES', budget), self.assertRaises(ValidationError):
            self.refresh(first)
        self.assertEqual(self.path.read_bytes(), before)
        with patch('xti.adapters.sqlite_groups.MAX_BYTES', 1), self.assertRaises(StorageError):
            self.groups.execute('groups.list')
        self.refresh(first)
        with self.repo.storage._connection() as c, c:
            c.execute('DELETE FROM research_group_journal WHERE sequence=2')
        with self.assertRaises(StorageError):
            self.groups.execute('groups.list')

    def test_derived_temporal_and_scope_tamper_rejected_even_with_recomputed_hash(self):
        from xti.domain.research import identity
        row = self.pair()
        for field, value in (('temporal', {**row['temporal'], 'state':'unknown'}),
                             ('attribution','same_actor'), ('coverage_complete',False)):
            bad = deepcopy(row); bad[field] = value
            bad['evidence_sha256'] = identity({k:v for k,v in bad.items() if k!='evidence_sha256'})
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate_group(bad)

    def test_backup_restore_and_v85_migration_preserve_old_case_and_new_group(self):
        from tests.case_evidence_v85_fixture import case_evidence_layout_v85
        with self.repo.storage._connection() as c, c:
            case_evidence_layout_v85(c); c.execute('PRAGMA user_version=85')
        with self.assertRaises(StorageError):
            self.preview()
        result = self.repo.storage.migrate()
        self.assertEqual((result['from_version'], result['to_version']), (85, 86))
        with closing(sqlite3.connect(result['backup'])) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 85)
            self.assertFalse(c.execute("SELECT name FROM sqlite_master WHERE name='research_group_journal'").fetchall())
        record = self.capture(self.pair())
        backup, restored = self.root/'group-backup.db', self.root/'restored'/'xti.db'
        self.repo.storage.backup(backup); SQLiteAssetRepository.restore(backup, restored)
        new = EvidenceService(SQLiteEvidenceRepository(restored), clock=lambda: self.at)
        self.assertEqual(new.execute('groups.show', identifier=record['id'])['record'], record)

    def test_cli_and_engine_share_results_and_reject_silent_limit_changes(self):
        self.pair()
        for args in (['groups','preview','domain','example.com'],
                     ['research','example.com','--type','domain','--groups','--max-hops','3']):
            code,out,err = self.invoke(['--data-dir',str(self.data),'--json',*args])
            self.assertEqual((code,err), (0,''), out)
            self.assertEqual(json.loads(out)['data']['records'][0]['id'],self.row()['id'])
        for flags in (['--limit','21'],['--node-limit','5']):
            code,out,err = self.invoke(['--data-dir',str(self.data),'--json','research','example.com','--type','domain','--groups',*flags])
            self.assertEqual(code,2,out+err)
        request = {'contract_version':1,'request_id':'group-read','operation':'groups.preview','parameters':ROOT}
        code,out,err = self.invoke(['--data-dir',str(self.data),'engine'],request)
        self.assertEqual((code,err),(0,''),out)
        self.assertEqual(json.loads(out)['data']['records'][0]['id'],self.row()['id'])

    def test_bounded_monitor_runs_only_local_rechecks_and_preserves_history(self):
        from xti.interfaces.research_groups import monitor_group
        first = self.capture(self.pair()); sleeps=[]
        result = monitor_group(self.path, first['id'], rounds=2, interval_seconds=1, sleep=sleeps.append)
        self.assertEqual(sleeps,[1])
        self.assertEqual([r['revision'] for r in result['rounds']],[2,3])
        self.assertEqual(len(self.groups.execute('groups.show', identifier=first['id'])['record']['history']),3)

    def test_case_freezes_group_and_company_review_preserves_last_saved_state(self):
        from xti.config import Settings
        from xti.interfaces.cli import make_case_service
        from xti.interfaces.cases import evidence_detail_lines
        from xti.interfaces.company_review import make_company_review_service
        accepted = self.review(self.capture(self.pair()))
        cases = make_case_service(Settings(data_dir=self.data))
        case = cases.create('Shared infrastructure', summary='Controlled fixture', reason='Analyst investigation').case
        from contextlib import redirect_stdout, redirect_stderr
        from io import StringIO
        from xti.interfaces.cli import main
        out,err=StringIO(),StringIO()
        with redirect_stdout(out),redirect_stderr(err):
            code=main(['--data-dir',str(self.data),'--json','cases','evidence-add',case.id,
                '--type','research_group','--evidence-id',accepted['id'],'--reason','Preserve reviewed proof'])
        self.assertEqual((code,err.getvalue()),(0,''),out.getvalue())
        link = cases.add_evidence(case.id, 'research_group', accepted['id'], reason='Preserve reviewed proof').evidence
        frozen = json.loads(link.snapshot_json)
        self.assertEqual(frozen['group'], accepted['group'])
        self.assertTrue(frozen['review_current'])
        self.assertIn('example.com', '\n'.join(evidence_detail_lines(link)))
        self.dns('third.example'); self.refresh(accepted)
        self.assertEqual(json.loads(link.snapshot_json), frozen)
        graph = self.graph()
        self.assertTrue(any(n['record_type']=='case' for n in graph['nodes']))
        view = make_company_review_service(self.path).show()
        self.assertEqual(view['groups']['records'][0]['revision'], 3)
        self.assertFalse(view['groups']['records'][0]['review_current'])

    def test_certificate_requires_actual_presentation_and_large_groups_are_explicitly_omitted(self):
        from tests.test_research_surface import SurfaceResearchTests
        f=SurfaceResearchTests(); f.setUp(); self.addCleanup(f.doCleanups)
        f.tls('first.example',ip='192.0.2.10'); f.tls('second.example',ip='192.0.2.11')
        service=EvidenceService(SQLiteEvidenceRepository(f.path), clock=lambda:f.at)
        rows=service.execute('groups.preview',indicator_type='domain',value='first.example')['records']
        row=next(r for r in rows if r['rule']=='shared_certificate')
        self.assertEqual({m['key'][1] for m in row['members']},{'first.example','second.example'})
        self.assertIn('shared_certificate_not_ownership',row['noise_reasons'])
        self.pair()
        with patch('xti.domain.research_groups.MAX_MEMBERS',1):
            result=self.preview()
        self.assertEqual(result['records'],[])
        self.assertFalse(result['coverage_complete'])
        self.assertEqual(result['omitted_group_count'],1)
        self.assertIn('group_size_limit',result['limitations'])

    def test_omitted_large_group_keeps_remaining_capture_partial_and_unacceptable(self):
        self.pair()
        self.dns('other.example', ip='93.184.216.35')
        self.dns('third.example', ip='93.184.216.35')
        self.dns('fourth.example', ip='93.184.216.35')
        with patch('xti.domain.research_groups.MAX_MEMBERS', 2):
            result = self.preview(max_hops=4)
            self.assertEqual(len(result['records']), 1)
            self.assertEqual(result['omitted_group_count'], 1)
            self.assertFalse(result['records'][0]['coverage_complete'])
            record = self.capture(result['records'][0])
            before = self.path.read_bytes()
            with self.assertRaises(ValidationError):
                self.review(record)
            self.assertEqual(self.path.read_bytes(), before)

    def test_queue_paginates_examined_groups_even_when_first_window_has_no_pending_rows(self):
        self.pair(); self.dns('other.example',ip='93.184.216.35'); self.dns('third.example',ip='93.184.216.35')
        rows=self.preview(max_hops=4)['records']
        for index,row in enumerate(rows):
            record=self.capture(row,key='capture-'+str(index))
            if index==0:
                self.review(record)
        first=self.groups.execute('groups.queue',limit=1)
        self.assertEqual(first['records'],[])
        self.assertEqual(first['examined_count'],1)
        self.assertTrue(first['has_more'])
        second=self.groups.execute('groups.queue',limit=1,offset=first['next_offset'],expected_snapshot=first['snapshot_id'])
        self.assertEqual(second['records'][0]['queue_state'],'needs_review')

    def test_organization_report_and_html_include_group_only_for_explicit_domain_root(self):
        from tests.test_organization_report import OrganizationReportTests
        f=OrganizationReportTests(); f.setUp(); self.addCleanup(f.doCleanups)
        f.link()
        self.dns(path=f.database); self.dns('other.example',path=f.database)
        service=EvidenceService(SQLiteEvidenceRepository(f.database),clock=lambda:self.at)
        row=service.execute('groups.preview',**ROOT)['records'][0]
        service.execute('groups.capture',**ROOT,**row['scope'],identifier=row['id'],
            evidence_sha256=row['evidence_sha256'],expected_revision=0,idempotency_key='capture')
        report=f.report()
        section=next(s for s in report.targets[0].sections if s.kind=='research_groups')
        self.assertEqual(section.items[0].id,row['id'])
        output=f.data.parent.resolve()/'group-report.html'
        f.result('organizations','export',f.organization['id'],'--output',str(output))
        self.assertIn(row['id'],output.read_text())


class ReportGroupTests(unittest.TestCase):
    def test_duplicate_document_content_forms_one_group_and_does_not_invent_event_time(self):
        from tests.test_reports import ReportTests, NOW
        f=ReportTests(); f.setUp(); self.addCleanup(f.doCleanups)
        f.capture()
        from tests.test_news_storage import article
        duplicate=article('second-copy', title=f.item.title, summary=f.item.summary)
        f.f.apply(duplicate); f.capture('copy', identifier=duplicate.id)
        service=EvidenceService(SQLiteEvidenceRepository(f.path), clock=lambda:NOW)
        rows=service.execute('groups.preview', indicator_type='ipv4', value='192.0.2.10')['records']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['temporal']['state'],'unknown')
        self.assertEqual(len(rows[0]['anchors']),2)
        self.assertIn('duplicate_document_content',rows[0]['noise_reasons'])
        self.assertEqual(rows[0]['attribution'],'not_assessed')


class GroupCompanyTests(unittest.TestCase):
    def test_same_group_id_and_request_key_are_isolated_and_writes_need_workspace_fence(self):
        from tests.test_platform_isolation import PlatformIsolationTests
        f=PlatformIsolationTests(); f.setUp(); self.addCleanup(f.doCleanups)
        helper=GroupTests(); helper.setUp(); self.addCleanup(helper.doCleanups)
        groups={}
        for company in ('alpha','beta'):
            path=f.contexts[company].database
            helper.dns(path=path); helper.dns('other.example',path=path)
            row=f.complete(company,f.request('groups.preview',ROOT))['records'][0]
            request={**ROOT, **row['scope'], 'identifier':row['id'], 'evidence_sha256':row['evidence_sha256'],
                'expected_revision':0,'idempotency_key':'same-key','expected_workspace_id':f.contexts[company].workspace_id}
            groups[company]=f.complete(company,f.request('groups.capture',request))['record']
        self.assertEqual(groups['alpha']['id'],groups['beta']['id'])
        self.assertNotEqual(groups['alpha']['history'][0]['id'],groups['beta']['history'][0]['id'])
        request={'identifier':groups['alpha']['id'],'expected_revision':1,'idempotency_key':'refresh',
            'expected_workspace_id':f.contexts['beta'].workspace_id}
        f.rejected('alpha',f.request('groups.refresh',request),error='scope_mismatch')
        request.pop('expected_workspace_id')
        f.rejected('alpha',f.request('groups.refresh',request),error='invalid_parameters')
        f.rejected('alpha',f.request('groups.show',{'identifier':'0'*64}),error='not_found')

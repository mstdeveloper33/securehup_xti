"""Current explicit organization membership scopes one readonly period snapshot."""
from contextlib import closing
from dataclasses import asdict
from datetime import timedelta
import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.application.organizations import OrganizationService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.application.ransomlook_watches import RansomLookWatchService
from xti.domain.assets import ValidationError
from xti.interfaces.periodic_changes import periodic_changes_lines
from tests import test_periodic_changes as base
from tests.test_brand_username_watches import github, NOW
from tests.test_organizations_core import RecordingLock
from tests.test_ransomware_history import snapshot as tc_snapshot
from tests.test_ransomlook_history import snapshot as rl_snapshot
from tests.test_threatcluster_ransomware import claim
from tests.test_ransomlook_ransomware import post


class OrganizationPeriodicChangesTests(unittest.TestCase):
    finding = base.PeriodicChangesTests.finding
    report = base.PeriodicChangesTests.report
    social = base.PeriodicChangesTests.social

    def setUp(self):
        base.PeriodicChangesTests.setUp(self)
        self.organizations = OrganizationService(
            SQLiteOrganizationRepository(self.path), RecordingLock(), clock=lambda: NOW,
        )
        self.organization = self.organizations.add('First organization', reason='Açık kullanıcı seçimi.').organization
        self.second = self.organizations.add('Other organization', reason='Açık kullanıcı seçimi.').organization

    def link(self, kind='domain', value='example.com', organization=None):
        return self.organizations.link(
            (organization or self.organization).id, kind=kind, value=value,
            reason='Bu kuruluş için açıkça seçildi.',
        ).link

    @staticmethod
    def rows(report):
        return [row for section in report.sections for group in
                (section.changes, section.baselines, section.failures) for row in group]

    def test_only_explicit_roots_and_watches_are_selected_without_inferred_subdomains(self):
        selected = self.finding()
        excluded = self.finding('outside-candidate.example', asset=self.other)
        child, _ = self.storage.add('sub.example.com')
        sub = self.finding('child-candidate.example', asset=child)
        source = self.social({'GitHub': github()}, {'GitHub': github()})
        selected_watch = source.add('Explicit watch', 'samplebrand', platforms=('GitHub',)).watch
        inferred_watch = source.add('example.com', 'samplebrand', platforms=('GitHub',)).watch
        source.run(selected_watch.id)
        source.run(inferred_watch.id)
        self.link()
        self.link('domain', 'other.example', self.second)
        self.link('username-watch', selected_watch.id)
        self.link('username-watch', inferred_watch.id, self.second)
        report = self.report(organization_id=self.organization.id)
        rows = self.rows(report)
        identifiers = {row.record_id for row in rows}
        self.assertIn(selected, identifiers)
        self.assertTrue({excluded, sub}.isdisjoint(identifiers))
        self.assertEqual({row.watch_id for row in rows if row.watch_id}, {selected_watch.id})
        self.assertTrue(all(row.scope_id in {'example.com', selected_watch.id} for row in report.coverage if row.scope_kind != 'global-source'))
        self.assertNotIn(inferred_watch.id, json.dumps(asdict(report)))
        self.assertIn('geçmişteki kuruluş üyeliği', ' '.join(report.notes))
        self.assertEqual(report.organization_scope.organization.id, self.organization.id)

    def test_current_links_apply_to_old_evidence_and_revocation_never_falls_back_to_all(self):
        selected = self.finding(at=NOW - timedelta(hours=2))
        self.finding(asset=self.other)
        self.organizations.clock = lambda: NOW + timedelta(hours=1)
        link = self.link()
        self.assertEqual([row.record_id for row in self.rows(self.report(organization_id=self.organization.id))], [selected])
        self.organizations.unlink(self.organization.id, link.id, reason='Bağlantı geri çekildi.')
        empty = self.report(organization_id=self.organization.id)
        self.assertEqual((self.rows(empty), empty.coverage), ([], ()))
        self.assertEqual(empty.organization_scope.excluded_link_count, 1)
        self.link()
        self.organizations.revoke(self.organization.id, reason='Kuruluş geri çekildi.')
        revoked = self.report(organization_id=self.organization.id)
        self.assertEqual((self.rows(revoked), revoked.coverage), ([], ()))
        self.assertIn('geri çekilmiş', '\n'.join(periodic_changes_lines(revoked)))
        self.assertEqual(self.report().sections[0].total_change_count, 2)

    def test_inactive_target_is_excluded_although_organization_link_still_exists(self):
        service = self.social({'GitHub': github()})
        watch = service.add('Selected watch', 'samplebrand', platforms=('GitHub',)).watch
        service.run(watch.id)
        self.link('username-watch', watch.id)
        self.assertEqual(len(self.rows(self.report(organization_id=self.organization.id))), 1)
        service.revoke(watch.id, reason='Kapsamdan çıkarıldı.')
        report = self.report(organization_id=self.organization.id)
        self.assertEqual((self.rows(report), report.coverage), ([], ()))
        self.assertEqual(report.organization_scope.excluded_link_count, 1)

    def test_family_ids_stay_separate_and_ransomware_source_history_is_explicit_shared_context(self):
        for family, kind, claims_type, watches_type, service_type, snapshot, make in (
            ('threatcluster', 'ransomware-watch', SQLiteRansomwareClaimRepository,
             SQLiteRansomwareWatchRepository, RansomwareWatchService, tc_snapshot, claim),
            ('ransomlook', 'ransomlook-watch', SQLiteRansomLookClaimRepository,
             SQLiteRansomLookWatchRepository, RansomLookWatchService, rl_snapshot, post),
        ):
            claims = claims_type(self.path)
            source = claims.apply(snapshot([make('Example Holding')], fetched_at=NOW),
                                  started_at=NOW.isoformat(), finished_at=NOW.isoformat(), item_limit=100)
            service = service_type(watches_type(self.path), claims, clock=lambda: NOW)
            kwargs = {'kind': 'organization'}
            watch = service.add('Selected ' + family, 'Example', match_mode='contains', **kwargs).watch
            unrelated = service.add('Unrelated ' + family, 'Example', match_mode='contains', **kwargs).watch
            selected_run = service.run(watch.id)
            service.run(unrelated.id)
            self.link(kind, watch.id)
            section = next(s for s in self.report(organization_id=self.organization.id).sections if s.family == family)
            self.assertEqual(section.total_baseline_count, 1)
            row = section.baselines[0]
            self.assertEqual((row.watch_id, row.run_id, row.source_run_id), (watch.id, selected_run.run.id, source.run.id))
            self.assertIn(row.run_id, row.commands[0])
            self.assertEqual(row.value_changes[0].after, 'reported')
            self.assertNotIn(unrelated.id, json.dumps(asdict(self.report(organization_id=self.organization.id))))

    def test_offset_reaches_rows_after_first_500_with_stable_counts_and_no_overlap(self):
        self.link()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executemany('INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)', (
                (str(uuid4()), self.asset.id, self.asset.value, f'candidate-{i}.example',
                 'rules-v1', '["typo"]', 'new', NOW.isoformat(), NOW.isoformat())
                for i in range(503)
            ))
        first = self.report(organization_id=self.organization.id, limit=500).sections[0]
        second = self.report(organization_id=self.organization.id, limit=500, offset=500).sections[0]
        self.assertEqual((first.total_change_count, second.total_change_count), (503, 503))
        self.assertEqual((len(first.changes), len(second.changes)), (500, 3))
        self.assertEqual(len({r.record_id for r in first.changes + second.changes}), 503)
        self.assertEqual((first.omitted_count, second.omitted_count), (3, 500))
        self.assertEqual(second.offset, 500)
        self.assertEqual(second, self.report(organization_id=self.organization.id, limit=500, offset=500).sections[0])

    def test_validation_precedes_read_and_unknown_org_never_becomes_empty_success(self):
        for values in ({'domain': 'example.com', 'organization_id': self.organization.id},
                       {'organization_id': 'not-an-id'}, {'offset': True}, {'offset': -1}, {'offset': 1_000_001}):
            with self.subTest(values=values), patch.object(self.repo, 'read', side_effect=AssertionError('read')):
                with self.assertRaises(ValidationError):
                    self.report(**values)
        with self.assertRaises(ValidationError):
            self.report(organization_id=str(uuid4()))

    def test_readonly_validation_and_corrupt_membership_fail_closed(self):
        self.link()
        self.finding()
        before = self.path.read_bytes()
        with patch('socket.socket.connect', side_effect=AssertionError('network')), patch(
            'xti.adapters.worker_lock.LocalExecutionLock.acquire', side_effect=AssertionError('write lock'),
        ):
            self.report(organization_id=self.organization.id)
        self.assertEqual(before, self.path.read_bytes())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE organization_links SET target_value=?', ('missing.example',))
        damaged = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.report(organization_id=self.organization.id)
        self.assertEqual(damaged, self.path.read_bytes())

    def test_multi_domain_attempt_keeps_selected_targets_and_masks_unrelated_failure_text(self):
        self.link()
        jobs = SQLiteJobRepository(self.path)
        with patch('xti.adapters.sqlite_jobs._now', return_value=NOW.isoformat()):
            job = jobs.create(('example.com', 'other.example'), False, 'crt.sh', 'rules-v1')
            attempt = jobs.start(job.id)
            jobs.finish(attempt.id, 'failed', error='other.example external failure detail')
        report = self.report(organization_id=self.organization.id)
        section = next(item for item in report.sections if item.family == 'brand')
        self.assertEqual(section.total_failure_count, 1)
        row = section.failures[0]
        self.assertEqual((row.record_id, row.asset_value), (attempt.id, 'example.com'))
        self.assertTrue(row.shared_scope)
        self.assertIn('kuruluş dışındaki hedefleri', row.evidence_note)
        self.assertNotIn('other.example', json.dumps(asdict(report)))
        relevant = [item for item in report.coverage if item.family == 'brand' and item.source == 'crt.sh']
        self.assertEqual([(item.scope_id, item.failed_count) for item in relevant], [('example.com', 1)])

    def test_links_and_evidence_share_the_same_snapshot(self):
        self.link()
        first = self.finding()
        second = self.finding(asset=self.other)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        original = self.repo._domains
        changed = []
        def interleave(*args):
            if not changed:
                changed.append(True)
                self.link('domain', 'other.example')
            return original(*args)
        with patch.object(self.repo, '_domains', side_effect=interleave):
            report = self.report(organization_id=self.organization.id)
        self.assertEqual({row.record_id for row in self.rows(report)}, {first})
        self.assertEqual(len(report.organization_scope.effective_links), 1)
        self.assertEqual({row.record_id for row in self.rows(self.report(organization_id=self.organization.id))}, {first, second})

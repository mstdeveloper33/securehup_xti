"""Local period boundaries, source gaps and conservative cross-family differences."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_periodic_changes import SQLitePeriodicChangesRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.application.ransomlook_watches import RansomLookWatchService
from xti.application.periodic_changes import PeriodicChangesService
from xti.domain.assets import ValidationError
from xti.domain.surface import SurfaceCandidateEvidence, SurfaceDiscoveryRunRequest
from xti.interfaces.periodic_changes import periodic_changes_lines
from xti.ports.discovery import SourceError
from tests.test_brand_username_watches import FakeSource, github, NOW
from tests.test_ransomware_history import snapshot as tc_snapshot
from tests.test_ransomlook_history import snapshot as rl_snapshot
from tests.test_threatcluster_ransomware import claim
from tests.test_ransomlook_ransomware import post
END = NOW + timedelta(hours=6)


class PeriodicChangesTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _ = self.storage.add('example.com')
        self.other, _ = self.storage.add('other.example')
        self.repo = SQLitePeriodicChangesRepository(self.path)

    def report(self, *, end=END, **values):
        return PeriodicChangesService(self.repo, clock=lambda: end).show(**values)

    def finding(
        self,
        domain='candidate.example',
        *,
        at=NOW,
        asset=None,
        rule='rules-v1',
        last_seen=None,
    ):
        asset = asset or self.asset
        identifier = str(uuid4())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                'INSERT INTO findings VALUES (?,?,?,?,?,?,?, ?,?)',
                (
                    identifier,
                    asset.id,
                    asset.value,
                    domain,
                    rule,
                    '["typo"]',
                    'new',
                    at.isoformat(),
                    (last_seen or at).isoformat(),
                ),
            )
        return identifier

    def social(self, *responses, at=NOW):
        return BrandUsernameWatchService(
            SQLiteBrandUsernameWatchRepository(self.path),
            FakeSource(*responses),
            clock=lambda: at,
        )

    def test_half_open_local_time_window_and_new_not_last_observed(self):
        start = END - timedelta(days=1)
        included = self.finding('a.example', at=start)
        self.finding('b.example', at=END)
        self.finding('c.example', at=start - timedelta(seconds=1), last_seen=NOW)
        report = self.report()
        section = next((section for section in report.sections if section.family == 'brand'))
        self.assertEqual([item.record_id for item in section.changes], [included])
        self.assertEqual(report.window.start_at, start.isoformat())
        self.assertEqual(report.window.end_at, END.isoformat())
        self.assertFalse(hasattr(report, 'threat_count'))

    def test_seven_day_window_and_input_validation_read_clock_once(self):
        self.finding(at=END - timedelta(days=6))
        self.assertEqual(self.report(days=1).sections[0].total_change_count, 0)
        self.assertEqual(self.report(days=7).sections[0].total_change_count, 1)
        calls = []
        service = PeriodicChangesService(self.repo, clock=lambda: calls.append(True) or END)
        service.show()
        self.assertEqual(calls, [True])
        for values in (
            {'days': True},
            {'days': 2},
            {'limit': True},
            {'limit': 0},
            {'domain': 'https://example.com'},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                service.show(**values)
        with self.assertRaises(ValidationError):
            PeriodicChangesService(self.repo, clock=lambda: datetime(2026, 10, 31)).show()

    def test_exact_counts_and_rule_versions_survive_view_limit(self):
        self.finding('same.example', rule='rule1')
        self.finding('same.example', rule='rule2')
        report = self.report(limit=1)
        section = report.sections[0]
        self.assertEqual(
            (section.total_change_count, len(section.changes), section.omitted_count),
            (2, 1, 1),
        )
        self.assertIn(section.changes[0].rule_version, {'rule1', 'rule2'})
        self.assertGreater(report.coverage_total_count, len(report.coverage))
        self.assertEqual(
            report.coverage_omitted_count,
            report.coverage_total_count - len(report.coverage),
        )
        self.assertIn('gösterilmeyen 1 satır', '\n'.join(periodic_changes_lines(report)))

    def test_social_baseline_and_later_missing_profile_are_separate(self):
        service = self.social(
            {'GitHub': github()},
            {},
            SourceError('Kontrollü kaynak hatası.'),
            at=NOW,
        )
        watch = service.add('Marka izlemesi', 'samplebrand', platforms=('GitHub',)).watch
        baseline = service.run(watch.id)
        service.clock = lambda: NOW + timedelta(minutes=1)
        changed = service.run(watch.id)
        service.clock = lambda: NOW + timedelta(minutes=2)
        failed = service.run(watch.id)
        section = next((value for value in self.report().sections if value.family == 'username'))
        self.assertEqual(
            (section.total_baseline_count, section.total_change_count, section.total_failure_count),
            (1, 1, 1),
        )
        self.assertEqual(section.baselines[0].run_id, baseline.run.id)
        self.assertEqual(section.changes[0].action, 'no_longer_reported')
        self.assertEqual(section.changes[0].previous_run_id, baseline.run.id)
        self.assertEqual(section.failures[0].run_id, failed.run.id)
        self.assertIn('Artık raporlanmıyor', '\n'.join(periodic_changes_lines(self.report())))

    def test_previous_run_outside_window_is_not_counted_again(self):
        service = self.social({'GitHub': github()}, {}, at=NOW)
        watch = service.add('Marka izlemesi', 'samplebrand', platforms=('GitHub',)).watch
        first = service.run(watch.id)
        service.clock = lambda: NOW + timedelta(hours=2)
        second = service.run(watch.id)
        report = self.report(end=NOW + timedelta(days=1, hours=1))
        section = next((value for value in report.sections if value.family == 'username'))
        self.assertEqual((section.total_baseline_count, section.total_change_count), (0, 1))
        self.assertEqual(
            (section.changes[0].run_id, section.changes[0].previous_run_id),
            (second.run.id, first.run.id),
        )

    def test_ransomware_sources_keep_baselines_changes_and_source_ids_separate(self):
        for family, claims_type, watches_type, service_type, snapshot, make in (
            (
                'threatcluster',
                SQLiteRansomwareClaimRepository,
                SQLiteRansomwareWatchRepository,
                RansomwareWatchService,
                tc_snapshot,
                claim,
            ),
            (
                'ransomlook',
                SQLiteRansomLookClaimRepository,
                SQLiteRansomLookWatchRepository,
                RansomLookWatchService,
                rl_snapshot,
                post,
            ),
        ):
            claims = claims_type(self.path)
            watches = watches_type(self.path)
            at = NOW
            first = claims.apply(
                snapshot([make('Example Holding')], fetched_at=at),
                started_at=at.isoformat(),
                finished_at=(at + timedelta(seconds=1)).isoformat(),
                item_limit=100,
            )
            service = service_type(watches, claims, clock=lambda: NOW + timedelta(seconds=2))
            watch = service.add(
                'Example kuruluşu',
                'Example',
                kind='organization',
                match_mode='contains',
            ).watch
            base = service.run(watch.id)
            at = NOW + timedelta(minutes=1)
            second = claims.apply(
                snapshot(
                    [make('Example Holding'), make('Example New', group='another-group')],
                    fetched_at=at,
                ),
                started_at=at.isoformat(),
                finished_at=(at + timedelta(seconds=1)).isoformat(),
                item_limit=100,
            )
            service.clock = lambda: NOW + timedelta(minutes=1, seconds=2)
            current = service.run(watch.id)
            section = next((value for value in self.report().sections if value.family == family))
            self.assertEqual((section.total_baseline_count, section.total_change_count), (1, 1))
            self.assertEqual(section.baselines[0].source_run_id, first.run.id)
            self.assertEqual(section.changes[0].source_run_id, second.run.id)
            self.assertEqual(section.changes[0].previous_run_id, base.run.id)
            self.assertEqual(section.changes[0].watch_id, watch.id)
            self.assertEqual(section.changes[0].run_id, current.run.id)

    def test_new_surface_candidate_is_counted_once_across_multiple_source_observations(self):
        repo = SQLiteSurfaceCandidateRepository(self.path)
        for minute, digest in ((1, 'a' * 64), (2, 'b' * 64)):
            at = NOW + timedelta(minutes=minute)
            evidence = (SurfaceCandidateEvidence(
                'sub.example.com',
                'crt.sh',
                'crt.sh',
                digest,
                'sub.example.com',
                (NOW - timedelta(days=30)).isoformat(),
            ),)
            request = SurfaceDiscoveryRunRequest(
                'complete',
                'https://crt.sh/',
                at.isoformat(),
                at.isoformat(),
                1,
                0,
                0,
                (),
                1,
                None,
            )
            repo.record_discovery(self.asset.id, self.asset.value, evidence, request)
        section = next((value for value in self.report().sections if value.family == 'surface'))
        self.assertEqual(section.total_change_count, 1)
        self.assertEqual(section.changes[0].value, 'sub.example.com')
        self.assertIsNotNone(section.changes[0].target_record_id)

    def test_domain_scope_never_infers_social_or_ransomware_ownership(self):
        self.finding()
        self.finding('other-candidate.example', asset=self.other)
        service = self.social({'GitHub': github()})
        watch = service.add('example.com', 'samplebrand', platforms=('GitHub',)).watch
        service.run(watch.id)
        report = self.report(domain='EXAMPLE.COM.')
        self.assertEqual([section.family for section in report.sections], ['brand', 'surface'])
        self.assertEqual(report.sections[0].total_change_count, 1)
        self.assertTrue(all((item.scope_id == 'example.com' for item in report.coverage)))
        with self.assertRaises(ValidationError):
            self.report(domain='missing.example')

    def test_no_history_success_zero_and_outside_period_are_distinct(self):
        repo = SQLiteSurfaceCandidateRepository(self.path)
        at = NOW - timedelta(days=2)
        request = SurfaceDiscoveryRunRequest(
            'complete',
            'https://crt.sh/',
            at.isoformat(),
            at.isoformat(),
            0,
            0,
            0,
            (),
            0,
            None,
        )
        repo.record_discovery(self.asset.id, self.asset.value, (), request)
        report = self.report(domain='example.com')
        discovery = next((item for item in report.coverage if item.family == 'surface' and item.source == 'crt.sh'))
        scan = next((item for item in report.coverage if item.family == 'brand' and item.source == 'crt.sh'))
        self.assertEqual(
            (discovery.coverage_state, scan.coverage_state),
            ('not_checked', 'no_history'),
        )
        request = SurfaceDiscoveryRunRequest(
            'complete',
            'https://crt.sh/',
            NOW.isoformat(),
            NOW.isoformat(),
            0,
            0,
            0,
            (),
            0,
            None,
        )
        repo.record_discovery(self.asset.id, self.asset.value, (), request)
        updated = next((item for item in self.report(domain='example.com').coverage if item.family == 'surface' and item.source == 'crt.sh'))
        self.assertEqual(
            (updated.coverage_state, updated.complete_count, updated.window_run_count),
            ('observed', 1, 1),
        )

    def test_readonly_no_network_and_invalid_selected_data_never_becomes_empty_success(self):
        service = self.social({'GitHub': github()})
        watch = service.add('Marka izlemesi', 'samplebrand', platforms=('GitHub',)).watch
        service.run(watch.id)
        before = self.path.read_bytes()
        with patch('socket.create_connection', side_effect=AssertionError('network called')):
            self.report()
        self.assertEqual(before, self.path.read_bytes())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE brand_username_watch_runs SET result_sha256=?', ('0' * 64,))
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.report()
        self.assertEqual(before, self.path.read_bytes())

    def test_all_families_share_one_sqlite_read_snapshot(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        original = self.repo._domains
        called = []

        def interleaved(*args):
            original(*args)
            if not called:
                called.append(True)
                self.social().add('Sonradan eklenen', 'newbrand', platforms=('GitHub',))
        with patch.object(self.repo, '_domains', side_effect=interleaved):
            report = self.report()
        self.assertFalse(any((item.family == 'username' for item in report.coverage)))
        self.assertTrue(any((item.family == 'username' for item in self.report().coverage)))
if __name__ == '__main__':
    unittest.main()

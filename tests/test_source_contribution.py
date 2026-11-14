"""Explicit sets, true completion denominators and no inferred provider attribution."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_source_contribution import SQLiteSourceContributionRepository
from xti.application.source_contribution import SourceContributionService
from xti.domain.assets import ValidationError
from xti.domain.discovery import ScanResult
from xti.domain.findings import ImportSummary
from xti.domain.surface import SurfaceCandidateEvidence, SurfaceDiscoveryRunRequest
from xti.interfaces.source_contribution import source_contribution_lines
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


class SourceContributionTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _ = self.storage.add('example.com')
        self.other, _ = self.storage.add('other.example')
        self.repo = SQLiteSourceContributionRepository(self.path)
        self.service = SourceContributionService(self.repo)
        self.jobs = SQLiteJobRepository(self.path)

    def surface(self, provider, names, *, status='complete', asset=None, minute=0):
        asset = asset or self.asset
        evidence = tuple((SurfaceCandidateEvidence(
            name,
            provider,
            f'{provider}:saved-reference',
            hashlib.sha256(f'{provider}:{name}'.encode()).hexdigest(),
            name,
            None,
        ) for name in names))
        at = (NOW + timedelta(minutes=minute)).isoformat()
        request = SurfaceDiscoveryRunRequest(
            status,
            'https://crt.sh/' if provider == 'crt.sh' else 'https://github.com/laramies/theHarvester',
            at,
            at,
            len(names),
            0,
            0,
            (),
            len(set(names)),
            'Kontrollü kaynak hatası.' if status == 'failed' else None,
            provider,
        )
        return SQLiteSurfaceCandidateRepository(self.path).record_discovery(asset.id, asset.value, evidence, request)

    def scan(
        self,
        provider,
        domains=(),
        *,
        status='complete',
        targets=('example.com',),
        rule='rule-v1',
        typos=False,
    ):
        job = self.jobs.create(targets, typos, provider, rule)
        if status == 'queued':
            return (job, None)
        attempt = self.jobs.start(job.id)
        if status == 'running':
            return (job, attempt)
        result = None
        if status in {'complete', 'partial'}:
            result = ScanResult(
                targets,
                attempt.started_at,
                datetime.now(timezone.utc).isoformat(),
                status,
                (),
                ImportSummary(0, 0, 0, 0, 0),
                tuple(domains),
            )
        finished = self.jobs.finish(
            attempt.id,
            status,
            result=result,
            error='Kontrollü hata.' if status in {'failed', 'interrupted'} else None,
        )
        return (job, finished)

    def test_surface_sets_overlap_unique_domains_review_and_repetition(self):
        self.surface('crt.sh', ('a.example.com', 'b.example.com'))
        self.surface('theharvester', ('b.example.com', 'c.example.com'))
        self.surface('crt.sh', ('a.example.com', 'b.example.com'), minute=1)
        self.surface('crt.sh', ('outside.other.example',), asset=self.other)
        with closing(sqlite3.connect(self.path)) as connection:
            candidate = connection.execute("SELECT id FROM surface_candidates WHERE domain='c.example.com'").fetchone()[0]
        SQLiteSurfaceCandidateRepository(self.path).decide_candidate(
            candidate,
            'rejected',
            'Örnek kapsam kararı.',
            (NOW + timedelta(minutes=2)).isoformat(),
        )
        group = self.service.show('example.com', family='surface').groups[0]
        self.assertEqual(group.union_domains.total_count, 3)
        self.assertEqual(group.overlaps[0].domains.total_count, 1)
        self.assertEqual(group.overlaps[0].domains.items[0].domain, 'b.example.com')
        self.assertEqual(group.comparison_state, 'local_comparison')
        for source in group.sources:
            self.assertEqual(
                (
                    source.all_domains.total_count,
                    source.shared_domains.total_count,
                    source.exclusive_domains.total_count,
                ),
                (2, 1, 1),
            )
        harvester = group.sources[1]
        self.assertEqual(dict(harvester.current_review_counts)['rejected'], 1)
        self.assertEqual(harvester.exclusive_domains.items[0].review_statuses, ('rejected',))
        self.assertEqual(group.sources[0].outcomes.complete, 2)
        self.assertEqual(len(group.sources[0].all_domains.items[0].evidence_ids), 1)

    def test_surface_no_history_and_complete_empty_are_not_the_same(self):
        empty = self.service.show('example.com', family='surface').groups[0]
        self.assertIsNone(empty.sources[0].outcomes.completion_rate)
        self.surface('crt.sh', ())
        self.surface('theharvester', (), status='failed')
        group = self.service.show('example.com', family='surface').groups[0]
        self.assertEqual(group.sources[0].complete_empty_attempt_count, 1)
        self.assertEqual(group.sources[0].outcomes.completion_rate, 1)
        self.assertEqual(group.sources[1].outcomes.completion_rate, 0)
        self.assertEqual(group.comparison_state, 'insufficient_history')
        self.assertEqual(group.union_domains.total_count, 0)

    def test_completion_denominator_excludes_running_and_queued(self):
        for status in ('complete', 'partial', 'failed', 'interrupted'):
            self.scan('crt.sh', status=status)
        self.scan('crt.sh', status='queued')
        self.scan('crt.sh', status='running')
        source = self.service.show('example.com', family='brand').groups[0].sources[0]
        self.assertEqual(
            (source.outcomes.completion_numerator, source.outcomes.completion_denominator),
            (1, 4),
        )
        self.assertEqual(source.outcomes.completion_rate, 0.25)
        self.assertEqual((source.outcomes.running, source.queued_job_count), (1, 1))
        self.assertEqual(source.resultless_attempt_count, 3)
        self.assertEqual(source.complete_empty_attempt_count, 1)

    def test_brand_rule_typos_groups_and_multiple_targets_remain_separate(self):
        first_job, first = self.scan('crt.sh', ('a.test', 'b.test'))
        self.scan('urlscan', ('b.test', 'c.test'))
        self.scan('crt.sh', ('not-attributable.test',), targets=('example.com', 'other.example'))
        self.scan('crt.sh', ('other-rule.test',), rule='rule-v2', typos=True)
        groups = self.service.show('example.com', family='brand').groups
        self.assertEqual(len(groups), 2)
        old = next((group for group in groups if group.rule_version == 'rule-v1'))
        self.assertEqual(old.union_domains.total_count, 3)
        self.assertEqual(old.overlaps[0].domains.items[0].domain, 'b.test')
        source = old.sources[0]
        self.assertEqual(source.excluded_multi_target_attempt_count, 1)
        self.assertEqual(source.excluded_multi_target_outcomes.complete, 1)
        self.assertEqual(source.outcomes.completion_denominator, 1)
        self.assertEqual(source.exclusive_domains.items[0].evidence_ids, (first.id,))
        self.assertEqual(source.exclusive_domains.items[0].record_ids, (first_job.id,))
        newer = next((group for group in groups if group.rule_version == 'rule-v2'))
        self.assertTrue(newer.typos)
        self.assertEqual(newer.union_domains.items[0].domain, 'other-rule.test')

    def test_free_text_observation_source_never_creates_provider_attribution(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                'INSERT INTO observations VALUES (?,?,?,?,?,?,?,?)',
                (
                    str(uuid4()),
                    'fake.test',
                    'fake.test',
                    'crt.sh:claimed-name',
                    'a' * 64,
                    1,
                    None,
                    NOW.isoformat(),
                ),
            )
        report = self.service.show('example.com', family='brand')
        self.assertEqual(report.groups, ())
        self.assertTrue(any(('bilinmiyor' in note for note in report.notes)))

    def test_domain_pages_change_details_not_totals(self):
        self.surface('crt.sh', ('a.example.com', 'b.example.com', 'c.example.com'))
        first = self.service.show('example.com', family='surface', detail_limit=1)
        second = self.service.show('example.com', family='surface', detail_limit=1, detail_offset=1)
        first_page = first.groups[0].union_domains
        second_page = second.groups[0].union_domains
        self.assertEqual((first_page.total_count, second_page.total_count), (3, 3))
        self.assertEqual(
            (first_page.items[0].domain, second_page.items[0].domain),
            ('a.example.com', 'b.example.com'),
        )
        self.assertTrue(first_page.has_more)
        lines = '\n'.join(source_contribution_lines(first))
        self.assertIn('a.example.com', lines)
        self.assertIn('Dayanak:', lines)
        self.assertIn('geçmiş yetersiz', lines)

    def test_unknown_provider_and_changed_job_target_are_rejected(self):
        job, attempt = self.scan('crt.sh', ('a.test',))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE scan_jobs SET provider='unknown-provider' WHERE id=?",
                (job.id,),
            )
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.service.show('example.com', family='brand')
        self.assertEqual(before, self.path.read_bytes())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                'UPDATE scan_jobs SET provider=\'crt.sh\',targets=\'["example.com","other.example"]\' WHERE id=?',
                (job.id,),
            )
        with self.assertRaises(StorageError):
            self.service.show('example.com', family='brand')

    def test_bounds_and_invalid_inputs_never_return_partial_ratios(self):
        self.scan('crt.sh', ('a.test', 'b.test'))
        with patch('xti.adapters.sqlite_source_contribution.MAX_CANDIDATE_VALUES', 1):
            with self.assertRaises(StorageError):
                self.service.show('example.com')
        for options in ({'family': 'unknown'}, {'detail_limit': True}, {'detail_offset': -1}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                self.service.show('example.com', **options)
        with self.assertRaises(ValidationError):
            self.service.show('missing.example')

    def test_report_has_no_network_write_or_new_source_selection(self):
        self.surface('crt.sh', ('a.example.com',))
        before = self.path.read_bytes()
        with patch('socket.create_connection', side_effect=AssertionError('network called')):
            report = self.service.show('example.com')
        self.assertEqual(before, self.path.read_bytes())
        self.assertIn('Domain keşfi/marka araması için yeni sağlayıcı seçilmedi', report.provider_evaluation)
        self.assertFalse((self.path.parent / 'backups').exists())

    def test_cross_family_snapshot_does_not_mix_concurrent_new_scan(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
        original = self.repo._surface
        wrote = []

        def interleaved(*args):
            result = original(*args)
            if not wrote:
                wrote.append(True)
                self.scan('crt.sh', ('later.test',))
            return result
        with patch.object(self.repo, '_surface', side_effect=interleaved):
            report = self.service.show('example.com')
        self.assertFalse(any((group.family == 'brand' for group in report.groups)))
        self.assertTrue(any((group.family == 'brand' for group in self.service.show('example.com').groups)))
if __name__ == '__main__':
    unittest.main()

"""Human-review candidates for conservative ransomware identity hand-offs."""

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.ransomware_watch_identity_candidates import (
    RansomwareWatchIdentityCandidateService,
)
from xti.application.ransomware_watches import RansomwareWatchService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from tests.test_threatcluster_ransomware import claim, content


NOW = datetime(2026, 10, 30, 23, 30, tzinfo=timezone.utc)


def feed(records, *, minute):
    return parse_threatcluster_ransomware_response(
        content(records), fetched_at=NOW + timedelta(minutes=minute),
    )


class RansomwareWatchIdentityCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.claims = SQLiteRansomwareClaimRepository(self.path)
        self.watch_repository = SQLiteRansomwareWatchRepository(self.path)
        self.watches = RansomwareWatchService(
            self.watch_repository, self.claims, clock=lambda: NOW,
        )
        self.candidates = RansomwareWatchIdentityCandidateService(
            self.watch_repository, self.claims,
        )

    def apply(self, records, *, minute):
        return self.claims.apply(
            feed(records, minute=minute),
            started_at=(NOW + timedelta(minutes=minute, seconds=1)).isoformat(),
            finished_at=(NOW + timedelta(minutes=minute, seconds=2)).isoformat(),
            item_limit=100,
        )

    def watch(self):
        return self.watches.add(
            "Alpha kuruluş", "Alpha Ltd", kind="organization",
        ).watch

    def test_discovery_time_change_is_a_candidate_without_merge_or_write(self):
        watch = self.watch()
        older = claim("Alpha Ltd", discovered="2026-10-29T12:00:00Z")
        newer = claim("Alpha Ltd", discovered="2026-10-30T12:00:00Z")
        self.apply([older], minute=1)
        self.apply([newer], minute=2)
        before = self.path.read_bytes()

        report = self.candidates.show(watch.id)

        self.assertEqual((report.total_candidate_count, len(report.candidates)), (1, 1))
        candidate = report.candidates[0]
        self.assertEqual(candidate.changed_identity_fields, ("discovered_at",))
        self.assertEqual(
            candidate.common_evidence, ("group", "victim", "website"),
        )
        self.assertEqual(candidate.successful_snapshot_gap, 0)
        self.assertTrue(candidate.older_matches_watch)
        self.assertTrue(candidate.newer_matches_watch)
        self.assertNotEqual(candidate.older_claim.id, candidate.newer_claim.id)
        self.assertEqual(self.path.read_bytes(), before)

    def test_name_and_time_change_can_keep_old_watch_relevance_via_group_and_site(self):
        watch = self.watch()
        self.apply([
            claim(
                "Alpha Ltd", group="sample-group", website="alpha.example",
                discovered="2026-10-28T12:00:00Z",
            ),
        ], minute=1)
        self.apply([
            claim(
                "Alpha Limited", group="sample-group", website="alpha.example",
                discovered="2026-10-30T12:00:00Z",
            ),
        ], minute=2)

        candidate = self.candidates.show(watch.id).candidates[0]
        self.assertEqual(candidate.common_evidence, ("group", "website"))
        self.assertEqual(
            candidate.changed_identity_fields, ("victim", "discovered_at"),
        )
        self.assertTrue(candidate.older_matches_watch)
        self.assertFalse(candidate.newer_matches_watch)

    def test_weak_overlap_coexistence_exact_reappearance_and_old_gap_are_excluded(self):
        watch = self.watch()
        alpha = claim(
            "Alpha Ltd", group="alpha-group", website="alpha.example",
            discovered="2026-10-27T12:00:00Z",
        )
        concurrent = claim(
            "Alpha Ltd", group="alpha-group", website="alpha.example",
            discovered="2026-10-28T12:00:00Z",
        )
        unrelated = claim(
            "Other Company", group="other-group", website="other.example",
            discovered="2026-10-30T11:00:00Z",
        )
        self.apply([alpha], minute=1)
        self.apply([alpha, concurrent], minute=2)
        self.apply([], minute=3)
        self.apply([], minute=4)
        self.apply([alpha, unrelated], minute=5)

        report = self.candidates.show(watch.id)
        self.assertEqual(report.total_candidate_count, 0)
        self.assertEqual(report.transition_pair_count, 0)

    def test_failed_run_does_not_break_adjacent_successful_snapshot_candidate(self):
        watch = self.watch()
        older = claim("Alpha Ltd", discovered="2026-10-29T12:00:00Z")
        newer = claim("Alpha Ltd", discovered="2026-10-30T12:00:00Z")
        self.apply([older], minute=1)
        self.apply([], minute=2)
        self.claims.record_failure(
            started_at=(NOW + timedelta(minutes=3)).isoformat(),
            finished_at=(NOW + timedelta(minutes=3, seconds=1)).isoformat(),
            error="Kaynak bağlantısı tamamlanamadı; sonuç üretilmedi.",
        )
        self.apply([newer], minute=4)

        report = self.candidates.show(watch.id)
        self.assertEqual(
            (report.complete_source_run_count, report.failed_source_run_count,
             report.total_candidate_count),
            (3, 1, 1),
        )
        self.assertEqual(report.candidates[0].successful_snapshot_gap, 1)

    def test_limit_is_display_only_and_cli_json_and_human_are_read_only(self):
        watch = self.watch()
        first = claim("Alpha Ltd", discovered="2026-10-28T12:00:00Z")
        second = claim("Alpha Ltd", discovered="2026-10-29T12:00:00Z")
        third = claim("Alpha Ltd", discovered="2026-10-30T12:00:00Z")
        self.apply([first], minute=1)
        self.apply([second], minute=2)
        self.apply([third], minute=3)
        before = self.path.read_bytes()

        report = self.candidates.show(watch.id, candidate_limit=1)
        self.assertEqual((report.total_candidate_count, len(report.candidates)), (2, 1))
        self.assertEqual(report.candidates[0].newer_claim.discovered_at,
                         "2026-10-30T12:00:00+00:00")

        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-dir", self.temp.name, "--json", "ransomware",
                "watch-identity-candidates", watch.id, "--candidate-limit", "1",
            ])
        payload = json.loads(output.getvalue())
        self.assertEqual((code, payload["data"]["total_candidate_count"]), (0, 2))

        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-dir", self.temp.name, "ransomware",
                "watch-identity-candidates", watch.id,
            ])
        self.assertEqual(code, 0)
        self.assertIn("ortak kanıt", output.getvalue())
        self.assertIn("birleştirmez", output.getvalue())
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_revoked_watch_and_invalid_limit_are_safe(self):
        watch = self.watch()
        self.watches.revoke(watch.id, reason="İzleme kapsamı kapatıldı")
        before = self.path.read_bytes()
        report = self.candidates.show(watch.id)
        self.assertEqual(
            (report.watch.active, report.total_candidate_count,
             report.complete_source_run_count),
            (False, 0, 0),
        )
        with self.assertRaises(ValidationError):
            self.candidates.show(watch.id, candidate_limit=0)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

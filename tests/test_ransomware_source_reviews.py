"""Append-only human decisions for cross-source ransomware comparisons."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_source_reviews import (
    SQLiteRansomwareSourceReviewRepository,
)
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.ransomware_source_comparison import (
    RansomwareSourceComparisonService,
)
from xti.application.ransomware_source_reviews import RansomwareSourceReviewService
from xti.domain.assets import ValidationError
from xti.domain.ransomlook_ransomware import RansomLookClaim
from xti.domain.ransomware_claims import RansomwareClaim
from xti.interfaces.cli import main
from tests.test_ransomlook_ransomware import content as ransomlook_content, post
from tests.test_threatcluster_ransomware import claim, content as threatcluster_content


NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)


class RansomwareSourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.threatcluster = SQLiteRansomwareClaimRepository(self.path)
        self.ransomlook = SQLiteRansomLookClaimRepository(self.path)
        self.review_repository = SQLiteRansomwareSourceReviewRepository(self.path)
        self.review_time = NOW + timedelta(hours=1)
        self.comparisons = RansomwareSourceComparisonService(
            self.threatcluster, self.ransomlook,
        )
        self.reviews = RansomwareSourceReviewService(
            self.review_repository, self.comparisons,
            clock=lambda: self.review_time,
        )

    def apply_threatcluster(self, *, minute):
        feed = parse_threatcluster_ransomware_response(
            threatcluster_content([
                claim(
                    "Example Holding", group="example-group",
                    discovered="2026-10-30T16:00:00Z",
                ),
            ]),
            fetched_at=NOW + timedelta(minutes=minute),
        )
        started = NOW + timedelta(minutes=minute, seconds=1)
        return self.threatcluster.apply(
            feed, started_at=started.isoformat(),
            finished_at=(started + timedelta(seconds=1)).isoformat(), item_limit=100,
        )

    def apply_ransomlook(self, *, minute):
        feed = parse_ransomlook_ransomware_response(
            ransomlook_content([
                post(
                    "Example Holding", group="example-group",
                    discovered="2026-10-30T16:00:00Z",
                ),
            ]),
            fetched_at=NOW + timedelta(minutes=minute),
        )
        started = NOW + timedelta(minutes=minute, seconds=1)
        return self.ransomlook.apply(
            feed, started_at=started.isoformat(),
            finished_at=(started + timedelta(seconds=1)).isoformat(), item_limit=100,
        )

    def make_comparison(self):
        self.apply_threatcluster(minute=1)
        self.apply_ransomlook(minute=2)
        return self.comparisons.compare().comparisons[0]

    def test_decision_chain_is_append_only_idempotent_and_never_merges_sources(self):
        comparison = self.make_comparison()
        first = self.reviews.decide(
            comparison.id, decision="possible_same",
            reason="Kuruluş, grup ve keşif zamanı iki kaynakta aynı.",
        )
        self.assertEqual(first.action, "recorded")
        self.assertEqual(first.details.current.decision, "possible_same")

        unchanged = self.reviews.decide(
            comparison.id, decision="possible_same",
            reason="Kuruluş, grup ve keşif zamanı iki kaynakta aynı.",
        )
        self.assertEqual(unchanged.action, "unchanged")
        self.assertEqual(unchanged.details.total_event_count, 1)

        self.review_time += timedelta(minutes=1)
        updated = self.reviews.decide(
            comparison.id, decision="different",
            reason="İki kaynak kaydı ayrı iddialar olarak değerlendirildi.",
        )
        self.assertEqual(updated.action, "updated")
        self.assertEqual(
            [event.decision for event in updated.details.events],
            ["possible_same", "different"],
        )
        self.assertEqual(
            updated.details.events[1].previous_event_id,
            updated.details.events[0].id,
        )

        report = self.reviews.decorate(self.comparisons.compare())
        self.assertEqual(report.comparisons[0].current_review.decision, "different")
        self.assertIsInstance(
            report.comparisons[0].threatcluster_claim, RansomwareClaim,
        )
        self.assertIsInstance(
            report.comparisons[0].ransomlook_claim, RansomLookClaim,
        )
        inspection = SQLiteAssetRepository(self.path).inspect()
        self.assertEqual(
            (
                inspection["ransomware_source_review_candidate_count"],
                inspection["ransomware_source_review_event_count"],
                inspection["ransomware_claim_run_count"],
                inspection["ransomlook_claim_run_count"],
            ),
            (1, 2, 1, 1),
        )

    def test_new_source_runs_keep_original_review_evidence_and_allow_update(self):
        comparison = self.make_comparison()
        first = self.reviews.decide(
            comparison.id, decision="uncertain",
            reason="İki açık kaynak dışında ek kanıt bulunmuyor.",
        )
        original_runs = (
            first.details.evidence.threatcluster_run_id,
            first.details.evidence.ransomlook_run_id,
        )
        self.apply_threatcluster(minute=3)
        self.apply_ransomlook(minute=4)
        self.review_time += timedelta(minutes=1)
        updated = self.reviews.decide(
            comparison.id, decision="possible_same",
            reason="Aynı kaynak çifti yeni snapshot'larda tekrar görüldü.",
        )
        self.assertEqual(updated.action, "updated")
        self.assertEqual(
            (
                updated.details.evidence.threatcluster_run_id,
                updated.details.evidence.ransomlook_run_id,
            ),
            original_runs,
        )
        self.assertEqual(updated.details.total_event_count, 2)

    def test_cli_records_shows_and_decorates_without_network(self):
        comparison = self.make_comparison()
        stdout, stderr = StringIO(), StringIO()
        with (
            patch.object(
                RansomwareSourceReviewService, "_now",
                return_value=self.review_time.isoformat(),
            ),
            patch(
                "xti.interfaces.cli.ThreatClusterRansomwareSource.fetch",
                side_effect=AssertionError("review must stay offline"),
            ),
            patch(
                "xti.interfaces.cli.RansomLookRansomwareSource.fetch",
                side_effect=AssertionError("review must stay offline"),
            ),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main([
                "--data-dir", self.temp.name, "ransomware", "source-review",
                comparison.id, "--decision", "uncertain", "--reason",
                "Ek doğrulama kanıtı bekleniyor.",
            ])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        self.assertIn("kararı kaydedildi", stdout.getvalue())

        before = self.path.read_bytes()
        stdout = StringIO()
        with redirect_stdout(stdout), redirect_stderr(StringIO()):
            self.assertEqual(main([
                "--data-dir", self.temp.name, "--json", "ransomware",
                "source-review-show", comparison.id,
            ]), 0)
        details = json.loads(stdout.getvalue())["data"]
        self.assertEqual(details["current"]["decision"], "uncertain")

        stdout = StringIO()
        with redirect_stdout(stdout), redirect_stderr(StringIO()):
            self.assertEqual(main([
                "--data-dir", self.temp.name, "ransomware", "source-compare",
            ]), 0)
        self.assertIn("İnsan kararı: belirsiz", stdout.getvalue())
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_input_clock_and_unknown_candidate_never_write(self):
        comparison = self.make_comparison()
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.reviews.decide(
                comparison.id, decision="same", reason="Geçerli gerekçe",
            )
        with self.assertRaises(ValidationError):
            self.reviews.decide(
                comparison.id, decision="uncertain", reason="x",
            )
        with self.assertRaises(ValidationError):
            self.reviews.decide(
                "0" * 64, decision="uncertain", reason="Geçerli gerekçe",
            )
        bad_clock = RansomwareSourceReviewService(
            self.review_repository, self.comparisons,
            clock=lambda: datetime(2026, 10, 30),
        )
        with self.assertRaises(ValidationError):
            bad_clock.decide(
                comparison.id, decision="uncertain", reason="Geçerli gerekçe",
            )
        self.assertEqual(self.path.read_bytes(), before)

    def test_corruption_fails_closed_and_backup_restore_keeps_chain(self):
        comparison = self.make_comparison()
        self.reviews.decide(
            comparison.id, decision="uncertain",
            reason="İlk değerlendirme belirsiz.",
        )
        self.review_time += timedelta(minutes=1)
        self.reviews.decide(
            comparison.id, decision="different",
            reason="İkinci değerlendirme farklı olay yönünde.",
        )
        backup = Path(self.temp.name) / "backup.db"
        restored = Path(self.temp.name) / "restored.db"
        SQLiteAssetRepository(self.path).backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        restored_details = SQLiteRansomwareSourceReviewRepository(restored).details(
            comparison.id, event_limit=10,
        )
        self.assertEqual(
            (restored_details.current.decision, restored_details.total_event_count),
            ("different", 2),
        )

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ransomware_source_review_events SET previous_event_id=NULL "
                "WHERE comparison_id=? AND sequence=(SELECT MAX(sequence) FROM "
                "ransomware_source_review_events WHERE comparison_id=?)",
                (comparison.id, comparison.id),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "karar zinciri"):
            self.reviews.show(comparison.id)
        self.assertEqual(self.path.read_bytes(), before)

    def test_changed_evidence_hash_fails_closed_without_repair(self):
        comparison = self.make_comparison()
        self.reviews.decide(
            comparison.id, decision="uncertain",
            reason="Bağımsız doğrulama kanıtı henüz bulunmuyor.",
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ransomware_source_review_events SET evidence_sha256=? "
                "WHERE comparison_id=?",
                ("0" * 64, comparison.id),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "karar geçmişi bozuk"):
            self.reviews.show(comparison.id)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

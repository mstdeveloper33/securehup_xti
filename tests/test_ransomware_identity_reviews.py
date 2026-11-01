"""Append-only human decisions for ransomware identity-change candidates."""

from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_identity_reviews import (
    SQLiteRansomwareIdentityReviewRepository,
)
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.ransomware_identity_reviews import RansomwareIdentityReviewService
from xti.application.ransomware_watch_identity_candidates import (
    RansomwareWatchIdentityCandidateService,
)
from xti.application.ransomware_watch_timeline import RansomwareWatchTimelineService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from tests.test_threatcluster_ransomware import claim, content


NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)


def feed(records, *, minute):
    return parse_threatcluster_ransomware_response(
        content(records), fetched_at=NOW + timedelta(minutes=minute),
    )


class RansomwareIdentityReviewTests(unittest.TestCase):
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
        self.watch = self.watches.add(
            "Alpha kuruluş", "Alpha Ltd", kind="organization",
        ).watch
        self.candidate_service = RansomwareWatchIdentityCandidateService(
            self.watch_repository, self.claims,
        )
        self.review_time = NOW + timedelta(hours=2)
        self.review_repository = SQLiteRansomwareIdentityReviewRepository(self.path)
        self.reviews = RansomwareIdentityReviewService(
            self.review_repository, self.candidate_service,
            clock=lambda: self.review_time,
        )

    def apply(self, records, *, minute):
        return self.claims.apply(
            feed(records, minute=minute),
            started_at=(NOW + timedelta(minutes=minute, seconds=1)).isoformat(),
            finished_at=(NOW + timedelta(minutes=minute, seconds=2)).isoformat(),
            item_limit=100,
        )

    def make_candidate(self):
        self.apply([
            claim("Alpha Ltd", discovered="2026-10-29T12:00:00Z"),
        ], minute=1)
        self.apply([
            claim("Alpha Ltd", discovered="2026-10-30T12:00:00Z"),
        ], minute=2)
        return self.candidate_service.show(self.watch.id).candidates[0]

    def test_decision_updates_append_history_and_never_merges_timeline_identity(self):
        candidate = self.make_candidate()
        first = self.reviews.decide(
            self.watch.id, candidate.id, decision="possible_same",
            reason="Grup ve kuruluş aynı; yalnız kaynak zamanı değişmiş.",
        )
        self.assertEqual(first.action, "recorded")
        self.assertEqual(first.details.current.decision, "possible_same")

        unchanged = self.reviews.decide(
            self.watch.id, candidate.id, decision="possible_same",
            reason="Grup ve kuruluş aynı; yalnız kaynak zamanı değişmiş.",
        )
        self.assertEqual(unchanged.action, "unchanged")
        self.assertEqual(unchanged.details.total_event_count, 1)

        self.review_time += timedelta(minutes=1)
        updated = self.reviews.decide(
            self.watch.id, candidate.id, decision="different",
            reason="İkinci kayıt ayrı bir kaynak ilanı olarak değerlendirildi.",
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

        timeline = RansomwareWatchTimelineService(
            self.watch_repository, self.claims,
        ).show(self.watch.id)
        self.assertEqual(timeline.distinct_claim_count, 2)
        decorated = self.reviews.decorate(
            self.candidate_service.show(self.watch.id),
        )
        self.assertEqual(
            decorated.candidates[0].current_review.decision, "different",
        )
        storage = SQLiteAssetRepository(self.path).inspect()
        self.assertEqual(storage["ransomware_identity_review_candidate_count"], 1)
        self.assertEqual(storage["ransomware_identity_review_event_count"], 2)

    def test_show_limit_cli_json_and_human_views_are_read_only(self):
        candidate = self.make_candidate()
        self.reviews.decide(
            self.watch.id, candidate.id, decision="uncertain",
            reason="Ortak alanlar var ancak ek doğrulama bulunmuyor.",
        )
        self.review_time += timedelta(minutes=1)
        self.reviews.decide(
            self.watch.id, candidate.id, decision="possible_same",
            reason="Zaman geçişi ve ortak alanlar birlikte değerlendirildi.",
        )
        before = self.path.read_bytes()
        details = self.reviews.show(candidate.id, event_limit=1)
        self.assertEqual((details.total_event_count, len(details.events)), (2, 1))

        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-dir", self.temp.name, "--json", "ransomware",
                "watch-identity-review-show", candidate.id, "--event-limit", "1",
            ])
        payload = json.loads(output.getvalue())
        self.assertEqual((code, payload["data"]["total_event_count"]), (0, 2))

        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-dir", self.temp.name, "ransomware",
                "watch-identity-candidates", self.watch.id,
            ])
        self.assertEqual(code, 0)
        self.assertIn("aynı olay olabilir", output.getvalue())
        self.assertIn(candidate.id, output.getvalue())
        self.assertEqual(self.path.read_bytes(), before)

    def test_cli_can_record_explicit_decision_under_lock(self):
        candidate = self.make_candidate()
        output = StringIO()
        with patch.object(
            RansomwareIdentityReviewService, "_now",
            return_value=(NOW + timedelta(hours=2)).isoformat(),
        ), redirect_stdout(output):
            code = main([
                "--data-dir", self.temp.name, "ransomware",
                "watch-identity-review", self.watch.id, candidate.id,
                "--decision", "uncertain", "--reason",
                "Ek kaynak kanıtı bekleniyor.",
            ])
        self.assertEqual(code, 0)
        self.assertIn("Karar kaydedildi", output.getvalue())
        self.assertEqual(self.reviews.show(candidate.id).current.decision, "uncertain")

    def test_invalid_candidate_decision_reason_and_clock_do_not_write(self):
        candidate = self.make_candidate()
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.reviews.decide(
                self.watch.id, candidate.id, decision="same", reason="Geçerli gerekçe",
            )
        with self.assertRaises(ValidationError):
            self.reviews.decide(
                self.watch.id, candidate.id, decision="uncertain", reason="x",
            )
        with self.assertRaises(ValidationError):
            self.reviews.decide(
                self.watch.id, "00000000-0000-0000-0000-000000000000",
                decision="uncertain", reason="Geçerli gerekçe",
            )
        bad_clock = RansomwareIdentityReviewService(
            self.review_repository, self.candidate_service,
            clock=lambda: datetime(2026, 10, 30),
        )
        with self.assertRaises(ValidationError):
            bad_clock.decide(
                self.watch.id, candidate.id, decision="uncertain",
                reason="Geçerli gerekçe",
            )
        self.assertEqual(self.path.read_bytes(), before)

    def test_hidden_chain_or_candidate_corruption_fails_closed(self):
        candidate = self.make_candidate()
        self.reviews.decide(
            self.watch.id, candidate.id, decision="uncertain",
            reason="İlk değerlendirme belirsiz.",
        )
        self.review_time += timedelta(minutes=1)
        self.reviews.decide(
            self.watch.id, candidate.id, decision="different",
            reason="İkinci değerlendirme farklı olay yönünde.",
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ransomware_identity_review_events SET previous_event_id=NULL "
                "WHERE candidate_id=? AND sequence=(SELECT MAX(sequence) FROM "
                "ransomware_identity_review_events WHERE candidate_id=?)",
                (candidate.id, candidate.id),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "karar zinciri"):
            self.reviews.show(candidate.id)
        self.assertEqual(self.path.read_bytes(), before)

    def test_candidate_snapshot_corruption_fails_closed_without_repair(self):
        candidate = self.make_candidate()
        self.reviews.decide(
            self.watch.id, candidate.id, decision="uncertain",
            reason="Ek kaynak kanıtı bulunmuyor.",
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ransomware_identity_review_events SET candidate_sha256=? "
                "WHERE candidate_id=?",
                ("0" * 64, candidate.id),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "karar geçmişi bozuk"):
            self.reviews.show(candidate.id)
        self.assertEqual(self.path.read_bytes(), before)

    def test_backup_restore_preserves_candidate_and_decision_chain(self):
        candidate = self.make_candidate()
        self.reviews.decide(
            self.watch.id, candidate.id, decision="uncertain",
            reason="İlk değerlendirme belirsiz.",
        )
        self.review_time += timedelta(minutes=1)
        self.reviews.decide(
            self.watch.id, candidate.id, decision="possible_same",
            reason="Ortak alanlar ve yakın geçiş birlikte değerlendirildi.",
        )
        backup = Path(self.temp.name) / "backup.db"
        restored = Path(self.temp.name) / "restored.db"
        SQLiteAssetRepository(self.path).backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        details = SQLiteRansomwareIdentityReviewRepository(restored).details(
            candidate.id, event_limit=10,
        )
        self.assertEqual(
            (details.current.decision, details.total_event_count),
            ("possible_same", 2),
        )


if __name__ == "__main__":
    unittest.main()

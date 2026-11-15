"""Source-independent candidate service preserves pagination, context and decisions."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.hibp_public_notices import parse_hibp_public_notices_response
from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_event_candidates import SQLiteEventCandidateRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_source_reviews import SQLiteRansomwareSourceReviewRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.event_candidates import EventCandidateService
from xti.application.ransomware_source_comparison import RansomwareSourceComparisonService
from xti.application.ransomware_source_reviews import RansomwareSourceReviewService
from xti.domain.assets import ValidationError
from tests.test_public_notices import item as notice_item
from tests.test_ransomlook_ransomware import content as rl_content, post
from tests.test_threatcluster_ransomware import content as tc_content, claim


NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)
DISCOVERED = "2026-10-30T16:00:00Z"


class EventCandidateServiceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteEventCandidateRepository(self.path)
        self.tc = SQLiteRansomwareClaimRepository(self.path)
        self.rl = SQLiteRansomLookClaimRepository(self.path)
        self.hibp = SQLitePublicNoticeRepository(self.path)
        self.now = NOW + timedelta(hours=1)
        self.service = EventCandidateService(self.repository, clock=lambda: self.now)

    def save_tc(self, *, website="alpha.example", minute=1):
        records = [
            {**claim("Alpha Ltd", group="alpha-group", discovered=DISCOVERED), "website": website},
            {**claim("Beta Ltd.", group="beta-group", discovered=DISCOVERED), "website": "beta.example"},
        ]
        feed = parse_threatcluster_ransomware_response(tc_content(records), fetched_at=NOW)
        at = (NOW + timedelta(minutes=minute)).isoformat()
        return self.tc.apply(feed, started_at=at, finished_at=at, item_limit=100)

    def populate(self):
        self.save_tc()
        feed = parse_ransomlook_ransomware_response(rl_content([
            post("Alpha Ltd", group="alpha-group", discovered=DISCOVERED),
            post("Beta Ltd", group="beta-group", discovered=DISCOVERED),
        ]), fetched_at=NOW)
        at = (NOW + timedelta(minutes=2)).isoformat()
        self.rl.apply(feed, started_at=at, finished_at=at, item_limit=100)
        records = [{**notice_item(name), "Domain": name.lower() + ".example"} for name in ("Alpha", "Beta")]
        feed = parse_hibp_public_notices_response(json.dumps(records).encode(), fetched_at=NOW)
        at = (NOW + timedelta(minutes=3)).isoformat()
        self.hibp.apply(feed, started_at=at, finished_at=at, item_limit=100)

    def test_possible_events_and_common_domain_context_are_counted_separately(self):
        self.populate()
        before = self.path.read_bytes()
        report = self.service.candidates()
        self.assertEqual((report.total_candidate_count, report.possible_same_event_count,
                          report.organization_context_count), (4, 2, 2))
        self.assertEqual([item.kind for item in report.candidates],
                         ["possible_same_event"] * 2 + ["organization_context"] * 2)
        self.assertEqual(len({item.id for item in report.candidates}), 4)
        for candidate in report.candidates:
            self.assertNotEqual(candidate.left.source_key, candidate.right.source_key)
            if candidate.kind == "organization_context":
                self.assertEqual({candidate.left.source_key, candidate.right.source_key}, {"hibp", "threatcluster"})
        self.assertEqual(self.path.read_bytes(), before)

    def test_display_limit_never_truncates_totals_and_pages_are_disjoint(self):
        self.populate()
        full = self.service.candidates()
        pages = [self.service.candidates(offset=index, limit=1) for index in range(5)]
        self.assertEqual([page.candidates[0].id for page in pages[:4]], [item.id for item in full.candidates])
        self.assertEqual([page.total_candidate_count for page in pages], [4] * 5)
        self.assertEqual([page.has_more for page in pages], [True, True, True, False, False])
        self.assertEqual(pages[-1].candidates, ())
        self.assertEqual([item.id for item in self.service.candidates().candidates], [item.id for item in full.candidates])

    def test_exact_domain_filter_preserves_scope_without_assigning_domain_to_ransomlook(self):
        self.populate()
        report = self.service.candidates(domain="ALPHA.EXAMPLE")
        self.assertEqual(report.domain_filter, "alpha.example")
        self.assertEqual((report.total_candidate_count, report.possible_same_event_count,
                          report.organization_context_count), (2, 1, 1))
        self.assertEqual([coverage.record_count for coverage in report.coverage], [2, 2, 2])
        rl = next(record for candidate in report.candidates for record in (candidate.left, candidate.right)
                  if record.source_key == "ransomlook")
        self.assertIsNone(rl.domain)
        self.assertEqual(self.service.candidates(domain="www.alpha.example").total_candidate_count, 0)
        self.assertEqual(self.service.candidates(domain="other.example").total_candidate_count, 0)

    def test_failed_last_attempt_retains_candidates_but_freshness_is_independent(self):
        self.populate()
        ids = [item.id for item in self.service.candidates().candidates]
        at = (NOW + timedelta(minutes=4)).isoformat()
        self.tc.record_failure(started_at=at, finished_at=at, error="Kaynak bağlantısı kesildi.")
        self.now += timedelta(days=2)
        report = self.service.candidates()
        self.assertEqual([item.id for item in report.candidates], ids)
        tc = next(source for source in report.coverage if source.source_key == "threatcluster")
        self.assertEqual((tc.status, tc.freshness, tc.record_count), ("last_attempt_failed", "stale", 2))
        self.assertNotEqual(tc.latest_run_id, tc.latest_success_run_id)
        self.assertIn("bağlantısı kesildi", " ".join(tc.notes))

    def test_never_failed_only_successfully_empty_and_future_time_are_distinct(self):
        empty = self.service.candidates()
        self.assertEqual({source.status for source in empty.coverage}, {"not_collected"})
        at = NOW.isoformat()
        self.hibp.record_failure(started_at=at, finished_at=at, error="Kaynak alınamadı.")
        feed = parse_ransomlook_ransomware_response(rl_content([]), fetched_at=NOW)
        self.rl.apply(feed, started_at=at, finished_at=at, item_limit=100)
        report = self.service.candidates()
        self.assertEqual([source.status for source in report.coverage], ["not_collected", "available", "unavailable"])
        self.assertEqual(report.total_candidate_count, 0)
        self.assertIn("başarılı kapsamı boş", " ".join(report.coverage[1].notes))
        self.now = NOW - timedelta(hours=1)
        report = self.service.candidates()
        self.assertEqual(report.coverage[1].freshness, "clock_error")
        self.assertEqual(report.coverage[2].freshness, "clock_error")

    def test_frozen_human_decision_is_displayed_separately_and_changed_evidence_is_marked(self):
        self.populate()
        comparisons = RansomwareSourceComparisonService(self.tc, self.rl)
        review_repository = SQLiteRansomwareSourceReviewRepository(self.path)
        reviews = RansomwareSourceReviewService(review_repository, comparisons, clock=lambda: NOW + timedelta(minutes=4))
        legacy_id = comparisons.compare().comparisons[0].id
        saved = reviews.decide(legacy_id, decision="different", reason="Ayrı olaylar olarak incelendi.")
        first = next(item for item in self.service.candidates().candidates if item.legacy_comparison_id == legacy_id)
        self.assertEqual(first.legacy_review.decision, "different")
        self.assertTrue(first.legacy_review.evidence_matches)
        self.save_tc(website="other.example", minute=5)
        before = self.path.read_bytes()
        changed = next(item for item in self.service.candidates().candidates if item.legacy_comparison_id == legacy_id)
        self.assertEqual(changed.id, first.id)
        self.assertNotEqual(changed.evidence_sha256, first.evidence_sha256)
        self.assertFalse(changed.legacy_review.evidence_matches)
        self.assertEqual(changed.legacy_review.decision, "different")
        self.assertEqual(reviews.show(legacy_id), saved.details)
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_options_fail_before_storage_and_clock_must_be_aware(self):
        class NeverRead:
            def read(self):
                raise AssertionError("Invalid options must not read storage")
        service = EventCandidateService(NeverRead())
        for options in ({"limit": 0}, {"limit": True}, {"limit": 501}, {"offset": -1},
                        {"offset": False}, {"stale_after_hours": 0}, {"stale_after_hours": 8761},
                        {"domain": "https://example.com/a"}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                service.candidates(**options)
        with self.assertRaises(ValidationError):
            EventCandidateService(NeverRead(), clock=lambda: datetime(2026, 10, 30)).candidates()

    def test_capacity_overflow_raises_instead_of_silently_cutting_candidate_set(self):
        self.populate()
        for constant, limit in (("MAX_EVENT_RECORDS", 5), ("MAX_EVENT_PAIR_REFERENCES", 1),
                                ("MAX_EVENT_CANDIDATES", 1)):
            with self.subTest(constant=constant), patch("xti.application.event_candidates." + constant, limit):
                with self.assertRaisesRegex(ValidationError, "kısmi sonuç üretilmedi"):
                    self.service.candidates(limit=1)


if __name__ == "__main__":
    unittest.main()

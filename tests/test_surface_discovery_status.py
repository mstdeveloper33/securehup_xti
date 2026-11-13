"""Latest passive discovery outcome without confusing outage and empty data."""

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.application.surface_discovery_status import SurfaceDiscoveryStatusService
from xti.domain.assets import ValidationError
from xti.domain.surface import SurfaceCandidateEvidence, SurfaceDiscoveryRunRequest


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


class SurfaceDiscoveryStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.asset, _ = self.assets.add("example.com")
        self.repository = SQLiteSurfaceCandidateRepository(self.path)
        self.service = SurfaceDiscoveryStatusService(
            self.assets, self.repository, clock=lambda: NOW,
        )

    def record(
        self, status: str, *, domains=(), finished=None, warnings=(),
        skipped_names=0, error=None, provider="crt.sh",
    ):
        finished = finished or NOW - timedelta(hours=1)
        evidence = tuple(
            SurfaceCandidateEvidence(
                domain, provider, f"fixture:{provider}:{number}",
                hashlib.sha256(f"certificate-{number}".encode()).hexdigest(),
                domain, finished.isoformat(),
            )
            for number, domain in enumerate(domains, start=1)
        )
        return self.repository.record_discovery(
            self.asset.id,
            self.asset.value,
            evidence,
            SurfaceDiscoveryRunRequest(
                status, "https://crt.sh/?q=%25.example.com",
                (finished - timedelta(minutes=1)).isoformat(), finished.isoformat(),
                len(evidence), skipped_names, 0, tuple(warnings),
                len(set(domains)), error, provider,
            ),
        )[1]

    def test_no_run_is_unknown_and_read_only(self):
        before = self.path.read_bytes()
        report = self.service.show("EXAMPLE.COM")
        self.assertEqual(
            (report.source_status, report.result_status, report.outcome, report.freshness),
            ("never", "unknown", "never", "never"),
        )
        self.assertFalse(report.empty_result_confirmed)
        self.assertEqual(report.next_step, "run_discovery")
        self.assertEqual(self.path.read_bytes(), before)

    def test_complete_empty_result_is_distinct_and_can_become_stale(self):
        self.record("complete")
        current = self.service.show("example.com", freshness_hours=24)
        self.assertEqual(
            (
                current.source_status, current.result_status, current.outcome,
                current.coverage_complete, current.empty_result_confirmed,
                current.freshness, current.next_step,
            ),
            ("available", "none_observed", "complete_empty", True, True, "current", "none"),
        )

        stale_service = SurfaceDiscoveryStatusService(
            self.assets, self.repository, clock=lambda: NOW + timedelta(hours=24),
        )
        stale = stale_service.show("example.com", freshness_hours=24)
        self.assertEqual((stale.freshness, stale.next_step), ("stale", "run_discovery"))
        self.assertTrue(stale.empty_result_confirmed)

    def test_partial_empty_and_partial_found_never_confirm_absence(self):
        self.record(
            "partial", warnings=("Kaynak kapsamı sınırlı.",), skipped_names=1,
        )
        empty = self.service.show("example.com")
        self.assertEqual(
            (empty.source_status, empty.result_status, empty.outcome),
            ("incomplete", "none_observed", "partial_empty"),
        )
        self.assertFalse(empty.empty_result_confirmed)
        self.assertEqual(empty.next_step, "review_and_retry")

        self.record(
            "partial", domains=("api.example.com",),
            warnings=("Sonuç sınırına ulaşıldı.",),
        )
        found = self.service.show("example.com")
        self.assertEqual(
            (found.result_status, found.outcome, found.candidate_count),
            ("candidates_observed", "partial_found", 1),
        )
        self.assertFalse(found.coverage_complete)

    def test_failed_and_future_time_do_not_become_empty_success(self):
        self.record("failed", error="Kaynak yanıt vermedi.")
        failed = self.service.show("example.com")
        self.assertEqual(
            (failed.source_status, failed.result_status, failed.outcome),
            ("unavailable", "unknown", "failed"),
        )
        self.assertFalse(failed.empty_result_confirmed)
        self.assertEqual(failed.next_step, "retry_discovery")

        self.record("complete", finished=NOW + timedelta(minutes=1))
        future = self.service.show("example.com")
        self.assertEqual(future.freshness, "clock_error")
        self.assertEqual(future.next_step, "run_discovery")

    def test_latest_provider_is_visible_and_preserved_in_next_command(self):
        self.record("complete", provider="theharvester")
        report = self.service.show("example.com")
        self.assertEqual(report.provider, "theharvester")

    def test_provider_health_keeps_success_failure_and_empty_state_separate(self):
        self.record("complete", domains=("api.example.com",), provider="crt.sh")
        self.record(
            "failed", provider="theharvester", error="Arşiv kaynağı yanıt vermedi.",
        )
        before = self.path.read_bytes()

        latest = self.service.show("example.com")
        crtsh = self.service.show("example.com", provider="crt.sh")
        report = self.service.health("example.com")

        self.assertEqual((latest.provider, latest.outcome), ("theharvester", "failed"))
        self.assertEqual((crtsh.provider, crtsh.outcome), ("crt.sh", "complete_found"))
        self.assertEqual(
            [(item.provider, item.outcome) for item in report.sources],
            [("crt.sh", "complete_found"), ("theharvester", "failed")],
        )
        self.assertEqual(
            (report.complete_count, report.failed_count, report.never_run_count),
            (1, 1, 0),
        )
        self.assertEqual(report.attention_count, 1)
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_threshold_and_unknown_root_do_not_mutate_storage(self):
        before = self.path.read_bytes()
        for value in (0, 8761, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, "1–8760"):
                    self.service.show("example.com", freshness_hours=value)
        with self.assertRaisesRegex(ValidationError, "kayıtlı değil"):
            self.service.show("unknown.example")
        with self.assertRaisesRegex(ValidationError, "crt.sh veya theharvester"):
            self.service.show("example.com", provider="subfinder")
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

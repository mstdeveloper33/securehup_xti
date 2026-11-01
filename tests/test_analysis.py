"""Unified, read-only external-risk analysis over existing local evidence."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_surface_freshness import SQLiteSurfaceFreshnessRepository
from xti.adapters.sqlite_surface_overview import SQLiteSurfaceOverviewRepository
from xti.application.analysis import UnifiedAnalysisRefreshService, UnifiedAnalysisService
from xti.application.cti_indicators import CtiIndicatorService
from xti.application.surface import SurfaceOverviewService
from xti.application.surface_discovery_status import SurfaceDiscoveryStatusService
from xti.application.surface_exposure import SurfaceExposureService
from xti.application.surface_freshness import SurfaceFreshnessService
from xti.domain.assets import ValidationError
from xti.domain.cti_feeds import CtiFeedRun
from xti.domain.findings import DomainInput, ImportDocument, MatchCandidate


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


class StubFeedService:
    def __init__(self, run: CtiFeedRun):
        self.run = run
        self.calls = 0

    def sync(self):
        self.calls += 1
        return self.run


def feed_run(status: str = "complete") -> CtiFeedRun:
    return CtiFeedRun(
        id="feed-run-1", sequence=1, source_name="feodo-tracker", status=status,
        source_url="https://example.invalid/feed.json", content_sha256=("a" * 64 if status == "complete" else None),
        started_at=NOW.isoformat(), finished_at=NOW.isoformat(),
        source_record_count=1 if status == "complete" else 0,
        indicator_count=1 if status == "complete" else 0,
        added_count=1 if status == "complete" else 0, observed_count=0,
        updated_count=0, unchanged_count=0, reactivated_count=0,
        revoked_count=0, error=None if status == "complete" else "Kaynak geçici olarak erişilemiyor.",
    )


class UnifiedAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.asset, _ = self.assets.add("example.com")
        self.findings = SQLiteFindingRepository(self.path)
        self.indicators = SQLiteCtiIndicatorRepository(self.path)
        self.service = UnifiedAnalysisService(
            SurfaceOverviewService(
                self.assets, SQLiteSurfaceOverviewRepository(self.path),
            ),
            SurfaceFreshnessService(
                self.assets, SQLiteSurfaceFreshnessRepository(self.path), clock=lambda: NOW,
            ),
            SurfaceDiscoveryStatusService(
                self.assets, SQLiteSurfaceCandidateRepository(self.path), clock=lambda: NOW,
            ),
            SurfaceExposureService(
                self.assets, SQLiteSurfaceFreshnessRepository(self.path), clock=lambda: NOW,
            ),
            self.findings,
            self.indicators,
            clock=lambda: NOW,
        )

    def test_empty_evidence_is_honest_and_read_only(self):
        before = self.path.read_bytes()
        report = self.service.show("EXAMPLE.COM")

        self.assertEqual(report.asset_value, "example.com")
        self.assertTrue(report.stored_data_only)
        self.assertEqual(report.vulnerability_scope, "disabled")
        self.assertEqual(report.findings.total, 0)
        self.assertEqual(report.discovery.outcome, "never")
        self.assertEqual(report.freshness.scope_status, "missing")
        self.assertEqual(report.exposures.candidate_count, 0)
        self.assertEqual(report.ioc_catalog_status, "empty")
        self.assertEqual(report.ioc_checked_values, ("example.com",))
        self.assertEqual(report.ioc_matches, ())
        self.assertTrue(any("surface discover" in step for step in report.next_steps))
        self.assertTrue(any("surface approve" in step for step in report.next_steps))
        self.assertEqual(self.path.read_bytes(), before)

    def test_finding_and_exact_current_ioc_are_combined_without_a_verdict(self):
        document = ImportDocument(
            "test-source",
            hashlib.sha256(b"candidate").hexdigest(),
            (DomainInput("example-login.net", "example-login.net", 1, NOW.isoformat()),),
        )
        self.findings.save_import(document, (MatchCandidate(
            self.asset.id, self.asset.value, "example-login.net", "test-rule-v1",
            ("Marka adına login eki eklenmiş.",),
        ),))
        CtiIndicatorService(self.indicators, clock=lambda: NOW).add(
            "domain", "example.com", source_name="manual",
            source_reference="local:test-case", confidence=65,
            description="Test kaynak iddiası.",
        )
        CtiIndicatorService(self.indicators, clock=lambda: NOW).add(
            "domain", "example-login.net", source_name="second-source",
            source_reference="local:candidate", confidence=50,
            description="Aday domain için test kaynak iddiası.",
        )

        before = self.path.read_bytes()
        report = self.service.show("example.com")

        self.assertEqual(report.findings.total, 1)
        self.assertEqual(report.findings.new, 1)
        self.assertEqual(report.findings.samples[0].domain, "example-login.net")
        self.assertEqual(report.ioc_catalog_status, "available")
        self.assertEqual(
            report.ioc_checked_values, ("example.com", "example-login.net"),
        )
        self.assertEqual(len(report.ioc_matches), 2)
        matches = {item.value: item for item in report.ioc_matches}
        self.assertEqual(matches["example.com"].current_source_count, 1)
        self.assertEqual(matches["example.com"].maximum_confidence, 65)
        self.assertEqual(matches["example-login.net"].current_source_count, 1)
        self.assertEqual(matches["example-login.net"].maximum_confidence, 50)
        self.assertEqual(self.path.read_bytes(), before)

    def test_ioc_scope_includes_findings_hidden_by_display_limit(self):
        document = ImportDocument(
            "test-source",
            hashlib.sha256(b"two-candidates").hexdigest(),
            (
                DomainInput("example-first.net", "example-first.net", 1, NOW.isoformat()),
                DomainInput("example-second.net", "example-second.net", 2, NOW.isoformat()),
            ),
        )
        self.findings.save_import(document, (
            MatchCandidate(
                self.asset.id, self.asset.value, "example-first.net", "test-rule-v1",
                ("İlk test adayı.",),
            ),
            MatchCandidate(
                self.asset.id, self.asset.value, "example-second.net", "test-rule-v1",
                ("İkinci test adayı.",),
            ),
        ))
        CtiIndicatorService(self.indicators, clock=lambda: NOW).add(
            "domain", "example-second.net", source_name="manual",
            source_reference="local:hidden-candidate", confidence=55,
            description="Görünüm sınırı dışındaki aday.",
        )

        report = self.service.show("example.com", finding_limit=1)

        self.assertEqual(len(report.findings.samples), 1)
        self.assertTrue(report.findings.has_more)
        self.assertEqual(
            report.ioc_checked_values,
            ("example.com", "example-first.net", "example-second.net"),
        )
        self.assertEqual(
            tuple(item.value for item in report.ioc_matches), ("example-second.net",),
        )

    def test_limits_and_unknown_asset_fail_without_mutation(self):
        before = self.path.read_bytes()
        for limit in (0, 51, True):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValidationError, "1–50"):
                    self.service.show("example.com", finding_limit=limit)
        with self.assertRaisesRegex(ValidationError, "kayıtlı değil"):
            self.service.show("unknown.example")
        self.assertEqual(self.path.read_bytes(), before)

    def test_explicit_refresh_validates_target_then_returns_a_new_report(self):
        feed = StubFeedService(feed_run())
        service = UnifiedAnalysisRefreshService(
            self.service, feed, source="feodo",
        )

        result = service.run("example.com")

        self.assertEqual(feed.calls, 1)
        self.assertEqual(result.refresh.status, "complete")
        self.assertEqual(result.report.asset_value, "example.com")
        with self.assertRaisesRegex(ValidationError, "kayıtlı değil"):
            service.run("unknown.example")
        self.assertEqual(feed.calls, 1)

    def test_refresh_failure_remains_distinct_from_analysis_result(self):
        feed = StubFeedService(feed_run("failed"))
        result = UnifiedAnalysisRefreshService(
            self.service, feed, source="feodo",
        ).run("example.com")

        self.assertEqual(result.refresh.status, "failed")
        self.assertIn("erişilemiyor", result.refresh.error)
        self.assertEqual(result.report.ioc_catalog_status, "empty")

        with self.assertRaisesRegex(ValidationError, "desteklenmiyor"):
            UnifiedAnalysisRefreshService(self.service, feed, source="unknown")


if __name__ == "__main__":
    unittest.main()

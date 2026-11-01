"""Conservative, read-only technology hints from stored service evidence."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_freshness import SQLiteSurfaceFreshnessRepository
from xti.application.technology import TechnologyService
from xti.domain.assets import ValidationError
from xti.domain.services import (
    SERVICE_POLICY_VERSION,
    SERVICE_PORT_HINTS,
    SERVICE_PORTS,
    ServicePortResult,
    ServiceScanResult,
)


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
ADDRESS = "93.184.216.34"


def service_result(
    *, opened: tuple[int, ...] = (22, 443), unknown: tuple[int, ...] = (),
    dns_status: str = "resolved",
) -> ServiceScanResult:
    observed = (NOW - timedelta(hours=1)).isoformat()
    resolved = dns_status == "resolved"
    return ServiceScanResult(
        "example.com", ADDRESS, observed, observed, SERVICE_POLICY_VERSION,
        dns_status, (ADDRESS,) if resolved else (), ADDRESS if resolved else None,
        tuple(ServicePortResult(
            port,
            "unknown" if port in unknown else "open" if port in opened else "closed",
            SERVICE_PORT_HINTS[port],
        ) for port in SERVICE_PORTS) if resolved else (),
        tuple(f"{port}/tcp: sonuç alınamadı." for port in unknown) if resolved
        else ("DNS doğrulaması tamamlanamadı.",),
        ("Yalnız TCP bağlantısı.",),
    )


class TechnologyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.asset, _ = self.assets.add("example.com")
        self.surface = SQLiteSurfaceRepository(self.path, clock=lambda: NOW)
        self.service = TechnologyService(
            self.assets, SQLiteSurfaceFreshnessRepository(self.path), clock=lambda: NOW,
        )

    def approve(self) -> None:
        self.surface.activate(
            self.asset.id, self.asset.value, "Kendi kurumsal alan adım",
            (NOW - timedelta(days=2)).isoformat(),
        )

    def append(self, result: ServiceScanResult, *, recorded_at=NOW - timedelta(hours=1)):
        return SQLiteSurfaceServiceScanRepository(
            self.path, clock=lambda: recorded_at,
        ).append_check(self.asset.id, "Yönettiğim kesin genel IP", result)

    def test_missing_service_evidence_is_honest_and_read_only(self):
        before = self.path.read_bytes()
        report = self.service.show("EXAMPLE.COM")
        self.assertEqual(report.scope_status, "missing")
        self.assertEqual(report.coverage.status, "not_checked")
        self.assertEqual((report.hint_count, report.cve_match_eligible_count), (0, 0))
        self.assertEqual(report.hints, ())
        self.assertEqual(self.path.read_bytes(), before)

    def test_open_ports_are_hints_without_vendor_product_version_or_cve_match(self):
        self.approve()
        self.append(service_result(opened=(22, 443)))
        before = self.path.read_bytes()
        report = self.service.show("example.com")
        self.assertEqual(report.coverage.status, "current")
        self.assertEqual(report.checked_address, ADDRESS)
        self.assertEqual(report.hint_count, 2)
        self.assertEqual(report.cve_match_eligible_count, 0)
        self.assertEqual([item.port for item in report.hints], [22, 443])
        for item in report.hints:
            self.assertEqual((item.vendor, item.product, item.version), (None, None, None))
            self.assertEqual(item.confidence, "hint")
            self.assertEqual(item.detection_method, "tcp_connect_only")
            self.assertFalse(item.cve_match_eligible)
            self.assertIn("CVE", item.limitations[-1])
        self.assertEqual(self.path.read_bytes(), before)

    def test_partial_failed_stale_and_future_evidence_stay_distinct(self):
        self.approve()
        self.append(service_result(opened=(443,), unknown=(22,)))
        partial = self.service.show("example.com")
        self.assertEqual(partial.coverage.status, "partial")
        self.assertEqual([item.port for item in partial.hints], [443])

        stale_path = Path(self.temp.name) / "stale" / "xti.db"
        assets = SQLiteAssetRepository(stale_path)
        assets.initialize()
        asset, _ = assets.add("example.com")
        surface = SQLiteSurfaceRepository(stale_path, clock=lambda: NOW)
        surface.activate(asset.id, asset.value, "Yetkili adres", NOW.isoformat())
        SQLiteSurfaceServiceScanRepository(
            stale_path, clock=lambda: NOW - timedelta(days=2),
        ).append_check(asset.id, "Yönettiğim IP", service_result())
        stale_service = TechnologyService(
            assets, SQLiteSurfaceFreshnessRepository(stale_path), clock=lambda: NOW,
        )
        stale = stale_service.show("example.com")
        self.assertEqual(stale.coverage.status, "stale")
        self.assertTrue(all(item.evidence_freshness == "stale" for item in stale.hints))

        future_path = Path(self.temp.name) / "future" / "xti.db"
        future_assets = SQLiteAssetRepository(future_path)
        future_assets.initialize()
        future_asset, _ = future_assets.add("example.com")
        future_surface = SQLiteSurfaceRepository(future_path, clock=lambda: NOW)
        future_surface.activate(
            future_asset.id, future_asset.value, "Yetkili adres", NOW.isoformat(),
        )
        SQLiteSurfaceServiceScanRepository(
            future_path, clock=lambda: NOW + timedelta(minutes=1),
        ).append_check(future_asset.id, "Yönettiğim IP", service_result())
        future = TechnologyService(
            future_assets, SQLiteSurfaceFreshnessRepository(future_path), clock=lambda: NOW,
        ).show("example.com")
        self.assertEqual(future.coverage.status, "clock_error")
        self.assertTrue(all(
            item.evidence_freshness == "clock_error" for item in future.hints
        ))

        failed_path = Path(self.temp.name) / "failed" / "xti.db"
        failed_assets = SQLiteAssetRepository(failed_path)
        failed_assets.initialize()
        failed_asset, _ = failed_assets.add("example.com")
        failed_surface = SQLiteSurfaceRepository(failed_path, clock=lambda: NOW)
        failed_surface.activate(
            failed_asset.id, failed_asset.value, "Yetkili adres", NOW.isoformat(),
        )
        SQLiteSurfaceServiceScanRepository(
            failed_path, clock=lambda: NOW,
        ).append_check(
            failed_asset.id, "Yönettiğim IP", service_result(dns_status="failed"),
        )
        failed = TechnologyService(
            failed_assets, SQLiteSurfaceFreshnessRepository(failed_path), clock=lambda: NOW,
        ).show("example.com")
        self.assertEqual(failed.coverage.status, "failed")
        self.assertEqual(failed.hints, ())

    def test_invalid_threshold_and_unknown_asset_fail_without_mutation(self):
        before = self.path.read_bytes()
        for value in (0, 8761, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, "1–8760"):
                    self.service.show("example.com", stale_after_hours=value)
        with self.assertRaisesRegex(ValidationError, "kayıtlı değil"):
            self.service.show("unknown.example")
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

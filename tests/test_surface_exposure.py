"""Read-only, explainable candidates from stored surface evidence."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_surface_freshness import SQLiteSurfaceFreshnessRepository
from xti.application.surface_exposure import SurfaceExposureService
from xti.domain.assets import ValidationError
from xti.domain.enrichment import ProbeResult
from xti.domain.mail import MailDnsResult
from xti.domain.services import (
    SERVICE_POLICY_VERSION,
    SERVICE_PORT_HINTS,
    SERVICE_PORTS,
    ServicePortResult,
    ServiceScanResult,
)
from xti.domain.surface import SurfaceDiscoveryRunRequest


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
ADDRESS = "93.184.216.34"


def tls_failed_result() -> ProbeResult:
    observed = (NOW - timedelta(hours=1)).isoformat()
    return ProbeResult(
        "example.com", observed, observed, "exposure-web-test-v1",
        "resolved", (ADDRESS,), "failed", "not_checked", None,
        ADDRESS, ("TLS doğrulaması tamamlanamadı.",), ("Sınırlı kontrol.",),
    )


def mail_result(*, null_mx: bool = False) -> MailDnsResult:
    observed = (NOW - timedelta(hours=1)).isoformat()
    return MailDnsResult(
        "example.com", observed, observed, "exposure-mail-test-v1",
        "present", ("0 .",) if null_mx else ("10 mail.example.com",),
        "missing", (), "missing", (), (), ("Sınırlı DNS kanıtı.",),
    )


def service_result(*, opened: tuple[int, ...]) -> ServiceScanResult:
    observed = (NOW - timedelta(hours=1)).isoformat()
    return ServiceScanResult(
        "example.com", ADDRESS, observed, observed, SERVICE_POLICY_VERSION,
        "resolved", (ADDRESS,), ADDRESS,
        tuple(ServicePortResult(
            port, "open" if port in opened else "closed", SERVICE_PORT_HINTS[port],
        ) for port in SERVICE_PORTS),
        (), ("Yalnız TCP bağlantısı.",),
    )


class SurfaceExposureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.asset, _ = self.assets.add("example.com")
        self.surface = SQLiteSurfaceRepository(
            self.path, clock=lambda: NOW - timedelta(hours=1),
        )
        self.service = SurfaceExposureService(
            self.assets, SQLiteSurfaceFreshnessRepository(self.path), clock=lambda: NOW,
        )

    def approve(self) -> None:
        self.surface.activate(
            self.asset.id, self.asset.value, "Kendi kurumsal alan adım",
            (NOW - timedelta(days=2)).isoformat(),
        )

    def record_discovery(self, status: str, *, finished=None, error=None):
        finished = finished or NOW - timedelta(hours=1)
        return SQLiteSurfaceCandidateRepository(self.path).record_discovery(
            self.asset.id, self.asset.value, (), SurfaceDiscoveryRunRequest(
                status, "https://crt.sh/?q=%25.example.com",
                (finished - timedelta(minutes=1)).isoformat(), finished.isoformat(),
                0, 0, 0, (), 0, error,
            ),
        )[1]

    def test_missing_evidence_and_unsupported_checks_are_honest_and_read_only(self):
        before = self.path.read_bytes()
        report = self.service.show("EXAMPLE.COM")
        self.assertEqual(report.candidate_count, 0)
        self.assertEqual(report.scope_status, "missing")
        self.assertEqual(
            [item.status for item in report.coverage],
            [
                "not_checked", "not_checked", "not_checked", "not_checked",
                "not_checked", "unsupported",
            ],
        )
        self.assertEqual(report.coverage[0].check_type, "passive_discovery")
        self.assertEqual(report.coverage[4].check_type, "subdomain_takeover")
        self.assertEqual(report.coverage[-1].check_type, "admin_panel_identification")
        self.assertEqual((report.current_coverage_count, report.attention_coverage_count), (0, 5))
        self.assertIn("surface approve example.com", report.scope_next_command)
        self.assertIn("surface discover example.com", report.coverage[0].next_command)
        self.assertEqual(self.path.read_bytes(), before)

    def test_passive_complete_empty_failure_and_age_are_distinct(self):
        self.record_discovery("complete")
        current = self.service.show("example.com")
        discovery = current.coverage[0]
        self.assertEqual(discovery.status, "current")
        self.assertIsNone(discovery.next_command)
        self.assertIn("yalnız bu kaynak yanıtında", discovery.reason)

        stale_service = SurfaceExposureService(
            self.assets, SQLiteSurfaceFreshnessRepository(self.path),
            clock=lambda: NOW + timedelta(hours=24),
        )
        stale = stale_service.show("example.com").coverage[0]
        self.assertEqual(stale.status, "stale")
        self.assertIn("surface discover example.com", stale.next_command)

        self.record_discovery("failed", error="Kaynak yanıt vermedi.")
        failed = self.service.show("example.com").coverage[0]
        self.assertEqual(failed.status, "failed")
        self.assertIn("boş veya güvenli sonuç değildir", failed.reason)

    def test_corrupt_latest_discovery_run_fails_closed(self):
        self.record_discovery("complete")
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("UPDATE surface_discovery_runs SET warnings = '{}' ")
            connection.commit()
        finally:
            connection.close()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "geçmişi bozuk"):
            self.service.show("example.com")
        self.assertEqual(self.path.read_bytes(), before)

    def test_web_mail_and_reachable_service_candidates_keep_limitations(self):
        self.approve()
        self.surface.append_check(self.asset.id, tls_failed_result())
        SQLiteSurfaceMailRepository(
            self.path, clock=lambda: NOW - timedelta(hours=1),
        ).append_check(self.asset.id, mail_result())
        SQLiteSurfaceServiceScanRepository(
            self.path, clock=lambda: NOW - timedelta(hours=1),
        ).append_check(
            self.asset.id, "Yönettiğim kesin genel IP",
            service_result(opened=(22, 443, 8443)),
        )

        before = self.path.read_bytes()
        report = self.service.show("example.com")
        self.assertEqual(report.scope_status, "active")
        self.assertEqual(report.candidate_count, 5)
        self.assertEqual(report.stale_candidate_count, 0)
        self.assertEqual(report.clock_error_candidate_count, 0)
        self.assertEqual(
            [item.candidate_type for item in report.candidates],
            [
                "tls_connection_or_validation_issue",
                "mail_spf_missing",
                "mail_dmarc_missing",
                "remote_access_port_22",
                "alternate_web_port_8443",
            ],
        )
        service_candidates = [
            item for item in report.candidates
            if item.category == "service_reachability"
        ]
        self.assertTrue(all("ürün" in item.limitations[0] for item in service_candidates))
        self.assertEqual(self.path.read_bytes(), before)

    def test_null_mx_does_not_create_false_missing_policy_candidates(self):
        self.approve()
        SQLiteSurfaceMailRepository(
            self.path, clock=lambda: NOW - timedelta(hours=1),
        ).append_check(self.asset.id, mail_result(null_mx=True))
        report = self.service.show("example.com")
        self.assertEqual(report.candidate_count, 0)
        self.assertEqual(report.coverage[2].status, "current")

    def test_stale_and_future_evidence_are_not_presented_as_current(self):
        self.approve()
        old_repository = SQLiteSurfaceMailRepository(
            self.path, clock=lambda: NOW - timedelta(days=2),
        )
        old_repository.append_check(self.asset.id, mail_result())
        stale = self.service.show("example.com", stale_after_hours=24)
        self.assertEqual(stale.coverage[2].status, "stale")
        self.assertTrue(all(
            item.evidence_freshness == "stale" for item in stale.candidates
        ))

        future_path = Path(self.temp.name) / "future" / "xti.db"
        assets = SQLiteAssetRepository(future_path)
        assets.initialize()
        asset, _ = assets.add("future.example")
        surface = SQLiteSurfaceRepository(future_path, clock=lambda: NOW)
        surface.activate(asset.id, asset.value, "Yetkili adres", NOW.isoformat())
        observed = NOW.isoformat()
        future_mail = MailDnsResult(
            "future.example", observed, observed, "future-test-v1",
            "present", ("10 mail.future.example",), "missing", (),
            "missing", (), (), (),
        )
        SQLiteSurfaceMailRepository(
            future_path, clock=lambda: NOW + timedelta(minutes=1),
        ).append_check(asset.id, future_mail)
        report = SurfaceExposureService(
            assets, SQLiteSurfaceFreshnessRepository(future_path), clock=lambda: NOW,
        ).show("future.example")
        self.assertEqual(report.coverage[2].status, "clock_error")
        self.assertEqual(report.clock_error_candidate_count, 2)
        self.assertTrue(all(
            item.evidence_freshness == "clock_error" for item in report.candidates
        ))

    def test_invalid_threshold_and_unknown_root_fail_without_mutation(self):
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

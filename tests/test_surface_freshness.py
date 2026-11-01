"""Read-only freshness classification for stored surface evidence."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_freshness import SQLiteSurfaceFreshnessRepository
from xti.application.surface_freshness import SurfaceFreshnessService
from xti.domain.assets import ValidationError
from xti.domain.enrichment import ProbeResult
from xti.domain.mail import MailDnsResult


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


def web_result():
    observed = (NOW - timedelta(hours=1)).isoformat()
    return ProbeResult(
        "example.com", observed, observed, "freshness-web-test-v1",
        "resolved", ("93.184.216.34",), "valid", "responded", 200,
        "93.184.216.34", (), ("Sınırlı HEAD kontrolü.",),
    )


def partial_mail_result():
    observed = (NOW - timedelta(hours=24)).isoformat()
    return MailDnsResult(
        "example.com", observed, observed, "freshness-mail-test-v1",
        "present", ("10 mail.example.com",),
        "failed", (),
        "present", ("v=DMARC1; p=reject",),
        ("SPF: sorgu tamamlanamadı.",), (),
    )


class SurfaceFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.asset, _ = self.assets.add("example.com")
        self.service = SurfaceFreshnessService(
            self.assets, SQLiteSurfaceFreshnessRepository(self.path), clock=lambda: NOW,
        )

    def test_missing_scope_and_evidence_are_visible_without_writes(self):
        before = self.path.read_bytes()
        report = self.service.show("EXAMPLE.COM")
        self.assertEqual(report.scope_status, "missing")
        self.assertEqual((report.current_count, report.stale_count), (0, 0))
        self.assertEqual((report.never_count, report.clock_error_count), (3, 0))
        self.assertEqual(
            [item.check_type for item in report.items],
            ["web", "mail", "services"],
        )
        self.assertTrue(all(item.result_status == "not_checked" for item in report.items))
        self.assertEqual(self.path.read_bytes(), before)

    def test_current_stale_and_never_are_separate_from_result_quality(self):
        surface = SQLiteSurfaceRepository(
            self.path, clock=lambda: NOW - timedelta(hours=1),
        )
        surface.activate(
            self.asset.id, self.asset.value, "Kendi alan adım",
            (NOW - timedelta(days=2)).isoformat(),
        )
        surface.append_check(self.asset.id, web_result())
        SQLiteSurfaceMailRepository(
            self.path, clock=lambda: NOW - timedelta(hours=24),
        ).append_check(self.asset.id, partial_mail_result())

        before = self.path.read_bytes()
        report = self.service.show("example.com", freshness_hours=24)
        self.assertEqual(report.scope_status, "active")
        self.assertEqual(
            (report.current_count, report.stale_count, report.never_count),
            (1, 1, 1),
        )
        items = {item.check_type: item for item in report.items}
        self.assertEqual(
            (items["web"].freshness, items["web"].result_status),
            ("current", "complete"),
        )
        self.assertEqual(
            (items["mail"].freshness, items["mail"].result_status),
            ("stale", "partial"),
        )
        self.assertEqual(items["services"].freshness, "never")
        self.assertEqual(self.path.read_bytes(), before)

    def test_future_record_time_is_clock_error_and_revoked_scope_is_preserved(self):
        surface = SQLiteSurfaceRepository(
            self.path, clock=lambda: NOW + timedelta(minutes=1),
        )
        surface.activate(
            self.asset.id, self.asset.value, "Kendi alan adım",
            (NOW - timedelta(days=1)).isoformat(),
        )
        surface.append_check(self.asset.id, web_result())
        surface.revoke(
            self.asset.id, "Artık yönetmiyorum", (NOW + timedelta(minutes=2)).isoformat(),
        )
        report = self.service.show("example.com")
        self.assertEqual(report.scope_status, "revoked")
        self.assertEqual(report.clock_error_count, 1)
        self.assertEqual(report.items[0].freshness, "clock_error")

    def test_invalid_threshold_and_unknown_root_fail_without_mutation(self):
        before = self.path.read_bytes()
        for value in (0, 8761, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValidationError, "1–8760"):
                    self.service.show("example.com", freshness_hours=value)
        with self.assertRaisesRegex(ValidationError, "kayıtlı değil"):
            self.service.show("unknown.example")
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

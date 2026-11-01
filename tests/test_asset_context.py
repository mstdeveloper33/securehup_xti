"""Human asset criticality and evidence-derived internet context."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tests.test_services import scan_result
from tests.test_surface import result as web_result
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_asset_context import SQLiteAssetCriticalityRepository
from xti.application.asset_context import AssetCriticalityService
from xti.domain.asset_context import build_internet_exposure_context
from xti.domain.assets import ValidationError
from xti.domain.services import ServiceScanChange, ServiceScanCheck
from xti.domain.surface import SurfaceChange, SurfaceCheck, SurfaceScope
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def scope(*, active=True):
    return SurfaceScope(
        asset_id="11111111-1111-4111-8111-111111111111",
        asset_value="example.com", active=active, reason="Yetkili kurumsal alan adı",
        created_at=NOW.isoformat(), updated_at=NOW.isoformat(),
    )


def web_check(*, recorded_at=None, result=None):
    return SurfaceCheck(
        id="22222222-2222-4222-8222-222222222222", asset_id=scope().asset_id,
        asset_value="example.com", result=result or web_result(),
        state_sha256="a" * 64,
        change=SurfaceChange(
            kind="baseline", changed_fields=(), added_addresses=(),
            removed_addresses=(),
        ),
        recorded_at=(recorded_at or NOW).isoformat(),
    )


def service_check(*, recorded_at=None, opened=(443,)):
    return ServiceScanCheck(
        id="33333333-3333-4333-8333-333333333333", asset_id=scope().asset_id,
        asset_value="example.com", authorization_reason="Yönettiğim sabit sunucu",
        result=scan_result(opened=opened), state_sha256="b" * 64,
        change=ServiceScanChange(kind="baseline", changed_fields=(), transitions=()),
        recorded_at=(recorded_at or NOW).isoformat(),
    )


class AssetContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.storage.add("example.com")
        self.now = NOW
        self.repository = SQLiteAssetCriticalityRepository(self.path)
        self.service = AssetCriticalityService(
            self.repository, clock=lambda: self.now,
        )

    def test_lifecycle_is_idempotent_reversible_and_append_only(self):
        first = self.service.set(
            "EXAMPLE.COM", level="critical",
            reason="Müşteri işlemlerinin ana üretim hizmeti.",
        )
        self.assertEqual((first.action, first.changed), ("set", True))
        same = self.service.set(
            "example.com", level="critical",
            reason="Müşteri işlemlerinin ana üretim hizmeti.",
        )
        self.assertEqual((same.action, same.changed), ("unchanged", False))
        self.now += timedelta(minutes=1)
        updated = self.service.set(
            "example.com", level="high",
            reason="Gelir üreten hizmet; kısa kesinti tolere edilebilir.",
        )
        self.assertEqual(updated.action, "updated")
        self.now += timedelta(minutes=1)
        cleared = self.service.clear(
            "example.com", reason="Varlık üretim görevinden çıkarıldı.",
        )
        self.assertEqual((cleared.action, cleared.record.active), ("cleared", False))
        unchanged = self.service.clear(
            "example.com", reason="Varlık üretim görevinden çıkarıldı.",
        )
        self.assertFalse(unchanged.changed)
        self.now += timedelta(minutes=1)
        restored = self.service.set(
            "example.com", level="critical",
            reason="Ana üretim görevi yeniden etkinleştirildi.",
        )
        self.assertEqual(restored.action, "reactivated")
        details = self.service.show("example.com")
        self.assertEqual(
            [event.action for event in details.events],
            ["set", "updated", "cleared", "reactivated"],
        )
        self.assertEqual(details.total_event_count, 4)
        self.assertEqual(details.record.created_at, first.record.created_at)

    def test_validation_corruption_and_unknown_assets_fail_closed(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.service.set("unknown.example", level="high", reason="Geçerli gerekçe metni.")
        with self.assertRaises(ValidationError):
            self.service.set("example.com", level="urgent", reason="Geçerli gerekçe metni.")
        with self.assertRaises(ValidationError):
            self.service.set("example.com", level="high", reason="kısa")
        with self.assertRaises(ValidationError):
            self.service.show("example.com")
        self.assertEqual(self.path.read_bytes(), before)

        record = self.service.set(
            "example.com", level="high", reason="Kritik olmayan üretim hizmeti.",
        ).record
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE asset_criticalities SET reason='x' WHERE asset_id=?",
                (record.asset_id,),
            )
        corrupted = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.service.show("example.com")
        self.assertEqual(self.path.read_bytes(), corrupted)

    def test_backup_restore_preserves_decision_and_history(self):
        self.service.set(
            "example.com", level="high", reason="Gelir üreten dış hizmet.",
        )
        self.now += timedelta(minutes=1)
        self.service.set(
            "example.com", level="critical", reason="Kesinti doğrudan müşteri etkisi yaratır.",
        )
        before = self.service.show("example.com")
        backup = self.storage.backup(Path(self.temp.name) / "backup" / "criticality.db")
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        after = SQLiteAssetCriticalityRepository(restored).show(
            "example.com", event_limit=50,
        )
        self.assertEqual(after, before)

    def test_clock_regression_keeps_event_time_without_reversing_current_record(self):
        first = self.service.set(
            "example.com", level="high", reason="Gelir üreten üretim hizmeti.",
        ).record
        self.now -= timedelta(hours=1)
        updated = self.service.set(
            "example.com", level="critical",
            reason="Yeni değerlendirmede ana üretim hizmeti.",
        ).record
        details = self.service.show("example.com")
        self.assertEqual(updated.updated_at, first.updated_at)
        self.assertLess(
            datetime.fromisoformat(details.events[-1].recorded_at),
            datetime.fromisoformat(details.events[0].recorded_at),
        )
        self.assertEqual([event.action for event in details.events], ["set", "updated"])

    def test_internet_context_separates_current_stale_dns_and_absence(self):
        current = build_internet_exposure_context(
            scope(), web_check(), service_check(), checked_at=NOW,
            stale_after_hours=24,
        )
        self.assertEqual((current.status, current.freshness), ("confirmed", "current"))
        self.assertEqual(current.web_http_status_code, 200)
        self.assertEqual(current.open_service_ports, (443,))

        dns_only_result = web_result(tls="failed", http="not_attempted", code=None)
        dns_only = build_internet_exposure_context(
            scope(), web_check(result=dns_only_result), None, checked_at=NOW,
            stale_after_hours=24,
        )
        self.assertEqual(dns_only.status, "dns_only")
        stale = build_internet_exposure_context(
            scope(), web_check(recorded_at=NOW - timedelta(days=2)), None,
            checked_at=NOW, stale_after_hours=24,
        )
        self.assertEqual((stale.status, stale.freshness), ("unknown", "stale"))
        absent = build_internet_exposure_context(
            scope(), None, None, checked_at=NOW, stale_after_hours=24,
        )
        self.assertEqual((absent.status, absent.freshness), ("unknown", "never"))
        self.assertIn("no_surface_evidence", absent.reasons)
        inactive = build_internet_exposure_context(
            scope(active=False), web_check(), None, checked_at=NOW,
            stale_after_hours=24,
        )
        self.assertEqual(inactive.freshness, "scope_inactive")

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_terminal_json_and_doctor_expose_human_owned_context(self):
        code, stdout, stderr = self.invoke(
            "assets", "criticality-set", "example.com", "--level", "critical",
            "--reason", "Ana üretim ve müşteri giriş hizmeti.",
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout)["data"]["action"], "set")
        before = self.path.read_bytes()
        code, stdout, stderr = self.invoke(
            "assets", "criticality-show", "example.com", as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Varlık iş önemi", stdout)
        self.assertIn("Kritik", stdout)
        code, stdout, stderr = self.invoke("doctor", as_json=False)
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Varlık iş önemi: 1 etkin / 1 toplam", stdout)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

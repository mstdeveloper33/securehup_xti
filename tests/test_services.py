"""Approved exact-IP TCP service inventory and append-only evidence."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.services import SurfaceServiceScanService
from xti.application.surface import SurfaceService
from xti.domain.assets import ValidationError
from xti.domain.services import (
    SERVICE_POLICY_VERSION,
    SERVICE_PORT_HINTS,
    SERVICE_PORTS,
    ServicePortResult,
    ServiceScanResult,
)


START = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
ADDRESS = "93.184.216.34"


def scan_result(*, opened=(), unknown=(), address=ADDRESS, domain="example.com"):
    states = {
        port: "open" if port in opened else "unknown" if port in unknown else "closed"
        for port in SERVICE_PORTS
    }
    return ServiceScanResult(
        domain=domain, requested_address=address,
        started_at=START.isoformat(),
        finished_at=(START + timedelta(seconds=1)).isoformat(),
        policy_version=SERVICE_POLICY_VERSION, dns_status="resolved",
        addresses=(address,), checked_address=address,
        ports=tuple(
            ServicePortResult(port, states[port], SERVICE_PORT_HINTS[port])
            for port in SERVICE_PORTS
        ),
        errors=tuple(
            f"TCP {port}: bağlantı sonucu süre sınırında belirlenemedi."
            for port in SERVICE_PORTS if states[port] == "unknown"
        ),
        notes=("Yalnız TCP bağlantısı.",),
    )


class SequenceProbe:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []

    def check(self, domain, address):
        self.calls.append((domain, address))
        return self.values.pop(0)


class SurfaceServiceScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _ = self.storage.add("example.com")
        self.surface = SQLiteSurfaceRepository(self.path, clock=lambda: START)
        self.repository = SQLiteSurfaceServiceScanRepository(
            self.path, clock=lambda: START + timedelta(minutes=1),
        )

    def approve(self):
        SurfaceService(
            self.storage, self.surface, clock=lambda: START,
        ).approve("example.com", "Kendi kurumsal alan adım")

    def service(self, probe=None):
        return SurfaceServiceScanService(
            self.storage, self.surface, self.repository, probe,
        )

    def test_active_domain_and_exact_public_ip_are_required_before_probe(self):
        probe = SequenceProbe([scan_result()])
        service = self.service(probe)
        for address in ("127.0.0.1", "10.0.0.1", "not-an-ip"):
            with self.subTest(address=address):
                with self.assertRaises(ValidationError):
                    service.check("example.com", address, "Yetkili sunucum")
        with self.assertRaisesRegex(ValidationError, "kapsamına alınmamış"):
            service.check("example.com", ADDRESS, "Yetkili sunucum")
        self.assertEqual(probe.calls, [])

    def test_baseline_repeat_and_port_change_are_append_only(self):
        self.approve()
        probe = SequenceProbe([
            scan_result(opened=(22, 443)),
            scan_result(opened=(22, 443)),
            scan_result(opened=(443,), unknown=(25,)),
        ])
        service = self.service(probe)
        first = service.check("example.com", ADDRESS, "Yönettiğim sabit sunucu")
        second = service.check("example.com", ADDRESS, "Yönettiğim sabit sunucu")
        third = service.check("example.com", ADDRESS, "Yönettiğim sabit sunucu")
        self.assertEqual(
            [first.change.kind, second.change.kind, third.change.kind],
            ["baseline", "unchanged", "changed"],
        )
        self.assertEqual(third.change.changed_fields, ("ports",))
        self.assertEqual(
            [(item.port, item.before, item.after) for item in third.change.transitions],
            [(22, "open", "closed"), (25, "closed", "unknown")],
        )
        details = service.show("example.com")
        self.assertEqual(details.total_check_count, 3)
        self.assertEqual([item.id for item in details.checks], [first.id, second.id, third.id])
        self.assertEqual(probe.calls, [("example.com", ADDRESS)] * 3)

    def test_probe_identity_mismatch_and_scope_revocation_prevent_commit(self):
        self.approve()
        mismatch = SequenceProbe([scan_result(domain="other.example")])
        with self.assertRaisesRegex(ValidationError, "eşleşmiyor"):
            self.service(mismatch).check("example.com", ADDRESS, "Yetkili sunucum")

        outer = self

        class RevokingProbe:
            def check(self, domain, address):
                SurfaceService(
                    outer.storage, outer.surface,
                    clock=lambda: START + timedelta(minutes=2),
                ).revoke("example.com", "Kontrol sırasında yetki kaldırıldı")
                return scan_result()

        with self.assertRaisesRegex(ValidationError, "kaldırılmış"):
            self.service(RevokingProbe()).check(
                "example.com", ADDRESS, "Yönettiğim sabit sunucu",
            )
        self.assertEqual(self.service().show("example.com").total_check_count, 0)

    def test_corrupt_evidence_fails_closed_without_rewrite(self):
        self.approve()
        self.service(SequenceProbe([scan_result(opened=(443,))])).check(
            "example.com", ADDRESS, "Yönettiğim sabit sunucu",
        )
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                "UPDATE surface_service_checks SET state_sha256 = ?", ("0" * 64,),
            )
            connection.commit()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "Servis kontrol geçmişi bozuk"):
            self.service().show("example.com")
        self.assertEqual(self.path.read_bytes(), before)

    def test_backup_restore_preserves_service_evidence(self):
        self.approve()
        original = self.service(SequenceProbe([scan_result(opened=(80, 443))])).check(
            "example.com", ADDRESS, "Yönettiğim sabit sunucu",
        )
        backup = Path(self.temp.name) / "backup.db"
        self.storage.backup(backup)
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        details = SQLiteSurfaceServiceScanRepository(restored).details(
            self.asset.id, history_limit=20,
        )
        self.assertEqual(details.checks[0], original)

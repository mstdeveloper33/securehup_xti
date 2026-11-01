"""Local human-approved supplier inventory behavior."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.application.suppliers import SupplierService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


class SupplierInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.now = NOW
        self.repository = SQLiteSupplierRepository(self.path)
        self.service = SupplierService(self.repository, clock=lambda: self.now)

    def add(self, name="Örnek Bulut", domain="vendor.example"):
        return self.service.add(
            name,
            domain=domain,
            relationship_type="cloud",
            criticality="high",
            reason="Ana yedekleme hizmetini sağlıyor.",
        )

    def test_lifecycle_is_idempotent_reversible_and_append_only(self):
        first = self.add()
        self.assertEqual((first.action, first.changed), ("added", True))
        same = self.add()
        self.assertEqual((same.action, same.changed), ("unchanged", False))

        self.now += timedelta(minutes=1)
        updated = self.service.update(
            first.supplier.id,
            name="Örnek Cloud",
            criticality="critical",
            reason="Müşteri verisinin ana saklama hizmetini sağlıyor.",
        )
        self.assertEqual((updated.action, updated.changed), ("updated", True))
        self.assertEqual(updated.supplier.primary_domain, "vendor.example")

        self.now += timedelta(minutes=1)
        revoked = self.service.revoke(
            first.supplier.id, reason="Hizmet sözleşmesi sona erdi.",
        )
        self.assertEqual((revoked.action, revoked.supplier.active), ("revoked", False))
        same_revoke = self.service.revoke(
            first.supplier.id, reason="Hizmet sözleşmesi sona erdi.",
        )
        self.assertFalse(same_revoke.changed)

        self.now += timedelta(minutes=1)
        restored = self.service.add(
            "Örnek Cloud",
            domain="vendor.example",
            relationship_type="cloud",
            criticality="critical",
            reason="Yeni sözleşmeyle hizmet yeniden kullanılmaya başlandı.",
        )
        self.assertEqual((restored.action, restored.changed), ("reactivated", True))
        self.assertEqual(restored.supplier.id, first.supplier.id)
        details = self.service.show(first.supplier.id)
        self.assertEqual(
            [event.action for event in details.events],
            ["added", "updated", "revoked", "reactivated"],
        )
        self.assertEqual(details.total_event_count, 4)
        self.assertEqual(details.supplier.created_at, first.supplier.created_at)

    def test_same_name_different_domains_remain_distinct(self):
        first = self.add(name="Ortak İsim", domain="first.example")
        second = self.add(name="Ortak İsim", domain="second.example")
        records = self.service.list()
        self.assertEqual(len(records), 2)
        self.assertNotEqual(first.supplier.id, second.supplier.id)
        self.assertEqual(
            {record.primary_domain for record in records},
            {"first.example", "second.example"},
        )

        with self.assertRaisesRegex(ValidationError, "update"):
            self.service.add(
                "Başka Kuruluş",
                domain="first.example",
                relationship_type="software",
                criticality="low",
                reason="Farklı bir ilişki olduğu iddia ediliyor.",
            )

    def test_validation_and_corruption_fail_closed(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.service.add(
                "x", domain="vendor.example", relationship_type="cloud",
                criticality="high", reason="Geçerli uzunlukta gerekçe.",
            )
        with self.assertRaises(ValidationError):
            self.service.add(
                "Geçerli Ad", domain="vendor.example", relationship_type="hosting",
                criticality="high", reason="Geçerli uzunlukta gerekçe.",
            )
        with self.assertRaises(ValidationError):
            self.service.update(
                "11111111-1111-4111-8111-111111111111",
                reason="Geçerli uzunlukta gerekçe.",
            )
        self.assertEqual(self.path.read_bytes(), before)

        supplier = self.add().supplier
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE suppliers SET criticality='low' WHERE id=?", (supplier.id,),
            )
        corrupted = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "geçmişle uyuşmuyor"):
            self.service.show(supplier.id)
        self.assertEqual(self.path.read_bytes(), corrupted)

    def test_list_and_show_are_read_only_and_backup_restore_preserves_history(self):
        supplier = self.add().supplier
        self.now += timedelta(minutes=1)
        self.service.update(
            supplier.id,
            relationship_type="software",
            reason="Hizmet artık yazılım lisansı olarak sınıflandırılıyor.",
        )
        before_bytes = self.path.read_bytes()
        before = self.service.show(supplier.id)
        self.assertEqual(self.service.list()[0].id, supplier.id)
        self.assertEqual(self.path.read_bytes(), before_bytes)

        backup = self.storage.backup(Path(self.temp.name) / "backup" / "supplier.db")
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        after = SQLiteSupplierRepository(restored).show(supplier.id, event_limit=50)
        self.assertEqual(after, before)

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_terminal_json_and_doctor_expose_supplier_inventory(self):
        code, stdout, stderr = self.invoke(
            "suppliers", "add", "Örnek Bulut", "--domain", "vendor.example",
            "--relationship", "cloud", "--criticality", "high",
            "--reason", "Ana yedekleme hizmetini sağlıyor.",
        )
        self.assertEqual((code, stderr), (0, ""))
        payload = json.loads(stdout)["data"]
        self.assertEqual(payload["action"], "added")
        supplier_id = payload["supplier"]["id"]

        before = self.path.read_bytes()
        code, stdout, stderr = self.invoke("suppliers", "list", as_json=False)
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Örnek Bulut", stdout)
        self.assertIn("Aynı isim", stdout)
        code, stdout, stderr = self.invoke(
            "suppliers", "show", supplier_id, as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Risk puanı üretilmedi", stdout)
        code, stdout, stderr = self.invoke("doctor", as_json=False)
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Tedarikçi envanteri: 1 etkin / 1 toplam; 1", stdout)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

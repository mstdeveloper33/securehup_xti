"""User-verified product evidence lifecycle and terminal boundary."""

from contextlib import closing, redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_products import SQLiteAssetProductRepository
from xti.application.products import AssetProductService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


class MovingClock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> datetime:
        value = self.value
        self.value += timedelta(minutes=1)
        return value


class ProductEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.path = self.data / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.assets.add("example.com")
        self.clock = MovingClock()
        self.service = AssetProductService(
            SQLiteAssetProductRepository(self.path), clock=self.clock,
        )

    def test_unknown_asset_and_invalid_identity_fail_without_partial_write(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValidationError, "önce"):
            self.service.add(
                "unknown.example", part="a", vendor="apache", product="http_server",
                version="2.4.58", evidence="Yönetim ekranında elle doğrulandı.",
            )
        for field, value in (("part", "x"), ("vendor", "Apache Corp"),
                             ("product", "http:server"), ("version", "*")):
            values = dict(
                part="a", vendor="apache", product="http_server", version="2.4.58",
                evidence="Yönetim ekranında elle doğrulandı.",
            )
            values[field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.service.add("example.com", **values)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.service.list(), ())

    def test_lifecycle_is_idempotent_and_history_is_append_only(self):
        added = self.service.add(
            "EXAMPLE.COM.", part="a", vendor="Apache", product="HTTP_SERVER",
            version="2.4.58", evidence="Yönetim ekranında elle doğrulandı.",
        )
        self.assertEqual(added.action, "added")
        self.assertEqual(
            (added.record.asset_value, added.record.vendor, added.record.product),
            ("example.com", "apache", "http_server"),
        )
        unchanged = self.service.add(
            "example.com", part="a", vendor="apache", product="http_server",
            version="2.4.58", evidence="Yönetim ekranında elle doğrulandı.",
        )
        self.assertEqual(unchanged.action, "unchanged")
        updated = self.service.add(
            "example.com", part="a", vendor="apache", product="http_server",
            version="2.4.58", evidence="Paket yöneticisi çıktısıyla doğrulandı.",
        )
        self.assertEqual(updated.action, "updated")
        revoked = self.service.revoke(
            added.record.id, reason="Sunucudan kaldırıldığı elle doğrulandı.",
        )
        self.assertEqual((revoked.action, revoked.record.active), ("revoked", False))
        self.assertEqual(
            self.service.revoke(
                added.record.id, reason="Tekrar kaldırma isteği oluşturuldu.",
            ).action,
            "unchanged",
        )
        reactivated = self.service.add(
            "example.com", part="a", vendor="apache", product="http_server",
            version="2.4.58", evidence="Paket yeniden kuruldu ve sürüm doğrulandı.",
        )
        self.assertEqual((reactivated.action, reactivated.record.id),
                         ("reactivated", added.record.id))
        details = self.service.show(added.record.id)
        self.assertEqual(details.total_event_count, 4)
        self.assertEqual(
            [event.action for event in reversed(details.events)],
            ["added", "updated", "revoked", "reactivated"],
        )
        self.assertEqual(self.assets.inspect()["active_asset_product_count"], 1)

    def test_exact_asset_scope_and_active_filter_do_not_mix_tenants(self):
        self.assets.add("second.example")
        first = self.service.add(
            "example.com", part="a", vendor="openssl", product="openssl",
            version="1.0.1f", evidence="Paket listesinde sürüm doğrulandı.",
        )
        second = self.service.add(
            "second.example", part="o", vendor="canonical", product="ubuntu_linux",
            version="22.04", evidence="İşletim sistemi sürümü elle doğrulandı.",
        )
        self.service.revoke(first.record.id, reason="Eski paket artık kullanılmıyor.")
        self.assertEqual(self.service.list(asset_value="example.com"), ())
        self.assertEqual(
            [record.id for record in self.service.list(
                asset_value="example.com", active_only=False,
            )], [first.record.id],
        )
        self.assertEqual(
            [record.id for record in self.service.list(asset_value="second.example")],
            [second.record.id],
        )

    def test_clock_regression_preserves_event_and_does_not_reverse_record_time(self):
        added = self.service.add(
            "example.com", part="a", vendor="openssl", product="openssl",
            version="3.0.0", evidence="İlk paket çıktısıyla doğrulandı.",
        )
        regressed = AssetProductService(
            SQLiteAssetProductRepository(self.path),
            clock=lambda: NOW - timedelta(days=1),
        ).add(
            "example.com", part="a", vendor="openssl", product="openssl",
            version="3.0.0", evidence="Saat gerilerken yeni kanıt doğrulandı.",
        )
        self.assertEqual(regressed.action, "updated")
        self.assertEqual(regressed.record.updated_at, added.record.updated_at)
        details = self.service.show(added.record.id)
        self.assertEqual([event.action for event in reversed(details.events)],
                         ["added", "updated"])
        self.assertLess(details.events[0].recorded_at, details.events[1].recorded_at)

    def test_corrupt_record_or_event_fails_closed_without_mutation(self):
        result = self.service.add(
            "example.com", part="a", vendor="openssl", product="openssl",
            version="1.0.1f", evidence="Paket listesinde sürüm doğrulandı.",
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE asset_products SET vendor='Open SSL' WHERE id=?",
                (result.record.id,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "bozuk"):
            self.service.show(result.record.id)
        self.assertEqual(self.path.read_bytes(), before)

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE asset_products SET vendor='openssl' WHERE id=?",
                (result.record.id,),
            )
            connection.execute(
                "UPDATE asset_product_events SET evidence='x' WHERE asset_product_id=?",
                (result.record.id,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "geçmişi bozuk"):
            self.service.show(result.record.id)
        self.assertEqual(self.path.read_bytes(), before)

    def call_cli(self, *arguments: str) -> tuple[int, str, str]:
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_add_list_show_revoke_and_safe_json(self):
        code, output, error = self.call_cli(
            "products", "add", "example.com", "--part", "a",
            "--vendor", "apache", "--product", "http_server", "--version", "2.4.58",
            "--evidence", "Başlık <script>alert(1)</script> ile elle doğrulandı.",
        )
        self.assertEqual((code, error), (0, ""))
        added = json.loads(output)["data"]
        product_id = added["record"]["id"]
        before = self.path.read_bytes()
        listed = json.loads(self.call_cli("products", "list", "example.com")[1])["data"]
        shown = json.loads(self.call_cli("products", "show", product_id)[1])["data"]
        self.assertEqual(listed["records"][0]["id"], product_id)
        self.assertEqual(shown["record"]["evidence"],
                         "Başlık <script>alert(1)</script> ile elle doğrulandı.")
        self.assertEqual(self.path.read_bytes(), before)
        revoked = json.loads(self.call_cli(
            "products", "revoke", product_id, "--reason", "Paket kaldırıldı ve doğrulandı.",
        )[1])["data"]
        self.assertEqual(revoked["action"], "revoked")
        self.assertEqual(json.loads(self.call_cli("products", "list")[1])["data"]["records"], [])
        self.assertEqual(len(json.loads(self.call_cli(
            "products", "list", "--all",
        )[1])["data"]["records"]), 1)


if __name__ == "__main__":
    unittest.main()

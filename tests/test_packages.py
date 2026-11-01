"""Exact Red Hat RPM evidence lifecycle and terminal boundary."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_packages import SQLiteAssetPackageRepository
from xti.application.packages import AssetPackageService
from xti.domain.assets import ValidationError
from xti.domain.packages import redhat_rpm_purl, source_rpm_parts
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
CPE = "cpe:/o:redhat:enterprise_linux:6::client"


class MovingClock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> datetime:
        value = self.value
        self.value += timedelta(minutes=1)
        return value


class PackageEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.assets.add("example.com")
        self.service = AssetPackageService(
            SQLiteAssetPackageRepository(self.path), clock=MovingClock(),
        )

    def add(self, **changes):
        values = {
            "provider": "redhat", "name": "openssl", "epoch": 0,
            "version": "1.0.1e", "release": "16.el6_5.7", "architecture": "x86_64",
            "distribution_cpe": CPE,
            "source_rpm": "openssl-1.0.1e-16.el6_5.7.src.rpm",
            "evidence": "RPM sorgusu ve işletim sistemi kaydı birlikte doğrulandı.",
        }
        values.update(changes)
        return self.service.add("example.com", **values)

    def test_exact_identity_builds_purl_and_parses_source_rpm(self):
        added = self.add(name="OpenSSL", architecture="X86_64")
        self.assertEqual(added.action, "added")
        self.assertEqual(added.record.name, "openssl")
        self.assertEqual(added.record.architecture, "x86_64")
        self.assertEqual(
            added.record.purl,
            "pkg:rpm/redhat/openssl@1.0.1e-16.el6_5.7?arch=x86_64",
        )
        self.assertEqual(
            source_rpm_parts(added.record.source_rpm),
            ("openssl", "1.0.1e", "16.el6_5.7"),
        )
        self.assertEqual(
            redhat_rpm_purl(
                name="openssl", version="1.0.1e", release="16.el6_5.7",
                architecture="x86_64",
            ),
            added.record.purl,
        )
        self.assertEqual(self.assets.inspect()["active_asset_package_count"], 1)

    def test_invalid_or_unknown_asset_fails_without_partial_write(self):
        before = self.path.read_bytes()
        bad_values = (
            ("name", "open ssl"), ("epoch", -1), ("version", "1.0 1"),
            ("release", "16/el6"), ("architecture", "x86-64"),
            ("distribution_cpe", "cpe:/o:canonical:ubuntu_linux:22.04"),
            ("source_rpm", "../../openssl.src.rpm"),
        )
        for field, value in bad_values:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.add(**{field: value})
        with self.assertRaisesRegex(ValidationError, "önce"):
            self.service.add(
                "unknown.example", provider="redhat", name="openssl", epoch=0,
                version="1.0.1e", release="16.el6_5.7", architecture="x86_64",
                distribution_cpe=CPE, source_rpm=None,
                evidence="Paket ve dağıtım elle doğrulandı.",
            )
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.service.list(), ())

    def test_lifecycle_updates_source_evidence_and_keeps_append_only_history(self):
        added = self.add(source_rpm=None)
        unchanged = self.add(source_rpm=None)
        self.assertEqual(unchanged.action, "unchanged")
        updated = self.add()
        self.assertEqual((updated.action, updated.record.id), ("updated", added.record.id))
        revoked = self.service.revoke(
            added.record.id, reason="Paket sunucudan kaldırıldı ve doğrulandı.",
        )
        self.assertEqual((revoked.action, revoked.record.active), ("revoked", False))
        self.assertEqual(
            self.service.revoke(
                added.record.id, reason="İkinci kaldırma isteği değişiklik üretmemeli.",
            ).action,
            "unchanged",
        )
        reactivated = self.add(evidence="Paket yeniden kuruldu ve RPM sorgusuyla doğrulandı.")
        self.assertEqual((reactivated.action, reactivated.record.id),
                         ("reactivated", added.record.id))
        details = self.service.show(added.record.id)
        self.assertEqual(details.total_event_count, 4)
        self.assertEqual(
            [event.action for event in reversed(details.events)],
            ["added", "updated", "revoked", "reactivated"],
        )
        self.assertIsNone(details.events[-1].source_rpm)

    def test_distribution_context_is_part_of_identity(self):
        client = self.add()
        server = self.add(distribution_cpe="cpe:/o:redhat:enterprise_linux:6::server")
        self.assertNotEqual(client.record.id, server.record.id)
        self.assertEqual(len(self.service.list()), 2)

    def test_corrupt_purl_or_event_fails_closed_without_mutation(self):
        added = self.add()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE asset_packages SET purl='pkg:rpm/redhat/other@1?arch=x86_64' WHERE id=?",
                (added.record.id,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "bozuk"):
            self.service.show(added.record.id)
        self.assertEqual(self.path.read_bytes(), before)

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE asset_packages SET purl=? WHERE id=?", (added.record.purl, added.record.id),
            )
            connection.execute(
                "UPDATE asset_package_events SET evidence='x' WHERE asset_package_id=?",
                (added.record.id,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "geçmişi bozuk"):
            self.service.show(added.record.id)
        self.assertEqual(self.path.read_bytes(), before)

    def call_cli(self, *arguments: str) -> tuple[int, str, str]:
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_add_list_show_revoke_is_read_safe(self):
        code, output, error = self.call_cli(
            "packages", "add", "example.com", "--name", "openssl", "--epoch", "0",
            "--version", "1.0.1e", "--release", "16.el6_5.7", "--arch", "x86_64",
            "--distribution-cpe", CPE, "--source-rpm",
            "openssl-1.0.1e-16.el6_5.7.src.rpm", "--evidence",
            "RPM çıktısı <kanıt> olarak kullanıcı tarafından doğrulandı.",
        )
        self.assertEqual((code, error), (0, ""))
        package_id = json.loads(output)["data"]["record"]["id"]
        before = self.path.read_bytes()
        listed = json.loads(self.call_cli("packages", "list", "example.com")[1])["data"]
        shown = json.loads(self.call_cli("packages", "show", package_id)[1])["data"]
        self.assertEqual(listed["records"][0]["id"], package_id)
        self.assertEqual(shown["record"]["distribution_cpe"], CPE)
        self.assertEqual(self.path.read_bytes(), before)
        revoked = json.loads(self.call_cli(
            "packages", "revoke", package_id, "--reason",
            "Paket kaldırıldı ve envanterden doğrulandı.",
        )[1])["data"]
        self.assertEqual(revoked["action"], "revoked")
        self.assertEqual(json.loads(self.call_cli("packages", "list")[1])["data"]["records"], [])


if __name__ == "__main__":
    unittest.main()

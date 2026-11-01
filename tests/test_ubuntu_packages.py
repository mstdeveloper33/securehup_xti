"""Verified Ubuntu binary-to-source inventory and Canonical matching."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ubuntu_packages import SQLiteUbuntuAssetPackageRepository
from xti.adapters.ubuntu_osv import UbuntuOsvAdvisorySource, parse_ubuntu_osv_response
from xti.application.assets import AssetService
from xti.application.ubuntu_packages import (
    UbuntuAssetPackageService,
    UbuntuInventoryMatchService,
    UbuntuInventoryScanService,
)
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


CVE = "CVE-2025-6491"


def osv_payload():
    return json.dumps({
        "schema_version": "1.7.0", "id": f"UBUNTU-{CVE}",
        "aliases": [], "upstream": [CVE],
        "modified": "2026-10-20T18:00:00Z",
        "published": "2025-07-13T22:15:00Z",
        "affected": [{
            "package": {
                "ecosystem": "Ubuntu:24.04:LTS", "name": "php8.3",
                "purl": "pkg:deb/ubuntu/php8.3@8.3.6-0ubuntu0.24.04.5",
            },
            "versions": ["8.3.6-0ubuntu0.24.04.4"],
            "ranges": [{
                "type": "ECOSYSTEM",
                "events": [
                    {"introduced": "0"}, {"fixed": "8.3.6-0ubuntu0.24.04.5"},
                ],
            }],
        }],
        "references": [{
            "type": "ADVISORY", "url": "https://ubuntu.com/security/notices/USN-7648-1",
        }],
    }, separators=(",", ":")).encode()


class FakeSource:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def fetch(self, cve_id):
        self.calls.append(cve_id)
        return self.snapshot


class UbuntuPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "ubuntu inventory"
        self.path = self.data / "xti.db"
        assets = SQLiteAssetRepository(self.path)
        assets.initialize()
        AssetService(assets).add("example.com")
        self.repository = SQLiteUbuntuAssetPackageRepository(self.path)
        self.service = UbuntuAssetPackageService(
            self.repository,
            clock=lambda: datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc),
        )

    def add(self, **changes):
        values = dict(
            ecosystem="Ubuntu:24.04:LTS", binary_name="php8.3-cli",
            binary_version="8.3.6-0ubuntu0.24.04.99", architecture="amd64",
            source_name="php8.3", source_version="8.3.6-0ubuntu0.24.04.4",
            evidence="dpkg-query ve apt-cache showsrc çıktıları birlikte doğrulandı.",
        )
        values.update(changes)
        return self.service.add("example.com", **values)

    def test_lifecycle_keeps_exact_binary_source_relation_and_history(self):
        added = self.add()
        self.assertEqual(added.action, "added")
        record = added.record
        self.assertEqual(
            (record.binary_name, record.binary_version, record.architecture),
            ("php8.3-cli", "8.3.6-0ubuntu0.24.04.99", "amd64"),
        )
        self.assertEqual(
            (record.source_name, record.source_version),
            ("php8.3", "8.3.6-0ubuntu0.24.04.4"),
        )
        self.assertEqual(self.add().action, "unchanged")
        updated = self.add(evidence="Binary ve source bağı ikinci komutla yeniden doğrulandı.")
        self.assertEqual((updated.action, updated.record.id), ("updated", record.id))
        revoked = self.service.revoke(
            record.id, reason="Paket kaldırıldı ve dpkg-query ile doğrulandı.",
        )
        self.assertFalse(revoked.record.active)
        reactivated = self.add(evidence="Paket yeniden kuruldu ve source bağı doğrulandı.")
        self.assertEqual((reactivated.action, reactivated.record.id),
                         ("reactivated", record.id))
        details = self.service.show(record.id)
        self.assertEqual(details.total_event_count, 4)
        self.assertEqual(
            [event.action for event in reversed(details.events)],
            ["added", "updated", "revoked", "reactivated"],
        )

    def test_new_source_version_is_distinct_and_invalid_input_writes_nothing(self):
        first = self.add()
        second = self.add(source_version="8.3.6-0ubuntu0.24.04.5")
        self.assertNotEqual(first.record.id, second.record.id)
        before = self.path.read_bytes()
        for field, value in (
            ("ecosystem", "Debian:12"), ("binary_name", "PHP CLI"),
            ("binary_version", "8.3 6"), ("architecture", "AMD 64"),
            ("source_name", "PHP Source"), ("source_version", "8_3"),
            ("evidence", "x"),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.add(**{field: value})
        with self.assertRaisesRegex(ValidationError, "önce"):
            self.service.add(
                "unknown.example", ecosystem="Ubuntu:24.04:LTS",
                binary_name="php8.3-cli", binary_version="1", architecture="amd64",
                source_name="php8.3", source_version="1",
                evidence="Paket bağı kullanıcı tarafından doğrulandı.",
            )
        self.assertEqual(self.path.read_bytes(), before)

    def test_match_uses_source_version_not_binary_version_and_is_read_only(self):
        package = self.add().record
        snapshot = parse_ubuntu_osv_response(osv_payload(), CVE)
        source = FakeSource(snapshot)
        before = self.path.read_bytes()
        report = UbuntuInventoryMatchService(self.repository, source).match(
            package.id, CVE, reference_limit=1,
        )
        self.assertEqual(report.comparison.status, "before_fixed_boundary")
        self.assertEqual(report.comparison.installed_version, package.source_version)
        self.assertNotEqual(package.binary_version, package.source_version)
        self.assertEqual(source.calls, [CVE])
        self.assertEqual(self.path.read_bytes(), before)

        self.service.revoke(
            package.id, reason="Paket artık kurulu değil ve kullanıcı doğruladı.",
        )
        inactive_source = FakeSource(snapshot)
        with self.assertRaisesRegex(ValidationError, "Kaldırılmış"):
            UbuntuInventoryMatchService(self.repository, inactive_source).match(
                package.id, CVE,
            )
        self.assertEqual(inactive_source.calls, [])

    def test_inventory_scan_fetches_once_counts_all_and_prioritizes_display(self):
        before_fixed = self.add().record
        at_fixed = self.add(
            binary_version="8.3.6-0ubuntu0.24.04.100",
            source_version="8.3.6-0ubuntu0.24.04.5",
        ).record
        self.add(
            binary_version="8.3.6-0ubuntu0.24.04.101",
            source_version="8.3.6-0ubuntu0.24.04.6",
        )
        self.add(
            binary_name="openssl", binary_version="3.0.13-0ubuntu3.6",
            source_name="openssl", source_version="3.0.13-0ubuntu3.6",
        )
        snapshot = parse_ubuntu_osv_response(osv_payload(), CVE)
        source = FakeSource(snapshot)
        before = self.path.read_bytes()
        report = UbuntuInventoryScanService(self.repository, source).scan(
            CVE, asset_value="example.com", limit=2, reference_limit=1,
        )
        self.assertEqual(source.calls, [CVE])
        self.assertEqual(report.total_active_package_count, 4)
        self.assertEqual(
            (
                report.before_fixed_boundary_count,
                report.at_fixed_boundary_count,
                report.after_fixed_boundary_count,
                report.not_listed_count,
            ),
            (1, 1, 1, 1),
        )
        self.assertEqual(
            [item.package.id for item in report.items],
            [before_fixed.id, at_fixed.id],
        )
        self.assertTrue(report.truncated)
        self.assertEqual(report.displayed_count, 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_inventory_scan_avoids_network_when_empty_and_validates_hidden_rows(self):
        snapshot = parse_ubuntu_osv_response(osv_payload(), CVE)
        source = FakeSource(snapshot)
        report = UbuntuInventoryScanService(self.repository, source).scan(CVE)
        self.assertFalse(report.source_requested)
        self.assertEqual(source.calls, [])

        self.add()
        hidden = self.add(
            binary_name="openssl", binary_version="3.0.13-0ubuntu3.6",
            source_name="openssl", source_version="3.0.13-0ubuntu3.6",
        ).record
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ubuntu_asset_packages SET evidence='x' WHERE id = ?",
                (hidden.id,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "kanıtı bozuk"):
            UbuntuInventoryScanService(self.repository, source).scan(CVE, limit=1)
        self.assertEqual(source.calls, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_inventory_scan_rejects_unknown_asset_and_corrupt_event_before_network(self):
        snapshot = parse_ubuntu_osv_response(osv_payload(), CVE)
        source = FakeSource(snapshot)
        service = UbuntuInventoryScanService(self.repository, source)
        with self.assertRaisesRegex(ValidationError, "Kayıtlı varlık"):
            service.scan(CVE, asset_value="unknown.example")
        self.assertEqual(source.calls, [])

        package = self.add().record
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ubuntu_asset_package_events SET evidence='x' "
                "WHERE ubuntu_package_id = ?", (package.id,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "geçmişi bozuk"):
            service.scan(CVE)
        self.assertEqual(source.calls, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_doctor_count_and_backup_restore_preserve_record_and_history(self):
        package = self.add().record
        self.add(evidence="Binary/source ilişkisi ikinci kez doğrulandı.")
        self.assertEqual(
            SQLiteAssetRepository(self.path).inspect()[
                "active_ubuntu_asset_package_count"
            ],
            1,
        )

        backup = Path(self.temp.name) / "backup" / "ubuntu-inventory.db"
        SQLiteAssetRepository(self.path).backup(backup)
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)

        details = UbuntuAssetPackageService(
            SQLiteUbuntuAssetPackageRepository(restored)
        ).show(package.id)
        self.assertEqual(details.record, self.service.show(package.id).record)
        self.assertEqual(details.events, self.service.show(package.id).events)
        self.assertEqual(details.total_event_count, 2)
        self.assertEqual(
            SQLiteAssetRepository(restored).inspect()[
                "active_ubuntu_asset_package_count"
            ],
            1,
        )

    def test_corrupt_hidden_history_fails_closed_without_mutation(self):
        package = self.add().record
        self.add(evidence="Binary/source ilişkisi ikinci kez doğrulandı.")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ubuntu_asset_package_events SET evidence='x' "
                "WHERE rowid = (SELECT MIN(rowid) FROM ubuntu_asset_package_events "
                "WHERE ubuntu_package_id = ?)", (package.id,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "geçmişi bozuk"):
            self.service.show(package.id, event_limit=1)
        self.assertEqual(self.path.read_bytes(), before)

    def call_cli(self, *arguments: str):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_inventory_lifecycle_and_match(self):
        code, output, error = self.call_cli(
            "ubuntu-packages", "add", "example.com",
            "--ecosystem", "Ubuntu:24.04:LTS",
            "--binary-package", "php8.3-cli",
            "--binary-version", "8.3.6-0ubuntu0.24.04.99",
            "--arch", "amd64", "--source-package", "php8.3",
            "--source-version", "8.3.6-0ubuntu0.24.04.4",
            "--evidence", "dpkg-query ve apt-cache showsrc birlikte doğrulandı.",
        )
        self.assertEqual((code, error), (0, ""))
        package_id = json.loads(output)["data"]["record"]["id"]
        before = self.path.read_bytes()
        listed = json.loads(self.call_cli("ubuntu-packages", "list")[1])["data"]
        shown = json.loads(self.call_cli("ubuntu-packages", "show", package_id)[1])["data"]
        self.assertEqual(listed["records"][0]["id"], package_id)
        self.assertEqual(shown["record"]["source_name"], "php8.3")
        snapshot = parse_ubuntu_osv_response(osv_payload(), CVE)
        with patch.object(UbuntuOsvAdvisorySource, "fetch", return_value=snapshot):
            matched = json.loads(self.call_cli(
                "vuln", "ubuntu-inventory-match", package_id, CVE,
            )[1])["data"]
            scanned = json.loads(self.call_cli(
                "vuln", "ubuntu-inventory-scan", CVE,
                "--domain", "example.com", "--limit", "1",
            )[1])["data"]
        self.assertEqual(matched["comparison"]["status"], "before_fixed_boundary")
        self.assertEqual(scanned["before_fixed_boundary_count"], 1)
        self.assertEqual(scanned["items"][0]["package"]["id"], package_id)
        self.assertEqual(self.path.read_bytes(), before)

        doctor = json.loads(self.call_cli("doctor")[1])["data"]
        self.assertEqual(doctor["active_ubuntu_asset_package_count"], 1)


if __name__ == "__main__":
    unittest.main()

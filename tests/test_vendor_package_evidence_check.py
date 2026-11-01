"""Decision-neutral currency checks for stored exact RPM/VEX evidence."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from io import StringIO
import json
import unittest
from unittest.mock import patch

from tests.test_vendor_advisory import COMPONENT_ID, CVE, payload
from tests import test_vendor_package_evidence as evidence_fixtures
from tests.test_vulnerability_exposures import NOW
from xti.adapters.redhat_csaf_vex import RedHatCsafVexSource, parse_redhat_vex_response
from xti.adapters.sqlite_packages import SQLiteAssetPackageRepository
from xti.adapters.sqlite_vendor_package_evidence import SQLiteVendorPackageEvidenceRepository
from xti.application.packages import AssetPackageService
from xti.application.vendor_package_evidence_check import VendorPackageEvidenceCheckService
from xti.interfaces.cli import main


class VendorPackageEvidenceCheckTests(unittest.TestCase):
    setUp = evidence_fixtures.VendorPackageEvidenceTests.setUp

    def service(self, source=None, clock=None):
        return evidence_fixtures.VendorPackageEvidenceTests.service(
            self, source=source, clock=clock,
        )

    def stored(self):
        return self.service().add(
            self.exposure.id, self.package.id, selected_vex_product_id=COMPONENT_ID,
            summary="Kesin Red Hat bağı güncellik kontrolü için seçildi.",
        ).mutation.record

    def checker(self, snapshot=None):
        return VendorPackageEvidenceCheckService(
            SQLiteVendorPackageEvidenceRepository(self.path),
            SQLiteAssetPackageRepository(self.path),
            evidence_fixtures.Source(snapshot or self.snapshot),
            clock=lambda: NOW + timedelta(hours=2),
        )

    def test_unchanged_source_package_and_relation_are_read_only_current(self):
        evidence = self.stored()
        before = self.path.read_bytes()
        report = self.checker().check(evidence.id)
        self.assertEqual(report.state, "current")
        self.assertFalse(report.source_changed)
        self.assertFalse(report.package_snapshot_changed)
        self.assertTrue(report.selected_relation_present)
        self.assertEqual(report.current_vendor_status, "fixed")
        self.assertEqual(self.path.read_bytes(), before)

    def test_source_refresh_same_statement_and_status_change_are_distinct(self):
        evidence = self.stored()
        refreshed = json.loads(payload())
        refreshed["document"]["tracking"]["version"] = "4"
        refreshed["document"]["tracking"]["current_release_date"] = "2026-10-29T19:00:00+00:00"
        refreshed["document"]["tracking"]["revision_history"].append({
            "date": "2026-10-29T19:00:00+00:00", "number": "4", "summary": "Refresh",
        })
        snapshot = parse_redhat_vex_response(json.dumps(refreshed).encode(), CVE)
        report = self.checker(snapshot).check(evidence.id)
        self.assertEqual(report.state, "source_document_changed_same_statement")
        self.assertTrue(report.source_changed)

        changed = json.loads(json.dumps(refreshed))
        status = changed["vulnerabilities"][0]["product_status"]
        status["known_affected"] = status.pop("fixed")
        snapshot = parse_redhat_vex_response(json.dumps(changed).encode(), CVE)
        report = self.checker(snapshot).check(evidence.id)
        self.assertEqual(report.state, "statement_changed")
        self.assertEqual(report.current_vendor_status, "known_affected")

    def test_reverified_or_inactive_package_stops_or_marks_without_writing(self):
        evidence = self.stored()
        AssetPackageService(
            SQLiteAssetPackageRepository(self.path), clock=lambda: NOW + timedelta(hours=2),
        ).add(
            "example.com", provider="redhat", name="openssl", epoch=0,
            version="3.2.2", release="1.el9", architecture="x86_64",
            distribution_cpe="cpe:/o:redhat:enterprise_linux:9",
            source_rpm="openssl-3.2.2-1.el9.src.rpm",
            evidence="RPM güncellik kontrolü öncesinde yeniden doğrulandı.",
        )
        report = self.checker().check(evidence.id)
        self.assertEqual(report.state, "package_snapshot_changed")
        self.assertTrue(report.package_snapshot_changed)

        AssetPackageService(
            SQLiteAssetPackageRepository(self.path), clock=lambda: NOW + timedelta(hours=3),
        ).revoke(self.package.id, reason="Paket kaldırıldığı için etkisizleştirildi.")
        source = evidence_fixtures.Source(self.snapshot)
        report = VendorPackageEvidenceCheckService(
            SQLiteVendorPackageEvidenceRepository(self.path),
            SQLiteAssetPackageRepository(self.path), source,
            clock=lambda: NOW + timedelta(hours=4),
        ).check(evidence.id)
        self.assertEqual(report.state, "package_inactive")
        self.assertFalse(report.source_checked)
        self.assertEqual(source.calls, [])

    def test_selected_relation_missing_is_not_called_safe(self):
        evidence = self.stored()
        changed = json.loads(payload())
        component = changed["product_tree"]["branches"][0]["branches"][1]["product"]
        component["name"] = "openssl-0:3.2.2-2.el9.x86_64"
        component["product_id"] = "openssl-0:3.2.2-2.el9.x86_64"
        component["product_identification_helper"]["purl"] = (
            "pkg:rpm/redhat/openssl@3.2.2-2.el9?arch=x86_64"
        )
        relation = changed["product_tree"]["relationships"][0]
        relation["product_reference"] = component["product_id"]
        snapshot = parse_redhat_vex_response(json.dumps(changed).encode(), CVE)
        report = self.checker(snapshot).check(evidence.id)
        self.assertEqual(report.state, "selected_relation_missing")
        self.assertFalse(report.selected_relation_present)
        self.assertIsNone(report.current_vendor_status)

    def test_cli_check_uses_current_source_and_never_writes(self):
        evidence = self.stored()
        before = self.path.read_bytes()
        output, error = StringIO(), StringIO()
        with patch.object(RedHatCsafVexSource, "fetch", return_value=self.snapshot) as fetch:
            with redirect_stdout(output), redirect_stderr(error):
                code = main([
                    "--data-dir", str(self.data), "vuln", "vendor-evidence-check", evidence.id,
                ])
        self.assertEqual((code, error.getvalue()), (0, ""))
        self.assertIn("Kanıt güncel", output.getvalue())
        fetch.assert_called_once_with(CVE)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

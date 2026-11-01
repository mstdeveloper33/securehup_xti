"""Exact local Red Hat RPM to direct CSAF VEX relationship matching."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.redhat_csaf_vex import RedHatCsafVexSource, parse_redhat_vex_response
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_packages import SQLiteAssetPackageRepository
from xti.application.packages import AssetPackageService
from xti.application.vendor_package_match import VendorPackageMatchService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from tests.test_vendor_advisory import CVE, payload


CPE = "cpe:/o:redhat:enterprise_linux:9"


class Source:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def fetch(self, cve_id):
        self.calls.append(cve_id)
        return self.snapshot


class VendorPackageMatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.assets.add("example.com")
        self.packages = AssetPackageService(SQLiteAssetPackageRepository(self.path))
        self.snapshot = parse_redhat_vex_response(payload(), CVE)

    def add(self, **changes):
        values = {
            "provider": "redhat", "name": "openssl", "epoch": 0,
            "version": "3.2.2", "release": "1.el9", "architecture": "x86_64",
            "distribution_cpe": CPE,
            "source_rpm": "openssl-3.2.2-1.el9.src.rpm",
            "evidence": "RPM sorgusu ve Red Hat sürüm kaydı birlikte doğrulandı.",
        }
        values.update(changes)
        return self.packages.add("example.com", **values).record

    def test_exact_binary_nevra_purl_and_cpe_produce_vendor_statement_only(self):
        package = self.add()
        source = Source(self.snapshot)
        before = self.path.read_bytes()
        report = VendorPackageMatchService(
            SQLiteAssetPackageRepository(self.path), source,
        ).match(package.id, CVE)
        self.assertEqual(source.calls, [CVE])
        self.assertEqual((report.match_state, report.vendor_status),
                         ("exact_vendor_statement", "fixed"))
        self.assertEqual(report.total_match_count, 1)
        self.assertEqual(report.matches[0].match_kind, "exact_binary_package")
        self.assertEqual(report.matches[0].context_cpe, CPE)
        self.assertIn("insan maruziyet kararını değiştirmez", report.notes[0])
        self.assertEqual(self.path.read_bytes(), before)

    def test_different_distribution_or_nevra_is_honest_no_match(self):
        for changes in (
            {"distribution_cpe": "cpe:/o:redhat:enterprise_linux:9::server"},
            {"release": "2.el9"},
            {"architecture": "aarch64"},
            {"epoch": 1},
        ):
            with self.subTest(changes=changes):
                package = self.add(**changes)
                report = VendorPackageMatchService(
                    SQLiteAssetPackageRepository(self.path), Source(self.snapshot),
                ).match(package.id, CVE)
                self.assertEqual((report.match_state, report.vendor_status, report.matches),
                                 ("no_exact_match", None, ()))

    def test_source_package_context_requires_verified_source_rpm_and_exact_cpe(self):
        document = json.loads(payload())
        component = document["product_tree"]["branches"][0]["branches"][1]["product"]
        component.update({
            "name": "openssl.src", "product_id": "openssl.src",
            "product_identification_helper": {"purl": "pkg:rpm/redhat/openssl?arch=src"},
        })
        relation = document["product_tree"]["relationships"][0]
        relation["product_reference"] = "openssl.src"
        relation["full_product_name"] = {
            "name": "openssl source as a component of Red Hat Enterprise Linux 9",
            "product_id": "rhel-9:openssl.src",
        }
        status = document["vulnerabilities"][0]["product_status"]
        status.clear()
        status["known_not_affected"] = ["rhel-9:openssl.src"]
        document["vulnerabilities"][0]["remediations"] = []
        snapshot = parse_redhat_vex_response(json.dumps(document).encode(), CVE)

        package = self.add()
        report = VendorPackageMatchService(
            SQLiteAssetPackageRepository(self.path), Source(snapshot),
        ).match(package.id, CVE)
        self.assertEqual((report.vendor_status, report.matches[0].match_kind),
                         ("known_not_affected", "source_package_context"))

        no_source = self.add(release="2.el9", source_rpm=None)
        report = VendorPackageMatchService(
            SQLiteAssetPackageRepository(self.path), Source(snapshot),
        ).match(no_source.id, CVE)
        self.assertEqual(report.match_state, "no_exact_match")

    def test_invalid_limit_and_inactive_package_stop_before_network(self):
        package = self.add()
        source = Source(self.snapshot)
        service = VendorPackageMatchService(SQLiteAssetPackageRepository(self.path), source)
        with self.assertRaises(ValidationError):
            service.match(package.id, CVE, match_limit=0)
        self.assertEqual(source.calls, [])
        self.packages.revoke(package.id, reason="Paket kaldırıldı ve doğrulandı.")
        with self.assertRaisesRegex(ValidationError, "Kaldırılmış"):
            service.match(package.id, CVE)
        self.assertEqual(source.calls, [])

    def test_cli_json_is_read_only_and_uses_current_direct_source(self):
        package = self.add()
        before = self.path.read_bytes()
        output, error = StringIO(), StringIO()
        with patch.object(RedHatCsafVexSource, "fetch", return_value=self.snapshot):
            with redirect_stdout(output), redirect_stderr(error):
                code = main([
                    "--data-dir", str(self.data), "--json", "vuln", "vendor-match",
                    package.id, CVE,
                ])
        self.assertEqual((code, error.getvalue()), (0, ""))
        data = json.loads(output.getvalue())["data"]
        self.assertEqual(data["match_state"], "exact_vendor_statement")
        self.assertEqual(data["matches"][0]["match_kind"], "exact_binary_package")
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

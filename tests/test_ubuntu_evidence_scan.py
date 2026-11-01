"""Offline plans and bounded bulk checks for selected Ubuntu evidence."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from io import StringIO
import json
import unittest
from unittest.mock import patch

from tests import test_ubuntu_evidence as fixtures
from tests.test_vulnerability_exposures import CVE, NOW
from xti.adapters.sqlite_ubuntu_packages import SQLiteUbuntuAssetPackageRepository
from xti.adapters.sqlite_vulnerability_exposure_evidence import (
    SQLiteVulnerabilityExposureEvidenceRepository,
)
from xti.adapters.sqlite_vulnerability_exposures import (
    SQLiteVulnerabilityExposureRepository,
)
from xti.adapters.ubuntu_osv import UbuntuOsvAdvisorySource
from xti.application.ubuntu_evidence_scan import (
    UbuntuEvidencePlanService,
    UbuntuEvidenceScanService,
)
from xti.application.ubuntu_packages import UbuntuAssetPackageService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


class UbuntuEvidenceScanTests(unittest.TestCase):
    setUp = fixtures.UbuntuExposureEvidenceTests.setUp
    add_package = fixtures.UbuntuExposureEvidenceTests.add_package
    service = fixtures.UbuntuExposureEvidenceTests.service

    def evidence(self, package=None, summary="Ubuntu sonucu toplu kontrol için seçildi."):
        return self.service().add(
            self.exposure.id, (package or self.package).id, summary=summary,
        ).mutation.record

    def planner(self):
        return UbuntuEvidencePlanService(
            SQLiteVulnerabilityExposureEvidenceRepository(self.path),
            SQLiteVulnerabilityExposureRepository(self.path),
            SQLiteUbuntuAssetPackageRepository(self.path),
            clock=lambda: NOW + timedelta(hours=4),
        )

    def scanner(self, source):
        return UbuntuEvidenceScanService(
            SQLiteVulnerabilityExposureEvidenceRepository(self.path),
            SQLiteVulnerabilityExposureRepository(self.path),
            SQLiteUbuntuAssetPackageRepository(self.path), source,
            clock=lambda: NOW + timedelta(hours=4),
        )

    def second_package(self):
        return self.add_package(
            binary_name="php8.3-fpm",
            binary_version="8.3.6-0ubuntu0.24.04.100",
        ).record

    def test_plan_is_offline_counts_all_and_prioritizes_local_attention(self):
        first = self.evidence()
        second_package = self.second_package()
        second = self.evidence(
            second_package, "İkinci Ubuntu sonucu toplu kontrol için seçildi.",
        )
        UbuntuAssetPackageService(
            SQLiteUbuntuAssetPackageRepository(self.path),
            clock=lambda: NOW + timedelta(hours=2),
        ).add(
            "example.com", ecosystem="Ubuntu:24.04:LTS",
            binary_name="php8.3-cli",
            binary_version="8.3.6-0ubuntu0.24.04.99", architecture="amd64",
            source_name="php8.3", source_version="8.3.6-0ubuntu0.24.04.4",
            evidence="İlk paket plan öncesi yeniden doğrulandı.",
        )
        UbuntuAssetPackageService(
            SQLiteUbuntuAssetPackageRepository(self.path),
            clock=lambda: NOW + timedelta(hours=3),
        ).revoke(second_package.id, reason="İkinci paket kaldırıldı ve doğrulandı.")

        before = self.path.read_bytes()
        report = self.planner().plan(asset_value="example.com", limit=1)
        self.assertEqual(report.total_active_evidence_count, 2)
        self.assertEqual(report.package_snapshot_changed_count, 1)
        self.assertEqual(report.package_inactive_count, 1)
        self.assertEqual(report.local_current_count, 0)
        self.assertEqual(report.items[0].evidence.id, second.id)
        self.assertEqual(report.items[0].local_state, "package_inactive")
        self.assertTrue(report.truncated)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertNotEqual(first.id, second.id)

    def test_scan_reuses_one_canonical_fetch_for_same_cve_and_writes_nothing(self):
        self.evidence()
        self.evidence(
            self.second_package(), "İkinci paket aynı CVE için seçildi.",
        )
        source = fixtures.Source(self.snapshot)
        before = self.path.read_bytes()
        report = self.scanner(source).scan(limit=20)
        self.assertEqual(report.selected_count, 2)
        self.assertEqual(report.source_request_count, 1)
        self.assertEqual(source.calls, [CVE])
        self.assertEqual(report.current_count, 2)
        self.assertEqual(report.changed_count, 0)
        self.assertEqual(report.skipped_source_count, 0)
        self.assertFalse(report.truncated)
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_scope_bad_limits_unknown_domain_and_hidden_bad_reference_stop_safely(self):
        source = fixtures.Source(self.snapshot)
        empty = self.scanner(source).scan(limit=10)
        self.assertEqual(empty.selected_count, 0)
        self.assertEqual(empty.source_request_count, 0)
        self.assertEqual(source.calls, [])

        for limit in (0, 21):
            with self.subTest(limit=limit), self.assertRaises(ValidationError):
                self.scanner(source).scan(limit=limit)
        with self.assertRaisesRegex(ValidationError, "Kayıtlı varlık"):
            self.scanner(source).scan(asset_value="unknown.example")
        self.assertEqual(source.calls, [])

        repository = SQLiteVulnerabilityExposureEvidenceRepository(self.path)
        repository.add(
            exposure_id=self.exposure.id, evidence_type="package_inventory",
            source_reference="ubuntu-osv-v1:malformed",
            summary="Bozuk ayrılmış başvuru planı güvenli durdurmalıdır.",
            recorded_at=(NOW + timedelta(hours=1)).isoformat(),
        )
        with self.assertRaises(ValidationError):
            self.scanner(source).scan(limit=1)
        self.assertEqual(source.calls, [])

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main([*argv, *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_plan_is_offline_and_scan_is_bounded(self):
        self.evidence()
        with patch.object(UbuntuOsvAdvisorySource, "fetch") as fetch:
            code, output, error = self.invoke(
                "vuln", "ubuntu-evidence-plan", "--domain", "example.com",
            )
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(output)["data"]["total_active_evidence_count"], 1)
        fetch.assert_not_called()

        before = self.path.read_bytes()
        with patch.object(
            UbuntuOsvAdvisorySource, "fetch", return_value=self.snapshot,
        ) as fetch:
            code, output, error = self.invoke(
                "vuln", "ubuntu-evidence-scan", "--limit", "10",
                as_json=False,
            )
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Canonical çağrısı: 1", output)
        fetch.assert_called_once_with(CVE)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

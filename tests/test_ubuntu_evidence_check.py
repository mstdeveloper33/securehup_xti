"""Decision-neutral currency checks for selected Ubuntu evidence."""

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
from xti.adapters.ubuntu_osv import UbuntuOsvAdvisorySource, parse_ubuntu_osv_response
from xti.application.ubuntu_evidence_check import UbuntuEvidenceCheckService
from xti.application.ubuntu_packages import UbuntuAssetPackageService
from xti.domain.assets import ValidationError
from xti.domain.ubuntu_evidence import parse_ubuntu_evidence_reference
from xti.interfaces.cli import main


class UbuntuEvidenceCheckTests(unittest.TestCase):
    setUp = fixtures.UbuntuExposureEvidenceTests.setUp
    add_package = fixtures.UbuntuExposureEvidenceTests.add_package
    service = fixtures.UbuntuExposureEvidenceTests.service
    generic_evidence = fixtures.UbuntuExposureEvidenceTests.generic_evidence

    def stored(self):
        return self.service().add(
            self.exposure.id, self.package.id,
            summary="Ubuntu sonucu güncellik kontrolü için seçildi.",
        ).mutation.record

    def checker(self, source=None, clock=None):
        return UbuntuEvidenceCheckService(
            SQLiteVulnerabilityExposureEvidenceRepository(self.path),
            SQLiteVulnerabilityExposureRepository(self.path),
            SQLiteUbuntuAssetPackageRepository(self.path),
            source or fixtures.Source(self.snapshot),
            clock=clock or (lambda: NOW + timedelta(hours=2)),
        )

    def test_unchanged_package_source_and_result_are_read_only_current(self):
        evidence = self.stored()
        before = self.path.read_bytes()
        report = self.checker().check(evidence.id)
        self.assertEqual(report.state, "current")
        self.assertFalse(report.source_changed)
        self.assertFalse(report.package_snapshot_changed)
        self.assertTrue(report.selected_relation_present)
        self.assertEqual(report.current_match_status, "before_fixed_boundary")
        self.assertEqual(self.path.read_bytes(), before)

    def test_source_refresh_same_result_and_changed_result_are_distinct(self):
        evidence = self.stored()
        refreshed = parse_ubuntu_osv_response(
            fixtures.ubuntu_payload(modified="2026-10-29T18:30:00Z"), CVE,
        )
        report = self.checker(fixtures.Source(refreshed)).check(evidence.id)
        self.assertEqual(report.state, "source_document_changed_same_result")
        self.assertTrue(report.source_changed)

        changed = parse_ubuntu_osv_response(
            fixtures.ubuntu_payload(
                fixed="8.3.6-0ubuntu0.24.04.4",
                modified="2026-10-29T18:45:00Z",
            ),
            CVE,
        )
        report = self.checker(fixtures.Source(changed)).check(evidence.id)
        self.assertEqual(report.state, "result_changed")
        self.assertEqual(report.current_match_status, "at_fixed_boundary")

    def test_missing_relation_and_withdrawn_record_are_not_called_safe(self):
        evidence = self.stored()
        missing = parse_ubuntu_osv_response(
            fixtures.ubuntu_payload(package="openssl"), CVE,
        )
        report = self.checker(fixtures.Source(missing)).check(evidence.id)
        self.assertEqual(report.state, "selected_relation_missing")
        self.assertFalse(report.selected_relation_present)

        withdrawn = parse_ubuntu_osv_response(
            fixtures.ubuntu_payload(withdrawn="2026-10-29T18:00:00Z"), CVE,
        )
        report = self.checker(fixtures.Source(withdrawn)).check(evidence.id)
        self.assertEqual(report.state, "record_withdrawn")
        self.assertFalse(report.selected_relation_present)

    def test_reverified_inactive_package_and_revoked_evidence_are_distinct(self):
        evidence = self.stored()
        UbuntuAssetPackageService(
            SQLiteUbuntuAssetPackageRepository(self.path),
            clock=lambda: NOW + timedelta(hours=2),
        ).add(
            "example.com", ecosystem="Ubuntu:24.04:LTS",
            binary_name="php8.3-cli",
            binary_version="8.3.6-0ubuntu0.24.04.99", architecture="amd64",
            source_name="php8.3", source_version="8.3.6-0ubuntu0.24.04.4",
            evidence="Paket güncellik kontrolünden önce yeniden doğrulandı.",
        )
        report = self.checker().check(evidence.id)
        self.assertEqual(report.state, "package_snapshot_changed_same_result")
        self.assertTrue(report.package_snapshot_changed)

        UbuntuAssetPackageService(
            SQLiteUbuntuAssetPackageRepository(self.path),
            clock=lambda: NOW + timedelta(hours=3),
        ).revoke(self.package.id, reason="Paket kaldırıldığı için etkisizleştirildi.")
        source = fixtures.Source(self.snapshot)
        report = self.checker(source).check(evidence.id)
        self.assertEqual(report.state, "package_inactive")
        self.assertFalse(report.source_checked)
        self.assertEqual(source.calls, [])

        evidence2 = self.service().add(
            self.exposure.id,
            self.add_package(
                binary_name="php8.3-fpm",
                binary_version="8.3.6-0ubuntu0.24.04.100",
            ).record.id,
            summary="İkinci paket sonucu etkisiz kanıt kontrolü için seçildi.",
        ).mutation.record
        self.generic_evidence().revoke(
            evidence2.id, reason="Kanıt insan incelemesiyle etkisizleştirildi.",
        )
        source = fixtures.Source(self.snapshot)
        report = self.checker(source).check(evidence2.id)
        self.assertEqual(report.state, "evidence_inactive")
        self.assertFalse(report.source_checked)
        self.assertEqual(source.calls, [])

    def test_package_change_during_source_check_is_visible_and_never_writes(self):
        evidence = self.stored()
        later = UbuntuAssetPackageService(
            SQLiteUbuntuAssetPackageRepository(self.path),
            clock=lambda: NOW + timedelta(hours=3),
        )

        class UpdatingSource:
            def fetch(inner, cve_id):
                later.add(
                    "example.com", ecosystem="Ubuntu:24.04:LTS",
                    binary_name="php8.3-cli",
                    binary_version="8.3.6-0ubuntu0.24.04.99", architecture="amd64",
                    source_name="php8.3", source_version="8.3.6-0ubuntu0.24.04.4",
                    evidence="Paket salt okunur kontrol sırasında yeniden doğrulandı.",
                )
                return self.snapshot

        report = self.checker(UpdatingSource()).check(evidence.id)
        self.assertEqual(report.state, "package_changed_during_check")
        details = self.generic_evidence().show(evidence.id)
        self.assertEqual(details.total_event_count, 1)

    def test_reserved_reference_and_non_ubuntu_evidence_fail_before_network(self):
        evidence = self.stored()
        parsed = parse_ubuntu_evidence_reference(evidence.source_reference)
        self.assertEqual((parsed.cve_id, parsed.package_id), (CVE, self.package.id))
        with self.assertRaisesRegex(ValidationError, "yalnız ubuntu-evidence-add"):
            self.generic_evidence().add(
                self.exposure.id, evidence_type="package_inventory",
                source_reference=evidence.source_reference,
                summary="Ayrılmış Ubuntu bağı genel komutla taklit edilmemelidir.",
            )

        note = self.generic_evidence().add(
            self.exposure.id, evidence_type="analyst_note",
            source_reference="local-note-ubuntu-check",
            summary="Bu kayıt Ubuntu paket sonucu değildir.",
        ).record
        source = fixtures.Source(self.snapshot)
        with self.assertRaisesRegex(ValidationError, "Ubuntu paket sonucu değil"):
            self.checker(source).check(note.id)
        self.assertEqual(source.calls, [])

        for value in (
            "not-ubuntu", "ubuntu-osv-v1:too:few",
            f"ubuntu-osv-v1:{CVE}:{self.package.id}:{'0' * 64}:{'1' * 64}:not_listed",
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parse_ubuntu_evidence_reference(value)

    def test_cli_check_uses_current_source_and_never_writes(self):
        evidence = self.stored()
        before = self.path.read_bytes()
        output, error = StringIO(), StringIO()
        with patch.object(
            UbuntuOsvAdvisorySource, "fetch", return_value=self.snapshot,
        ) as fetch:
            with redirect_stdout(output), redirect_stderr(error):
                code = main([
                    "--data-dir", str(self.data),
                    "vuln", "ubuntu-evidence-check", evidence.id,
                ])
        self.assertEqual((code, error.getvalue()), (0, ""))
        self.assertIn("Kanıt güncel", output.getvalue())
        fetch.assert_called_once_with(CVE)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

"""Human-approved OSV advisory reference transfer into exposure evidence."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_osv_advisory import payload
from tests.test_vulnerability_exposures import CVE, NOW, nvd_snapshot
from xti.adapters.osv_dev import OsvDevAdvisorySource, parse_osv_response
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_nvd import SQLiteNvdRepository
from xti.adapters.sqlite_product_vulnerability import SQLiteProductVulnerabilityRepository
from xti.adapters.sqlite_products import SQLiteAssetProductRepository
from xti.adapters.sqlite_vulnerability_exposure_evidence import (
    SQLiteVulnerabilityExposureEvidenceRepository,
)
from xti.adapters.sqlite_vulnerability_exposures import (
    SQLiteVulnerabilityExposureRepository,
)
from xti.application.osv_advisory_evidence import OsvAdvisoryEvidenceService
from xti.application.products import AssetProductService
from xti.application.vulnerability_exposure_evidence import (
    VulnerabilityExposureEvidenceService,
)
from xti.application.vulnerability_exposures import VulnerabilityExposureService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


REFERENCE = "https://vendor.example/security/4001"


class FakeSource:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def fetch(self, cve_id):
        self.calls.append(cve_id)
        if isinstance(self.snapshot, BaseException):
            raise self.snapshot
        return self.snapshot


class OsvAdvisoryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        storage = SQLiteAssetRepository(self.path)
        storage.initialize()
        storage.add("example.com")
        SQLiteNvdRepository(self.path).apply(
            nvd_snapshot(), started_at="2026-10-29T11:00:00+00:00",
            finished_at="2026-10-29T11:00:01+00:00",
        )
        product = AssetProductService(
            SQLiteAssetProductRepository(self.path), clock=lambda: NOW,
        ).add(
            "example.com", part="a", vendor="acme", product="agent", version="1.0",
            evidence="Paket yöneticisi çıktısıyla doğrulandı.",
        ).record
        self.exposure = VulnerabilityExposureService(
            SQLiteVulnerabilityExposureRepository(self.path),
            SQLiteProductVulnerabilityRepository(self.path), clock=lambda: NOW,
        ).open(
            product.id, CVE, reason="Ürün-CVE adayı insan incelemesine alındı.",
        ).view.exposure
        self.snapshot = parse_osv_response(payload(), CVE)

    def service(self, source):
        return OsvAdvisoryEvidenceService(
            SQLiteVulnerabilityExposureRepository(self.path),
            SQLiteVulnerabilityExposureEvidenceRepository(self.path), source,
            clock=lambda: NOW + timedelta(hours=1),
        )

    def test_exact_current_https_advisory_is_added_with_source_context(self):
        source = FakeSource(self.snapshot)
        result = self.service(source).add(
            self.exposure.id, evidence_type="vendor_advisory",
            selected_reference=REFERENCE,
            summary="OSV başvurusundaki üretici duyurusu insan tarafından seçildi.",
        )
        self.assertEqual(source.calls, [CVE])
        self.assertEqual(result.queried_cve_id, CVE)
        self.assertEqual(result.record_id, "GHSA-abcd-1234-5678")
        self.assertEqual(result.selected_reference, REFERENCE)
        self.assertEqual(result.mutation.action, "added")
        self.assertEqual(result.mutation.record.evidence_type, "vendor_advisory")
        self.assertIn("içeriğin doğruluğunu", result.notes[0])

        records = VulnerabilityExposureEvidenceService(
            SQLiteVulnerabilityExposureEvidenceRepository(self.path), clock=lambda: NOW,
        ).list(self.exposure.id)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_reference, REFERENCE)

    def test_invalid_input_or_unknown_exposure_stops_before_osv_and_write(self):
        source = FakeSource(self.snapshot)
        service = self.service(source)
        before = self.path.read_bytes()
        invalid = (
            dict(evidence_type="package_inventory", selected_reference=REFERENCE,
                 summary="Geçerli uzunlukta fakat yanlış türde açıklama."),
            dict(evidence_type="vendor_advisory",
                 selected_reference="http://vendor.example/security/4001",
                 summary="HTTPS olmayan kaynak reddedilmeli."),
            dict(evidence_type="vendor_advisory", selected_reference=REFERENCE,
                 summary="kısa"),
        )
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValidationError):
                    service.add(self.exposure.id, **arguments)
        with self.assertRaises(ValidationError):
            service.add(
                "11111111-1111-4111-8111-111111111111",
                evidence_type="vendor_advisory", selected_reference=REFERENCE,
                summary="Var olmayan inceleme ağ isteğinden önce reddedilmeli.",
            )
        self.assertEqual(source.calls, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_unlisted_reference_or_source_error_never_writes_evidence(self):
        before = self.path.read_bytes()
        source = FakeSource(self.snapshot)
        with self.assertRaisesRegex(ValidationError, "ADVISORY"):
            self.service(source).add(
                self.exposure.id, evidence_type="distribution_advisory",
                selected_reference="https://distribution.example/security/4001",
                summary="OSV kaydında bulunmayan duyuru reddedilmeli.",
            )
        self.assertEqual(source.calls, [CVE])
        self.assertEqual(self.path.read_bytes(), before)

        failure = FakeSource(SourceError("OSV bağlantısı tamamlanamadı."))
        with self.assertRaises(SourceError):
            self.service(failure).add(
                self.exposure.id, evidence_type="vendor_advisory",
                selected_reference=REFERENCE,
                summary="Kaynak hatasında kalıcı kanıt yazılmamalı.",
            )
        self.assertEqual(self.path.read_bytes(), before)

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_fetches_current_osv_record_then_persists_only_selected_reference(self):
        with patch.object(
            OsvDevAdvisorySource, "fetch", return_value=self.snapshot,
        ) as fetch:
            code, stdout, stderr = self.invoke(
                "vuln", "advisory-evidence-add", self.exposure.id,
                "--type", "vendor_advisory", "--reference", REFERENCE,
                "--summary", "OSV önizlemesindeki üretici duyurusu elle seçildi.",
            )
        self.assertEqual((code, stderr), (0, ""))
        data = json.loads(stdout)["data"]
        self.assertEqual(data["selected_reference"], REFERENCE)
        self.assertEqual(data["mutation"]["action"], "added")
        fetch.assert_called_once_with(CVE)

        code, stdout, stderr = self.invoke(
            "vuln", "exposure-evidence-list", self.exposure.id, as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Üretici duyurusu", stdout)
        self.assertIn(REFERENCE, stdout)


if __name__ == "__main__":
    unittest.main()

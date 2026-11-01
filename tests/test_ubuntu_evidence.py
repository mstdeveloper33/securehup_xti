"""Human-selected Canonical Ubuntu result as exposure supporting evidence."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_vulnerability_exposures import CVE, NOW, nvd_snapshot
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_nvd import SQLiteNvdRepository
from xti.adapters.sqlite_product_vulnerability import SQLiteProductVulnerabilityRepository
from xti.adapters.sqlite_products import SQLiteAssetProductRepository
from xti.adapters.sqlite_ubuntu_packages import SQLiteUbuntuAssetPackageRepository
from xti.adapters.sqlite_vulnerability_exposure_evidence import (
    SQLiteVulnerabilityExposureEvidenceRepository,
)
from xti.adapters.sqlite_vulnerability_exposure_queue import (
    SQLiteVulnerabilityExposureQueueRepository,
)
from xti.adapters.sqlite_vulnerability_exposures import (
    SQLiteVulnerabilityExposureRepository,
)
from xti.adapters.ubuntu_osv import UbuntuOsvAdvisorySource, parse_ubuntu_osv_response
from xti.application.products import AssetProductService
from xti.application.ubuntu_evidence import UbuntuExposureEvidenceService
from xti.application.ubuntu_packages import UbuntuAssetPackageService
from xti.application.vulnerability_exposure_evidence import (
    VulnerabilityExposureEvidenceService,
)
from xti.application.vulnerability_exposure_queue import (
    VulnerabilityExposureQueueService,
)
from xti.application.vulnerability_exposures import VulnerabilityExposureService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


def ubuntu_payload(
    *, package="php8.3", fixed="8.3.6-0ubuntu0.24.04.5", withdrawn=None,
    modified="2026-10-29T18:00:00Z",
):
    value = {
        "schema_version": "1.7.0",
        "id": f"UBUNTU-{CVE}",
        "aliases": [],
        "upstream": [CVE],
        "modified": modified,
        "published": "2026-01-02T00:00:00Z",
        "affected": [{
            "package": {
                "ecosystem": "Ubuntu:24.04:LTS",
                "name": package,
                "purl": "pkg:deb/ubuntu/php8.3@8.3.6-0ubuntu0.24.04.5",
            },
            "versions": ["8.3.6-0ubuntu0.24.04.4"],
            "ranges": [{
                "type": "ECOSYSTEM",
                "events": [
                    {"introduced": "0"},
                    {"fixed": fixed},
                ],
            }],
        }],
        "references": [{
            "type": "ADVISORY",
            "url": "https://ubuntu.com/security/notices/USN-9999-1",
        }],
    }
    if withdrawn is not None:
        value["withdrawn"] = withdrawn
    return json.dumps(value, separators=(",", ":")).encode()


class Source:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def fetch(self, cve_id):
        self.calls.append(cve_id)
        return self.snapshot


class UbuntuExposureEvidenceTests(unittest.TestCase):
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
        self.packages = UbuntuAssetPackageService(
            SQLiteUbuntuAssetPackageRepository(self.path), clock=lambda: NOW,
        )
        self.package = self.add_package().record
        self.snapshot = parse_ubuntu_osv_response(ubuntu_payload(), CVE)

    def add_package(self, asset="example.com", **changes):
        values = dict(
            ecosystem="Ubuntu:24.04:LTS", binary_name="php8.3-cli",
            binary_version="8.3.6-0ubuntu0.24.04.99", architecture="amd64",
            source_name="php8.3", source_version="8.3.6-0ubuntu0.24.04.4",
            evidence="dpkg-query ve apt-cache showsrc birlikte doğrulandı.",
        )
        values.update(changes)
        return self.packages.add(asset, **values)

    def service(self, source=None, clock=None):
        return UbuntuExposureEvidenceService(
            SQLiteVulnerabilityExposureRepository(self.path),
            SQLiteUbuntuAssetPackageRepository(self.path),
            SQLiteVulnerabilityExposureEvidenceRepository(self.path),
            source or Source(self.snapshot),
            clock=clock or (lambda: NOW + timedelta(hours=1)),
        )

    def generic_evidence(self, path=None):
        return VulnerabilityExposureEvidenceService(
            SQLiteVulnerabilityExposureEvidenceRepository(path or self.path),
            clock=lambda: NOW + timedelta(hours=2),
        )

    def test_selected_current_result_is_sealed_visible_and_does_not_change_decision(self):
        source = Source(self.snapshot)
        result = self.service(source).add(
            self.exposure.id, self.package.id,
            summary="Canonical sonucu ve yerel source paket sürümü birlikte seçildi.",
        )
        self.assertEqual(source.calls, [CVE])
        self.assertEqual(result.mutation.action, "added")
        self.assertEqual(result.comparison.status, "before_fixed_boundary")
        record = result.mutation.record
        self.assertEqual(record.evidence_type, "package_inventory")
        self.assertEqual(record.source_reference, result.source_reference)
        self.assertTrue(record.source_reference.startswith(f"ubuntu-osv-v1:{CVE}:"))
        self.assertIn(self.snapshot.content_sha256, record.source_reference)
        self.assertIn(result.package_snapshot_sha256, record.source_reference)

        repeated = self.service(source).add(
            self.exposure.id, self.package.id,
            summary="Canonical sonucu ve yerel source paket sürümü birlikte seçildi.",
        )
        self.assertEqual(repeated.mutation.action, "unchanged")
        details = self.generic_evidence().show(record.id)
        self.assertEqual(details.total_event_count, 1)
        self.assertEqual(self.generic_evidence().list(self.exposure.id), (record,))

        exposure = SQLiteVulnerabilityExposureRepository(self.path).details(
            self.exposure.id, event_limit=10,
            checked_at=(NOW + timedelta(hours=2)).isoformat(),
        )
        self.assertEqual(exposure.view.exposure.status, "investigating")
        self.assertEqual(exposure.total_event_count, 1)
        queue = VulnerabilityExposureQueueService(
            SQLiteVulnerabilityExposureQueueRepository(self.path),
            clock=lambda: NOW + timedelta(hours=2),
        ).show(evidence_filter="present")
        self.assertEqual((queue.total_count, queue.active_evidence_count), (1, 1))
        self.assertEqual(queue.items[0].active_evidence_types, ("package_inventory",))

        backup = Path(self.temp.name) / "backup.db"
        SQLiteAssetRepository(self.path).backup(backup)
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(self.generic_evidence(restored).show(record.id), details)

    def test_cross_asset_invalid_input_and_unlisted_result_never_write(self):
        SQLiteAssetRepository(self.path).add("other.example")
        other = self.add_package("other.example").record
        source = Source(self.snapshot)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValidationError, "aynı varlığa"):
            self.service(source).add(
                self.exposure.id, other.id,
                summary="Başka varlığın paketi kanıt olarak bağlanmamalıdır.",
            )
        self.assertEqual(source.calls, [])
        self.assertEqual(self.path.read_bytes(), before)

        for exposure_id, package_id, summary in (
            ("bad", self.package.id, "Kimlik ağ çağrısından önce reddedilmelidir."),
            (self.exposure.id, "bad", "Paket kimliği ağdan önce reddedilmelidir."),
            (self.exposure.id, self.package.id, "x"),
        ):
            invalid_source = Source(self.snapshot)
            with self.subTest(exposure_id=exposure_id, package_id=package_id):
                with self.assertRaises(ValidationError):
                    self.service(invalid_source).add(
                        exposure_id, package_id, summary=summary,
                    )
                self.assertEqual(invalid_source.calls, [])

        unlisted = parse_ubuntu_osv_response(ubuntu_payload(package="openssl"), CVE)
        unlisted_source = Source(unlisted)
        with self.assertRaisesRegex(ValidationError, "affected paket bağı"):
            self.service(unlisted_source).add(
                self.exposure.id, self.package.id,
                summary="Listelenmeyen paket sonucu destek kanıtı sayılmamalıdır.",
            )
        self.assertEqual(unlisted_source.calls, [CVE])
        self.assertEqual(self.generic_evidence().list(self.exposure.id), ())

        withdrawn = parse_ubuntu_osv_response(
            ubuntu_payload(withdrawn="2026-10-29T18:00:00Z"), CVE,
        )
        with self.assertRaisesRegex(ValidationError, "affected paket bağı"):
            self.service(Source(withdrawn)).add(
                self.exposure.id, self.package.id,
                summary="Geri çekilmiş kayıt kalıcı paket kanıtı olmamalıdır.",
            )
        self.assertEqual(self.generic_evidence().list(self.exposure.id), ())

    def test_package_change_during_fetch_blocks_stale_selection_atomically(self):
        later = UbuntuAssetPackageService(
            SQLiteUbuntuAssetPackageRepository(self.path),
            clock=lambda: NOW + timedelta(minutes=5),
        )

        class UpdatingSource:
            def fetch(inner, cve_id):
                later.add(
                    "example.com", ecosystem="Ubuntu:24.04:LTS",
                    binary_name="php8.3-cli",
                    binary_version="8.3.6-0ubuntu0.24.04.99",
                    architecture="amd64", source_name="php8.3",
                    source_version="8.3.6-0ubuntu0.24.04.4",
                    evidence="Paket kanıtı ağ isteği sırasında yeniden doğrulandı.",
                )
                return self.snapshot

        with self.assertRaisesRegex(ValidationError, "seçim sırasında değişti"):
            self.service(UpdatingSource()).add(
                self.exposure.id, self.package.id,
                summary="Eski paket anlık görüntüsüyle kanıt yazılmamalıdır.",
            )
        self.assertEqual(self.generic_evidence().list(self.exposure.id), ())

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main([*argv, *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_refetches_persists_and_existing_evidence_commands_read_it(self):
        with patch.object(
            UbuntuOsvAdvisorySource, "fetch", return_value=self.snapshot,
        ) as fetch:
            code, output, error = self.invoke(
                "vuln", "ubuntu-evidence-add", self.exposure.id, self.package.id,
                "--summary", "Terminalde seçilen Canonical paket sonucu kaydedildi.",
            )
        self.assertEqual((code, error), (0, ""))
        data = json.loads(output)["data"]
        evidence_id = data["mutation"]["record"]["id"]
        self.assertEqual(data["comparison"]["status"], "before_fixed_boundary")
        fetch.assert_called_once_with(CVE)

        code, output, error = self.invoke(
            "vuln", "exposure-evidence-show", evidence_id, as_json=False,
        )
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Yerel paket envanteri", output)
        self.assertIn("ubuntu-osv-v1", output)

        code, output, error = self.invoke(
            "vuln", "exposure-queue", "--evidence", "present", as_json=False,
        )
        self.assertEqual((code, error), (0, ""))
        self.assertIn("yerel paket envanteri", output)


if __name__ == "__main__":
    unittest.main()

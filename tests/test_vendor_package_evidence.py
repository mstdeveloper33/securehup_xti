"""Selected, structured Red Hat RPM/VEX evidence lifecycle."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tests.test_vendor_advisory import COMPONENT_ID, CVE, payload, payload_with_product_ids
from tests.test_vulnerability_exposures import NOW, nvd_snapshot
from xti.adapters.redhat_csaf_vex import RedHatCsafVexSource, parse_redhat_vex_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_nvd import SQLiteNvdRepository
from xti.adapters.sqlite_packages import SQLiteAssetPackageRepository
from xti.adapters.sqlite_product_vulnerability import SQLiteProductVulnerabilityRepository
from xti.adapters.sqlite_products import SQLiteAssetProductRepository
from xti.adapters.sqlite_vendor_package_evidence import SQLiteVendorPackageEvidenceRepository
from xti.adapters.sqlite_vulnerability_exposures import SQLiteVulnerabilityExposureRepository
from xti.adapters.sqlite_vulnerability_exposure_queue import (
    SQLiteVulnerabilityExposureQueueRepository,
)
from xti.application.packages import AssetPackageService
from xti.application.products import AssetProductService
from xti.application.vendor_package_evidence import VendorPackageEvidenceService
from xti.application.vendor_package_evidence_check import VendorPackageEvidenceCheckService
from xti.application.vendor_package_match import VendorPackageMatchService
from xti.application.vulnerability_exposures import VulnerabilityExposureService
from xti.application.vulnerability_exposure_queue import VulnerabilityExposureQueueService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


CPE = "cpe:/o:redhat:enterprise_linux:9"


class Source:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def fetch(self, cve_id):
        self.calls.append(cve_id)
        return self.snapshot


class VendorPackageEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        assets = SQLiteAssetRepository(self.path)
        assets.initialize()
        assets.add("example.com")
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
        self.packages = AssetPackageService(
            SQLiteAssetPackageRepository(self.path), clock=lambda: NOW,
        )
        self.package = self.packages.add(
            "example.com", provider="redhat", name="openssl", epoch=0,
            version="3.2.2", release="1.el9", architecture="x86_64",
            distribution_cpe=CPE, source_rpm="openssl-3.2.2-1.el9.src.rpm",
            evidence="RPM sorgusu ve Red Hat dağıtım kaydı doğrulandı.",
        ).record
        self.snapshot = parse_redhat_vex_response(payload(), CVE)

    def service(self, source=None, clock=None):
        return VendorPackageEvidenceService(
            SQLiteVulnerabilityExposureRepository(self.path),
            SQLiteAssetPackageRepository(self.path),
            SQLiteVendorPackageEvidenceRepository(self.path),
            source or Source(self.snapshot), clock=clock or (lambda: NOW + timedelta(hours=1)),
        )

    def test_selected_current_exact_relation_is_structured_and_does_not_change_decision(self):
        source = Source(self.snapshot)
        result = self.service(source).add(
            self.exposure.id, self.package.id, selected_vex_product_id=COMPONENT_ID,
            summary="Güncel Red Hat VEX tam RPM ilişkisi insan tarafından seçildi.",
        )
        self.assertEqual(source.calls, [CVE])
        record = result.mutation.record
        self.assertEqual(result.mutation.action, "added")
        self.assertEqual((record.vendor_status, record.match_kind),
                         ("fixed", "exact_binary_package"))
        self.assertEqual(record.source_sha256, self.snapshot.content_sha256)
        self.assertEqual(record.vex_product_id, COMPONENT_ID)
        self.assertEqual(record.context_cpe, CPE)
        self.assertEqual(record.package_updated_at, self.package.updated_at)
        details = self.service().show(record.id)
        self.assertEqual(details.total_event_count, 1)
        self.assertEqual(self.service().list(self.exposure.id), (record,))
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
        self.assertEqual(queue.items[0].active_evidence_types, ("exact_vendor_package",))
        self.assertEqual(queue.items[0].priority_band, "normal")

        backup = Path(self.temp.name) / "backup.db"
        SQLiteAssetRepository(self.path).backup(backup)
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        restored_details = SQLiteVendorPackageEvidenceRepository(restored).details(
            record.id, event_limit=10,
        )
        self.assertEqual(restored_details, details)

    def test_opaque_product_ids_survive_selection_storage_recheck_and_restore(self):
        vex_id, context_id = " selected VEX product ", "Red Hat Enterprise Linux 9 "
        snapshot = parse_redhat_vex_response(payload_with_product_ids({
            COMPONENT_ID: vex_id, "rhel-9": context_id,
        }), CVE)
        source = Source(snapshot)
        service = self.service(source)
        arguments = dict(selected_vex_product_id=vex_id, summary="Opaque source identity fixture.")
        selected = service.add(self.exposure.id, self.package.id, **arguments)
        record = selected.mutation.record
        self.assertEqual((record.vex_product_id, record.context_product_id), (vex_id, context_id))
        self.assertEqual(record.source_sha256, snapshot.content_sha256)
        repeated = service.add(self.exposure.id, self.package.id, **arguments)
        self.assertEqual(repeated.mutation.action, "unchanged")
        details = service.show(record.id)
        self.assertEqual(details.total_event_count, 1)
        with self.assertRaisesRegex(ValidationError, "tekil"):
            service.add(self.exposure.id, self.package.id,
                        selected_vex_product_id=vex_id.strip(), summary="Wrong trimmed identity fixture.")
        self.assertEqual(service.show(record.id), details)
        check = VendorPackageEvidenceCheckService(
            SQLiteVendorPackageEvidenceRepository(self.path), SQLiteAssetPackageRepository(self.path), source,
            clock=lambda: NOW + timedelta(hours=2),
        ).check(record.id)
        self.assertEqual(check.state, "current")
        backup = Path(self.temp.name) / "opaque-backup.db"
        SQLiteAssetRepository(self.path).backup(backup)
        restored = Path(self.temp.name) / "opaque-restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteVendorPackageEvidenceRepository(restored).details(record.id, event_limit=10), details)

    def test_evidence_fetches_exposure_cve_after_previewing_a_different_cve(self):
        other_cve = "CVE-2014-0160"
        other_snapshot = parse_redhat_vex_response(payload().replace(CVE.encode(), other_cve.encode()), other_cve)
        snapshots, calls = {CVE: self.snapshot, other_cve: other_snapshot}, []

        class RoutedSource:
            def fetch(self, cve_id):
                calls.append(cve_id)
                return snapshots[cve_id]

        source = RoutedSource()
        preview = VendorPackageMatchService(SQLiteAssetPackageRepository(self.path), source).match(self.package.id, other_cve)
        self.assertEqual(preview.match_state, "exact_vendor_statement")
        selected = self.service(source).add(self.exposure.id, self.package.id,
            selected_vex_product_id=preview.matches[0].vex_product_id, summary="Exposure determines the CVE.")
        self.assertEqual(calls, [other_cve, CVE])
        self.assertEqual(selected.mutation.record.cve_id, self.exposure.cve_id)
        self.assertEqual(selected.mutation.record.source_url, self.snapshot.source_url)
        self.assertEqual(selected.mutation.record.source_sha256, self.snapshot.content_sha256)

    def test_wrong_selection_cross_asset_and_no_exact_match_never_write(self):
        before = self.path.read_bytes()
        source = Source(self.snapshot)
        with self.assertRaisesRegex(ValidationError, "tekil"):
            self.service(source).add(
                self.exposure.id, self.package.id, selected_vex_product_id="not-current",
                summary="Güncel olmayan ürün bağı reddedilmelidir.",
            )
        self.assertEqual(source.calls, [CVE])
        self.assertEqual(self.path.read_bytes(), before)

        SQLiteAssetRepository(self.path).add("other.example")
        other = self.packages.add(
            "other.example", provider="redhat", name="openssl", epoch=0,
            version="3.2.2", release="1.el9", architecture="x86_64",
            distribution_cpe=CPE, source_rpm="openssl-3.2.2-1.el9.src.rpm",
            evidence="Başka varlığa ait kesin RPM kaydı doğrulandı.",
        ).record
        source = Source(self.snapshot)
        with self.assertRaisesRegex(ValidationError, "aynı varlığa"):
            self.service(source).add(
                self.exposure.id, other.id, selected_vex_product_id=COMPONENT_ID,
                summary="Başka varlık kaydı bağlanmamalıdır.",
            )
        self.assertEqual(source.calls, [])

        mismatch = self.packages.add(
            "example.com", provider="redhat", name="openssl", epoch=0,
            version="3.2.2", release="2.el9", architecture="x86_64",
            distribution_cpe=CPE, source_rpm="openssl-3.2.2-2.el9.src.rpm",
            evidence="Farklı release kesin olarak doğrulandı.",
        ).record
        with self.assertRaisesRegex(ValidationError, "tek ve çelişkisiz"):
            self.service().add(
                self.exposure.id, mismatch.id, selected_vex_product_id=COMPONENT_ID,
                summary="Eşleşmeyen release kanıt sayılmamalıdır.",
            )
        self.assertEqual(self.service().list(self.exposure.id), ())

    def test_package_change_during_fetch_blocks_stale_selection_and_corruption_fails_closed(self):
        later_packages = AssetPackageService(
            SQLiteAssetPackageRepository(self.path), clock=lambda: NOW + timedelta(minutes=5),
        )

        class UpdatingSource:
            def fetch(inner, cve_id):
                later_packages.add(
                    "example.com", provider="redhat", name="openssl", epoch=0,
                    version="3.2.2", release="1.el9", architecture="x86_64",
                    distribution_cpe=CPE, source_rpm="openssl-3.2.2-1.el9.src.rpm",
                    evidence="RPM kanıtı ağ isteği sırasında yeniden doğrulandı.",
                )
                return self.snapshot

        with self.assertRaisesRegex(ValidationError, "seçimden sonra değişti"):
            self.service(UpdatingSource()).add(
                self.exposure.id, self.package.id, selected_vex_product_id=COMPONENT_ID,
                summary="Eski RPM anlık görüntüsüyle kanıt yazılmamalıdır.",
            )
        self.assertEqual(self.service().list(self.exposure.id), ())

        current = SQLiteAssetPackageRepository(self.path).details(
            self.package.id, event_limit=1,
        ).record
        record = self.service().add(
            self.exposure.id, current.id, selected_vex_product_id=COMPONENT_ID,
            summary="Yeniden eşleştirilen güncel RPM kanıtı seçildi.",
        ).mutation.record
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE vulnerability_vendor_package_evidence SET source_sha256='bad' WHERE id=?",
                (record.id,),
            )
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.service().show(record.id)
        with self.assertRaises(StorageError):
            VulnerabilityExposureQueueService(
                SQLiteVulnerabilityExposureQueueRepository(self.path),
                clock=lambda: NOW + timedelta(hours=2),
            ).show()
        self.assertEqual(self.path.read_bytes(), before)

    def test_revoke_reactivate_and_new_source_digest_preserve_history(self):
        first = self.service().add(
            self.exposure.id, self.package.id, selected_vex_product_id=COMPONENT_ID,
            summary="İlk güncel VEX ilişkisi seçildi.",
        ).mutation.record
        revoked = self.service().revoke(
            first.id, reason="Kanıt analist tarafından geçici olarak etkisizleştirildi.",
        )
        self.assertEqual(revoked.action, "revoked")
        self.assertEqual(self.service().list(self.exposure.id), ())
        reactivated = self.service(clock=lambda: NOW + timedelta(hours=2)).add(
            self.exposure.id, self.package.id, selected_vex_product_id=COMPONENT_ID,
            summary="Aynı kaynak yeniden değerlendirilip etkinleştirildi.",
        )
        self.assertEqual(reactivated.mutation.action, "reactivated")
        details = self.service().show(first.id)
        self.assertEqual(details.total_event_count, 3)
        self.assertEqual([event.action for event in details.events],
                         ["reactivated", "revoked", "added"])

        document = json.loads(payload())
        document["document"]["tracking"]["version"] = "4"
        document["document"]["tracking"]["current_release_date"] = "2026-10-29T19:00:00+00:00"
        document["document"]["tracking"]["revision_history"].append({
            "date": "2026-10-29T19:00:00+00:00", "number": "4", "summary": "Refresh",
        })
        newer = parse_redhat_vex_response(json.dumps(document).encode(), CVE)
        second = self.service(Source(newer), clock=lambda: NOW + timedelta(hours=3)).add(
            self.exposure.id, self.package.id, selected_vex_product_id=COMPONENT_ID,
            summary="Yeni belge sürümündeki kesin ilişki ayrıca seçildi.",
        ).mutation.record
        self.assertNotEqual(second.id, first.id)
        self.assertNotEqual(second.source_sha256, first.source_sha256)
        self.assertEqual(len(self.service().list(self.exposure.id)), 2)

    def test_reverified_package_snapshot_is_new_evidence_even_with_same_vex(self):
        first = self.service().add(
            self.exposure.id, self.package.id, selected_vex_product_id=COMPONENT_ID,
            summary="İlk RPM anlık görüntüsü için VEX bağı seçildi.",
        ).mutation.record
        AssetPackageService(
            SQLiteAssetPackageRepository(self.path), clock=lambda: NOW + timedelta(hours=2),
        ).add(
            "example.com", provider="redhat", name="openssl", epoch=0,
            version="3.2.2", release="1.el9", architecture="x86_64",
            distribution_cpe=CPE, source_rpm="openssl-3.2.2-1.el9.src.rpm",
            evidence="RPM aynı kimlikle yeniden doğrulandı.",
        )
        second = self.service(clock=lambda: NOW + timedelta(hours=3)).add(
            self.exposure.id, self.package.id, selected_vex_product_id=COMPONENT_ID,
            summary="Yeniden doğrulanan RPM anlık görüntüsü ayrıca seçildi.",
        ).mutation.record
        self.assertNotEqual(second.id, first.id)
        self.assertEqual(second.source_sha256, first.source_sha256)
        self.assertNotEqual(second.package_updated_at, first.package_updated_at)
        self.assertEqual(len(self.service().list(self.exposure.id)), 2)

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_refetches_then_persists_selected_relation_and_lists_it(self):
        with patch.object(RedHatCsafVexSource, "fetch", return_value=self.snapshot) as fetch:
            code, stdout, stderr = self.invoke(
                "vuln", "vendor-evidence-add", self.exposure.id, self.package.id,
                "--vex-product-id", COMPONENT_ID,
                "--summary", "vendor-match çıktısındaki kesin ilişki elle seçildi.",
            )
        self.assertEqual((code, stderr), (0, ""))
        data = json.loads(stdout)["data"]
        self.assertEqual(data["mutation"]["record"]["vendor_status"], "fixed")
        fetch.assert_called_once_with(CVE)

        code, stdout, stderr = self.invoke(
            "vuln", "vendor-evidence-list", self.exposure.id, as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("fixed", stdout)
        self.assertIn(COMPONENT_ID, stdout)

        code, stdout, stderr = self.invoke(
            "vuln", "exposure-queue", "--evidence", "present", as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("kesin üretici paket/VEX kanıtı", stdout)


if __name__ == "__main__":
    unittest.main()

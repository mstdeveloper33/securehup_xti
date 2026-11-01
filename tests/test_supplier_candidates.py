"""Evidence-bound supplier candidates and reversible human resolution."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.sqlite_supplier_candidates import (
    SQLiteSupplierCandidateRepository,
    SQLiteSupplierDependencySource,
)
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.supplier_candidates import SupplierCandidateService
from xti.application.suppliers import SupplierService
from xti.domain.assets import ValidationError
from xti.domain.cname import CNAME_POLICY_VERSION, CnameDnsResult, CnameHop
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 31, 15, tzinfo=timezone.utc)


def cname_result(target="edge.vendor.example", *, present=True):
    return CnameDnsResult(
        "api.example.com", NOW.isoformat(),
        (NOW + timedelta(seconds=1)).isoformat(), CNAME_POLICY_VERSION,
        "present" if present else "absent",
        (CnameHop("api.example.com", target),) if present else (),
        target if present else None,
        "resolved" if present else "not_applicable",
        ("93.184.216.34",) if present else (), (),
        ("Yalnız kayıtlı DNS kanıtı.",),
    )


class SupplierCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _ = self.storage.add("api.example.com")
        SQLiteSurfaceRepository(self.path, clock=lambda: NOW).activate(
            self.asset.id, self.asset.value, "Yönettiğim API adresi", NOW.isoformat(),
        )
        self.cnames = SQLiteSurfaceCnameRepository(
            self.path, clock=lambda: NOW + timedelta(minutes=1),
        )
        self.cnames.append_check(self.asset.id, cname_result())
        self.now = NOW + timedelta(minutes=2)
        self.repository = SQLiteSupplierCandidateRepository(self.path)
        self.service = SupplierCandidateService(
            SQLiteSupplierDependencySource(self.path), self.repository,
            PublicSuffixResolver(), clock=lambda: self.now,
        )
        self.suppliers = SupplierService(
            SQLiteSupplierRepository(self.path), clock=lambda: self.now,
        )

    def add_supplier(self, name="Örnek Sağlayıcı", domain="vendor.example"):
        return self.suppliers.add(
            name, domain=domain, relationship_type="cloud", criticality="high",
            reason="API hizmetinin dış sağlayıcısı olarak kullanılıyor.",
        ).supplier

    def test_refresh_is_local_idempotent_and_preserves_new_evidence(self):
        first = self.service.refresh()
        self.assertEqual(
            (first.observation_count, first.external_dependency_count,
             first.candidates_created, first.evidence_created),
            (1, 1, 1, 1),
        )
        candidate = self.service.list()[0]
        self.assertEqual(
            (candidate.asset_value, candidate.candidate_domain, candidate.status),
            ("api.example.com", "vendor.example", "pending"),
        )
        before = self.path.read_bytes()
        repeated = self.service.refresh()
        self.assertEqual(
            (repeated.candidates_created, repeated.candidates_existing,
             repeated.evidence_created, repeated.evidence_existing),
            (0, 1, 0, 1),
        )
        self.assertEqual(self.path.read_bytes(), before)

        self.cnames.append_check(self.asset.id, cname_result("cdn.vendor.example"))
        self.now += timedelta(minutes=1)
        changed = self.service.refresh()
        self.assertEqual((changed.candidates_existing, changed.evidence_created), (1, 1))
        details = self.service.show(candidate.id)
        self.assertEqual(details.total_evidence_count, 2)
        self.assertEqual(details.evidence[-1].target_domain, "cdn.vendor.example")

    def test_review_requires_active_supplier_and_is_reversible(self):
        self.service.refresh()
        candidate = self.service.list()[0]
        with self.assertRaisesRegex(ValidationError, "--supplier"):
            self.service.review(
                candidate.id, decision="accepted", supplier_id=None,
                reason="Bu hizmet için sözleşmemiz bulunuyor.",
            )
        supplier = self.add_supplier()
        accepted = self.service.review(
            candidate.id, decision="accepted", supplier_id=supplier.id,
            reason="Bu hizmet için sözleşmemiz bulunuyor.",
        )
        self.assertEqual((accepted.action, accepted.candidate.status), ("accepted", "accepted"))
        repeated = self.service.review(
            candidate.id, decision="accepted", supplier_id=supplier.id,
            reason="Bu hizmet için sözleşmemiz bulunuyor.",
        )
        self.assertFalse(repeated.changed)

        uncertain = self.service.review(
            candidate.id, decision="uncertain", supplier_id=None,
            reason="CNAME ortak altyapı olabilir; sözleşme bağı yeniden incelenecek.",
        )
        self.assertIsNone(uncertain.candidate.supplier_id)
        reopened = self.service.review(
            candidate.id, decision="pending", supplier_id=None,
            reason="Kuruluş bağlantısı yeniden insan incelemesine alındı.",
        )
        self.assertEqual(reopened.candidate.status, "pending")
        details = self.service.show(candidate.id)
        self.assertEqual(
            [item.decision for item in details.resolutions],
            ["accepted", "uncertain", "pending"],
        )
        self.assertEqual(details.total_resolution_count, 3)

    def test_same_registration_root_is_skipped_and_disappearing_link_is_historical(self):
        self.service.refresh()
        candidate = self.service.list()[0]
        self.cnames.append_check(self.asset.id, cname_result(present=False))
        self.now += timedelta(minutes=1)
        result = self.service.refresh()
        self.assertEqual((result.external_dependency_count, result.became_historical), (0, 1))
        self.assertEqual(self.service.list(), ())
        historical = self.service.list(status=None, current_only=False)
        self.assertEqual((historical[0].id, historical[0].current), (candidate.id, False))

        other = SQLiteAssetRepository(self.path).add("www.example.com")[0]
        SQLiteSurfaceRepository(self.path, clock=lambda: NOW).activate(
            other.id, other.value, "Yönettiğim web adresi", NOW.isoformat(),
        )
        SQLiteSurfaceCnameRepository(self.path, clock=lambda: self.now).append_check(
            other.id,
            CnameDnsResult(
                "www.example.com", NOW.isoformat(), self.now.isoformat(),
                CNAME_POLICY_VERSION, "present",
                (CnameHop("www.example.com", "origin.example.com"),),
                "origin.example.com", "resolved", ("93.184.216.34",), (), (),
            ),
        )
        skipped = self.service.refresh()
        self.assertEqual(skipped.external_dependency_count, 0)

    def test_corrupt_candidate_or_source_fails_closed_without_rewrite(self):
        self.service.refresh()
        candidate = self.service.list()[0]
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE supplier_candidate_evidence SET target_domain='other.example' "
                "WHERE candidate_id=?", (candidate.id,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "CNAME kanıtıyla uyuşmuyor"):
            self.service.show(candidate.id)
        with self.assertRaises(StorageError):
            self.service.refresh()
        self.assertEqual(self.path.read_bytes(), before)

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_terminal_json_read_views_backup_and_doctor(self):
        code, stdout, stderr = self.invoke("suppliers", "candidate-refresh")
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout)["data"]["candidates_created"], 1)
        candidate = self.service.list()[0]
        supplier = self.add_supplier()
        code, stdout, stderr = self.invoke(
            "suppliers", "candidate-review", candidate.id,
            "--decision", "accepted", "--supplier", supplier.id,
            "--reason", "Bu hizmet için sözleşmemiz bulunuyor.",
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout)["data"]["candidate"]["status"], "accepted")

        before = self.path.read_bytes()
        code, stdout, stderr = self.invoke(
            "suppliers", "candidate-list", "--status", "all", as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("vendor.example", stdout)
        code, stdout, stderr = self.invoke(
            "suppliers", "candidate-show", candidate.id, as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("CNAME yalnız teknik bağımlılık adayıdır", stdout)
        code, stdout, stderr = self.invoke("doctor", as_json=False)
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Tedarikçi adayı: 1 güncel", stdout)
        self.assertEqual(self.path.read_bytes(), before)

        backup = self.storage.backup(Path(self.temp.name) / "backup.db")
        restored = Path(self.temp.name) / "restore" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        after = SQLiteSupplierCandidateRepository(restored).show(
            candidate.id, evidence_limit=20, resolution_limit=20,
        )
        self.assertEqual(after.candidate.status, "accepted")
        self.assertEqual(after.total_resolution_count, 1)


if __name__ == "__main__":
    unittest.main()

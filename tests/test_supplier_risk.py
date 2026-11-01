"""Explainable supplier review cards without automatic breach conclusions."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_supplier_candidates import (
    SQLiteSupplierCandidateRepository,
    SQLiteSupplierDependencySource,
)
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.supplier_candidates import SupplierCandidateService
from xti.application.supplier_risk import SupplierRiskService
from xti.application.supplier_threat_events import SupplierThreatEventService
from xti.application.suppliers import SupplierService
from xti.domain.assets import ValidationError
from xti.domain.cname import CNAME_POLICY_VERSION, CnameDnsResult, CnameHop
from xti.interfaces.cli import main
from tests.test_ransomlook_ransomware import content as ransomlook_content, post
from tests.test_threatcluster_ransomware import claim, content as threatcluster_content


NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


class SupplierRiskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.supplier_repository = SQLiteSupplierRepository(self.path)
        self.supplier_service = SupplierService(
            self.supplier_repository, clock=lambda: NOW,
        )
        self.primary = self.supplier_service.add(
            "Example Holding", domain="example.com", relationship_type="cloud",
            criticality="critical", reason="Kritik bulut hizmeti ilişkisi doğrulandı.",
        ).supplier
        self.same_name = self.supplier_service.add(
            "Example Holding", domain="other.example", relationship_type="software",
            criticality="low", reason="Aynı adlı ayrı yazılım sağlayıcısıdır.",
        ).supplier
        self.threatcluster = SQLiteRansomwareClaimRepository(self.path)
        self.ransomlook = SQLiteRansomLookClaimRepository(self.path)
        self.candidate_repository = SQLiteSupplierCandidateRepository(self.path)
        self.event_service = SupplierThreatEventService(
            self.supplier_repository, self.threatcluster, self.ransomlook,
        )
        self.risk = SupplierRiskService(
            self.supplier_repository, self.candidate_repository, self.event_service,
        )

    def apply_sources(self, *, with_claim=True):
        threat_records = ([claim(
            "Example Holding", website="www.example.com",
            discovered="2026-10-30T12:00:00+00:00",
        )] if with_claim else [])
        threat = parse_threatcluster_ransomware_response(
            threatcluster_content(threat_records), fetched_at=NOW - timedelta(hours=2),
        )
        self.threatcluster.apply(
            threat,
            started_at=(NOW - timedelta(hours=1)).isoformat(),
            finished_at=(NOW - timedelta(hours=1) + timedelta(seconds=1)).isoformat(),
            item_limit=100,
        )
        ransom_records = ([post(
            "Example Holding", group="example-group",
            discovered="2026-10-30T18:00:00Z",
        )] if with_claim else [])
        ransom = parse_ransomlook_ransomware_response(
            ransomlook_content(ransom_records), fetched_at=NOW,
        )
        self.ransomlook.apply(
            ransom,
            started_at=(NOW + timedelta(minutes=1)).isoformat(),
            finished_at=(NOW + timedelta(minutes=1, seconds=1)).isoformat(),
            item_limit=100,
        )

    def accept_dependency(self):
        asset, _ = self.storage.add("portal.customer.com")
        SQLiteSurfaceRepository(self.path, clock=lambda: NOW).activate(
            asset.id, asset.value, "Yönettiğim müşteri portalı", NOW.isoformat(),
        )
        result = CnameDnsResult(
            asset.value, NOW.isoformat(), (NOW + timedelta(seconds=1)).isoformat(),
            CNAME_POLICY_VERSION, "present",
            (CnameHop(asset.value, "cdn.example.com"),),
            "cdn.example.com", "resolved", ("93.184.216.34",), (),
            ("Yalnız kayıtlı DNS kanıtı.",),
        )
        SQLiteSurfaceCnameRepository(
            self.path, clock=lambda: NOW + timedelta(minutes=2),
        ).append_check(asset.id, result)
        candidates = SupplierCandidateService(
            SQLiteSupplierDependencySource(self.path), self.candidate_repository,
            PublicSuffixResolver(), clock=lambda: NOW + timedelta(minutes=3),
        )
        candidates.refresh()
        candidate = candidates.list()[0]
        candidates.review(
            candidate.id, decision="accepted", supplier_id=self.primary.id,
            reason="Bu teknik hizmet bağı sözleşme kapsamında doğrulandı.",
        )
        return candidate

    def test_card_combines_criticality_dependency_and_source_evidence(self):
        self.apply_sources()
        candidate = self.accept_dependency()
        before = self.path.read_bytes()
        report = self.risk.list()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(report.total_supplier_count, 2)
        primary = next(
            card for card in report.cards if card.supplier.id == self.primary.id
        )
        self.assertEqual(primary.attention, "priority_review")
        self.assertEqual(primary.current_dependency_count, 1)
        self.assertEqual(primary.claim_candidate_count, 2)
        self.assertEqual(primary.matched_source_count, 2)
        self.assertEqual(primary.domain_evidence_count, 1)
        self.assertIn(candidate.id, [item.id for item in self.risk.show(
            self.primary.id,
        ).dependencies])
        details = self.risk.show(self.primary.id)
        self.assertEqual(len(details.events), 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_same_name_only_card_requires_identity_review(self):
        self.apply_sources()
        report = self.risk.list()
        ambiguous = next(
            card for card in report.cards if card.supplier.id == self.same_name.id
        )
        self.assertEqual(ambiguous.attention, "identity_review")
        self.assertEqual(ambiguous.domain_evidence_count, 0)
        self.assertEqual(ambiguous.ambiguous_name_count, 2)
        self.assertTrue(any("ayıramıyor" in reason for reason in ambiguous.reasons))

    def test_missing_data_and_successful_empty_snapshot_are_distinct(self):
        missing = self.risk.list()
        self.assertTrue(all(
            card.attention == "insufficient_data" for card in missing.cards
        ))
        self.assertEqual(missing.insufficient_data_count, 2)

        self.apply_sources(with_claim=False)
        empty = self.risk.list()
        self.assertTrue(all(
            card.attention == "no_current_match" for card in empty.cards
        ))
        self.assertEqual(empty.no_current_match_count, 2)
        self.assertTrue(all(card.available_source_count == 2 for card in empty.cards))

    def test_filter_validation_and_inactive_supplier_fail_closed(self):
        self.apply_sources()
        with self.assertRaisesRegex(ValidationError, "1–500"):
            self.risk.list(limit=0)
        self.supplier_service.revoke(
            self.same_name.id, reason="Tedarikçi ilişkisi sona erdi.",
        )
        report = self.risk.list()
        self.assertEqual(report.total_supplier_count, 1)
        with self.assertRaisesRegex(ValidationError, "risk kartı bulunamadı"):
            self.risk.show(self.same_name.id)

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_json_and_terminal_are_read_only_and_explain_limits(self):
        self.apply_sources()
        self.accept_dependency()
        before = self.path.read_bytes()
        code, stdout, stderr = self.invoke("suppliers", "risk-list")
        self.assertEqual((code, stderr), (0, ""))
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["priority_review_count"], 1)

        code, stdout, stderr = self.invoke(
            "suppliers", "risk-show", self.primary.id, as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("sayısal risk skoru değildir", stdout)
        self.assertIn("Eksik veya sınırlı veri", stdout)
        self.assertIn("İddia adayı ayrıntısı", stdout)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

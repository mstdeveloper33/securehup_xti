"""Layered, read-only classification of passive surface candidates."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_surface_inventory import SQLiteSurfaceInventoryRepository
from xti.application.surface_inventory import SurfaceInventoryService
from xti.domain.assets import ValidationError
from xti.domain.surface import SurfaceCandidateEvidence, SurfaceDiscoveryRunRequest


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc).isoformat()


def evidence(domain: str, number: int) -> SurfaceCandidateEvidence:
    return SurfaceCandidateEvidence(
        domain=domain,
        provider="crt.sh",
        source_name=f"https://crt.sh/?id={number}",
        source_sha256=hashlib.sha256(f"certificate-{number}".encode()).hexdigest(),
        raw_domain=domain,
        observed_at=NOW,
    )


class SurfaceInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.root, _ = self.assets.add("example.com")
        self.candidates = SQLiteSurfaceCandidateRepository(self.path)
        items = (
            evidence("api.example.com", 1),
            evidence("cdn.example.com", 2),
            evidence("vpn.example.com", 3),
        )
        self.candidates.record_discovery(
            self.root.id,
            self.root.value,
            items,
            SurfaceDiscoveryRunRequest(
                "complete", "https://crt.sh/?q=%25.example.com", NOW, NOW,
                3, 0, 0, (), len(items), None,
            ),
        )
        by_domain = {
            item.domain: item
            for item in self.candidates.list_candidates(
                self.root.id, status=None, limit=100,
            )
        }
        self.candidates.decide_candidate(
            by_domain["api.example.com"].id, "owned", "Kurumsal API adresim", NOW,
        )
        self.candidates.decide_candidate(
            by_domain["vpn.example.com"].id, "rejected", "Bize ait değil", NOW,
        )
        self.api, _ = self.assets.add("api.example.com")
        self.cdn, _ = self.assets.add("cdn.example.com")
        self.surface = SQLiteSurfaceRepository(self.path)
        self.surface.activate(
            self.cdn.id, self.cdn.value, "Yetkili CDN adresim", NOW,
        )
        self.service = SurfaceInventoryService(
            self.assets, SQLiteSurfaceInventoryRepository(self.path),
        )

    def test_layers_remain_independent_and_view_is_read_only(self):
        before = self.path.read_bytes()
        report = self.service.show("EXAMPLE.COM")

        self.assertEqual(report.root_scope_status, "not_approved")
        self.assertEqual(
            (
                report.candidate_counts.total,
                report.candidate_counts.pending,
                report.candidate_counts.owned,
                report.candidate_counts.rejected,
            ),
            (3, 1, 1, 1),
        )
        self.assertEqual((report.registered_count, report.active_scope_count), (2, 1))
        items = {item.domain: item for item in report.items}

        self.assertEqual(
            (
                items["api.example.com"].candidate_status,
                items["api.example.com"].registration_status,
                items["api.example.com"].scope_status,
                items["api.example.com"].next_step,
            ),
            ("owned", "registered", "not_approved", "approve_scope"),
        )
        self.assertEqual(
            (
                items["cdn.example.com"].candidate_status,
                items["cdn.example.com"].registration_status,
                items["cdn.example.com"].scope_status,
                items["cdn.example.com"].active_check_authorized,
                items["cdn.example.com"].next_step,
            ),
            ("pending", "registered", "active", True, "review_candidate"),
        )
        self.assertEqual(
            (
                items["vpn.example.com"].candidate_status,
                items["vpn.example.com"].registration_status,
                items["vpn.example.com"].scope_status,
                items["vpn.example.com"].next_step,
            ),
            ("rejected", "unregistered", "not_applicable", "none"),
        )
        self.assertEqual(self.path.read_bytes(), before)

    def test_owned_filter_and_limit_keep_global_layer_counts(self):
        report = self.service.show("example.com", status="owned", limit=1)
        self.assertEqual((report.matching_count, report.displayed_count), (1, 1))
        self.assertFalse(report.has_more)
        self.assertEqual(report.items[0].domain, "api.example.com")
        self.assertEqual(report.candidate_counts.total, 3)
        self.assertEqual((report.registered_count, report.active_scope_count), (2, 1))

    def test_approved_owned_candidate_becomes_monitorable_only_after_explicit_scope(self):
        self.surface.activate(
            self.api.id, self.api.value, "Yetkili API adresim", NOW,
        )
        report = self.service.show("example.com", status="owned")
        self.assertEqual(report.active_scope_count, 2)
        self.assertTrue(report.items[0].active_check_authorized)
        self.assertEqual(report.items[0].next_step, "monitor")

    def test_invalid_input_and_unknown_root_do_not_mutate_storage(self):
        before = self.path.read_bytes()
        for status, limit in (("invalid", 100), ("all", 0), ("all", True)):
            with self.subTest(status=status, limit=limit):
                with self.assertRaises(ValidationError):
                    self.service.show("example.com", status=status, limit=limit)
        with self.assertRaisesRegex(ValidationError, "kayıtlı değil"):
            self.service.show("unknown.example")
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

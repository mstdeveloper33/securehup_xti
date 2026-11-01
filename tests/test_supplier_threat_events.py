"""Offline source-bound claim candidates for human-approved suppliers."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.supplier_threat_events import SupplierThreatEventService
from xti.application.suppliers import SupplierService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from tests.test_ransomlook_ransomware import content as ransomlook_content, post
from tests.test_threatcluster_ransomware import claim, content as threatcluster_content


NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)


class SupplierThreatEventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.supplier_repository = SQLiteSupplierRepository(self.path)
        self.suppliers = SupplierService(
            self.supplier_repository, clock=lambda: NOW,
        )
        self.primary = self.suppliers.add(
            "Example Holding", domain="example.com", relationship_type="cloud",
            criticality="critical", reason="Kritik bulut hizmeti ilişkisi doğrulandı.",
        ).supplier
        self.same_name = self.suppliers.add(
            "Example Holding", domain="other.example", relationship_type="software",
            criticality="medium", reason="Aynı adlı ayrı yazılım sağlayıcısıdır.",
        ).supplier
        self.threatcluster = SQLiteRansomwareClaimRepository(self.path)
        self.ransomlook = SQLiteRansomLookClaimRepository(self.path)
        self.service = SupplierThreatEventService(
            self.supplier_repository, self.threatcluster, self.ransomlook,
        )

    def apply_sources(self):
        threat_feed = parse_threatcluster_ransomware_response(
            threatcluster_content([
                claim(
                    "Example Holding", website="www.example.com",
                    discovered="2026-10-30T12:00:00+00:00",
                ),
                claim(
                    "Unrelated Company", group="other-group", website="unrelated.example",
                    discovered="2026-10-30T11:00:00+00:00",
                ),
            ]),
            fetched_at=NOW - timedelta(hours=3),
        )
        threat_run = self.threatcluster.apply(
            threat_feed,
            started_at=(NOW - timedelta(hours=2)).isoformat(),
            finished_at=(NOW - timedelta(hours=2) + timedelta(seconds=1)).isoformat(),
            item_limit=100,
        ).run
        ransomlook_feed = parse_ransomlook_ransomware_response(
            ransomlook_content([
                post(
                    "Example Holding", group="example-group",
                    discovered="2026-10-30T18:00:00Z",
                ),
            ]),
            fetched_at=NOW,
        )
        ransomlook_run = self.ransomlook.apply(
            ransomlook_feed,
            started_at=(NOW + timedelta(minutes=1)).isoformat(),
            finished_at=(NOW + timedelta(minutes=1, seconds=1)).isoformat(),
            item_limit=100,
        ).run
        return threat_run, ransomlook_run

    def test_two_sources_stay_separate_and_match_evidence_is_explicit(self):
        threat_run, ransomlook_run = self.apply_sources()
        before = self.path.read_bytes()
        report = self.service.list()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(report.active_supplier_count, 2)
        self.assertEqual(report.total_event_count, 4)
        self.assertEqual(
            {item.source_key for item in report.events},
            {"threatcluster", "ransomlook"},
        )
        self.assertEqual(
            {item.snapshot_run_id for item in report.coverage},
            {threat_run.id, ransomlook_run.id},
        )
        primary_threat = next(
            item for item in report.events
            if item.supplier_id == self.primary.id and item.source_key == "threatcluster"
        )
        self.assertEqual(
            [(item.field, item.match_type) for item in primary_threat.match_evidence],
            [("website", "subdomain"), ("victim", "exact")],
        )
        self.assertEqual(primary_threat.same_name_supplier_count, 2)
        other_threat = next(
            item for item in report.events
            if item.supplier_id == self.same_name.id and item.source_key == "threatcluster"
        )
        self.assertEqual(
            [(item.field, item.match_type) for item in other_threat.match_evidence],
            [("victim", "exact")],
        )

        details = self.service.show(primary_threat.id)
        self.assertEqual(details.event.claim_id, primary_threat.claim_id)
        self.assertEqual(details.coverage.source_key, "threatcluster")
        self.assertEqual(self.path.read_bytes(), before)

    def test_supplier_and_source_filters_are_bounded_and_stable(self):
        self.apply_sources()
        first = self.service.list(
            supplier_id=self.primary.id, source="threatcluster", limit=1,
        )
        second = self.service.list(
            supplier_id=self.primary.id, source="threatcluster", limit=1,
        )
        self.assertEqual(first, second)
        self.assertEqual(first.total_event_count, 1)
        self.assertEqual(first.events[0].supplier_id, self.primary.id)
        self.assertEqual([item.source_key for item in first.coverage], ["threatcluster"])
        with self.assertRaisesRegex(ValidationError, "kaynağı"):
            self.service.list(source="unknown")
        with self.assertRaisesRegex(ValidationError, "1–500"):
            self.service.list(limit=0)
        with self.assertRaisesRegex(ValidationError, "olay kimliği"):
            self.service.show("not-an-id")

    def test_missing_and_failed_source_coverage_are_not_empty_success(self):
        empty = self.service.list(source="ransomlook")
        self.assertEqual(empty.events, ())
        self.assertEqual(empty.coverage[0].state, "not_collected")

        self.apply_sources()
        self.threatcluster.record_failure(
            started_at=(NOW + timedelta(minutes=2)).isoformat(),
            finished_at=(NOW + timedelta(minutes=2, seconds=1)).isoformat(),
            error="Kaynak geçici olarak yanıt vermedi.",
        )
        stale = self.service.list(source="threatcluster")
        self.assertEqual(stale.coverage[0].state, "stale_after_failure")
        self.assertEqual(stale.coverage[0].latest_attempt_status, "failed")
        self.assertGreater(stale.total_event_count, 0)

    def test_inactive_supplier_is_excluded_and_corrupt_source_fails_closed(self):
        self.apply_sources()
        self.suppliers.revoke(
            self.same_name.id, reason="Bu tedarikçi ilişkisi artık kullanılmıyor.",
        )
        report = self.service.list()
        self.assertEqual(report.active_supplier_count, 1)
        self.assertTrue(all(item.supplier_id == self.primary.id for item in report.events))
        with self.assertRaisesRegex(ValidationError, "Etkin tedarikçi"):
            self.service.list(supplier_id=self.same_name.id)

        import sqlite3
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ransomware_claim_run_items SET state_sha256=?",
                ("0" * 64,),
            )
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.service.list(source="threatcluster")
        self.assertEqual(self.path.read_bytes(), before)

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_terminal_and_json_are_offline_and_read_only(self):
        self.apply_sources()
        before = self.path.read_bytes()
        with (
            patch(
                "xti.interfaces.cli.ThreatClusterRansomwareSource.fetch",
                side_effect=AssertionError("event-list must stay offline"),
            ),
            patch(
                "xti.interfaces.cli.RansomLookRansomwareSource.fetch",
                side_effect=AssertionError("event-list must stay offline"),
            ),
        ):
            code, stdout, stderr = self.invoke("suppliers", "event-list")
        self.assertEqual((code, stderr), (0, ""))
        payload = json.loads(stdout)
        self.assertEqual(payload["data"]["total_event_count"], 4)
        event_id = payload["data"]["events"][0]["id"]

        code, stdout, stderr = self.invoke(
            "suppliers", "event-show", event_id, as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("doğrulanmış ihlal değildir", stdout)
        self.assertIn("Eşleşme dayanakları", stdout)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

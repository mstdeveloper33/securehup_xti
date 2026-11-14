"""Historical relations remain bounded, auditable and read-only across all pages."""

from argparse import ArgumentParser
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_asset_relations import SQLiteAssetRelationsRepository
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.sqlite_supplier_candidates import SQLiteSupplierCandidateRepository, SQLiteSupplierDependencySource
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.asset_relations import AssetRelationsService
from xti.application.supplier_candidates import SupplierCandidateService
from xti.application.suppliers import SupplierService
from xti.domain.assets import ValidationError
from xti.domain.cname import CNAME_POLICY_VERSION, CnameDnsResult, CnameHop
from xti.domain.enrichment import CertificateEvidence, ProbeResult
from xti.interfaces.asset_relations import register_asset_relations_parser, execute_asset_relations_command


NOW = datetime(2026, 10, 31, 15, tzinfo=timezone.utc)
DOMAIN = "api.example.com"


def probe(*, offset=0, ip="93.184.216.34", certificate=None):
    at = NOW + timedelta(seconds=offset)
    return ProbeResult(DOMAIN, at.isoformat(), (at + timedelta(seconds=1)).isoformat(),
                       "surface-test-v1", "resolved", (ip,), "valid", "responded", 200,
                       ip, (), (), certificate)


def cert(fingerprint="a" * 64):
    return CertificateEvidence(fingerprint, "01a2", "2026-10-01T00:00:00+00:00",
                               "2026-12-31T23:59:59+00:00", "Fixture CA", DOMAIN,
                               ("*.example.com", DOMAIN, "unrelated.example"))


def cname(*, target="edge.vendor.example", offset=0):
    at = NOW + timedelta(seconds=offset)
    return CnameDnsResult(DOMAIN, at.isoformat(), (at + timedelta(seconds=1)).isoformat(),
                         CNAME_POLICY_VERSION, "present", (CnameHop(DOMAIN, target),),
                         target, "resolved", ("93.184.216.34",), (), ())


class AssetRelationsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _ = self.storage.add(DOMAIN)
        self.at = NOW
        self.web = SQLiteSurfaceRepository(self.path, clock=lambda: self.at)
        self.web.activate(self.asset.id, DOMAIN, "Kendi alan adım", NOW.isoformat())
        self.cnames = SQLiteSurfaceCnameRepository(self.path, clock=lambda: self.at)
        self.repository = SQLiteAssetRelationsRepository(self.path)
        self.service = AssetRelationsService(self.repository)

    def sql(self, statement, arguments=()):
        with closing(sqlite3.connect(self.path)) as connection:
            result = connection.execute(statement, arguments).fetchall()
            connection.commit()
        return result

    def setup_supplier(self):
        self.cnames.append_check(self.asset.id, cname())
        candidates = SupplierCandidateService(
            SQLiteSupplierDependencySource(self.path), SQLiteSupplierCandidateRepository(self.path),
            PublicSuffixResolver(), clock=lambda: self.at)
        candidates.refresh()
        candidate = candidates.list()[0]
        suppliers = SupplierService(SQLiteSupplierRepository(self.path), clock=lambda: self.at)
        supplier = suppliers.add("Örnek Sağlayıcı", domain="vendor.example", relationship_type="cloud",
                                 criticality="high", reason="Kullandığım hizmet").supplier
        return candidates, candidate, suppliers, supplier

    def test_full_history_beyond_100_is_paginated_without_mutation(self):
        checks = []
        for index in range(121):
            self.at = NOW + timedelta(minutes=index)
            checks.append(self.web.append_check(self.asset.id, probe(offset=index, ip=f"93.184.216.{index + 1}")))
        before = self.path.read_bytes()
        report = self.service.show(DOMAIN, kind="dns", history=True, limit=50)
        self.assertEqual((report.total_count, len(report.items), report.has_more), (121, 50, True))
        items = list(report.items)
        for offset in (50, 100):
            items.extend(self.service.show(DOMAIN, kind="dns", history=True, offset=offset).items)
        self.assertEqual({item.evidence_id for item in items}, {check.id for check in checks})
        self.assertEqual(items[-1].observed_at, checks[0].result.finished_at)
        self.assertEqual(items[-1].recorded_at, checks[0].recorded_at)
        self.assertEqual(items[-1].state_sha256, checks[0].state_sha256)
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_and_empty_checks_do_not_erase_positive_edges(self):
        first = self.web.append_check(self.asset.id, probe(certificate=cert()))
        self.at += timedelta(minutes=1)
        failed = replace(probe(offset=10), dns_status="failed", addresses=(), tls_status="not_checked",
                         http_status="not_checked", http_status_code=None, connected_address=None,
                         errors=("DNS timeout",))
        failed_check = self.web.append_check(self.asset.id, failed)
        report = self.service.show(DOMAIN)
        self.assertEqual(report.total_relationship_count, 2)
        self.assertEqual({item.latest_evidence_id for item in report.items}, {first.id})
        self.assertEqual(report.coverage[0].latest_status, "failed")
        self.assertEqual(report.coverage[0].latest_evidence_id, failed_check.id)
        history = self.service.show(DOMAIN, history=True)
        failure = [item for item in history.items if item.kind == "dns" and item.target is None][0]
        self.assertEqual(failure.status, "failed")
        self.assertIn("DNS timeout", failure.details)
        self.assertTrue(any("kesintisiz" in note for note in history.notes))
        self.at += timedelta(minutes=1)
        self.web.append_check(self.asset.id, replace(failed, dns_status="no_address", errors=()))
        self.assertEqual(self.service.show(DOMAIN, kind="dns").total_count, 1)
        self.assertEqual(self.service.show(DOMAIN, kind="dns", history=True).items[0].status, "no_address")

    def test_certificate_identity_is_sha256_not_san_ownership(self):
        first = self.web.append_check(self.asset.id, probe(certificate=cert()))
        self.at += timedelta(minutes=1)
        self.web.append_check(self.asset.id, probe(offset=10, certificate=cert("b" * 64)))
        summary = self.service.show(DOMAIN, kind="certificate")
        self.assertEqual({item.target for item in summary.items}, {"a" * 64, "b" * 64})
        self.assertEqual({item.target_type for item in summary.items}, {"certificate_sha256"})
        self.assertEqual({item.subject for item in summary.items}, {DOMAIN})
        history = self.service.show(DOMAIN, kind="certificate", history=True)
        self.assertIn("unrelated.example", " ".join(history.items[-1].details))
        self.assertEqual(history.items[-1].evidence_id, first.id)
        self.assertEqual(self.storage.list(), [self.asset])
        self.at += timedelta(minutes=1)
        self.web.append_check(self.asset.id, replace(probe(), tls_status="failed", http_status="not_checked",
                                                    http_status_code=None, errors=("TLS timeout",)))
        report = self.service.show(DOMAIN, kind="certificate", history=True)
        self.assertEqual((report.items[0].status, report.coverage[0].latest_status), ("failed", "failed"))

    def test_cname_hops_target_ips_and_missing_target_are_distinct(self):
        evidence = replace(cname(), chain=(CnameHop(DOMAIN, "alias.vendor.example"),
                           CnameHop("alias.vendor.example", "edge.vendor.example")))
        check = self.cnames.append_check(self.asset.id, evidence)
        self.at += timedelta(minutes=1)
        missing = replace(cname(offset=10), target_status="failed", addresses=(), errors=("Timeout",))
        self.cnames.append_check(self.asset.id, missing)
        report = self.service.show(DOMAIN, kind="cname", history=True)
        self.assertEqual({item.relation for item in report.items},
                         {"cname_alias", "cname_target_address", "cname_target_observation"})
        self.assertTrue(any(item.subject == "alias.vendor.example" and item.target == "edge.vendor.example"
                            and item.evidence_id == check.id for item in report.items))
        self.assertTrue(any(item.status == "failed" and item.target is None for item in report.items))
        self.assertEqual(self.service.show(DOMAIN, kind="cname").total_count, 4)

    def test_human_supplier_acceptance_and_withdrawal_keep_exact_decisions(self):
        candidates, candidate, _, supplier = self.setup_supplier()
        self.assertEqual(self.service.show(DOMAIN, kind="supplier").total_count, 0)
        self.at += timedelta(minutes=1)
        candidates.review(candidate.id, decision="accepted", supplier_id=supplier.id, reason="Sözleşme doğrulandı")
        accepted = candidates.show(candidate.id).resolutions[-1]
        self.at += timedelta(minutes=1)
        candidates.review(candidate.id, decision="uncertain", supplier_id=None, reason="Bağlantı yeniden inceleniyor")
        withdrawn = candidates.show(candidate.id).resolutions[-1]
        report = self.service.show(DOMAIN, kind="supplier")
        item = report.items[0]
        self.assertEqual((item.target, item.observation_count, item.latest_event_status), (supplier.id, 1, "withdrawn"))
        self.assertEqual((item.first_observed_at, item.last_observed_at), (accepted.recorded_at, accepted.recorded_at))
        self.assertEqual(item.latest_evidence_id, withdrawn.id)
        history = self.service.show(DOMAIN, kind="supplier", history=True)
        self.assertEqual({item.evidence_id for item in history.items}, {accepted.id, withdrawn.id})
        self.assertTrue(all(item.source == "supplier-resolution" and item.candidate_id == candidate.id for item in history.items))
        self.assertIn("vendor.example", " ".join(history.items[0].details))
        self.assertTrue(any("dondurmaz" in note for note in history.notes))

    def test_old_corrupt_evidence_fails_even_outside_page_and_kind(self):
        check = self.web.append_check(self.asset.id, probe())
        self.web.append_check(self.asset.id, probe(offset=2))
        self.sql("UPDATE surface_checks SET state_sha256=? WHERE id=?", ("f" * 64, check.id))
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.service.show(DOMAIN, kind="supplier", offset=100, limit=1)
        self.assertEqual(self.path.read_bytes(), before)

    def test_recording_clock_rollback_does_not_hide_latest_failed_check(self):
        self.at += timedelta(hours=2)
        first = self.web.append_check(self.asset.id, probe(offset=20))
        self.at = NOW
        failed = replace(probe(offset=30), dns_status="failed", addresses=(), tls_status="not_checked",
                         http_status="not_checked", http_status_code=None, connected_address=None,
                         errors=("DNS timeout",))
        last = self.web.append_check(self.asset.id, failed)
        report = self.service.show(DOMAIN, kind="dns", history=True)
        self.assertEqual(report.items[0].evidence_id, first.id)
        self.assertEqual((report.coverage[0].latest_status, report.coverage[0].latest_evidence_id),
                         ("failed", last.id))
        self.assertEqual(self.service.show(DOMAIN, kind="dns").items[0].last_observed_at,
                         first.result.finished_at)

    def test_withdrawn_supplier_still_requires_intact_historical_identity(self):
        candidates, candidate, _, supplier = self.setup_supplier()
        candidates.review(candidate.id, decision="accepted", supplier_id=supplier.id, reason="Kurum doğruladı")
        candidates.review(candidate.id, decision="uncertain", supplier_id=None, reason="Yeniden inceleniyor")
        self.sql("DELETE FROM supplier_events WHERE supplier_id=?", (supplier.id,))
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.service.show(DOMAIN, kind="dns", offset=500)
        self.assertEqual(self.path.read_bytes(), before)

    def test_supplier_identity_replays_every_historical_lifecycle_transition(self):
        candidates, candidate, suppliers, supplier = self.setup_supplier()
        candidates.review(candidate.id, decision="accepted", supplier_id=supplier.id, reason="Kurum doğruladı")
        suppliers.update(supplier.id, criticality="critical", reason="Öncelik güncellendi")
        self.sql("UPDATE supplier_events SET action='reactivated' WHERE action='updated'")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "yaşam döngüsü"):
            self.service.show(DOMAIN, kind="supplier")
        self.assertEqual(self.path.read_bytes(), before)

    def test_supplier_source_and_asset_corruption_are_rejected(self):
        candidates, candidate, _, supplier = self.setup_supplier()
        candidates.review(candidate.id, decision="accepted", supplier_id=supplier.id, reason="Kurum tarafından doğrulandı")
        self.sql("UPDATE supplier_candidate_evidence SET state_sha256=?", ("f" * 64,))
        with self.assertRaises(StorageError):
            self.service.show(DOMAIN, kind="dns")

    def test_bounds_reject_instead_of_truncating_and_missing_domain_does_not_create(self):
        self.web.append_check(self.asset.id, probe())
        before = self.path.read_bytes()
        with patch("xti.adapters.sqlite_asset_relations._MAX_HISTORY_ROWS", 0):
            with self.assertRaisesRegex(StorageError, "eksik sonuç üretilmedi"):
                self.service.show(DOMAIN)
        with patch("xti.adapters.sqlite_asset_relations._MAX_PAYLOAD_BYTES", 1):
            with self.assertRaises(StorageError):
                self.service.show(DOMAIN)
        with patch("xti.domain.asset_relations.MAX_RELATION_OBSERVATIONS", 1):
            with self.assertRaises(ValidationError):
                self.service.show(DOMAIN)
        with self.assertRaisesRegex(ValidationError, "kayıtlı değil"):
            self.service.show("unknown.example")
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_domain_has_explicit_never_checked_coverage(self):
        other = self.storage.add("empty.example")[0]
        report = self.service.show(other.value, history=True)
        self.assertEqual((report.items, report.scope_active), ((), None))
        self.assertEqual([item.latest_status for item in report.coverage], ["never", "never", "never", "no_decision"])

    def test_one_snapshot_survives_concurrent_writer(self):
        self.sql("PRAGMA journal_mode=WAL")
        first = self.web.append_check(self.asset.id, probe())
        original = SQLiteSurfaceRepository._check
        inserted = []

        def decode(row, domain):
            result = original(row, domain)
            if not inserted:
                inserted.append(True)
                self.cnames.append_check(self.asset.id, cname())
            return result

        with patch.object(SQLiteSurfaceRepository, "_check", side_effect=decode):
            report = self.service.show(DOMAIN)
        self.assertEqual(report.total_relationship_count, 1)
        self.assertEqual(report.items[0].latest_evidence_id, first.id)
        self.assertEqual(report.coverage[2].check_count, 0)
        self.assertEqual(self.service.show(DOMAIN).coverage[2].check_count, 1)

    def test_terminal_and_json_include_evidence_and_escape_external_controls(self):
        evidence = replace(probe(certificate=cert()), errors=("bad\x1b[31m\nsource",))
        check = self.web.append_check(self.asset.id, evidence)
        parser = ArgumentParser()
        register_asset_relations_parser(parser.add_subparsers(dest="surface_action", required=True))
        args = parser.parse_args(["relations", DOMAIN, "--history", "--kind", "dns"])
        data, lines = execute_asset_relations_command(self.service, args)
        text = "\n".join(lines)
        self.assertNotIn("\x1b", text)
        self.assertIn("bad\\u001b[31m\\u000asource", text)
        self.assertIn(check.id, text)
        decoded = json.loads(json.dumps(data, ensure_ascii=True))
        self.assertEqual(decoded["items"][0]["evidence_id"], check.id)
        self.assertEqual(decoded["items"][0]["state_sha256"], check.state_sha256)
        for kwargs in ({"limit": 0}, {"offset": -1}, {"kind": "unknown"}, {"history": 1}):
            with self.assertRaises(ValidationError):
                self.service.show(DOMAIN, **kwargs)

    def test_cli_wires_local_read_only_history_and_reports_missing_asset(self):
        from xti.interfaces.cli import main
        check = self.web.append_check(self.asset.id, probe())
        before = self.path.read_bytes()
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors), patch(
            "socket.socket.connect", side_effect=AssertionError("No network"),
        ):
            status = main(["--data-dir", str(self.path.parent), "--json", "surface", "relations",
                           DOMAIN, "--kind", "dns", "--history", "--limit", "1"])
        self.assertEqual((status, errors.getvalue()), (0, ""))
        data = json.loads(output.getvalue())
        self.assertTrue(data["ok"])
        self.assertEqual(data["data"]["items"][0]["evidence_id"], check.id)
        self.assertEqual(self.path.read_bytes(), before)
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(["--data-dir", str(self.path.parent), "--json", "surface", "relations", "missing.example"])
        self.assertNotEqual(status, 0)
        self.assertFalse(json.loads(errors.getvalue())["ok"])
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

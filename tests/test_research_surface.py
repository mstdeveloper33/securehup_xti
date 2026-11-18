"""Stored CNAME/certificate paths, provenance, bounds and frozen review safety."""

from contextlib import closing
from copy import deepcopy
from datetime import timedelta
import json
import shlex
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import provision_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.sqlite_research import SQLiteResearchRepository, _Reader
from xti.adapters.sqlite_research_history import SQLiteResearchHistoryRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.research import ResearchService, priority_data
from xti.application.research_history import ResearchHistoryService
from xti.domain.cname import CnameDnsResult, CnameHop
from xti.domain.enrichment import CertificateEvidence, ProbeResult
from xti.domain.research import ResearchSnapshotChanged
from xti.domain.research_history import freeze
from xti.interfaces.research import research_lines, priority_lines
from tests.test_research import ResearchFixture, NOW, IP


FINGERPRINT = "a" * 64


class SurfaceResearchTests(ResearchFixture, unittest.TestCase):
    def scope(self, domain, path=None):
        path = path or self.path
        asset, _ = SQLiteAssetRepository(path).add(domain)
        surface = SQLiteSurfaceRepository(path, clock=lambda: self.at)
        surface.activate(asset.id, domain, "Controlled saved evidence", self.at.isoformat())
        return asset, surface

    def cname(self, domain="example.com", targets=("edge.example.net",), *,
              alias="present", target_status="resolved", ip=IP, path=None, error="Timeout"):
        path = path or self.path
        asset, _ = self.scope(domain, path)
        if alias != "present":
            targets, target_status = (), "not_applicable"
        chain = tuple(CnameHop(owner, target) for owner, target in zip((domain, *targets), targets))
        result = CnameDnsResult(domain, self.at.isoformat(), self.at.isoformat(), "google-doh-cname-v1",
            alias, chain, targets[-1] if targets else None, target_status,
            (ip,) if target_status == "resolved" else (),
            (error,) if alias == "failed" or target_status == "failed" else (), ())
        return SQLiteSurfaceCnameRepository(path, clock=lambda: self.at).append_check(asset.id, result)

    def tls(self, domain="example.com", fingerprint=FINGERPRINT, *, ip=IP, failed=False,
            names=("*.example.com", "example.com", "san-only.example"),
            issuer="Fixture CA", expires=None, starts=None, path=None):
        asset, surface = self.scope(domain, path)
        certificate = None if failed else CertificateEvidence(fingerprint, "01a2",
            (starts or NOW - timedelta(days=10)).isoformat(),
            (expires or NOW + timedelta(days=10)).isoformat(), issuer, "example.com", tuple(sorted(names)))
        result = ProbeResult(domain, self.at.isoformat(), self.at.isoformat(), "surface-fixture-v1",
            "resolved", (ip,), "failed" if failed else "valid", "not_checked", None,
            None if failed else ip, ("TLS timeout",) if failed else (), (), certificate)
        return surface.append_check(asset.id, result)

    def priorities(self, **parameters):
        return priority_data(self.service.priorities(indicator_type="domain", value="example.com", **parameters))

    def bindings(self, graph):
        nodes = {row["id"]: row for row in graph["nodes"]}
        return {(nodes[row["source_id"]]["value"], nodes[row["target_id"]]["value"], row["relationship_type"])
                for row in graph["edges"]}

    def history(self):
        return ResearchHistoryService(SQLiteResearchHistoryRepository(self.path), self.service)

    def sql(self, statement, parameters=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute(statement, parameters).fetchall()

    def test_cname_hops_are_directed_and_only_final_target_has_address(self):
        check = self.cname(targets=("edge.example.net", "origin.example.net"))
        before = self.files()
        graph = self.graph()
        self.assertEqual(self.bindings(graph), {
            ("example.com", "edge.example.net", "cname_alias"),
            ("edge.example.net", "origin.example.net", "cname_alias")})
        self.assertEqual({row["hops"] for row in graph["paths"]}, {1, 2})
        inverse = self.graph("origin.example.net")
        self.assertIn(("origin.example.net", IP, "cname_target_address"), self.bindings(inverse))
        self.assertNotIn(("edge.example.net", IP, "cname_target_address"), self.bindings(inverse))
        self.assertTrue(all(row["evidence"][0]["record_id"] == check.id for row in graph["edges"]))
        self.assertEqual(before, self.files())

    def test_unregistered_target_and_ip_can_find_incoming_cname(self):
        self.cname(ip="2606:4700:4700::1111")
        for value, kind in (("edge.example.net", "domain"), ("2606:4700:4700::1111", "ip")):
            with self.subTest(value=value):
                graph = self.graph(value, kind)
                self.assertIn(("example.com", "edge.example.net", "cname_alias"), self.bindings(graph))
                self.assertEqual(next(row for row in graph["nodes"] if row["value"] == "edge.example.net")["references"], [])

    def test_absent_failed_and_nxdomain_checks_do_not_invent_relationships(self):
        for status in ("absent", "nxdomain", "failed"):
            with self.subTest(status=status):
                check = self.cname(alias=status)
                graph = self.graph()
                self.assertEqual(graph["edges"], [])
                self.assertEqual(graph["nodes"][0]["evidence"][0]["status"], status)
                self.assertEqual(graph["nodes"][0]["evidence"][0]["record_id"], check.id)

    def test_partial_cname_keeps_hop_but_not_ip_and_priority_explains_failure(self):
        self.cname(target_status="failed")
        self.assertEqual(self.bindings(self.graph()), {("example.com", "edge.example.net", "cname_alias")})
        item = next(row for row in self.priorities()["items"] if row["value"] == "example.com")
        self.assertIn("latest_cname_check_failed", {row["code"] for row in item["reasons"]})

    def test_cname_repeats_merge_without_losing_history_or_later_failure(self):
        first = self.cname()
        self.at += timedelta(hours=1)
        repeat = self.cname()
        self.at += timedelta(hours=1)
        changed = self.cname(targets=("new.example.net",))
        failed = self.cname(alias="failed")
        graph = self.graph()
        old = next(row for row in graph["edges"] if row["relationship_type"] == "cname_alias"
                   and {e["record_id"] for e in row["evidence"]} == {first.id, repeat.id})
        self.assertEqual(old["evidence_total_count"], 2)
        self.assertTrue(any(changed.id == row["evidence"][0]["record_id"] for row in graph["edges"]))
        root = next(row for row in graph["nodes"] if row["id"] == graph["root_id"])
        self.assertEqual(root["evidence"][0]["record_id"], failed.id)

    def test_shared_observed_certificate_links_hosts_without_san_or_ownership_inference(self):
        first = self.tls()
        other = self.tls("other.example", ip="1.1.1.1")
        before = self.files()
        graph = self.graph()
        nodes = {row["id"]: row for row in graph["nodes"]}
        self.assertTrue(any([nodes[key]["value"] for key in row["node_ids"]] ==
            ["example.com", FINGERPRINT, "other.example"] for row in graph["paths"]))
        certificate = next(row for row in nodes.values() if row["kind"] == "certificate")
        self.assertEqual(certificate["record_type"], "tls_certificate")
        self.assertEqual(certificate["references"], [])
        self.assertEqual({row["record_id"] for row in certificate["evidence"]}, {first.id, other.id})
        self.assertTrue(all(row["current"] is None and row["status"] == "presented" for row in certificate["evidence"]))
        self.assertNotIn("san-only.example", {row["value"] for row in nodes.values()})
        self.assertNotIn("*.example.com", {row["value"] for row in nodes.values()})
        self.assertEqual(before, self.files())

    def test_same_issuer_and_san_with_different_fingerprint_do_not_link_hosts(self):
        self.tls()
        self.tls("other.example", "b" * 64, ip="1.1.1.1")
        values = {row["value"] for row in self.graph()["nodes"]}
        self.assertNotIn("other.example", values)
        self.assertNotIn("b" * 64, values)

    def test_certificate_is_not_file_hash_ioc_or_circl_query(self):
        self.tls()
        ioc = self.ioc(FINGERPRINT, "sha256")
        graph = self.graph()
        node = next(row for row in graph["nodes"] if row["kind"] == "certificate")
        self.assertEqual(node["references"], [])
        self.assertIsNone(node["enrichment"])
        self.assertEqual(node["warninglist_matches"], [])
        self.assertFalse(any(row["record_type"] == "cti_indicator" for row in node["evidence"]))
        file_graph = self.graph(FINGERPRINT, "sha256")
        self.assertEqual(len(file_graph["nodes"]), 1)
        self.assertEqual(file_graph["nodes"][0]["references"][0]["record_id"], ioc.indicator.id)

    def test_certificate_rotation_and_latest_tls_failure_preserve_original_checks(self):
        first = self.tls()
        second = self.tls(fingerprint="b" * 64)
        failed = self.tls(failed=True)
        graph = self.graph()
        edges = [row for row in graph["edges"] if row["relationship_type"] == "certificate_presented"]
        self.assertEqual({row["evidence"][0]["record_id"] for row in edges}, {first.id, second.id})
        root = next(row for row in self.priorities()["items"] if row["value"] == "example.com")
        self.assertIn("latest_tls_check_failed", {row["code"] for row in root["reasons"]})
        self.assertTrue(any(row["record_id"] == failed.id for row in root["evidence"]))

    def test_certificate_expiry_is_a_time_change_not_new_threat_or_withdrawal(self):
        self.tls(expires=NOW + timedelta(hours=1))
        history = self.history()
        first = history.record(indicator_type="domain", value="example.com")
        original = history.show(first["review"]["id"], view="items")
        self.at += timedelta(hours=2)
        second = history.record(indicator_type="domain", value="example.com")
        result = history.show(second["review"]["id"])
        self.assertTrue(result["changes"])
        self.assertEqual({row["origin"] for row in result["changes"]}, {"time_only"})
        self.assertTrue(any("certificate_expired" in row["after"]["reason_codes"] for row in result["changes"]))
        self.assertTrue(all(row["withdrawn_assertion_ids"] == [] for row in result["changes"]))
        self.assertEqual(history.show(first["review"]["id"], view="items"), original)

    def test_future_certificate_validity_has_linked_reason(self):
        self.tls(starts=NOW + timedelta(hours=1))
        item = next(row for row in self.priorities()["items"] if row["record_type"] == "tls_certificate")
        reason = next(row for row in item["reasons"] if row["code"] == "certificate_not_yet_valid")
        self.assertEqual(set(reason["evidence_ids"]), {row["id"] for row in item["evidence"]})

    def test_cname_and_web_state_integrity_and_scope_checks_fail_closed(self):
        self.cname()
        self.tls()
        for table in ("surface_cname_checks", "surface_checks"):
            digest = self.sql(f"SELECT state_sha256 FROM {table}")[0][0]
            self.sql(f"UPDATE {table} SET state_sha256=?", ("0" * 64,))
            with self.assertRaises(StorageError):
                self.graph()
            self.sql(f"UPDATE {table} SET state_sha256=?", (digest,))
        self.sql("DELETE FROM surface_scopes")
        with self.assertRaises(StorageError):
            self.graph()

    def test_cname_row_byte_and_adjacency_limits_remain_visible(self):
        self.cname()
        self.cname(targets=("second.example.net",))
        for constant, limitation in (("MAX_CNAME_CHECKS", "cname_history_window"),
                                     ("MAX_CNAME_BYTES", "cname_read_budget"),
                                     ("MAX_SURFACE_RELATIONS", "cname_adjacency_limit")):
            with self.subTest(constant=constant), patch("xti.adapters.sqlite_research_surface." + constant, 1):
                graph = self.graph()
                self.assertEqual(graph["status"], "partial")
                self.assertIn(limitation, graph["limitations"])

    def test_unreadable_new_cname_is_not_replaced_by_old_latest(self):
        self.cname()
        self.cname(alias="failed", error="Timeout " + "x" * 900)
        size = self.sql("SELECT LENGTH(CAST(result AS BLOB))+LENGTH(CAST(change AS BLOB)) "
                        "FROM surface_cname_checks ORDER BY rowid LIMIT 1")[0][0]
        with patch("xti.adapters.sqlite_research_surface.MAX_CNAME_BYTES", size):
            graph = self.graph()
        root = next(row for row in graph["nodes"] if row["id"] == graph["root_id"])
        self.assertEqual(root["evidence"], [])
        self.assertTrue(graph["edges"])
        self.assertIn("cname_read_budget", graph["limitations"])

    def test_repeated_edge_and_certificate_node_evidence_limits_keep_total(self):
        self.cname()
        self.cname()
        self.tls()
        self.tls()
        with patch("xti.adapters.sqlite_research_surface.MAX_SURFACE_EVIDENCE", 1):
            graph = self.graph()
        self.assertIn("source_evidence_limit", graph["limitations"])
        certificate = next(row for row in graph["nodes"] if row["kind"] == "certificate")
        self.assertEqual((len(certificate["evidence"]), certificate["evidence_total_count"]), (1, 2))
        edges = [row for row in graph["edges"] if row["relationship_type"] != "dns_address"]
        self.assertTrue(all((len(row["evidence"]), row["evidence_total_count"]) == (1, 2) for row in edges))

    def test_certificate_reverse_lookup_shares_web_budget_and_keeps_root_evidence(self):
        root = self.tls()
        self.tls("other.example", ip="1.1.1.1")
        with patch("xti.adapters.sqlite_research.MAX_DNS_CHECKS", 1):
            graph = self.graph()
        self.assertIn("dns_read_budget", graph["limitations"])
        self.assertNotIn("other.example", {row["value"] for row in graph["nodes"]})
        certificate = next(row for row in graph["nodes"] if row["kind"] == "certificate")
        self.assertEqual(certificate["evidence"][0]["record_id"], root.id)

    def test_shared_certificate_adjacency_limit_is_explicit(self):
        self.tls()
        self.tls("other.example", ip="1.1.1.1")
        with patch("xti.adapters.sqlite_research_surface.MAX_SURFACE_RELATIONS", 1):
            self.assertIn("certificate_adjacency_limit", self.graph()["limitations"])

    def test_snapshot_rejects_pages_after_cname_or_certificate_change(self):
        self.cname()
        old = self.graph(limit=1)
        self.tls()
        with self.assertRaises(ResearchSnapshotChanged):
            self.graph(offset=1, limit=1, expected_snapshot=old["snapshot_id"])
        old = self.graph(limit=1)
        self.cname(targets=("new.example.net",))
        with self.assertRaises(ResearchSnapshotChanged):
            self.graph(offset=1, limit=1, expected_snapshot=old["snapshot_id"])

    def test_node_with_fifty_ioc_sources_and_three_checks_can_be_frozen(self):
        self.cname()
        self.tls()
        for index in range(50):
            self.iocs.add("domain", "example.com", source_name=f"fixture-{index}",
                source_reference=f"report:{index}", confidence=50, description="Controlled claim")
        result = self.priorities()
        node = next(row for row in result["items"] if row["value"] == "example.com")
        self.assertEqual((len(node["evidence"]), node["evidence_total_count"]), (52, 53))
        self.assertEqual({row["record_type"] for row in node["evidence"][:3]},
            {"surface_check", "surface_tls_check", "surface_cname_check"})
        record = self.history().record(indicator_type="domain", value="example.com")
        self.assertTrue(record["review"]["id"])

    def test_v1_review_stays_readable_and_v2_starts_new_policy_baseline(self):
        repository = SQLiteResearchHistoryRepository(self.path)
        snapshot = freeze(priority_data(self.service.full_priorities(indicator_type="domain", value="example.com")))
        snapshot["policy_version"] = "research-priority-v1"
        from xti.domain.research_history import capture_scope
        previous, _ = repository.append(capture_scope(indicator_type="domain", value="example.com"), snapshot, "old-v1", None)
        original = deepcopy(repository.show(previous.header.id))
        self.cname()
        self.tls()
        current = self.history().record(indicator_type="domain", value="example.com")
        self.assertEqual(current["review"]["comparison"]["state"], "policy_baseline")
        self.assertEqual(repository.show(previous.header.id), original)

    def test_company_workspace_never_reads_same_fingerprint_from_other_company(self):
        root = self.root / "companies"
        first = provision_company_workspace(root, "first")
        second = provision_company_workspace(root, "second")
        from xti.interfaces.platform_jobs import initialize_jobs
        for context in (first, second):
            SQLiteAssetRepository(context.database).initialize()
            initialize_jobs(context)
        self.tls(path=first.database)
        self.cname(path=first.database)
        self.tls("secret.example", ip="1.1.1.1", path=second.database)
        self.cname("secret.example", targets=("private-vendor.example",), path=second.database)
        code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", "first"], self.request())
        self.assertEqual((code, err), (0, ""), out)
        self.assertNotIn("secret.example", out)
        self.assertNotIn("private-vendor.example", out)
        self.assertIn("certificate_presented", out)
        self.assertIn("cname_alias", out)

    def test_cli_engine_and_original_detail_commands_work_offline(self):
        self.cname()
        self.tls(issuer="Fixture [bold] CA $(touch nope)")
        before = self.files()
        code, out, err = self.invoke(["--data-dir", str(self.data), "engine"], self.request())
        self.assertEqual((code, err), (0, ""), out)
        data = json.loads(out)["data"]
        self.assertEqual(self.bindings(data), self.bindings(self.graph()))
        lines = research_lines(data, data_dir=self.data) + priority_lines(self.priorities(), data_dir=self.data)
        commands = {line.split("Ayrıntı: ", 1)[1] for line in lines if "Ayrıntı: " in line}
        self.assertTrue(any("--kind certificate" in command for command in commands))
        self.assertTrue(any("--kind cname" in command for command in commands))
        for command in sorted(commands):
            code, out, err = self.invoke(shlex.split(command)[1:])
            self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(before, self.files())

    def test_graph_uses_one_snapshot_during_concurrent_cname_and_tls_writes(self):
        self.cname()
        self.tls()
        self.sql("PRAGMA journal_mode=WAL")
        original, mutated = _Reader.neighbors, []

        def concurrent(reader, key):
            if not mutated:
                mutated.append(True)
                self.cname(targets=("new.example.net",))
                self.tls("new.example", ip="1.1.1.1")
            return original(reader, key)

        with patch.object(_Reader, "neighbors", concurrent):
            graph = self.graph()
        values = {row["value"] for row in graph["nodes"]}
        self.assertNotIn("new.example.net", values)
        self.assertNotIn("new.example", values)
        later = {row["value"] for row in self.graph()["nodes"]}
        self.assertIn("new.example.net", later)
        self.assertIn("new.example", later)

    def test_saved_review_and_surface_evidence_survive_backup(self):
        self.cname()
        self.tls()
        review = self.history().record(indicator_type="domain", value="example.com")
        original = self.history().show(review["review"]["id"], view="items")
        backup = self.root / "evidence-backup.db"
        SQLiteAssetRepository(self.path).backup(backup)
        service = ResearchService(SQLiteResearchRepository(backup), clock=lambda: self.at)
        restored = ResearchHistoryService(SQLiteResearchHistoryRepository(backup), service)
        self.assertEqual(restored.show(review["review"]["id"], view="items"), original)
        self.assertEqual(priority_data(service.priorities(indicator_type="domain", value="example.com")), self.priorities())

"""Evidence paths, historical claims, honest bounds and read-only protocol isolation."""

from contextlib import closing, contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import shlex
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import resolve_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_research import SQLiteResearchRepository, _Reader
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.cti_indicators import CtiIndicatorService
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.application.research import ResearchService, research_data
from xti.domain.assets import ValidationError
from xti.domain.enrichment import ProbeResult
from xti.domain.research import ResearchSnapshotChanged
from xti.interfaces.cli import main
from xti.interfaces.research import research_lines


NOW = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
IP = "93.184.216.34"


class ResearchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.data = self.root / "selected evidence"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.at = NOW
        self.service = ResearchService(SQLiteResearchRepository(self.path), clock=lambda: self.at)
        self.iocs = CtiIndicatorService(SQLiteCtiIndicatorRepository(self.path), clock=lambda: self.at)
        self.cti = CtiKnowledgeService(SQLiteCtiKnowledgeRepository(self.path), clock=lambda: self.at)
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Research must stay offline")))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("Research must stay offline")))
        self.enterContext(patch("subprocess.run", side_effect=AssertionError("No research subprocess")))
        self.enterContext(patch("subprocess.Popen", side_effect=AssertionError("No research subprocess")))

    def dns(self, domain="example.com", ip=IP, *, failed=False, observed=None, path=None, error="DNS timeout"):
        path = path or self.path
        asset, _ = SQLiteAssetRepository(path).add(domain)
        surface = SQLiteSurfaceRepository(path, clock=lambda: self.at)
        surface.activate(asset.id, domain, "Controlled owned fixture", self.at.isoformat())
        at = observed or self.at
        probe = ProbeResult(domain, at.isoformat(), at.isoformat(), "research-fixture-v1",
            "failed" if failed else "resolved", () if failed else (ip,),
            "not_checked", "not_checked", None, None, (), (error,) if failed else (), None)
        return surface.append_check(asset.id, probe)

    def ioc(self, value=IP, kind="ipv4", **changes):
        return self.iocs.add(kind, value, source_name="fixture", source_reference="report:ioc:" + value,
                             confidence=60, description="Fixture source assertion", **changes)

    def entity(self, name="Fixture Actor", kind="threat-actor"):
        return self.cti.add_entity(kind, name, source_name="fixture", source_reference="report:entity:" + name,
                                   confidence=55, aliases=(), description="Fixture CTI entity assertion")

    def relation(self, actor, *, indicator=None, entity=None, source="fixture", ref="report:relation"):
        return self.cti.add_relationship(actor.entity.id, "related-to",
            target_indicator_id=indicator.indicator.id if indicator else None,
            target_entity_id=entity.entity.id if entity else None,
            source_name=source, source_reference=ref, confidence=45,
            description="Source claims an explicit relationship")

    def graph(self, value="example.com", kind="domain", **options):
        return research_data(self.service.show(indicator_type=kind, value=value, **options))

    def files(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def invoke(self, arguments, request=None):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch("sys.stdin", StringIO(json.dumps(request))), \
                patch.object(SQLiteAssetRepository, "initialize", side_effect=AssertionError("Read may not initialize")):
            code = main(arguments)
        return code, out.getvalue(), err.getvalue()

    def request(self, **parameters):
        return {"contract_version": 1, "request_id": "research-1", "operation": "research.show",
                "parameters": {"indicator_type": "domain", "value": "example.com", **parameters}}

    def test_domain_ip_actor_two_hops_source_identity_and_no_mutation(self):
        check = self.dns()
        ioc, actor = self.ioc(), self.entity()
        relation = self.relation(actor, indicator=ioc)
        before = self.files()
        result = self.graph()
        self.assertEqual(result["status"], "related_records")
        self.assertEqual((result["collected_node_count"], result["collected_edge_count"], result["collected_path_count"]), (3, 2, 2))
        self.assertEqual([path["hops"] for path in result["paths"]], [1, 2])
        nodes = {node["value"]: node for node in result["nodes"]}
        self.assertEqual(nodes[IP]["references"][0]["record_id"], ioc.indicator.id)
        edge = next(item for item in result["edges"] if item["kind"] == "source_claim")
        self.assertEqual(edge["source_id"], nodes[actor.entity.id]["id"])
        self.assertEqual(edge["evidence"][0]["assertion_id"], relation.assertion.id)
        self.assertTrue(edge["evidence"][0]["event_id"])
        dns = next(item for item in result["edges"] if item["kind"] == "observation")
        self.assertEqual(dns["evidence"][0]["record_id"], check.id)
        self.assertEqual(dns["evidence"][0]["state_sha256"], check.state_sha256)
        self.assertEqual(before, self.files())

    def test_same_canonical_domain_and_indicator_have_one_node_original_refs_preserved(self):
        self.dns()
        ioc = self.ioc("example.com", "domain")
        data = self.graph("EXAMPLE.COM.")
        root = next(node for node in data["nodes"] if node["id"] == data["root_id"])
        self.assertEqual({ref["kind"] for ref in root["references"]}, {"domain", "indicator"})
        self.assertEqual(root["evidence"][-1]["record_id"], ioc.indicator.id)
        self.assertEqual(data["collected_node_count"], 2)

    def test_shared_hosting_does_not_infer_actor_or_domain_relationship(self):
        self.dns()
        self.dns("other.example")
        data = self.graph()
        self.assertEqual(data["collected_node_count"], 3)
        self.assertTrue(all(edge["relationship_type"] == "dns_address" for edge in data["edges"]))
        nodes = {item["id"]: item["value"] for item in data["nodes"]}
        self.assertIn(["example.com", IP, "other.example"],
                      [[nodes[key] for key in item["node_ids"]] for item in data["paths"]])

    def test_stale_dns_retained_with_latest_failure_and_revoked_claim(self):
        old = self.dns(observed=NOW - timedelta(days=3))
        ioc = self.ioc()
        actor = self.entity()
        relation = self.relation(actor, indicator=ioc)
        self.iocs.revoke(ioc.assertion.id, reason="Fixture withdrawal reason")
        self.cti.revoke_relationship(relation.assertion.id, reason="Fixture withdrawal reason")
        failure = self.dns(failed=True)
        data = self.graph()
        dns = next(edge for edge in data["edges"] if edge["kind"] == "observation")
        self.assertEqual((dns["evidence"][0]["record_id"], dns["evidence"][0]["freshness"]), (old.id, "stale"))
        root = next(node for node in data["nodes"] if node["id"] == data["root_id"])
        self.assertEqual((root["evidence"][0]["record_id"], root["evidence"][0]["status"]), (failure.id, "failed"))
        claims = [row for node in data["nodes"] for row in node["evidence"] if row["record_type"] == "cti_indicator"]
        self.assertEqual((claims[0]["status"], claims[0]["current"]), ("revoked", False))
        self.assertEqual(next(edge for edge in data["edges"] if edge["kind"] == "source_claim")["evidence"][0]["status"], "revoked")

    def test_conflicting_sources_not_collapsed_or_voted(self):
        self.dns()
        ioc = self.ioc()
        first, second = self.entity("First Actor"), self.entity("Second Actor")
        r1 = self.relation(first, indicator=ioc, source="first")
        r2 = self.relation(second, indicator=ioc, source="second")
        data = self.graph()
        self.assertEqual({row["assertion_id"] for edge in data["edges"] for row in edge["evidence"] if row["kind"] == "source_claim"},
                         {r1.assertion.id, r2.assertion.id})
        self.assertNotIn("risk_score", data)

    def test_cycles_and_one_hop_depth_bound(self):
        ioc, first, second = self.ioc(), self.entity("First Actor"), self.entity("Second Actor")
        self.relation(first, indicator=ioc)
        self.relation(second, indicator=ioc)
        self.relation(first, entity=second)
        self.relation(second, entity=first, ref="report:reverse")
        data = self.graph(IP, "ip")
        self.assertTrue(all(path["hops"] <= 2 and len(path["node_ids"]) == len(set(path["node_ids"])) for path in data["paths"]))
        one = self.graph(IP, "ip", max_hops=1)
        self.assertEqual(one["collected_edge_count"], 2)
        self.assertTrue(all(path["hops"] == 1 for path in one["paths"]))

    def test_pagination_is_stable_guard_detects_changes(self):
        self.dns()
        ioc = self.ioc()
        self.relation(self.entity(), indicator=ioc)
        full = self.graph()
        first = self.graph(limit=1)
        second = self.graph(offset=1, limit=1, expected_snapshot=first["snapshot_id"])
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(first["paths"] + second["paths"], full["paths"])
        self.dns("other.example")
        with self.assertRaises(ResearchSnapshotChanged):
            self.graph(offset=1, expected_snapshot=first["snapshot_id"])

    def test_node_edge_and_path_limits_are_explicit(self):
        self.dns()
        self.dns("other.example")
        for options, reason in (({"node_limit": 2}, "node_limit"), ({"edge_limit": 1}, "edge_limit")):
            with self.subTest(options=options):
                data = self.graph(**options)
                self.assertEqual(data["status"], "partial")
                self.assertFalse(data["coverage_complete"])
                self.assertIn(reason, data["limitations"])
        with patch("xti.domain.research.MAX_PATHS", 1):
            self.assertIn("path_limit", self.graph()["limitations"])

    def test_dns_window_does_not_claim_exhaustive_reverse_lookup(self):
        self.dns("old.example")
        self.dns("new.example")
        with patch("xti.adapters.sqlite_research.MAX_DNS_CHECKS", 1):
            data = self.graph(IP, "ip")
        self.assertEqual(data["status"], "partial")
        self.assertIn("dns_history_window", data["limitations"])
        self.assertFalse(data["coverage"][0]["complete"])

    def test_multiple_observations_one_edge_and_repeated_claim_no_duplicate_path(self):
        first, second = self.dns(), self.dns()
        ioc, actor = self.ioc(), self.entity()
        relation = self.relation(actor, indicator=ioc)
        self.assertEqual(self.relation(actor, indicator=ioc).relationship.id, relation.relationship.id)
        data = self.graph()
        dns = next(edge for edge in data["edges"] if edge["kind"] == "observation")
        self.assertEqual({row["record_id"] for row in dns["evidence"]}, {first.id, second.id})
        self.assertEqual(data["collected_path_count"], 2)

    def test_corrupt_dns_hash_and_reactivated_flag_fail_closed(self):
        check = self.dns()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE surface_checks SET state_sha256=? WHERE id=?", ("0" * 64, check.id))
            connection.commit()
        with self.assertRaises(StorageError):
            self.graph()
        ioc = self.ioc("different.example", "domain")
        self.iocs.revoke(ioc.assertion.id, reason="Fixture withdrawal reason")
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE cti_indicator_assertions SET active=1 WHERE id=?", (ioc.assertion.id,))
            connection.commit()
        with self.assertRaises(StorageError):
            self.graph("different.example")

    def test_no_records_invalid_inputs_and_missing_db_are_distinct(self):
        self.assertEqual(self.graph()["status"], "not_recorded")
        SQLiteAssetRepository(self.path).add("example.com")
        self.assertEqual(self.graph()["status"], "no_relationships")
        for options in ({"node_limit": True}, {"max_hops": 3}, {"offset": -1}, {"limit": 101},
                        {"edge_limit": 0}, {"expected_snapshot": "bad"}, {"stale_after_hours": 0}):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                self.graph(**options)
        for kind, value in (("url", "file:///private/test"), ("ip", "192.0.2.0/24"), ("domain", "*.example.com")):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                self.graph(value, kind)
        path = self.root / "absent" / "xti.db"
        with self.assertRaises(StorageError):
            ResearchService(SQLiteResearchRepository(path)).show(indicator_type="domain", value="example.com")
        self.assertFalse(path.parent.exists())

    def test_ipv6_canonicalization_and_expiry_separate_from_freshness(self):
        self.dns(ip="2001:4860:4860::8888")
        self.ioc("2001:4860:4860::8888", "ipv6", valid_until=(NOW - timedelta(hours=1)).isoformat())
        data = self.graph("2001:4860:4860:0:0:0:0:8888", "ip")
        self.assertEqual(data["query"]["indicator_type"], "ipv6")
        root = next(node for node in data["nodes"] if node["id"] == data["root_id"])
        self.assertEqual((root["evidence"][0]["status"], root["evidence"][0]["freshness"]), ("expired", "fresh"))

    def test_cli_detail_and_next_page_commands_preserve_selected_workspace(self):
        self.dns()
        self.relation(self.entity(), indicator=self.ioc())
        before = self.files()
        data = self.graph(limit=1)
        commands = []
        for line in research_lines(data, data_dir=self.data):
            if "Ayrıntı: " in line or "Sonraki sayfa: " in line:
                commands.append(shlex.split(line.split(": ", 1)[1])[1:])
        self.assertTrue(commands)
        for command in commands:
            self.assertEqual(command[0:2], ["--data-dir", str(self.data)])
            code, out, err = self.invoke(command)
            self.assertEqual((code, err), (0, ""), out)
        code, out, err = self.invoke(["--data-dir", str(self.data), "--json", "research", "example.com", "--type", "domain"])
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(json.loads(out)["data"]["collected_path_count"], 2)
        self.assertEqual(before, self.files())

    def test_engine_contract_refs_errors_and_snapshot_guard(self):
        self.dns()
        self.relation(self.entity(), indicator=self.ioc())
        args = ["--data-dir", str(self.data), "engine"]
        code, out, err = self.invoke(args, self.request(limit=1))
        self.assertEqual((code, err), (0, ""), out)
        response = json.loads(out)
        self.assertEqual(response["scope"]["mode"], "local-workspace")
        for node in response["data"]["nodes"]:
            for reference in node["references"]:
                request = {**self.request(), "operation": "record.get", "parameters": {"reference": reference}}
                code, out, err = self.invoke(args, request)
                self.assertEqual((code, err), (0, ""), out)
        for parameters in ({"company": "other"}, {"node_limit": True}, {"indicator_type": []}):
            code, out, err = self.invoke(args, self.request(**parameters))
            self.assertEqual(code, 2, out)
            self.assertEqual(json.loads(out)["error"]["code"], "invalid_parameters")
        self.dns("other.example")
        code, out, err = self.invoke(args, self.request(expected_snapshot=response["data"]["snapshot_id"]))
        self.assertEqual(code, 1, out)
        self.assertEqual(json.loads(out)["error"]["code"], "snapshot_changed")

    def test_one_read_transaction_does_not_mix_concurrent_writes(self):
        self.dns()
        ioc, actor = self.ioc(), self.entity()
        self.relation(actor, indicator=ioc)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        statements, connections, mutated = [], [], []
        original_connection, original_neighbors = SQLiteAssetRepository._connection, _Reader.neighbors

        @contextmanager
        def tracked(storage, **options):
            connections.append(options.get("readonly", False))
            with original_connection(storage, **options) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        def concurrent(reader, key):
            if not mutated:
                mutated.append(True)
                # A separate writer commits after the root read, before the
                # IOC is loaded. Subsequent reads must still see its old state.
                with closing(sqlite3.connect(self.path)) as writer, writer:
                    writer.execute("DELETE FROM cti_relationship_assertion_events")
            return original_neighbors(reader, key)

        with patch.object(SQLiteAssetRepository, "_connection", tracked), patch.object(_Reader, "neighbors", concurrent):
            data = self.graph()
        self.assertEqual(data["collected_path_count"], 2)
        self.assertEqual(connections, [True])
        self.assertEqual(statements.count("BEGIN"), 1)
        self.assertFalse(any(sql.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER"} for sql in statements))
        with self.assertRaises(StorageError):
            self.graph()

    def test_source_and_history_budgets_are_visible_or_fail_closed(self):
        self.dns()
        self.dns()
        with patch("xti.adapters.sqlite_research.MAX_SHOWN_SOURCES", 1):
            data = self.graph()
        self.assertIn("source_evidence_limit", data["limitations"])
        self.assertEqual(data["edges"][0]["evidence_total_count"], 2)
        self.assertEqual(len(data["edges"][0]["evidence"]), 1)
        with patch("xti.adapters.sqlite_research.MAX_DNS_BYTES", 1):
            data = self.graph()
        self.assertEqual(data["status"], "partial")
        self.assertIn("dns_read_budget", data["limitations"])
        self.ioc()
        with patch("xti.adapters.sqlite_research.MAX_AUDIT_ROWS", 1):
            with self.assertRaises(StorageError):
                self.graph(IP, "ip")

    def test_cti_adjacency_and_claim_limits_never_present_full_coverage(self):
        ioc, first, second = self.ioc(), self.entity("First Actor"), self.entity("Second Actor")
        self.relation(first, indicator=ioc)
        self.relation(first, indicator=ioc, source="second")
        self.relation(second, indicator=ioc)
        with patch("xti.adapters.sqlite_research.MAX_RELATIONS_PER_NODE", 1):
            self.assertIn("cti_adjacency_limit", self.graph(IP, "ip")["limitations"])
        with patch("xti.adapters.sqlite_research.MAX_SHOWN_SOURCES", 1):
            data = self.graph(IP, "ip")
        self.assertIn("source_evidence_limit", data["limitations"])
        self.assertTrue(any(edge["evidence_total_count"] == 2 for edge in data["edges"]))

    def test_byte_budget_cannot_label_older_dns_as_latest_check(self):
        old = self.dns()
        self.dns(failed=True, error="DNS timeout " + "x" * 500)
        with closing(sqlite3.connect(self.path)) as connection:
            size = connection.execute(
                "SELECT LENGTH(CAST(result AS BLOB))+LENGTH(CAST(change AS BLOB)) FROM surface_checks WHERE id=?",
                (old.id,)).fetchone()[0]
        with patch("xti.adapters.sqlite_research.MAX_DNS_BYTES", size):
            data = self.graph(IP, "ip")
        self.assertIn("dns_read_budget", data["limitations"])
        domain = next(node for node in data["nodes"] if node["kind"] == "domain")
        self.assertEqual(domain["evidence"], [])
        self.assertEqual(data["edges"][0]["evidence"][0]["record_id"], old.id)

    def test_managed_feed_receipts_and_local_withdrawal_preserve_provenance(self):
        from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository
        from tests.test_cti_feeds import raw, snapshot
        feed = SQLiteCtiFeedRepository(self.path).apply(snapshot(raw(IP)),
            started_at=NOW.isoformat(), finished_at=NOW.isoformat())
        data = self.graph(IP, "ip")
        evidence = data["nodes"][0]["evidence"][0]
        self.assertEqual(evidence["source_run_id"], feed.id)
        self.assertNotEqual(evidence["first_observed_at"], evidence["observed_at"])
        self.iocs.revoke(evidence["assertion_id"], reason="Operator withdrawal fixture")
        updated = self.graph(IP, "ip")["nodes"][0]["evidence"][0]
        self.assertEqual(updated["status"], "revoked")
        self.assertIsNone(updated["source_run_id"])
        self.assertNotEqual(evidence["event_id"], updated["event_id"])

    def test_large_unrelated_feed_is_not_a_research_node_limit(self):
        from xti.adapters.certpl_warning import parse_certpl_warning_response
        from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository
        from xti.domain.cti_feeds import CERTPL_POLICY
        body = "\n".join(("! Title: CERT.PL's Warning List", "! Version: 202611171100",
            "! Expires: 1 hours", "! Homepage: https://cert.pl/lista-ostrzezen/",
            *(f"unrelated-{index}.example.test" for index in range(10_001)), "")).encode()
        feed = SQLiteCtiFeedRepository(self.path, CERTPL_POLICY).apply(
            parse_certpl_warning_response(body, fetched_at=NOW), started_at=NOW.isoformat(), finished_at=NOW.isoformat())
        self.assertEqual(feed.indicator_count, 10_001)
        self.dns()
        self.relation(self.entity(), indicator=self.ioc())
        data = self.graph()
        self.assertTrue(data["coverage_complete"])
        self.assertEqual((data["collected_node_count"], data["collected_path_count"]), (3, 2))

    def test_backup_restore_keeps_ids_paths_and_source_evidence(self):
        self.dns()
        self.relation(self.entity(), indicator=self.ioc())
        data = self.graph()
        backup, restored = self.root / "backup.db", self.root / "restored" / "xti.db"
        SQLiteAssetRepository(self.path).backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        result = research_data(ResearchService(SQLiteResearchRepository(restored), clock=lambda: NOW).show(
            indicator_type="domain", value="example.com"))
        self.assertEqual(data, result)

    def test_two_companies_same_ip_and_unknown_disabled_never_fallback(self):
        root = self.root / "companies"
        # Provision is the only explicitly mutating operator step in this test.
        for company, domain in (("first", "example.com"), ("second", "private.example")):
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["platform", "provision", "--root", str(root), "--company", company]), 0, out.getvalue())
            context = resolve_company_workspace(root, company)
            self.dns(domain, path=context.database)
        before = self.files()
        for company, allowed, forbidden in (("first", "example.com", "private.example"),
                                             ("second", "private.example", "example.com")):
            code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", company],
                                         self.request(indicator_type="ip", value=IP))
            self.assertEqual((code, err), (0, ""), out)
            data = json.loads(out)
            self.assertEqual(data["scope"]["mode"], "company-workspace")
            self.assertIn(allowed, {node["value"] for node in data["data"]["nodes"]})
            self.assertNotIn(forbidden, out)
        self.assertEqual(before, self.files())
        code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", "unknown"], self.request())
        self.assertNotEqual(code, 0)
        self.assertIsNone(json.loads(out)["data"])
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["platform", "disable", "--root", str(root), "--company", "first"]), 0)
        code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", "first"], self.request())
        self.assertNotEqual(code, 0)
        self.assertIsNone(json.loads(out)["data"])


if __name__ == "__main__":
    unittest.main()

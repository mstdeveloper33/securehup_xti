"""Passive discovery evidence, human classification and workspace-safe research."""

from contextlib import closing
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import shlex
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import provision_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_research import SQLiteResearchRepository, _Reader
from xti.adapters.sqlite_research_history import SQLiteResearchHistoryRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.application.research import ResearchService, priority_data
from xti.application.research_history import ResearchHistoryService
from xti.domain.research import ResearchSnapshotChanged
from xti.domain.research_history import capture_scope, freeze
from xti.domain.surface import SurfaceCandidateEvidence, SurfaceDiscoveryRunRequest
from xti.interfaces.platform_jobs import initialize_jobs
from xti.interfaces.research import research_lines, priority_lines
from tests.test_research import ResearchFixture, IP


DEFAULT_TIME = object()


class DiscoveryResearchTests(ResearchFixture, unittest.TestCase):
    def repo(self, path=None):
        return SQLiteSurfaceCandidateRepository(path or self.path)

    def discover(self, domain="api.example.com", *, root="example.com", number=1,
                 observed=DEFAULT_TIME, raw=None, provider="crt.sh", path=None):
        path = path or self.path
        asset, _ = SQLiteAssetRepository(path).add(root)
        stamp = self.at.isoformat()
        observed = stamp if observed is DEFAULT_TIME else observed
        digest = hashlib.sha256(f"{provider}|{number}|{domain}".encode()).hexdigest()
        evidence = SurfaceCandidateEvidence(domain, provider, f"https://archive.example/record/{number}",
                                            digest, raw or domain, observed)
        self.repo(path).record_discovery(asset.id, root, (evidence,), SurfaceDiscoveryRunRequest(
            "complete", "https://archive.example/search", stamp, stamp, 1, 0, 0, (), 1, None, provider))
        candidate = next(row for row in self.repo(path).list_candidates(asset.id, status=None) if row.domain == domain)
        return self.repo(path).candidate_details(candidate.id, source_limit=500)

    def decide(self, candidate, status, reason="Controlled human classification", *, path=None):
        return self.repo(path).decide_candidate(candidate.id, status, reason, self.at.isoformat())

    def edges(self, kind="passive_subdomain", graph=None):
        return [row for row in (graph or self.graph(limit=100))["edges"] if row["relationship_type"] == kind]

    def priorities(self):
        return priority_data(self.service.priorities(indicator_type="domain", value="example.com", limit=100))

    def history(self, path=None):
        path = path or self.path
        service = ResearchService(SQLiteResearchRepository(path), clock=lambda: self.at)
        return ResearchHistoryService(SQLiteResearchHistoryRepository(path), service)

    def sql(self, statement, parameters=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute(statement, parameters).fetchall()

    def test_pending_archive_is_candidate_not_dns_ownership_or_scope(self):
        details = self.discover(raw="*.api.example.com")
        before = self.files()
        graph = self.graph(limit=100)
        self.assertEqual(self.edges("subdomain_classification", graph), [])
        edge = self.edges(graph=graph)[0]
        self.assertEqual(edge["kind"], "candidate_context")
        state, source = edge["evidence"]
        self.assertEqual((state["status"], state["current"]), ("pending", None))
        self.assertEqual((source["event_id"], source["state_sha256"], source["source_reference"]),
                         (details.sources[0].id, details.sources[0].source_sha256, details.sources[0].source_name))
        self.assertIn("*.api.example.com", source["description"])
        self.assertEqual({node["value"] for node in graph["nodes"]}, {"example.com", "api.example.com"})
        self.assertEqual(self.sql("SELECT value FROM assets"), [("example.com",)])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM surface_scopes"), [(0,)])
        self.assertEqual(self.files(), before)

    def test_owned_classification_preserves_original_event_without_enabling_active_checks(self):
        candidate = self.discover().candidate
        self.decide(candidate, "owned")
        last = self.repo().candidate_details(candidate.id).events[-1]
        before = self.files()
        row = self.edges("subdomain_classification")[0]["evidence"][0]
        self.assertEqual((row["status"], row["current"], row["event_id"]), ("owned", True, last.id))
        self.assertEqual(row["kind"], "human_decision")
        self.assertEqual(row["time_basis"], "decision_recorded_at")
        self.assertEqual(row["observed_at"], row["recorded_at"])
        self.assertIsNone(row["assertion_id"])
        self.assertIsNone(row["confidence"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM surface_scopes"), [(0,)])
        self.assertEqual(self.files(), before)

    def test_rejection_reopening_and_reason_change_keep_separate_history(self):
        candidate = self.discover().candidate
        for status, reason in (("owned", "Initial review"), ("rejected", "Review corrected"),
                               ("pending", "Reopen review"), ("pending", "Additional context")):
            self.decide(candidate, status, reason)
        rows = self.edges("subdomain_classification")[0]["evidence"]
        self.assertEqual([row["status"] for row in rows], ["pending", "pending", "rejected", "owned"])
        self.assertEqual([row["current"] for row in rows], [True, False, False, False])
        details = self.repo().candidate_details(candidate.id)
        self.assertEqual({row["event_id"] for row in rows}, {event.id for event in details.events[1:]})
        self.assertEqual(self.edges()[0]["evidence"][0]["status"], "pending")
        self.assertNotIn(details.events[0].id, {row["event_id"] for row in rows})

    def test_repeat_archive_does_not_refresh_source_time_or_reset_decision(self):
        original = self.discover(observed=(self.at - timedelta(days=40)).isoformat())
        self.decide(original.candidate, "rejected")
        first = self.graph()
        self.at += timedelta(days=5)
        repeated = self.discover(observed=original.sources[0].observed_at)
        self.assertEqual(repeated.candidate.status, "rejected")
        self.assertEqual(repeated.candidate.source_count, 1)
        graph = self.graph()
        self.assertEqual(graph["snapshot_id"], first["snapshot_id"])
        self.assertEqual(self.edges(graph=graph)[0]["evidence"][1]["observed_at"], original.sources[0].observed_at)

    def test_source_time_absent_uses_receipt_time_and_multiple_providers_keep_identity(self):
        first = self.discover(observed=None)
        self.at += timedelta(hours=1)
        second = self.discover(number=2, provider="theharvester")
        rows = self.edges()[0]["evidence"][1:]
        self.assertEqual({row["event_id"] for row in rows}, {row.id for row in second.sources})
        old = next(row for row in rows if row["event_id"] == first.sources[0].id)
        self.assertEqual(old["time_basis"], "response_received_at")
        self.assertEqual(old["observed_at"], first.sources[0].recorded_at)
        self.assertEqual({row["source"] for row in rows}, {"crt.sh", "theharvester"})

    def test_empty_or_failed_new_discovery_does_not_erase_old_candidate(self):
        candidate = self.discover().candidate
        self.decide(candidate, "owned")
        first = self.graph()
        self.at += timedelta(hours=1)
        stamp = self.at.isoformat()
        for status in ("complete", "failed"):
            self.repo().record_discovery(candidate.asset_id, candidate.asset_value, (), SurfaceDiscoveryRunRequest(
                status, "https://archive.example/search", stamp, stamp, 0, 0, 0, (), 0,
                "Fixture source timeout" if status == "failed" else None))
        self.assertEqual(self.graph()["snapshot_id"], first["snapshot_id"])
        self.assertEqual(self.edges("subdomain_classification")[0]["evidence"][0]["status"], "owned")

    def test_root_candidate_dns_ip_path_fits_two_hops_without_ownership_inference(self):
        self.discover()
        check = self.dns("api.example.com")
        graph = self.graph(limit=100)
        nodes = {row["id"]: row["value"] for row in graph["nodes"]}
        self.assertIn(["example.com", "api.example.com", IP],
                      [[nodes[value] for value in path["node_ids"]] for path in graph["paths"]])
        self.assertTrue(any(row["record_id"] == check.id for edge in graph["edges"] for row in edge["evidence"]))
        self.assertEqual(self.edges("subdomain_classification", graph), [])

    def test_reverse_lookup_preserves_direction_and_uses_explicit_stored_root(self):
        self.discover()
        graph = self.graph("api.example.com", limit=100)
        nodes = {row["id"]: row["value"] for row in graph["nodes"]}
        edge = self.edges(graph=graph)[0]
        self.assertEqual((nodes[edge["source_id"]], nodes[edge["target_id"]]), ("example.com", "api.example.com"))
        unrelated = self.graph("absent.example.com")
        self.assertEqual(unrelated["edges"], [])

    def test_same_candidate_name_under_two_registered_roots_keeps_distinct_decisions(self):
        first = self.discover("api.shop.example.com")
        second = self.discover("api.shop.example.com", root="shop.example.com")
        self.decide(first.candidate, "owned")
        self.decide(second.candidate, "rejected")
        graph = self.graph("api.shop.example.com", limit=100)
        decisions = self.edges("subdomain_classification", graph)
        self.assertEqual({row["evidence"][0]["status"] for row in decisions}, {"owned", "rejected"})
        node = next(row for row in graph["nodes"] if row["id"] == graph["root_id"])
        self.assertEqual({ref["record_id"] for ref in node["references"]}, {first.candidate.id, second.candidate.id})

    def test_candidate_rejection_does_not_revoke_independent_active_scope(self):
        candidate = self.discover().candidate
        self.dns(candidate.domain)
        self.decide(candidate, "rejected")
        before = self.files()
        self.graph()
        active = SQLiteSurfaceRepository(self.path).list()
        self.assertEqual(len(active), 1)
        self.assertEqual(self.files(), before)

    def test_current_classification_priorities_do_not_promote_old_owned_or_rejected_states(self):
        candidate = self.discover().candidate
        for status in ("owned", "rejected", "pending"):
            self.decide(candidate, status)
            item = next(row for row in self.priorities()["items"] if row["record_type"] == "subdomain_classification")
            codes = {row["code"] for row in item["reasons"]}
            self.assertEqual(codes, {"surface_candidate_" + status})
            self.assertEqual(item["priority"], "verify" if status == "pending" else "context")

    def test_old_decision_does_not_become_stale_network_evidence(self):
        candidate = self.discover().candidate
        self.decide(candidate, "owned")
        self.at += timedelta(days=10)
        self.discover(number=2)
        item = next(row for row in self.priorities()["items"] if row["record_type"] == "subdomain_classification")
        self.assertEqual({row["code"] for row in item["reasons"]}, {"surface_candidate_owned"})
        self.assertEqual(item["evidence"][0]["freshness"], "stale")

    def test_clock_rollback_uses_event_insertion_order_and_preserves_seen_range(self):
        candidate = self.discover().candidate
        self.decide(candidate, "owned")
        self.at -= timedelta(days=1)
        self.decide(candidate, "rejected")
        self.discover(number=2)
        self.assertEqual(self.edges("subdomain_classification")[0]["evidence"][0]["status"], "rejected")

    def test_candidate_and_byte_budgets_skip_unverified_records_before_decode(self):
        self.discover()
        for name, limit in (("MAX_DISCOVERY_AUDIT_ROWS", 2), ("MAX_DISCOVERY_AUDIT_BYTES", 1),
                            ("MAX_DISCOVERY_DECISIONS", 0)):
            with self.subTest(name=name), patch("xti.adapters.sqlite_research_discovery." + name, limit), \
                 patch.object(SQLiteSurfaceCandidateRepository, "_details", side_effect=AssertionError("Preflight must precede decoding")):
                graph = self.graph()
                self.assertEqual(graph["edges"], [])
                self.assertIn("discovery_read_budget", graph["limitations"])
                coverage = next(row for row in graph["coverage"] if row["kind"] == "surface_candidates")
                self.assertEqual((coverage["examined_count"], coverage["complete"]), (0, False))

    def test_candidate_selection_limit_and_graph_budgets_are_explicit(self):
        self.discover()
        self.discover("vpn.example.com")
        with patch("xti.adapters.sqlite_research_discovery.MAX_DISCOVERY_CANDIDATES", 1):
            graph = self.graph()
        self.assertIn("discovery_candidate_limit", graph["limitations"])
        self.assertFalse(graph["coverage_complete"])
        self.assertIn("node_limit", self.graph(node_limit=2)["limitations"])

    def test_byte_preflight_counts_identity_and_timestamp_fields_before_decoding(self):
        self.discover()
        for field in ("source_sha256", "recorded_at", "id"):
            with self.subTest(field=field):
                original = self.sql(f"SELECT {field} FROM surface_candidate_sources")[0][0]
                self.sql(f"UPDATE surface_candidate_sources SET {field}=?", ("X" * 20000,))
                with patch("xti.adapters.sqlite_research_discovery.MAX_DISCOVERY_AUDIT_BYTES", 10000), \
                     patch.object(SQLiteSurfaceCandidateRepository, "_details", side_effect=AssertionError("Bound before decode")):
                    self.assertIn("discovery_read_budget", self.graph()["limitations"])
                self.sql(f"UPDATE surface_candidate_sources SET {field}=?", (original,))

    def test_truncated_source_and_decision_histories_keep_latest_state_and_true_totals(self):
        candidate = self.discover().candidate
        for index in range(2, 55):
            self.discover(number=index)
            self.decide(candidate, "owned", f"Controlled review {index}")
        graph = self.graph()
        archive = self.edges(graph=graph)[0]
        decisions = self.edges("subdomain_classification", graph)[0]
        self.assertEqual((len(archive["evidence"]), archive["evidence_total_count"]), (50, 55))
        self.assertEqual((len(decisions["evidence"]), decisions["evidence_total_count"]), (50, 53))
        self.assertTrue(decisions["evidence"][0]["current"])
        self.assertIn("source_evidence_limit", graph["limitations"])
        self.history().record(indicator_type="domain", value="example.com")

    def test_unrelated_large_catalog_does_not_consume_selected_history_budget(self):
        self.discover()
        other = self.discover("api.other.example", root="other.example").candidate
        self.sql("UPDATE surface_candidate_sources SET raw_domain=? WHERE candidate_id=?", ("X" * 20000, other.id))
        with patch("xti.adapters.sqlite_research_discovery.MAX_DISCOVERY_AUDIT_BYTES", 10000):
            graph = self.graph()
        self.assertTrue(graph["coverage_complete"])
        self.assertEqual(len(self.edges(graph=graph)), 1)

    def test_old_archive_import_does_not_hide_newer_observation_at_evidence_limit(self):
        first = self.discover()
        for index in range(2, 5):
            self.discover(number=index, observed=(self.at - timedelta(days=index)).isoformat())
        with patch("xti.adapters.sqlite_research_discovery.MAX_DISCOVERY_EVIDENCE", 2):
            edge = self.edges()[0]
        self.assertEqual(edge["evidence"][1]["event_id"], first.sources[0].id)
        self.assertEqual(edge["evidence"][1]["freshness"], "fresh")

    def test_corrupt_root_reference_is_not_silently_ignored_in_reverse_lookup(self):
        candidate = self.discover().candidate
        self.sql("UPDATE surface_candidates SET asset_id='missing-root' WHERE id=?", (candidate.id,))
        with self.assertRaises(StorageError):
            self.graph(candidate.domain)

    def test_projection_corruption_and_missing_source_are_storage_errors(self):
        candidate = self.discover().candidate
        self.sql("UPDATE surface_candidates SET status='owned' WHERE id=?", (candidate.id,))
        with self.assertRaises(StorageError): self.graph()
        self.sql("UPDATE surface_candidates SET status='pending' WHERE id=?", (candidate.id,))
        self.sql("DELETE FROM surface_candidate_sources WHERE candidate_id=?", (candidate.id,))
        with self.assertRaises(StorageError): self.graph()

    def test_root_mismatch_out_of_scope_and_deleted_initial_event_are_storage_errors(self):
        candidate = self.discover().candidate
        for field, value in (("asset_value", "other.example"), ("domain", "outside.example"),
                             ("domain", "API.EXAMPLE.COM"), ("last_seen_at", "2000-01-01T00:00:00+00:00")):
            with self.subTest(field=field, value=value):
                original = getattr(candidate, field)
                self.sql(f"UPDATE surface_candidates SET {field}=? WHERE id=?", (value, candidate.id))
                with self.assertRaises(StorageError): self.graph()
                self.sql(f"UPDATE surface_candidates SET {field}=? WHERE id=?", (original, candidate.id))
        self.decide(candidate, "owned")
        self.sql("DELETE FROM surface_candidate_events WHERE action='discovered'")
        with self.assertRaises(StorageError): self.graph()

    def test_invalid_source_digest_and_event_transition_are_rejected(self):
        candidate = self.discover().candidate
        original = self.repo().candidate_details(candidate.id).sources[0].source_sha256
        self.sql("UPDATE surface_candidate_sources SET source_sha256='invalid'")
        with self.assertRaises(StorageError): self.graph()
        self.sql("UPDATE surface_candidate_sources SET source_sha256=?", (original,))
        self.decide(candidate, "owned")
        self.sql("UPDATE surface_candidate_events SET action='updated' WHERE status='owned'")
        with self.assertRaises(StorageError): self.graph()

    def test_decision_updates_invalidate_page_snapshot(self):
        candidate = self.discover().candidate
        self.discover("vpn.example.com")
        first = self.graph(limit=1)
        self.decide(candidate, "owned")
        with self.assertRaises(ResearchSnapshotChanged):
            self.graph(limit=1, offset=1, expected_snapshot=first["snapshot_id"])

    def test_concurrent_classification_uses_single_read_snapshot(self):
        candidate = self.discover().candidate
        self.sql("PRAGMA journal_mode=WAL")
        original, changed = _Reader.neighbors, []
        def update(reader, key):
            if not changed:
                changed.append(True)
                self.decide(candidate, "owned")
            return original(reader, key)
        with patch.object(_Reader, "neighbors", update):
            graph = self.graph()
        self.assertEqual(self.edges("subdomain_classification", graph), [])
        self.assertEqual(self.edges("subdomain_classification")[0]["evidence"][0]["status"], "owned")

    def test_frozen_review_records_decision_changes_without_ioc_withdrawal(self):
        candidate = self.discover().candidate
        self.decide(candidate, "owned")
        service = self.history()
        first = service.record(indicator_type="domain", value="example.com")
        original = service.show(first["review"]["id"], view="items", limit=100)
        self.decide(candidate, "rejected")
        second = service.record(indicator_type="domain", value="example.com")
        changes = service.show(second["review"]["id"])["changes"]
        self.assertTrue(changes)
        self.assertEqual({row["origin"] for row in changes}, {"evidence_or_mixed"})
        self.assertTrue(all(row["withdrawn_assertion_ids"] == [] for row in changes))
        self.assertEqual(service.show(first["review"]["id"], view="items", limit=100), original)

    def test_old_v3_model_two_review_remains_unchanged_and_v4_starts_baseline(self):
        repository = SQLiteResearchHistoryRepository(self.path)
        old = freeze(priority_data(self.service.full_priorities(indicator_type="domain", value="example.com")))
        old["policy_version"] = "research-priority-v3"
        review, _ = repository.append(capture_scope(indicator_type="domain", value="example.com"), old, "v3", None)
        original = deepcopy(repository.show(review.header.id))
        self.discover()
        new = self.history().record(indicator_type="domain", value="example.com")
        self.assertEqual(new["review"]["comparison"]["state"], "policy_baseline")
        self.assertEqual(repository.show(review.header.id), original)

    def test_cli_engine_record_references_and_detail_commands_use_selected_workspace(self):
        candidate = self.discover().candidate
        self.decide(candidate, "owned")
        before = self.files()
        code, out, err = self.invoke(["--data-dir", str(self.data), "engine"], self.request(limit=100))
        self.assertEqual((code, err), (0, ""), out)
        graph = json.loads(out)["data"]
        ref = next(ref for node in graph["nodes"] for ref in node["references"] if ref["record_type"] == "surface_candidate")
        code, out, err = self.invoke(["--data-dir", str(self.data), "engine"],
            {**self.request(), "operation": "record.get", "parameters": {"reference": ref}})
        self.assertEqual((code, err), (0, ""), out)
        lines = research_lines(graph, data_dir=self.data) + priority_lines(self.priorities(), data_dir=self.data)
        self.assertTrue(any("Karar:" in line and "son karar" in line for line in lines))
        commands = {line.split("Ayrıntı: ", 1)[1] for line in lines if "Ayrıntı: " in line}
        for command in commands:
            code, out, err = self.invoke(shlex.split(command)[1:])
            self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(self.files(), before)

    def test_company_isolation_and_backup_preserve_candidate_and_decision_identity(self):
        root = self.root / "companies"
        for company in ("first", "second"):
            context = provision_company_workspace(root, company)
            SQLiteAssetRepository(context.database).initialize()
            initialize_jobs(context)
            candidate = self.discover(path=context.database).candidate
            self.decide(candidate, "owned", company + " private decision", path=context.database)
        code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", "first"], self.request())
        self.assertEqual((code, err), (0, ""), out)
        self.assertIn("first private decision", out)
        self.assertNotIn("second private decision", out)
        candidate = self.discover().candidate
        self.decide(candidate, "rejected")
        original = self.history().record(indicator_type="domain", value="example.com")
        backup = self.root / "discovery-backup.db"
        SQLiteAssetRepository(self.path).backup(backup)
        self.assertEqual(self.history(backup).show(original["review"]["id"], view="items", limit=100),
                         self.history().show(original["review"]["id"], view="items", limit=100))

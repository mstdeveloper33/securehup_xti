"""Human supplier decisions remain separate from technical candidate evidence."""

from contextlib import closing
from copy import deepcopy
from datetime import timedelta
import json
import shlex
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import provision_company_workspace
from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_research import SQLiteResearchRepository, _Reader
from xti.adapters.sqlite_research_history import SQLiteResearchHistoryRepository
from xti.adapters.sqlite_supplier_candidates import SQLiteSupplierCandidateRepository, SQLiteSupplierDependencySource
from xti.adapters.sqlite_supplier_history import read_supplier_history, supplier_scope
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.application.research import ResearchService, priority_data
from xti.application.research_history import ResearchHistoryService
from xti.application.supplier_candidates import SupplierCandidateService
from xti.application.suppliers import SupplierService
from xti.domain.assets import ValidationError
from xti.domain.research import ResearchSnapshotChanged
from xti.domain.research_history import capture_scope, freeze, validate_snapshot
from xti.interfaces.platform_jobs import initialize_jobs
from xti.interfaces.research import research_lines, priority_lines
from tests.test_research import ResearchFixture
from tests import test_research_surface as surface_fixture


class SupplierResearchTests(ResearchFixture, unittest.TestCase):
    scope = surface_fixture.SurfaceResearchTests.scope
    cname = surface_fixture.SurfaceResearchTests.cname
    tls = surface_fixture.SurfaceResearchTests.tls

    def setUp(self):
        super().setUp()
        self.suppliers = self.supplier_service()
        self.candidates = self.candidate_service()

    def supplier_service(self, path=None):
        return SupplierService(SQLiteSupplierRepository(path or self.path), clock=lambda: self.at)

    def candidate_service(self, path=None):
        path = path or self.path
        return SupplierCandidateService(SQLiteSupplierDependencySource(path),
            SQLiteSupplierCandidateRepository(path), PublicSuffixResolver(), clock=lambda: self.at)

    def candidate(self, domain="example.com", target="edge.vendor.example", *, path=None):
        self.cname(domain, targets=(target,), path=path)
        service = self.candidate_service(path)
        service.refresh()
        root = PublicSuffixResolver().parts(target).registrable_domain
        return next(row for row in service.list(status=None, current_only=False)
                    if row.asset_value == domain and row.candidate_domain == root)

    def supplier(self, domain="vendor.example", name="Fixture Supplier", *, path=None):
        return self.supplier_service(path).add(name, domain=domain, relationship_type="cloud",
            criticality="critical", reason="Human supplied inventory fixture").supplier

    def review(self, candidate, decision, supplier=None, *, path=None, reason="Controlled human review"):
        return self.candidate_service(path).review(candidate.id, decision=decision,
            supplier_id=supplier.id if supplier else None, reason=reason)

    def accepted(self):
        candidate, supplier = self.candidate(), self.supplier()
        self.review(candidate, "accepted", supplier)
        return candidate, supplier

    def priorities(self):
        return priority_data(self.service.priorities(indicator_type="domain", value="example.com", limit=100))

    def history(self):
        return ResearchHistoryService(SQLiteResearchHistoryRepository(self.path), self.service)

    def sql(self, query, parameters=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute(query, parameters).fetchall()

    def links(self, graph=None):
        return [edge for edge in (graph or self.graph(limit=100))["edges"]
                if edge["relationship_type"] == "human_supplier_link"]

    def candidate_node(self, graph=None):
        return next(node for node in (graph or self.graph(limit=100))["nodes"] if node["kind"] == "supplier_candidate")

    def test_pending_candidate_is_never_an_approved_supplier_and_keeps_cname_provenance(self):
        candidate = self.candidate()
        details = self.candidates.show(candidate.id)
        before = self.files()
        graph = self.graph(limit=100)
        self.assertEqual(self.links(graph), [])
        self.assertFalse(any(row["kind"] == "supplier" for row in graph["nodes"]))
        node = self.candidate_node(graph)
        self.assertEqual(node["value"], candidate.id)
        self.assertEqual(node["evidence"][0]["status"], "pending")
        proof = next(row for row in node["evidence"] if row["record_type"] == "supplier_candidate_evidence")
        self.assertEqual(proof["event_id"], details.evidence[0].id)
        self.assertEqual(proof["source_reference"], details.evidence[0].source_evidence_id)
        self.assertEqual(proof["state_sha256"], details.evidence[0].state_sha256)
        self.assertEqual(proof["kind"], "candidate_context")
        self.assertEqual(self.files(), before)

    def test_acceptance_is_human_decision_with_original_event_and_supplier_reference(self):
        candidate, supplier = self.accepted()
        decision = self.candidates.show(candidate.id).resolutions[-1]
        graph = self.graph(limit=100)
        link = self.links(graph)[0]
        self.assertEqual(link["kind"], "human_decision")
        row = link["evidence"][0]
        self.assertEqual((row["record_id"], row["event_id"], row["source_reference"]),
                         (decision.id, decision.id, candidate.id))
        self.assertEqual((row["status"], row["current"], row["time_basis"]), ("accepted", True, "decision_recorded_at"))
        node = next(row for row in graph["nodes"] if row["kind"] == "supplier")
        self.assertEqual(node["references"][0], {"kind": "supplier", "record_type": "supplier",
            "namespace": "local-suppliers", "record_id": supplier.id})
        self.assertEqual(graph["model_version"], 3)
        reasons = {reason["code"] for item in self.priorities()["items"] for reason in item["reasons"]}
        self.assertNotIn("active_indicator_claim", reasons)
        self.assertNotIn("supplier_review_pending", reasons)

    def test_rejected_or_uncertain_without_prior_acceptance_never_creates_supplier_link(self):
        candidate = self.candidate()
        for decision in ("rejected", "uncertain", "pending"):
            with self.subTest(decision=decision):
                self.review(candidate, decision)
                graph = self.graph(limit=100)
                self.assertEqual(self.links(graph), [])
                human = [row for row in self.candidate_node(graph)["evidence"] if row["kind"] == "human_decision"]
                self.assertEqual((human[0]["status"], human[0]["current"]), (decision, True))
                self.assertTrue(all(not row["current"] for row in human[1:]))
                item = next(row for row in self.priorities()["items"] if row["record_type"] == "supplier_candidate" and row["subject_kind"] == "node")
                reasons = {row["code"] for row in item["reasons"]}
                self.assertEqual("supplier_review_pending" in reasons, decision in {"pending", "uncertain"})

    def test_rejection_retains_old_acceptance_but_marks_latest_binding_withdrawn(self):
        candidate, _ = self.accepted()
        before = self.links()[0]
        self.at += timedelta(hours=1)
        self.review(candidate, "rejected")
        latest = self.candidates.show(candidate.id).resolutions[-1]
        after = self.links()[0]
        self.assertEqual(before["id"], after["id"])
        self.assertEqual([row["status"] for row in after["evidence"]], ["withdrawn", "accepted"])
        self.assertEqual([row["current"] for row in after["evidence"]], [True, False])
        self.assertEqual(after["evidence"][0]["record_id"], latest.id)
        self.assertIn("rejected", after["evidence"][0]["description"])
        item = next(row for row in self.priorities()["items"] if row["id"] == after["id"])
        self.assertIn("supplier_link_withdrawn", {row["code"] for row in item["reasons"]})

    def test_provider_replacement_and_reacceptance_keep_separate_binding_histories(self):
        candidate, first = self.accepted()
        second = self.supplier("other-vendor.example", "Another Supplier")
        self.review(candidate, "accepted", second)
        graph = self.graph(limit=100)
        names = {node["id"]: node["value"] for node in graph["nodes"]}
        links = {names[link["target_id"]]: link for link in self.links(graph)}
        self.assertEqual(links[first.id]["evidence"][0]["status"], "withdrawn")
        self.assertEqual(links[second.id]["evidence"][0]["status"], "accepted")
        self.assertEqual(links[first.id]["evidence"][0]["event_id"], links[second.id]["evidence"][0]["event_id"])
        self.review(candidate, "accepted", first)
        graph = self.graph(limit=100)
        names = {node["id"]: node["value"] for node in graph["nodes"]}
        links = {names[link["target_id"]]: link for link in self.links(graph)}
        self.assertEqual([row["status"] for row in links[first.id]["evidence"]], ["accepted", "withdrawn", "accepted"])
        self.assertEqual(links[second.id]["evidence"][0]["status"], "withdrawn")

    def test_reopened_candidate_is_not_current_approval(self):
        candidate, _ = self.accepted()
        self.review(candidate, "pending")
        self.assertEqual(self.links()[0]["evidence"][0]["status"], "withdrawn")
        self.assertEqual(self.candidate_node()["evidence"][0]["status"], "pending")

    def test_disappearing_technical_evidence_does_not_fabricate_human_withdrawal(self):
        candidate, _ = self.accepted()
        self.cname(alias="absent")
        self.candidates.refresh()
        graph = self.graph(limit=100)
        state = self.candidate_node(graph)["evidence"][0]
        self.assertFalse(state["current"])
        self.assertEqual(state["status"], "accepted")
        self.assertEqual(self.links(graph)[0]["evidence"][0]["status"], "accepted")
        self.assertEqual(self.candidates.show(candidate.id).total_resolution_count, 1)
        reasons = {r["code"] for item in self.priorities()["items"] for r in item["reasons"]}
        self.assertIn("supplier_dependency_historical", reasons)
        self.assertNotIn("supplier_link_withdrawn", reasons)

    def test_research_does_not_silently_refresh_stored_candidate_currency(self):
        self.accepted()
        self.cname(alias="absent")
        before = self.files()
        graph = self.graph(limit=100)
        self.assertTrue(self.candidate_node(graph)["evidence"][0]["current"])
        self.assertIn("son aday yenilemesinde", self.candidate_node(graph)["evidence"][0]["description"])
        self.assertEqual(self.files(), before)

    def test_supplier_revocation_is_separate_from_candidate_acceptance(self):
        candidate, supplier = self.accepted()
        self.suppliers.revoke(supplier.id, reason="Inventory disabled by human")
        graph = self.graph(limit=100)
        node = next(row for row in graph["nodes"] if row["kind"] == "supplier")
        self.assertEqual(node["evidence"][0]["status"], "revoked")
        self.assertTrue(node["evidence"][0]["current"])
        self.assertEqual(self.links(graph)[0]["evidence"][0]["status"], "accepted")
        self.assertEqual(self.candidates.show(candidate.id).candidate.status, "accepted")
        reasons = {r["code"] for item in self.priorities()["items"] for r in item["reasons"]}
        self.assertIn("supplier_inventory_inactive", reasons)

    def test_supplier_rename_preserves_identity_and_original_decision_snapshots(self):
        _, supplier = self.accepted()
        self.suppliers.update(supplier.id, name="Renamed Provider", reason="Human rename fixture")
        node = next(row for row in self.graph(limit=100)["nodes"] if row["kind"] == "supplier")
        self.assertEqual(node["value"], supplier.id)
        self.assertEqual(node["label"], "Renamed Provider")
        self.assertIn("Fixture Supplier", node["evidence"][-1]["description"])

    def test_candidate_domain_and_manually_linked_supplier_domain_stay_distinct(self):
        candidate = self.candidate()
        supplier = self.supplier("holding.example", "Holding Fixture")
        self.review(candidate, "accepted", supplier)
        graph = self.graph(limit=100)
        values = {node["value"] for node in graph["nodes"]}
        self.assertTrue({"vendor.example", "holding.example", candidate.id, supplier.id} <= values)
        inventory = next(row for row in graph["edges"] if row["relationship_type"] == "supplier_registered_domain")
        self.assertEqual(inventory["kind"], "human_decision")

    def test_reverse_supplier_domain_finds_customer_domain_in_two_hops(self):
        _, supplier = self.accepted()
        graph = self.graph(supplier.primary_domain, limit=100)
        nodes = {node["id"]: node["value"] for node in graph["nodes"]}
        self.assertTrue(any([nodes[key] for key in path["node_ids"]] ==
            [supplier.primary_domain, supplier.id, "example.com"] for path in graph["paths"]))

    def test_inventory_alone_does_not_link_unrelated_customer_or_merge_same_name(self):
        first = self.supplier()
        second = self.supplier("second.example", "Fixture Supplier")
        self.dns()
        self.assertFalse(any(row["kind"] == "supplier" for row in self.graph()["nodes"]))
        graph = self.graph(first.primary_domain)
        self.assertIn(first.id, {row["value"] for row in graph["nodes"]})
        self.assertNotIn(second.id, {row["value"] for row in graph["nodes"]})
        self.assertEqual(self.links(graph), [])

    def test_old_human_decisions_are_not_network_staleness_or_threat_votes(self):
        supplier = self.supplier()
        self.at += timedelta(days=100)
        result = priority_data(self.service.priorities(indicator_type="domain", value=supplier.primary_domain))
        node = next(item for item in result["items"] if item["record_type"] == "supplier")
        self.assertEqual(node["evidence"][0]["freshness"], "stale")
        self.assertEqual([r["code"] for r in node["reasons"]], ["recorded_context"])

    def test_candidate_and_lifecycle_budgets_skip_unverified_records_with_partial_scope(self):
        self.accepted()
        for constant in ("MAX_SUPPLIER_AUDIT_ROWS", "MAX_SUPPLIER_AUDIT_BYTES"):
            with self.subTest(constant=constant), patch("xti.adapters.sqlite_research_suppliers." + constant, 1):
                graph = self.graph()
                self.assertEqual(graph["status"], "partial")
                self.assertIn("supplier_read_budget", graph["limitations"])
                self.assertFalse(any(row["kind"] in {"supplier", "supplier_candidate"} for row in graph["nodes"]))
                root_coverage = next(row for row in graph["coverage"] if row["kind"] == "supplier_candidates" and row["scope"] == ["domain", "example.com"])
                self.assertFalse(root_coverage["complete"])
                self.assertEqual(root_coverage["examined_count"], 0)

    def test_large_unrelated_catalog_is_not_loaded_or_counted_as_selected_history(self):
        self.accepted()
        for index in range(4):
            self.supplier(f"unrelated-{index}.example", f"Unrelated {index}")
        with patch("xti.adapters.sqlite_supplier_history.MAX_SUPPLIERS", 1), \
             patch("xti.adapters.sqlite_supplier_history.MAX_SUPPLIER_EVENTS", 1):
            graph = self.graph(limit=100)
        self.assertEqual(len(self.links(graph)), 1)
        self.assertNotIn("supplier_read_budget", graph["limitations"])

    def test_scoped_lifecycle_is_not_a_whole_workspace_watermark(self):
        supplier = self.supplier()
        with closing(sqlite3.connect(self.path)) as connection:
            history = read_supplier_history(connection, supplier_id=supplier.id)
        self.assertFalse(history.complete)
        with self.assertRaisesRegex(ValueError, "complete supplier history"):
            supplier_scope(history, supplier.id)

    def test_missing_supplier_lifecycle_entry_is_rejected(self):
        _, supplier = self.accepted()
        self.suppliers.update(supplier.id, name="New Name", reason="Human update fixture")
        self.sql("DELETE FROM supplier_events WHERE action='added'")
        with self.assertRaises(StorageError):
            self.graph()

    def test_corrupt_supplier_identity_is_storage_error_not_bad_user_input(self):
        supplier = self.supplier()
        self.sql("UPDATE suppliers SET id='broken-identity' WHERE id=?", (supplier.id,))
        self.sql("UPDATE supplier_events SET supplier_id='broken-identity' WHERE supplier_id=?", (supplier.id,))
        with self.assertRaises(StorageError):
            self.graph(supplier.primary_domain)

    def test_historical_supplier_reference_and_candidate_scope_are_audited(self):
        candidate, supplier = self.accepted()
        self.review(candidate, "rejected")
        self.sql("DELETE FROM suppliers WHERE id=?", (supplier.id,))
        with self.assertRaises(StorageError):
            self.graph("vendor.example")

    def test_candidate_projection_and_cname_hash_corruption_fail_closed(self):
        candidate = self.candidate()
        self.sql("UPDATE supplier_candidates SET status='uncertain',resolution_reason='Forged decision' WHERE id=?", (candidate.id,))
        with self.assertRaises(StorageError):
            self.graph()
        self.sql("UPDATE supplier_candidates SET status='pending',resolution_reason=NULL WHERE id=?", (candidate.id,))
        self.sql("UPDATE surface_cname_checks SET state_sha256=?", ("0" * 64,))
        with self.assertRaises(StorageError):
            self.graph()

    def test_byte_budget_is_checked_before_candidate_history_materialization(self):
        self.candidate()
        self.sql("UPDATE supplier_candidate_resolution_events SET reason='unused'")
        with patch("xti.adapters.sqlite_research_suppliers.MAX_SUPPLIER_AUDIT_BYTES", 1), \
             patch.object(SQLiteSupplierCandidateRepository, "_validated_details", side_effect=AssertionError("Must bound before decoding")):
            self.assertIn("supplier_read_budget", self.graph()["limitations"])

    def test_adjacency_and_evidence_caps_are_explicit_and_preserve_latest_decision(self):
        candidate, supplier = self.accepted()
        self.review(candidate, "rejected")
        self.review(candidate, "accepted", supplier)
        with patch("xti.adapters.sqlite_research_suppliers.MAX_SHOWN_EVIDENCE", 1):
            graph = self.graph(limit=100)
        link = self.links(graph)[0]
        self.assertEqual((len(link["evidence"]), link["evidence_total_count"]), (1, 3))
        self.assertTrue(link["evidence"][0]["current"])
        self.assertIn("source_evidence_limit", graph["limitations"])
        with patch("xti.adapters.sqlite_research_suppliers.MAX_SUPPLIER_ADJACENCY", 1):
            self.assertIn("supplier_adjacency_limit", self.graph()["limitations"])

    def test_review_changes_invalidate_page_snapshot(self):
        candidate, _ = self.accepted()
        graph = self.graph(limit=1)
        self.review(candidate, "rejected")
        with self.assertRaises(ResearchSnapshotChanged):
            self.graph(limit=1, offset=1, expected_snapshot=graph["snapshot_id"])

    def test_single_read_snapshot_during_supplier_and_decision_writes(self):
        candidate, supplier = self.accepted()
        self.sql("PRAGMA journal_mode=WAL")
        original, changed = _Reader.neighbors, []

        def concurrent(reader, key):
            if not changed:
                changed.append(True)
                self.review(candidate, "rejected")
                self.suppliers.update(supplier.id, name="Concurrent Name", reason="Concurrent rename fixture")
            return original(reader, key)

        with patch.object(_Reader, "neighbors", concurrent):
            graph = self.graph(limit=100)
        self.assertEqual(self.links(graph)[0]["evidence"][0]["status"], "accepted")
        self.assertNotIn("Concurrent Name", {node["label"] for node in graph["nodes"]})
        self.assertEqual(self.links()[0]["evidence"][0]["status"], "withdrawn")

    def test_human_decision_change_is_evidence_change_not_clock_or_ioc_withdrawal(self):
        candidate, _ = self.accepted()
        history = self.history()
        first = history.record(indicator_type="domain", value="example.com")
        original = history.show(first["review"]["id"], view="items", limit=100)
        self.review(candidate, "rejected")
        second = history.record(indicator_type="domain", value="example.com")
        changes = history.show(second["review"]["id"])["changes"]
        self.assertTrue(changes)
        self.assertEqual({row["origin"] for row in changes}, {"evidence_or_mixed"})
        self.assertTrue(all(row["withdrawn_assertion_ids"] == [] for row in changes))
        self.assertEqual(history.show(first["review"]["id"], view="items", limit=100), original)

    def test_v1_history_remains_readable_and_v2_rejects_ambiguous_downgrade(self):
        repository = SQLiteResearchHistoryRepository(self.path)
        snapshot = freeze(priority_data(self.service.full_priorities(indicator_type="domain", value="example.com")))
        snapshot["model_version"] = 1
        snapshot["policy_version"] = "research-priority-v2"
        for item in snapshot['items']:
            item.pop('discovery')
        previous, _ = repository.append(capture_scope(indicator_type="domain", value="example.com"), snapshot, "old-v1", None)
        old = deepcopy(repository.show(previous.header.id))
        self.accepted()
        current = self.history().record(indicator_type="domain", value="example.com")
        self.assertEqual(current["review"]["comparison"]["state"], "policy_baseline")
        self.assertEqual(repository.show(previous.header.id), old)
        new = freeze(priority_data(self.service.full_priorities(indicator_type="domain", value="example.com")))
        self.assertEqual(new["model_version"], 3)
        new["model_version"] = 1
        with self.assertRaises(ValidationError):
            validate_snapshot(new)

    def test_fifty_decisions_keep_latest_human_and_technical_evidence_within_capture_bound(self):
        candidate, supplier = self.accepted()
        for index in range(52):
            self.review(candidate, "accepted", supplier, reason=f"Controlled decision number {index}")
        result = self.history().record(indicator_type="domain", value="example.com")
        stored = self.history().show(result["review"]["id"], view="items", limit=100)
        node = next(row for row in stored["evaluation"]["items"] if row["subject_kind"] == "node" and row["record_type"] == "supplier_candidate")
        self.assertEqual(len(node["evidence"]), 52)
        self.assertGreater(node["evidence_total_count"], 52)
        self.assertTrue(node["evidence"][1]["current"])
        self.assertEqual(node["evidence"][2]["record_type"], "supplier_candidate_evidence")
        self.assertFalse(stored["evaluation"]["coverage_complete"])

    def test_model_two_rejects_decision_relabeling_as_source_observation_or_claim(self):
        self.accepted()
        snapshot = freeze(priority_data(self.service.full_priorities(indicator_type="domain", value="example.com")))
        for field, value in (("time_basis", "source_observation"), ("assertion_id", "fake-claim"),
                             ("confidence", 99), ("event_id", None), ("current", None)):
            with self.subTest(field=field):
                corrupted = deepcopy(snapshot)
                row = next(row for item in corrupted["items"] for row in item["evidence"] if row["kind"] == "human_decision")
                row[field] = value
                with self.assertRaises(ValidationError):
                    validate_snapshot(corrupted)

    def test_model_change_alone_starts_baseline_instead_of_mixing_semantics(self):
        from xti.domain.research_history import compare
        snapshot = freeze(priority_data(self.service.full_priorities(indicator_type="domain", value="example.com")))
        old = deepcopy(snapshot)
        old["model_version"] = 1
        self.assertEqual(compare(old, snapshot)["state"], "policy_baseline")

    def test_cli_engine_details_and_record_get_use_selected_workspace_offline(self):
        self.accepted()
        before = self.files()
        code, out, err = self.invoke(["--data-dir", str(self.data), "engine"], self.request(limit=100))
        self.assertEqual((code, err), (0, ""), out)
        graph = json.loads(out)["data"]
        self.assertEqual(graph["model_version"], 3)
        lines = research_lines(graph, data_dir=self.data) + priority_lines(self.priorities(), data_dir=self.data)
        self.assertTrue(any("Karar:" in line and "son karar" in line for line in lines))
        commands = {line.split("Ayrıntı: ", 1)[1] for line in lines if "Ayrıntı: " in line}
        for command in commands:
            code, out, err = self.invoke(shlex.split(command)[1:])
            self.assertEqual((code, err), (0, ""), out)
        ref = next(node["references"][0] for node in graph["nodes"] if node["kind"] == "supplier")
        code, out, err = self.invoke(["--data-dir", str(self.data), "engine"],
            {**self.request(), "operation": "record.get", "parameters": {"reference": ref}})
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(self.files(), before)

    def test_company_isolation_and_history_backup_preserve_human_provenance(self):
        root = self.root / "companies"
        first = provision_company_workspace(root, "first")
        second = provision_company_workspace(root, "second")
        for context in (first, second):
            SQLiteAssetRepository(context.database).initialize()
            initialize_jobs(context)
            candidate = self.candidate(path=context.database)
            supplier = self.supplier(name=context.company_id + " Supplier", path=context.database)
            self.review(candidate, "accepted", supplier, path=context.database)
        code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", "first"], self.request())
        self.assertEqual((code, err), (0, ""), out)
        self.assertIn("first Supplier", out)
        self.assertNotIn("second Supplier", out)
        self.accepted()
        original = self.history().record(indicator_type="domain", value="example.com")
        backup = self.root / "supplier-review.db"
        SQLiteAssetRepository(self.path).backup(backup)
        service = ResearchService(SQLiteResearchRepository(backup), clock=lambda: self.at)
        restored = ResearchHistoryService(SQLiteResearchHistoryRepository(backup), service)
        self.assertEqual(restored.show(original["review"]["id"], view="items", limit=100),
                         self.history().show(original["review"]["id"], view="items", limit=100))

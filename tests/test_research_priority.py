"""Explainable review order, lifecycle/time changes and read-only scoped delivery."""

from contextlib import closing, contextmanager, redirect_stdout
from datetime import timedelta
from io import StringIO
import json
import shlex
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import resolve_company_workspace
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_enrichment import SQLiteEnrichmentRepository
from xti.adapters.sqlite_research import SQLiteResearchRepository, _Reader
from xti.adapters.sqlite_warninglists import SQLiteWarninglistRepository
from xti.application.indicator_enrichment import EnrichmentService
from xti.application.research import ResearchService, priority_data
from xti.application.warninglists import WarninglistService
from xti.domain.assets import ValidationError
from xti.domain.research import ResearchSnapshotChanged
from xti.interfaces.cli import main
from xti.interfaces.research import priority_lines
from xti.ports.discovery import SourceError
from tests.test_research import ResearchFixture, NOW, IP
from tests.test_indicator_enrichment import Source, HASH, URL, url_body, encoded
from tests.test_warninglists import Source as ListSource


def codes(item):
    return {reason["code"] for reason in item["reasons"]}


class ResearchPriorityTests(ResearchFixture, unittest.TestCase):
    def priorities(self, value="example.com", kind="domain", **options):
        return priority_data(self.service.priorities(indicator_type=kind, value=value, **options))

    def request(self, **parameters):
        return {"contract_version": 1, "request_id": "priorities-1", "operation": "research.priorities",
                "parameters": {"indicator_type": "domain", "value": "example.com", **parameters}}

    def source_claim(self, source, **changes):
        return self.iocs.add("ipv4", IP, source_name=source, source_reference="report:" + source,
            confidence=changes.pop("confidence", 60), description="Controlled source claim", **changes)

    def test_full_neighborhood_ranked_before_paging_and_reasons_have_real_evidence(self):
        self.dns()
        ioc = self.ioc()
        self.relation(self.entity(), indicator=ioc)
        before = self.files()
        result = self.priorities(limit=1)
        self.assertEqual(result["collected_item_count"], 5)
        first = result["items"][0]
        self.assertEqual((first["value"], first["priority"]), (IP, "review_first"))
        self.assertIn("active_indicator_claim", codes(first))
        self.assertEqual(first["evidence"][0]["assertion_id"], ioc.assertion.id)
        self.assertTrue(result["has_more"])
        full = self.priorities()
        for item in full["items"]:
            ids = {row["id"] for row in item["evidence"]}
            for reason in item["reasons"]:
                self.assertLessEqual(set(reason["evidence_ids"]), ids)
        self.assertNotIn("risk_score", json.dumps(full))
        self.assertEqual(before, self.files())

    def test_page_order_totals_and_out_of_range_do_not_depend_on_path_page(self):
        self.dns()
        self.relation(self.entity(), indicator=self.ioc())
        full = self.priorities()
        pages = [self.priorities(offset=index, limit=1, expected_snapshot=full["snapshot_id"])
                 for index in range(full["collected_item_count"] + 1)]
        self.assertEqual([item for page in pages for item in page["items"]], full["items"])
        self.assertEqual(pages[-1]["items"], [])
        self.assertFalse(pages[-1]["has_more"])
        self.assertTrue(all(page["priority_counts"] == full["priority_counts"] for page in pages))

    def test_stale_active_expired_and_revoked_are_separate(self):
        self.ioc()
        self.at += timedelta(days=2)
        old = self.priorities(IP, "ip")["items"][0]
        self.assertEqual(old["priority"], "verify")
        self.assertIn("stale_active_indicator", codes(old))
        self.source_claim("expires", valid_until=(self.at - timedelta(hours=1)).isoformat())
        self.iocs.revoke(old["evidence"][0]["assertion_id"], reason="Analyst withdrawal fixture")
        final = self.priorities(IP, "ip")["items"][0]
        self.assertEqual(final["priority"], "context")
        self.assertIn("inactive_claims_only", codes(final))
        self.assertNotIn("source_status_difference", codes(final))
        self.assertEqual({row["status"] for row in final["evidence"]}, {"revoked", "expired"})

    def test_source_state_difference_preserves_both_claims_without_voting(self):
        first = self.source_claim("first", confidence=1)
        second = self.source_claim("second", confidence=100)
        self.iocs.revoke(second.assertion.id, reason="Different source withdrew its claim")
        item = self.priorities(IP, "ip")["items"][0]
        self.assertIn("source_status_difference", codes(item))
        reason = next(row for row in item["reasons"] if row["code"] == "source_status_difference")
        self.assertEqual(set(reason["evidence_ids"]), {row["id"] for row in item["evidence"]})
        self.assertEqual({row["confidence"] for row in item["evidence"]}, {1, 100})
        self.assertTrue(next(row for row in item["evidence"] if row["assertion_id"] == first.assertion.id)["current"])
        self.assertIn("tek başına", reason["message"])

    def test_two_actors_or_same_source_history_do_not_fabricate_conflict(self):
        self.dns()
        ioc = self.ioc()
        self.relation(self.entity("Actor A"), indicator=ioc, source="one")
        self.relation(self.entity("Actor B"), indicator=ioc, source="two")
        self.assertTrue(all("source_status_difference" not in codes(item) for item in self.priorities()["items"]))

    def test_source_confidence_does_not_change_priority(self):
        low = self.source_claim("fixture", confidence=1)
        before = self.priorities(IP, "ip")["items"][0]
        high = self.source_claim("fixture", confidence=100)
        after = self.priorities(IP, "ip")["items"][0]
        self.assertEqual(low.assertion.id, high.assertion.id)
        self.assertEqual((before["priority"], codes(before)), (after["priority"], codes(after)))
        self.assertEqual(after["evidence"][0]["confidence"], 100)

    def test_duplicate_claim_does_not_duplicate_item_or_add_priority(self):
        self.dns()
        actor, ioc = self.entity(), self.ioc()
        first = self.relation(actor, indicator=ioc)
        initial = self.priorities()
        for _ in range(3):
            self.assertEqual(self.relation(actor, indicator=ioc).relationship.id, first.relationship.id)
        updated = self.priorities()
        self.assertEqual(initial, updated)

    def test_response_size_cap_and_invalid_clock_remain_errors(self):
        with patch("xti.interfaces.engine.MAX_RESPONSE_BYTES", 2000):
            code, out, err = self.invoke(["--data-dir", str(self.data), "engine"], self.request())
        self.assertEqual((code, err), (1, ""), out)
        self.assertEqual(json.loads(out)["error"]["code"], "response_too_large")
        for clock in (lambda: NOW.replace(tzinfo=None), lambda: "not a datetime"):
            with self.subTest(clock=clock), self.assertRaises(ValidationError):
                ResearchService(SQLiteResearchRepository(self.path), clock=clock).priorities(
                    indicator_type="domain", value="example.com")

    def test_terminal_preserves_literal_markup_and_escapes_controls(self):
        self.dns()
        actor = self.entity("[bold]Controlled actor[/bold]")
        self.relation(actor, indicator=self.ioc())
        data = self.priorities()
        lines = "\n".join(priority_lines(data, data_dir=self.data))
        self.assertIn("[bold]Controlled actor[/bold]", lines)
        # Defensive rendering even if an upstream caller supplies raw controls.
        data["items"][0]["label"] = "\x1b[31mControlled actor\x1b[0m\nInjected"
        lines = "\n".join(priority_lines(data, data_dir=self.data))
        self.assertNotIn("\x1b", lines)
        self.assertNotIn("\nInjected", lines)
        self.assertIn("\\u001b", lines)

    def test_fresh_dns_repeat_clears_stale_priority_without_losing_old_evidence(self):
        old = self.dns(observed=NOW - timedelta(days=3))
        initial = self.priorities()
        self.assertTrue(any("stale_evidence" in codes(item) for item in initial["items"]))
        new = self.dns()
        result = self.priorities()
        edge = next(item for item in result["items"] if item["subject_kind"] == "relationship")
        self.assertNotIn("stale_evidence", codes(edge))
        self.assertEqual({row["record_id"] for row in edge["evidence"]}, {old.id, new.id})
        self.assertTrue(all(item["priority"] == "context" for item in result["items"]))

    def test_context_with_direct_evidence_precedes_link_only_nodes(self):
        self.dns()
        data = self.priorities()
        last = data["items"][-1]
        self.assertEqual(last["value"], IP)
        self.assertIn("relationship_context_only", codes(last))
        self.assertTrue(all(item["evidence"] for item in data["items"][:-1]))
        self.assertIn("ek inceleme gerekçesi çıkmadı", "\n".join(priority_lines(data)))

    def test_latest_failure_keeps_old_dns_as_separate_evidence(self):
        old = self.dns(observed=NOW - timedelta(days=3))
        failure = self.dns(failed=True)
        result = self.priorities()
        root = next(item for item in result["items"] if item["id"] == result["root_id"])
        self.assertIn("latest_check_failed", codes(root))
        self.assertEqual(root["evidence"][0]["record_id"], failure.id)
        edge = next(item for item in result["items"] if item["subject_kind"] == "relationship")
        self.assertEqual(edge["evidence"][0]["record_id"], old.id)
        self.assertIn("stale_evidence", codes(edge))

    def test_future_timestamp_is_not_current_confirmation(self):
        self.dns(observed=NOW + timedelta(seconds=1))
        result = self.priorities()
        self.assertEqual(result["items"][0]["priority"], "review_first")
        self.assertIn("future_evidence_time", codes(result["items"][0]))
        self.assertEqual(result["items"][0]["evidence"][0]["freshness"], "future")

    def test_missing_evidence_is_visible_without_clean_verdict_or_write(self):
        before = self.files()
        data = self.priorities()
        self.assertEqual(data["status"], "not_recorded")
        self.assertEqual(data["collected_item_count"], 1)
        self.assertEqual(data["items"][0]["priority"], "verify")
        self.assertIn("evidence_missing", codes(data["items"][0]))
        self.assertEqual(before, self.files())
        SQLiteAssetRepository(self.path).add("example.com")
        self.assertEqual(self.priorities()["status"], "no_relationships")

    def test_time_threshold_changes_snapshot_and_policy_parameters_are_guarded(self):
        self.ioc()
        first = self.priorities(IP, "ip")
        self.at += timedelta(hours=24)
        boundary = self.priorities(IP, "ip", expected_snapshot=first["snapshot_id"])
        self.assertEqual(boundary["items"][0]["priority"], "review_first")
        self.at += timedelta(seconds=1)
        with self.assertRaises(ResearchSnapshotChanged):
            self.priorities(IP, "ip", expected_snapshot=first["snapshot_id"])
        self.assertIn("stale_active_indicator", codes(self.priorities(IP, "ip")["items"][0]))
        with self.assertRaises(ResearchSnapshotChanged):
            self.priorities(IP, "ip", stale_after_hours=48, expected_snapshot=first["snapshot_id"])

    def test_refresh_or_withdrawal_changes_guard_and_recomputes_priority(self):
        ioc = self.ioc()
        first = self.priorities(IP, "ip")
        self.iocs.revoke(ioc.assertion.id, reason="Withdraw for review fixture")
        with self.assertRaises(ResearchSnapshotChanged):
            self.priorities(IP, "ip", expected_snapshot=first["snapshot_id"])
        self.assertEqual(self.priorities(IP, "ip")["items"][0]["priority"], "context")

    def test_warninglist_context_does_not_silence_active_ioc(self):
        value = "104.21.6.71"
        self.ioc(value)
        source = ListSource()
        lists = WarninglistService(SQLiteWarninglistRepository(self.path), source, clock=lambda: self.at)
        run = lists.sync(["cloudflare"])["runs"][0]
        before = self.files()
        item = self.priorities(value, "ip")["items"][0]
        self.assertEqual(item["priority"], "review_first")
        self.assertIn("indicator_with_list_context", codes(item))
        self.assertEqual(item["warninglist_matches"][0]["run_id"], run["id"])
        self.assertTrue(item["evidence"][0]["current"])
        self.assertEqual(before, self.files())

    def test_url_old_archive_and_hash_response_times_keep_distinct_meanings(self):
        source = Source()
        enrich = EnrichmentService(SQLiteEnrichmentRepository(self.path), source, clock=lambda: self.at)
        enrich.refresh(indicator_type="sha256", value=HASH)
        file_context = self.priorities(HASH, "sha256")
        self.assertTrue(all(item["priority"] == "context" for item in file_context["items"]))
        self.assertTrue(all(row["time_basis"] == "response_received_at" for item in file_context["items"] for row in item["evidence"]))
        source.content = url_body(has_more=True)
        enrich.refresh(indicator_type="url", value=URL)
        archive = self.priorities(URL, "url")
        self.assertIn("enrichment_result_window", archive["limitations"])
        edges = [item for item in archive["items"] if item["subject_kind"] == "relationship"]
        self.assertTrue(all("stale_evidence" in codes(item) for item in edges))
        self.assertTrue(all(row["time_basis"] == "source_observation" for item in edges for row in item["evidence"]))

    def test_failed_enrichment_retains_old_absence_and_age_even_without_edges(self):
        source = Source()
        source.status, source.content = 404, encoded({"message": "Non existing SHA-256", "query": HASH})
        enrich = EnrichmentService(SQLiteEnrichmentRepository(self.path), source, clock=lambda: self.at)
        good = enrich.refresh(indicator_type="sha256", value=HASH)["run"]
        self.at += timedelta(days=2)
        source.error = SourceError("Controlled timeout")
        failed = enrich.refresh(indicator_type="sha256", value=HASH)["run"]
        item = self.priorities(HASH, "sha256")["items"][0]
        self.assertLessEqual({"source_lookup_failed", "source_no_match", "stale_evidence"}, codes(item))
        self.assertEqual({row["record_id"] for row in item["evidence"]}, {good["id"], failed["id"]})
        self.assertEqual(item["enrichment"]["successful_run"]["id"], good["id"])
        self.assertEqual(item["enrichment"]["source"]["id"], "circl")

    def test_limits_and_truncated_evidence_never_imply_full_coverage(self):
        self.dns()
        self.dns()
        self.dns("other.example")
        for options, expected in (({"node_limit": 2}, "node_limit"), ({"edge_limit": 1}, "edge_limit")):
            with self.subTest(options=options):
                result = self.priorities(**options)
                self.assertIn(expected, result["limitations"])
                self.assertFalse(result["coverage_complete"])
        with patch("xti.adapters.sqlite_research.MAX_SHOWN_SOURCES", 1):
            data = self.priorities()
        self.assertIn("source_evidence_limit", data["limitations"])
        self.assertTrue(any("evidence_truncated" in codes(item) for item in data["items"]))

    def test_cli_and_engine_share_same_explanation_and_safe_selected_detail_commands(self):
        self.dns()
        self.relation(self.entity(), indicator=self.ioc())
        before = self.files()
        with patch.object(ResearchService, "_now", return_value=NOW.isoformat()):
            code, out, err = self.invoke(["--data-dir", str(self.data), "--json", "research", "example.com", "--type", "domain", "--priorities"])
            self.assertEqual((code, err), (0, ""), out)
            cli = json.loads(out)["data"]
            code, out, err = self.invoke(["--data-dir", str(self.data), "engine"], self.request())
            self.assertEqual((code, err), (0, ""), out)
            self.assertEqual(cli, json.loads(out)["data"])
            text = "\n".join(priority_lines(self.priorities(limit=1), data_dir=self.data))
            self.assertIn("Önce incele", text)
            self.assertIn("Sonraki sayfa:", text)
            for line in text.splitlines():
                if any(key in line for key in ("Ayrıntı: ", "Sonraki sayfa: ", "Kanıt yolları: ")):
                    command = shlex.split(line.split(": ", 1)[1])[1:]
                    self.assertEqual(command[:2], ["--data-dir", str(self.data)])
                    code, out, err = self.invoke(command)
                    self.assertEqual((code, err), (0, ""), out)
        self.assertEqual(before, self.files())

    def test_contract_validation_manifest_and_changed_snapshot_errors(self):
        args = ["--data-dir", str(self.data), "engine"]
        code, out, err = self.invoke(args + ["--describe"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("research.priorities", json.loads(out)["data"]["operations"])
        for options in ({"company": "other"}, {"data_dir": "/tmp/other"}, {"limit": True}, {"offset": -1},
                        {"node_limit": 101}, {"max_hops": 3}, {"indicator_type": []}, {"stale_after_hours": 0},
                        {"expected_snapshot": "bad"}, {"value": "*.example.com"}):
            code, out, err = self.invoke(args, self.request(**options))
            self.assertEqual((code, err), (2, ""), out)
            self.assertEqual(json.loads(out)["error"]["code"], "invalid_parameters")
        code, out, err = self.invoke(args, self.request(expected_snapshot="0" * 64))
        self.assertEqual((code, err), (1, ""), out)
        self.assertEqual(json.loads(out)["error"]["code"], "snapshot_changed")

    def test_corruption_and_missing_db_fail_closed_without_creation(self):
        check = self.dns()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE surface_checks SET state_sha256=? WHERE id=?", ("0" * 64, check.id))
        with self.assertRaises(StorageError):
            self.priorities()
        missing = self.root / "absent" / "xti.db"
        with self.assertRaises(StorageError):
            ResearchService(SQLiteResearchRepository(missing)).priorities(indicator_type="domain", value="example.com")
        self.assertFalse(missing.parent.exists())

    def test_backup_restore_preserves_priority_and_evidence_ids(self):
        self.dns()
        self.relation(self.entity(), indicator=self.ioc())
        before = self.priorities()
        backup, restored = self.root / "copy.db", self.root / "restored" / "xti.db"
        SQLiteAssetRepository(self.path).backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        after = priority_data(ResearchService(SQLiteResearchRepository(restored), clock=lambda: NOW).priorities(
            indicator_type="domain", value="example.com"))
        self.assertEqual(before, after)

    def test_one_read_snapshot_does_not_mix_concurrent_claim_change(self):
        self.dns()
        ioc = self.ioc()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        original, writes, statements = _Reader.neighbors, [], []
        original_connection = SQLiteAssetRepository._connection

        @contextmanager
        def tracked(storage, **options):
            with original_connection(storage, **options) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        def concurrent(reader, key):
            if not writes:
                writes.append(True)
                self.iocs.revoke(ioc.assertion.id, reason="Concurrent analyst withdrawal")
            return original(reader, key)

        with patch.object(SQLiteAssetRepository, "_connection", tracked), patch.object(_Reader, "neighbors", concurrent):
            data = self.priorities()
        first = next(item for item in data["items"] if item["value"] == IP)
        self.assertIn("active_indicator_claim", codes(first))
        after = next(item for item in self.priorities()["items"] if item["value"] == IP)
        self.assertIn("inactive_claims_only", codes(after))
        self.assertEqual(statements.count("BEGIN"), 1)

    def test_company_priorities_are_isolated_and_disabled_never_falls_back(self):
        root = self.root / "companies"
        for company, domain in (("first", "first.example"), ("second", "second.example")):
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["platform", "provision", "--root", str(root), "--company", company]), 0)
            context = resolve_company_workspace(root, company)
            self.dns(domain, path=context.database)
        before = self.files()
        for company, present, absent in (("first", "first.example", "second.example"),
                                          ("second", "second.example", "first.example")):
            code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", company],
                                         self.request(indicator_type="ip", value=IP))
            self.assertEqual((code, err), (0, ""), out)
            self.assertIn(present, out)
            self.assertNotIn(absent, out)
            self.assertEqual(json.loads(out)["scope"]["mode"], "company-workspace")
        self.assertEqual(before, self.files())
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["platform", "disable", "--root", str(root), "--company", "first"]), 0)
        for company in ("first", "unknown"):
            code, out, err = self.invoke(["platform", "request", "--root", str(root), "--company", company], self.request())
            self.assertNotEqual(code, 0)
            self.assertIsNone(json.loads(out)["data"])


if __name__ == "__main__":
    unittest.main()

"""Explicit public-catalog collection, durable retry and scheduling acceptance."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.hibp_public_notices import parse_hibp_public_notices_response
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.collection_profiles import (
    CollectionProfileDefinition, canonical_definition_json, definition_sha256,
)
from xti.domain.public_notices import HIBP_ATTRIBUTION, HIBP_LICENSE
from xti.ports.discovery import SourceError
from tests import test_collection_watch_cli as fixtures
from tests.test_public_notices import item as public_item


def public_catalog(*records):
    return parse_hibp_public_notices_response(
        json.dumps(records or (public_item(),)).encode(),
        fetched_at=datetime.now(timezone.utc),
    )


class CollectionPublicNoticeCLITests(unittest.TestCase):
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files
    add_social = fixtures.CollectionWatchCLITests.add_social

    def setUp(self):
        fixtures.CollectionWatchCLITests.setUp(self)
        self.catalog = fixtures.ClaimSource(public_catalog(
            public_item("Exact", "example.com"), public_item("Other", "other.example"),
        ))
        self.catalog_factory = self.enterContext(patch(
            "xti.interfaces.cli.HibpPublicNoticeSource", return_value=self.catalog,
        ))

    def collect(self, *extra, expected_code=0):
        return self.result("collect", "example.com", "--task", "notices-hibp", *extra,
                           expected_code=expected_code)

    def receipt(self, history):
        records = [item for item in history["receipts"] if item["result_kind"] == "public_notice_run"]
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]["source_run_id"])
        self.assertEqual(records[0]["source_attribution"], HIBP_ATTRIBUTION)
        self.assertEqual(records[0]["source_license"], HIBP_LICENSE)
        self.assertEqual(records[0]["source_scope"], "global-catalog")
        return records[0]

    def assert_attribution(self, output):
        self.assertIn(HIBP_ATTRIBUTION, output)
        self.assertIn(HIBP_LICENSE, output)

    def test_default_collection_never_constructs_or_fetches_public_catalog(self):
        result = self.result("collect", "example.com")
        self.assertNotIn("notices-hibp", [step["task"]["id"] for step in result["steps"]])
        self.catalog_factory.assert_not_called()
        self.assertEqual(self.catalog.calls, 0)
        self.assertEqual(SQLitePublicNoticeRepository(self.database).status().total_run_count, 0)

    def test_notices_only_profile_plan_is_readonly_and_selection_is_explicit(self):
        saved = self.result("profiles", "save", "Katalog", "example.com", "--task", "notices-hibp")
        self.assertEqual(saved["profile"]["definition"]["task_ids"], ["notices-hibp"])
        before = self.files()
        with patch.object(LocalExecutionLock, "acquire", side_effect=AssertionError("Plan must not acquire writer lock")):
            plan = self.result("collect", "--profile", "katalog", "--plan")
            self.result("profiles", "show", "katalog")
            code, output, error = self.invoke("collect", "--profile", "katalog", "--plan", as_json=False)
        self.assertEqual((code, error), (0, ""))
        self.assertEqual([(task["id"], task["kind"], task["source"]) for task in plan["tasks"]],
                         [("notices-hibp", "public_notice", "hibp")])
        self.assertIn("notices-hibp", output)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.catalog.calls, 0)
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])

    def test_global_catalog_count_attribution_and_exact_receipt_are_not_domain_findings(self):
        collected = self.collect()
        notice = collected["steps"][0]["public_notices"]
        self.assertEqual(notice["run"]["notice_count"], 2)
        self.assertTrue(notice["is_baseline"])
        self.assertEqual(notice["attribution"], HIBP_ATTRIBUTION)
        self.assertEqual(notice["license"], HIBP_LICENSE)
        self.assertEqual(collected["analysis"]["findings"]["total"], 0)
        history = self.result("collections", "show", collected["session_id"])
        receipt = self.receipt(history)
        self.assertEqual(receipt["result_id"], notice["run"]["id"])
        self.assertEqual(receipt["result_status"], "complete")
        self.assertIsNone(receipt["source_run_id"])
        self.assertEqual(receipt["source_attribution"], HIBP_ATTRIBUTION)
        self.assertEqual(receipt["source_license"], HIBP_LICENSE)
        self.assertEqual(receipt["source_scope"], "global-catalog")
        self.assertEqual(dict(receipt["summary"])["notice_count"], 2)
        self.assertEqual(dict(receipt["summary"])["is_baseline"], 1)
        self.assertEqual(history["steps"][0]["kind"], "public_notice")
        self.assertEqual(history["steps"][0]["source"], "hibp")
        before = self.files()
        code, output, error = self.invoke("collections", "show", collected["session_id"], as_json=False)
        self.assertEqual((code, error), (0, ""))
        self.assert_attribution(output)
        self.assertIn("katalo", output.lower())
        self.assertEqual(self.files(), before)
        code, output, error = self.invoke("collect", "example.com", "--task", "notices-hibp", as_json=False)
        self.assertEqual(code, 0, error)
        self.assertIn("Toplama: notices-hibp", error)
        self.assert_attribution(output)
        self.assertIn("katalo", output.lower())
        self.assertIn("domain", output.lower())
        self.assertEqual(self.catalog.calls, 2)

    def test_invalid_mixed_selection_and_profile_overrides_fail_before_fetch_or_write(self):
        self.result("profiles", "save", "Katalog", "example.com", "--task", "notices-hibp")
        before = self.files()
        for arguments in (
            ("collect", "example.com", "--task", "notices-hibp", "--username-watch", str(uuid4())),
            ("collect", "example.com", "--task", "notices-hibp", "--typos"),
            ("collect", "unknown.example", "--task", "notices-hibp"),
            ("collect", "--profile", "Katalog", "--task", "notices-hibp"),
        ):
            with self.subTest(arguments=arguments):
                code, _, _ = self.invoke(*arguments)
                self.assertNotEqual(code, 0)
        self.assertEqual(self.catalog.calls, 0)
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])
        self.assertEqual(self.files(), before)

    def test_successful_catalog_is_retained_when_other_source_is_retried(self):
        self.urlscan.responses["example*"] = SourceError("Arşiv geçici olarak erişilemiyor.")
        first = self.collect("--task", "scan-urlscan", expected_code=3)
        first_history = self.result("collections", "show", first["session_id"])
        receipt = self.receipt(first_history)
        before = self.files()
        plan = self.result("collections", "resume", first["session_id"], "--plan")
        self.assertEqual([unit["step_key"] for unit in plan["units"]], ["scan-urlscan"])
        self.assertEqual(plan["retained"][0]["receipt"], receipt)
        code, output, error = self.invoke("collections", "resume", first["session_id"], "--plan", as_json=False)
        self.assertEqual((code, error), (0, ""))
        self.assert_attribution(output)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.catalog.calls, 1)
        self.urlscan.responses["example*"] = fixtures.batch()
        second = self.result("collections", "resume", first["session_id"])
        self.assertEqual(second["history"]["session"]["status"], "complete")
        self.assertEqual([step["step_key"] for step in second["history"]["steps"]], ["scan-urlscan"])
        self.assertEqual(second["history"]["retained"][0]["receipt"], receipt)
        self.assertEqual(self.catalog.calls, 1)
        self.assertEqual(self.result("collections", "show", first["session_id"]), first_history)
        code, output, error = self.invoke("collections", "show", second["history"]["session"]["id"], as_json=False)
        self.assertEqual((code, error), (0, ""))
        self.assert_attribution(output)

    def test_failed_catalog_preserves_baseline_and_resume_only_retries_catalog(self):
        baseline = self.collect()["steps"][0]["public_notices"]["run"]
        self.catalog.value = SourceError("Katalog kaynağı geçici olarak erişilemiyor.")
        first = self.collect("--task", "scan-urlscan", expected_code=3)
        history = self.result("collections", "show", first["session_id"])
        failure = self.receipt(history)
        self.assertEqual(failure["result_status"], "failed")
        self.assertNotEqual(failure["result_id"], baseline["id"])
        self.assertTrue(all(value == 0 for value in dict(failure["summary"]).values()))
        status = self.result("notices", "status")
        self.assertEqual(status["latest_complete_run"]["id"], baseline["id"])
        plan = self.result("collections", "resume", first["session_id"], "--plan")
        self.assertEqual([unit["step_key"] for unit in plan["units"]], ["notices-hibp"])
        old_scan_calls = list(self.urlscan.calls)
        self.catalog.value = public_catalog(public_item())
        second = self.result("collections", "resume", first["session_id"])
        self.assertEqual(second["history"]["session"]["status"], "complete")
        self.assertEqual(self.urlscan.calls, old_scan_calls)
        self.assertEqual(self.catalog.calls, 3)

    def test_source_commit_survives_outer_interrupt_without_refetch(self):
        original = SQLitePublicNoticeRepository.apply
        def interrupt_after_commit(repository, *arguments, **options):
            original(repository, *arguments, **options)
            raise KeyboardInterrupt()
        with patch.object(SQLitePublicNoticeRepository, "apply", interrupt_after_commit):
            code, _, _ = self.invoke("collect", "example.com", "--task", "notices-hibp")
        self.assertEqual(code, 130)
        session = self.result("collections", "list")["sessions"][0]
        history = self.result("collections", "show", session["id"])
        receipt = self.receipt(history)
        self.assertEqual(receipt["result_status"], "complete")
        plan = self.result("collections", "resume", session["id"], "--plan")
        self.assertEqual(plan["units"], [])
        self.assertEqual(plan["retained"][0]["receipt"], receipt)
        resumed = self.result("collections", "resume", session["id"])
        self.assertEqual(resumed["history"]["session"]["status"], "complete")
        self.assertEqual(resumed["history"]["receipts"], [])
        self.assertEqual(resumed["history"]["retained"][0]["receipt"], receipt)
        self.assertEqual(self.catalog.calls, 1)
        self.assertEqual(SQLitePublicNoticeRepository(self.database).status().total_run_count, 1)

    def test_notices_only_profile_generates_and_prepares_schedule_without_collection(self):
        self.result("profiles", "save", "Katalog", "example.com", "--task", "notices-hibp")
        destination = self.data.parent / "public-catalog-units"
        before = self.files()
        with patch("subprocess.run", side_effect=AssertionError("Schedule must not activate service")):
            generated = self.result("schedule", "generate", "Katalog", "--output", str(destination), "--at", "07:30", "--timezone", "UTC")
            self.assertEqual(self.files(), before)
            prepared = self.result("schedule", "prepare", "Katalog", "--keep", "1")
        self.assertTrue(Path(generated["service_file"]).is_file())
        self.assertIn("--profile=Katalog", Path(generated["service_file"]).read_text())
        self.assertTrue(prepared["backup"]["restore_verified"])
        self.assertTrue(Path(prepared["backup"]["path"]).is_file())
        self.assertEqual(self.catalog.calls, 0)
        self.assertEqual(self.result("collections", "list")["sessions"], [])
        self.assertEqual(SQLitePublicNoticeRepository(self.database).status().total_run_count, 0)

    def test_organization_period_view_does_not_turn_global_catalog_into_domain_changes(self):
        organization = self.result("organizations", "add", "Açık test grubu")["organization"]
        self.result("organizations", "link", organization["id"], "--kind", "domain", "--value", "example.com")
        self.collect()
        self.catalog.value = public_catalog(
            public_item("Exact", "example.com"), public_item("FOREIGN_CATALOG_NOTICE", "foreign.example"),
        )
        second = self.collect()
        global_run = second["steps"][0]["public_notices"]["run"]
        self.assertEqual((global_run["notice_count"], global_run["added_count"], global_run["removed_count"]), (2, 1, 1))
        before = self.files()
        report = self.result("changes", "--organization", organization["id"], "--days", "7")
        notices = next(section for section in report["sections"] if section["family"] == "notices")
        self.assertEqual(notices["total_baseline_count"], 1)
        self.assertEqual(notices["total_change_count"], 0)
        payload = json.dumps(report)
        self.assertNotIn("FOREIGN_CATALOG_NOTICE", payload)
        self.assertNotIn("foreign.example", payload)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.catalog.calls, 2)

    def test_legacy_profile_definition_bytes_and_hash_are_unchanged(self):
        legacy = {
            "asset_value": "example.com", "task_ids": ["scan-crtsh", "scan-urlscan", "discover-crtsh"],
            "username_watch_ids": [], "ransomware_watch_ids": [], "ransomlook_watch_ids": [],
            "typos": False, "stale_after_hours": 24, "finding_limit": 10, "watch_item_limit": 100, "version": 1,
        }
        expected = json.dumps(legacy, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        definition = CollectionProfileDefinition("example.com")
        self.assertEqual(canonical_definition_json(definition), expected)
        self.assertEqual(definition_sha256(definition), hashlib.sha256(expected.encode()).hexdigest())
        saved = self.result("profiles", "save", "Legacy", "example.com")["profile"]
        self.assertEqual(saved["definition_sha256"], hashlib.sha256(expected.encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()

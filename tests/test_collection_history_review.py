"""Final analysis failure preserves receipts and retries without source collection."""

from dataclasses import replace
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import StorageError
from xti.application.analysis import UnifiedAnalysisService
from tests import test_collection_watch_cli as fixtures


class CollectionHistoryReviewTests(unittest.TestCase):
    setUp = fixtures.CollectionWatchCLITests.setUp
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files

    def assert_analysis_failure_retries_without_sources(self, mode):
        original = UnifiedAnalysisService.show
        calls = 0

        def final_failure(service, *args, **kwargs):
            nonlocal calls
            calls += 1
            # Two read-only preflight views precede the single final analysis.
            if calls == 3 and mode == "storage":
                raise StorageError("Kontrollü analiz okuma hatası.")
            report = original(service, *args, **kwargs)
            if calls == 3:
                return replace(report, asset_value="different.example")
            return report

        with patch.object(UnifiedAnalysisService, "show", final_failure):
            code, _, error = self.invoke("collect", "example.com", "--task", "scan-crtsh")
        self.assertEqual(code, 1 if mode == "storage" else 2)
        self.assertIn("analiz", error.lower())
        self.assertEqual(calls, 3)
        session = self.result("collections", "list")["sessions"][0]
        self.assertEqual((session["status"], session["analysis_status"], session["stop_reason"]), ("failed", "failed", "analysis_failed"))
        old = self.result("collections", "show", session["id"])
        self.assertEqual(old["steps"][0]["status"], "complete")
        self.assertEqual(len(old["receipts"]), 1)
        receipt_id = old["receipts"][0]["result_id"]
        source_calls = (list(self.crt.calls), list(self.urlscan.calls), self.threatcluster.calls, self.ransomlook.calls)
        before = self.files()
        plan = self.result("collections", "resume", session["id"], "--plan")
        self.assertEqual(plan["units"], [])
        self.assertEqual(self.files(), before)
        resumed = self.result("collections", "resume", session["id"])
        self.assertEqual(resumed["history"]["session"]["status"], "complete")
        self.assertEqual(resumed["history"]["steps"], [])
        self.assertEqual(resumed["history"]["retained"][0]["receipt"]["result_id"], receipt_id)
        self.assertEqual(resumed["analysis"]["asset_value"], "example.com")
        self.assertEqual((self.crt.calls, self.urlscan.calls, self.threatcluster.calls, self.ransomlook.calls), source_calls)
        self.assertEqual(self.result("collections", "show", session["id"])["session"]["status"], "failed")

    def test_foreign_domain_final_analysis_is_rejected_and_resume_only_analyzes(self):
        self.assert_analysis_failure_retries_without_sources("foreign_domain")

    def test_final_analysis_storage_failure_preserves_complete_source_receipt(self):
        self.assert_analysis_failure_retries_without_sources("storage")


if __name__ == "__main__":
    unittest.main()

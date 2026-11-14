"""Real SQLite collection history/resume with offline providers and crash boundaries."""

import unittest
from unittest.mock import patch

from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.ports.discovery import SourceError
from tests import test_collection_watch_cli as fixtures


class CollectionHistoryCLITests(unittest.TestCase):
    setUp = fixtures.CollectionWatchCLITests.setUp
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files
    add_social = fixtures.CollectionWatchCLITests.add_social
    add_tc = fixtures.CollectionWatchCLITests.add_tc
    add_rl = fixtures.CollectionWatchCLITests.add_rl

    def latest(self):
        return self.result("collections", "list")["sessions"][0]

    def test_normal_run_records_source_links_and_readonly_history(self):
        social, tc, rl = self.add_social(), self.add_tc(), self.add_rl()
        self.maigret.responses.append({"GitHub": fixtures.github()})
        self.result(
            "profiles", "save", "gunluk", "example.com", "--task", "scan-crtsh",
            "--username-watch", social.id, "--ransomware-watch", tc.id, "--ransomlook-watch", rl.id,
        )
        collected = self.result("collect", "--profile", "gunluk")
        session_id = collected["session_id"]
        before = self.files()
        history = self.result("collections", "show", session_id)
        self.assertEqual(history["session"]["status"], "complete")
        self.assertEqual(len(history["steps"]), 6)
        self.assertEqual(len(history["receipts"]), 6)
        self.assertEqual(history["session"]["plan"]["origin"]["revision"], 1)
        self.result("collections", "list")
        self.assertEqual(self.files(), before)
        code, _, _ = self.invoke("collections", "resume", session_id)
        self.assertNotEqual(code, 0)
        self.assertEqual(self.threatcluster.calls, 1)
        self.assertEqual(self.ransomlook.calls, 1)

    def test_retry_only_failed_source_preserves_previous_results_and_old_status(self):
        self.crt.responses["%example%"] = SourceError("Arşive erişilemiyor.")
        self.crt.responses["example%"] = SourceError("Arşive erişilemiyor.")
        first = self.result("collect", "example.com", expected_code=3)
        session_id = first["session_id"]
        before = self.files()
        plan = self.result("collections", "resume", session_id, "--plan")
        self.assertEqual([unit["step_key"] for unit in plan["units"]], ["scan-crtsh"])
        self.assertEqual(len(plan["retained"]), 2)
        self.assertEqual(self.files(), before)
        previous_urlscan = list(self.urlscan.calls)
        previous_discovery = self.crt.calls.count("%.example.com")
        self.crt.responses["%example%"] = fixtures.batch()
        self.crt.responses["example%"] = fixtures.batch()
        second = self.result("collections", "resume", session_id)
        self.assertEqual(second["history"]["session"]["status"], "complete")
        self.assertEqual(second["history"]["session"]["generation"], 2)
        self.assertEqual(len(second["history"]["steps"]), 1)
        self.assertEqual(len(second["history"]["retained"]), 2)
        self.assertEqual(self.urlscan.calls, previous_urlscan)
        self.assertEqual(self.crt.calls.count("%.example.com"), previous_discovery)
        self.assertEqual(self.result("collections", "show", session_id)["session"]["status"], "partial")
        self.assertNotEqual(self.invoke("collections", "resume", session_id)[0], 0)

    def test_member_commit_survives_interrupt_before_outer_result_and_is_not_repeated(self):
        a, b = self.add_tc("Kuruluş A"), self.add_tc("Kuruluş B")
        first_id, second_id = sorted((a.id, b.id))
        original = SQLiteRansomwareWatchRepository.run

        def interrupt_after_commit(repository, watch_id, snapshot, **options):
            result = original(repository, watch_id, snapshot, **options)
            if watch_id == first_id:
                raise KeyboardInterrupt()
            return result

        with patch.object(SQLiteRansomwareWatchRepository, "run", interrupt_after_commit):
            code, _, _ = self.invoke(
                "collect", "example.com", "--task", "scan-crtsh",
                "--ransomware-watch", a.id, "--ransomware-watch", b.id,
            )
        self.assertEqual(code, 130)
        first = self.latest()
        self.assertEqual(first["status"], "interrupted")
        plan = self.result("collections", "resume", first["id"], "--plan")
        self.assertEqual([unit["step_key"] for unit in plan["units"]], [
            "ransomware-refresh:threatcluster", f"ransomware-watch:threatcluster:{second_id}",
        ])
        completed_before = self.tc.show(first_id, run_limit=10).total_run_count
        scan_calls = list(self.crt.calls)
        resumed = self.result("collections", "resume", first["id"])
        self.assertEqual(resumed["history"]["session"]["status"], "complete")
        self.assertEqual(self.tc.show(first_id, run_limit=10).total_run_count, completed_before)
        self.assertEqual(self.tc.show(second_id, run_limit=10).total_run_count, 1)
        self.assertEqual(self.crt.calls, scan_calls)
        self.assertEqual(self.threatcluster.calls, 2)
        retained = [item for item in resumed["history"]["retained"] if item["unit"]["kind"] == "ransomware_watch"]
        self.assertEqual(len(retained), 1)
        new_receipt = next(item for item in resumed["history"]["receipts"] if item["result_kind"] == "threatcluster_watch_run")
        self.assertNotEqual(retained[0]["receipt"]["source_run_id"], new_receipt["source_run_id"])

    def test_failed_refresh_retry_never_runs_watch_against_old_snapshot(self):
        watch = self.add_tc()
        self.threatcluster.value = SourceError("Kaynak kapalı.")
        first = self.result(
            "collect", "example.com", "--task", "scan-crtsh", "--ransomware-watch", watch.id,
            expected_code=3,
        )
        self.assertEqual(self.tc.show(watch.id).total_run_count, 0)
        second = self.result("collections", "resume", first["session_id"], expected_code=3)
        self.assertEqual(self.tc.show(watch.id).total_run_count, 0)
        self.assertEqual(second["history"]["session"]["status"], "partial")
        self.threatcluster.value = fixtures.threatcluster_feed([fixtures.claim()])
        third = self.result("collections", "resume", second["history"]["session"]["id"])
        self.assertEqual(third["history"]["session"]["status"], "complete")
        self.assertEqual(self.tc.show(watch.id).total_run_count, 1)

    def test_changed_profile_prevents_retry_but_old_history_remains_readable(self):
        self.result("profiles", "save", "gunluk", "example.com")
        self.crt.responses["%example%"] = SourceError("Kaynak kapalı.")
        self.crt.responses["example%"] = SourceError("Kaynak kapalı.")
        first = self.result("collect", "--profile", "gunluk", expected_code=3)
        self.result("profiles", "save", "gunluk", "example.com", "--task", "discover-crtsh")
        before_calls = list(self.crt.calls)
        self.result("collections", "show", first["session_id"])
        code, _, _ = self.invoke("collections", "resume", first["session_id"])
        self.assertNotEqual(code, 0)
        self.assertEqual(self.crt.calls, before_calls)


if __name__ == "__main__":
    unittest.main()

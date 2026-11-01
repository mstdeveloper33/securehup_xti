"""Terminal-first controlled NVD date-window workflow."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_nvd_window import (
    END,
    START,
    FakeWindowSource,
    custom_page,
    cve,
    page,
)
from xti.interfaces.cli import main


class NvdWindowCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.database = self.data / "xti.db"
        self.source = FakeWindowSource([
            page([cve("CVE-2026-10001")], total=1),
        ])
        self.ok("init")

    def invoke(self, *arguments, as_json=True, data=None):
        argv = ["--data-dir", str(data or self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("xti.interfaces.cli.NvdWindowSource", return_value=self.source),
            patch("xti.application.vulnerability.time.sleep", return_value=None),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def ok(self, *arguments):
        code, stdout, stderr = self.invoke(*arguments)
        self.assertEqual((code, stderr), (0, ""))
        value = json.loads(stdout)
        self.assertTrue(value["ok"])
        return value["data"]

    def window_args(self, action):
        return (
            "vuln", action, "--start", START, "--end", END,
            "--page-size", "2",
        )

    def test_plan_is_read_only_fetches_one_page_and_complete_rerun_is_offline(self):
        before = self.database.read_bytes()
        planned = self.ok(*self.window_args("nvd-window-plan"))
        self.assertEqual((planned["state"], planned["next_start_index"]), ("new", 0))
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.source.calls, [])

        fetched = self.ok(*self.window_args("nvd-window-fetch"))
        self.assertEqual(fetched["status"], "complete")
        self.assertEqual(fetched["run"]["created_count"], 1)
        self.assertEqual(len(self.source.calls), 1)
        after_fetch = self.database.read_bytes()

        complete = self.ok(*self.window_args("nvd-window-plan"))
        self.assertEqual((complete["state"], complete["will_request"]), ("complete", False))
        again = self.ok(*self.window_args("nvd-window-fetch"))
        self.assertEqual(again["status"], "already_complete")
        self.assertEqual(len(self.source.calls), 1)
        self.assertEqual(self.database.read_bytes(), after_fetch)

        code, stdout, stderr = self.invoke(
            *self.window_args("nvd-window-plan"), as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("tamamlandı", stdout)
        self.assertIn("Ağ isteği: yapılmayacak", stdout)

    def test_source_failure_is_audited_without_progress_and_retry_can_continue(self):
        self.source.values.clear()
        self.source.error = "NVD geçici olarak erişilemiyor."
        code, stdout, stderr = self.invoke(*self.window_args("nvd-window-fetch"))
        self.assertEqual((code, stderr), (3, ""))
        failed = json.loads(stdout)["data"]
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["plan_after"]["next_start_index"], 0)
        self.assertEqual(failed["plan_after"]["state"], "failed")

        self.source.error = None
        self.source.values.append(page([cve("CVE-2026-10001")], total=1))
        retried = self.ok(*self.window_args("nvd-window-fetch"))
        self.assertEqual(retried["status"], "complete")
        self.assertEqual(retried["plan_after"]["last_error"], None)

    def test_invalid_or_missing_storage_stops_before_network(self):
        before = self.database.read_bytes()
        for args in (
            ("vuln", "nvd-window-plan", "--start", START, "--end", END,
             "--page-size", "101"),
            ("vuln", "nvd-window-fetch", "--start", START,
             "--end", "2026-10-10T00:00:00Z"),
            ("vuln", "nvd-window-fetch", "--start", "2026-10-01T00:00:00",
             "--end", END),
        ):
            code, stdout, stderr = self.invoke(*args)
            self.assertEqual((code, stdout), (2, ""))
            self.assertEqual(json.loads(stderr)["error"]["code"], "validation_error")
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.source.calls, [])

        missing = Path(self.temp.name) / "missing"
        code, stdout, stderr = self.invoke(
            *self.window_args("nvd-window-fetch"), data=missing,
        )
        self.assertEqual((code, stdout), (1, ""))
        self.assertEqual(json.loads(stderr)["error"]["code"], "storage_error")
        self.assertFalse(missing.exists())
        self.assertEqual(self.source.calls, [])

    def test_list_coverage_show_and_restart_are_terminal_first(self):
        self.ok(*self.window_args("nvd-window-fetch"))
        before_reads = self.database.read_bytes()
        listed = self.ok("vuln", "nvd-window-list", "--status", "complete")
        coverage = self.ok(
            "vuln", "nvd-window-coverage", "--start", START, "--end", END,
        )
        gap_plan = self.ok(
            "vuln", "nvd-window-gap-plan", "--start", START,
            "--end", "2026-10-17T00:00:00.000Z", "--page-size", "2",
            "--limit", "2",
        )
        shown = self.ok(
            "vuln", "nvd-window-show", "--start", START, "--end", END,
            "--page-size", "2",
        )
        operations = self.ok(
            "vuln", "nvd-window-operations", "--start", START, "--end", END,
            "--recent-limit", "5",
        )
        self.assertEqual(listed["matched_count"], 1)
        self.assertTrue(coverage["fully_covered"])
        self.assertEqual(
            (gap_plan["candidate_count"], gap_plan["shown_count"],
             gap_plan["truncated"]),
            (3, 2, True),
        )
        self.assertEqual(gap_plan["candidates"][0]["window_start"], END)
        self.assertEqual(shown["total_restart_count"], 0)
        self.assertEqual(
            (operations["status"], operations["complete_window_count"],
             operations["coverage"]["fully_covered"]),
            ("covered", 1, True),
        )
        self.assertEqual(self.database.read_bytes(), before_reads)
        self.assertEqual(len(self.source.calls), 1)

        code, stdout, stderr = self.invoke(
            "vuln", "nvd-window-gap-plan", "--start", START,
            "--end", "2026-10-17T00:00:00.000Z", "--page-size", "2",
            "--limit", "1", as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("ağ isteği göndermez", stdout)
        self.assertIn("Daha fazla aday var", stdout)
        self.assertEqual(len(self.source.calls), 1)

        restarted = self.ok(
            "vuln", "nvd-window-restart", "--start", START, "--end", END,
            "--page-size", "2", "--reason", "Toplam değişti; baştan doğrulanacak.",
        )
        self.assertEqual(restarted["event"]["previous_state"], "complete")
        self.assertEqual(restarted["plan_after"]["next_start_index"], 0)
        shown = self.ok(
            "vuln", "nvd-window-show", "--start", START, "--end", END,
            "--page-size", "2",
        )
        self.assertEqual(shown["total_restart_count"], 1)
        self.assertEqual(shown["summary"]["state"], "ready")
        self.assertEqual(len(self.source.calls), 1)

        before_invalid = self.database.read_bytes()
        code, stdout, stderr = self.invoke(
            "vuln", "nvd-window-restart", "--start", START, "--end", END,
            "--page-size", "2", "--reason", "x",
        )
        self.assertEqual((code, stdout), (2, ""))
        self.assertEqual(json.loads(stderr)["error"]["code"], "validation_error")
        self.assertEqual(self.database.read_bytes(), before_invalid)

    def test_gap_fetch_is_bounded_and_stops_on_first_failure(self):
        first_end = "2026-10-08T00:00:00.000Z"
        second_end = "2026-10-15T00:00:00.000Z"
        requested_end = "2026-10-16T00:00:00.000Z"
        self.source.values = [
            custom_page(
                [cve("CVE-2026-10001")],
                window_start=START, window_end=first_end, total=1,
            ),
            custom_page(
                [cve("CVE-2026-10002", modified="2026-10-09T12:00:00.000")],
                window_start=first_end, window_end=second_end, total=1,
            ),
        ]
        result = self.ok(
            "vuln", "nvd-window-gap-fetch", "--start", START,
            "--end", requested_end, "--page-size", "2", "--limit", "2",
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual(
            (result["attempted_count"], result["successful_page_count"],
             result["unattempted_candidate_count"]),
            (2, 2, 1),
        )
        self.assertEqual(len(self.source.calls), 2)
        self.assertEqual(result["plan_after"]["candidate_count"], 1)

        second_data = Path(self.temp.name) / "failed-data"
        code, stdout, stderr = self.invoke("init", data=second_data)
        self.assertEqual((code, stderr), (0, ""))
        self.assertTrue(json.loads(stdout)["ok"])
        self.source.calls.clear()
        self.source.values.clear()
        self.source.error = "Kontrollü NVD kaynak hatası."
        code, stdout, stderr = self.invoke(
            "vuln", "nvd-window-gap-fetch", "--start", START,
            "--end", requested_end, "--page-size", "2", "--limit", "3",
            data=second_data,
        )
        self.assertEqual((code, stderr), (3, ""))
        failed = json.loads(stdout)["data"]
        self.assertEqual((failed["status"], failed["attempted_count"]), ("stopped", 1))
        self.assertEqual(failed["unattempted_candidate_count"], 2)
        self.assertEqual(len(self.source.calls), 1)


if __name__ == "__main__":
    unittest.main()

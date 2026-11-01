"""User-facing durable queue/history/retry behavior without real HTTP requests."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError

from tests.test_discovery import FakeSource, batch, document


class JobCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "saved jobs with spaces"
        self.database = self.data / "xti.db"

    def invoke(self, *arguments, source=None, as_json=True):
        stdout, stderr = StringIO(), StringIO()
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        if arguments and arguments[0] in {"scan", "watch"}:
            arguments = (*arguments, "--source", "crt.sh")
        with (
            patch("xti.interfaces.cli.CrtShSource", return_value=source or FakeSource()),
            patch("xti.interfaces.cli.UrlscanSource", return_value=FakeSource()),
        ):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def success(self, *arguments, source=None):
        code, stdout, stderr = self.invoke(*arguments, source=source)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        return payload["data"]

    def enqueue(self, domain="example.com"):
        return self.success("scan", domain, "--queue")["job"]

    def test_queue_then_worker_in_later_invocation_uses_saved_target(self):
        no_network = FakeSource()
        queued = self.success("scan", "example.com", "--queue", source=no_network)["job"]
        self.assertEqual(no_network.calls, [])
        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["attempt_count"], 0)
        source = FakeSource({"%example%": batch(document("example-support.net"))})
        executed = self.success("worker", "--once", source=source)
        self.assertEqual(executed["job_id"], queued["id"])
        self.assertEqual(executed["attempt_number"], 1)
        self.assertEqual(executed["summary"]["findings_created"], 1)
        details = self.success("jobs", "show", queued["id"])
        self.assertEqual(details["job"]["status"], "complete")
        self.assertEqual(details["attempts"][0]["id"], executed["attempt_id"])
        self.assertEqual(len(details["attempts"][0]["queries"]), 2)

    def test_scan_automatically_records_history_and_exposes_job_identity(self):
        result = self.success("scan", "example.com")
        self.assertTrue(result["job_id"])
        self.assertTrue(result["attempt_id"])
        listed = self.success("jobs", "list")["jobs"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], result["job_id"])
        self.assertEqual(listed[0]["status"], "complete")
        details = self.success("jobs", "show", result["job_id"])
        self.assertEqual(details["attempts"][0]["result"]["queries"], result["queries"])

    def test_failed_job_can_be_retried_without_losing_failed_attempt(self):
        failed = FakeSource({
            "%example%": SourceError("Kaynak yanıt vermiyor."),
            "example%": SourceError("Kaynak yanıt vermiyor."),
        })
        code, stdout, stderr = self.invoke("scan", "example.com", source=failed)
        self.assertEqual(code, 3, stderr)
        first = json.loads(stdout)["data"]
        self.assertEqual(first["status"], "failed")
        source = FakeSource({"%example%": batch(document("example-support.net"))})
        second = self.success("jobs", "retry", first["job_id"], source=source)
        self.assertEqual(second["job_id"], first["job_id"])
        self.assertEqual(second["attempt_number"], 2)
        self.assertNotEqual(second["attempt_id"], first["attempt_id"])
        details = self.success("jobs", "show", first["job_id"])
        self.assertEqual([attempt["status"] for attempt in details["attempts"]], ["failed", "complete"])
        self.assertEqual(details["attempts"][0]["queries"][0]["error"], "Kaynak yanıt vermiyor.")

    def test_ctrl_c_records_interruption_and_completed_query(self):
        class InterruptedSource(FakeSource):
            def search(self, pattern):
                if self.calls:
                    raise KeyboardInterrupt
                return super().search(pattern)

        source = InterruptedSource({"%example%": batch(document("example-support.net"))})
        code, stdout, stderr = self.invoke("scan", "example.com", source=source)
        self.assertEqual(code, 130)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"]["code"], "interrupted")
        jobs = self.success("jobs", "list", "--status", "interrupted")["jobs"]
        self.assertEqual(len(jobs), 1)
        details = self.success("jobs", "show", jobs[0]["id"])
        self.assertEqual(details["attempts"][0]["status"], "interrupted")
        self.assertEqual(len(details["attempts"][0]["queries"]), 1)
        self.assertEqual(details["attempts"][0]["queries"][0]["pattern"], "%example%")

    def test_busy_scan_keeps_request_queued_and_reports_distinct_error(self):
        self.success("init")
        source = FakeSource()
        with LocalExecutionLock(self.database).acquire():
            code, stdout, stderr = self.invoke("scan", "example.com", source=source)
        self.assertEqual(code, 4)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"]["code"], "worker_busy")
        self.assertEqual(source.calls, [])
        jobs = self.success("jobs", "list", "--status", "queued")["jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["attempt_count"], 0)

    def test_list_and_show_are_read_only_even_for_running_attempt(self):
        job = self.enqueue()
        repository = SQLiteJobRepository(self.database)
        running = repository.start(job["id"])
        before = self.database.read_bytes()
        source = FakeSource()
        self.success("jobs", "list", source=source)
        details = self.success("jobs", "show", job["id"], source=source)
        self.assertEqual(details["job"]["status"], "running")
        self.assertEqual(details["attempts"][0]["id"], running.id)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(source.calls, [])

    def test_watch_records_separate_jobs_for_each_cycle(self):
        source = FakeSource({"%example%": batch(document("example-support.net"))})
        with patch("xti.interfaces.cli.time.sleep") as sleep:
            code, stdout, stderr = self.invoke(
                "watch", "example.com", "--cycles", "2", source=source,
            )
        self.assertEqual(code, 0, stderr)
        outputs = [json.loads(line)["data"] for line in stdout.splitlines()]
        self.assertEqual(len(outputs), 2)
        self.assertNotEqual(outputs[0]["job_id"], outputs[1]["job_id"])
        self.assertEqual([value["attempt_number"] for value in outputs], [1, 1])
        self.assertEqual([value["summary"]["findings_created"] for value in outputs], [1, 0])
        self.assertEqual(len(self.success("jobs", "list")["jobs"]), 2)
        sleep.assert_called_once()

    def test_empty_worker_reports_no_work_and_makes_no_network_call(self):
        self.success("init")
        source = FakeSource()
        self.assertEqual(self.success("worker", "--once", source=source)["processed"], 0)
        self.assertEqual(source.calls, [])

    def test_history_filter_and_limit_select_saved_jobs(self):
        first = self.enqueue()
        self.enqueue("anotherbrand.com")
        self.success("jobs", "retry", first["id"])
        pending = self.success("jobs", "list", "--status", "queued", "--limit", "1")["jobs"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["targets"], ["anotherbrand.com"])
        self.assertEqual(len(self.success("jobs", "list", "--status", "complete")["jobs"]), 1)

    def test_invalid_history_request_never_runs_source_or_changes_database(self):
        self.enqueue()
        before = self.database.read_bytes()
        for arguments in (
            ("jobs", "list", "--limit", "0"),
            ("jobs", "list", "--limit", "101"),
            ("jobs", "list", "--status", "unknown"),
            ("jobs", "show", "missing-job"),
            ("jobs", "retry", "missing-job"),
        ):
            with self.subTest(arguments=arguments):
                source = FakeSource()
                code, stdout, stderr = self.invoke(*arguments, source=source)
                self.assertEqual(code, 2, stderr)
                self.assertEqual(stdout, "")
                self.assertFalse(json.loads(stderr)["ok"])
                self.assertEqual(source.calls, [])
                self.assertEqual(self.database.read_bytes(), before)

    def test_missing_history_does_not_initialize_a_database(self):
        code, stdout, stderr = self.invoke("jobs", "list")
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertFalse(json.loads(stderr)["ok"])
        self.assertFalse(self.data.exists())

    def test_human_history_output_escapes_saved_external_errors(self):
        source = FakeSource({"%example%": SourceError("Yanıt\x1b[31m bozuldu.")})
        code, stdout, stderr = self.invoke("scan", "example.com", source=source)
        self.assertEqual(code, 3, stderr)
        job_id = json.loads(stdout)["data"]["job_id"]
        code, stdout, stderr = self.invoke("jobs", "show", job_id, as_json=False)
        self.assertEqual(code, 0, stderr)
        self.assertNotIn("\x1b", stdout + stderr)
        self.assertIn("Yanıt", stdout)

    def test_recover_marks_abandoned_attempt_without_contacting_source(self):
        job = self.enqueue()
        repository = SQLiteJobRepository(self.database)
        running = repository.start(job["id"])
        source = FakeSource()
        recovered = self.success("jobs", "recover", source=source)
        self.assertEqual(recovered["recovered"], 1)
        details = self.success("jobs", "show", job["id"])
        self.assertEqual(details["job"]["status"], "interrupted")
        self.assertEqual(details["attempts"][0]["id"], running.id)
        self.assertEqual(details["attempts"][0]["status"], "interrupted")
        self.assertEqual(source.calls, [])

    def test_sources_reports_saved_query_outcome_without_a_live_request(self):
        source = FakeSource({"%example%": SourceError("Kaynak zaman aşımına uğradı.")})
        code, stdout, stderr = self.invoke("scan", "example.com", source=source)
        self.assertEqual(code, 3, stderr)
        report = json.loads(stdout)["data"]
        read_only_source = FakeSource()
        before = self.database.read_bytes()
        sources = self.success("sources", source=read_only_source)["sources"]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["job_id"], report["job_id"])
        self.assertEqual(sources[0]["source_status"], "partial")
        self.assertEqual(sources[0]["queries"], report["queries"])
        self.assertTrue(sources[0]["finished_at"])
        self.assertEqual(read_only_source.calls, [])
        self.assertEqual(self.database.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

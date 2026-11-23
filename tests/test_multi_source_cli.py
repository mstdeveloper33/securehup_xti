"""Two-source terminal output and independent durable jobs, with no live requests."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError

from tests.test_discovery import FakeSource, batch, document
from tests.test_multi_source import (
    COVERAGE_NOTE, FakeUrlscanSource, scoped_batch, urlscan_document,
)


class MultiSourceCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "two providers with spaces"
        self.database = self.data / "xti.db"
        self.crt = FakeSource({"%example%": batch(document("example-support.net"))})
        self.urlscan = FakeUrlscanSource({"example*": scoped_batch(urlscan_document())})

    def invoke(self, *arguments, crt=None, urlscan=None, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("xti.interfaces.cli.CrtShSource", return_value=crt or self.crt),
            patch("xti.interfaces.cli.UrlscanSource", return_value=urlscan or self.urlscan),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def success(self, *arguments, **kwargs):
        code, stdout, stderr = self.invoke(*arguments, **kwargs)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        return payload["data"]

    def failed_crt(self):
        return FakeSource({
            "%example%": SourceError("Sertifika kaynağı yanıt vermedi."),
            "example%": SourceError("Sertifika kaynağı yanıt vermedi."),
        })

    def test_default_scan_emits_one_envelope_and_distinct_provider_jobs(self):
        code, stdout, stderr = self.invoke("scan", "EXAMPLE.COM.")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        self.assertEqual(len(stdout.splitlines()), 1)
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "complete")
        results = payload["data"]["results"]
        self.assertEqual([item["provider"] for item in results], ["crt.sh", "urlscan"])
        self.assertEqual(len({item["job_id"] for item in results}), 2)
        self.assertEqual(len({item["attempt_id"] for item in results}), 2)
        self.assertTrue(all(item["targets"] == ["example.com"] for item in results))
        self.assertTrue(all(item["attempt_number"] == 1 for item in results))
        self.assertEqual(self.crt.calls, ["%example%", "example%"])
        self.assertEqual(self.urlscan.calls, ["example*"])
        self.assertEqual(results[1]["queries"][0]["coverage_notes"], [COVERAGE_NOTE])
        self.assertEqual(results[1]["queries"][0]["record_count"], 1)
        self.assertNotIn("certificate_count", results[1]["queries"][0])
        findings = SQLiteFindingRepository(self.database)
        saved = findings.list_findings()
        self.assertEqual(len(saved), 1)
        self.assertEqual(len(findings.get_finding(saved[0].id).observations), 2)
        self.assertEqual(len(self.success("jobs", "list")["jobs"]), 2)

    def test_explicit_urlscan_selects_only_that_provider_and_keeps_single_result_shape(self):
        data = self.success("scan", "example.com", "--source", "urlscan")
        self.assertEqual(data["provider"], "urlscan")
        self.assertEqual(data["status"], "complete")
        self.assertNotIn("results", data)
        self.assertEqual(data["candidate_domains"], ["example-support.net"])
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, ["example*"])
        jobs = self.success("jobs", "list")["jobs"]
        self.assertEqual([job["provider"] for job in jobs], ["urlscan"])

    def test_failed_first_source_keeps_second_source_results_and_separate_history(self):
        code, stdout, stderr = self.invoke("scan", "example.com", crt=self.failed_crt())
        self.assertEqual(code, 3, stderr)
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["data"]["status"], "partial")
        failed, succeeded = payload["data"]["results"]
        self.assertEqual(failed["provider"], "crt.sh")
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["summary"]["observations_created"], 0)
        self.assertEqual(succeeded["provider"], "urlscan")
        self.assertEqual(succeeded["status"], "complete")
        self.assertEqual(succeeded["summary"]["findings_created"], 1)
        self.assertEqual(self.urlscan.calls, ["example*"])
        jobs = SQLiteJobRepository(self.database)
        self.assertEqual(jobs.get(failed["job_id"]).job.status, "failed")
        self.assertEqual(jobs.get(succeeded["job_id"]).job.status, "complete")
        self.assertTrue(all(query.error for query in jobs.get(failed["job_id"]).attempts[0].queries))

    def test_both_sources_fail_without_reporting_successful_empty_search(self):
        urlscan = FakeUrlscanSource({"example*": SourceError("Web inceleme kaynağı yanıt vermedi.")})
        code, stdout, stderr = self.invoke("scan", "example.com", crt=self.failed_crt(), urlscan=urlscan)
        self.assertEqual(code, 3, stderr)
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["data"]["status"], "failed")
        self.assertTrue(all(item["status"] == "failed" for item in payload["data"]["results"]))
        self.assertEqual(SQLiteFindingRepository(self.database).list_findings(), [])

    def test_limited_result_from_second_source_makes_aggregate_partial(self):
        source = FakeUrlscanSource({
            "example*": scoped_batch(urlscan_document(), warnings=("İlk 100 kayıt işlendi.",)),
        })
        code, stdout, stderr = self.invoke("scan", "example.com", urlscan=source)
        self.assertEqual(code, 3, stderr)
        data = json.loads(stdout)["data"]
        self.assertEqual(data["status"], "partial")
        self.assertEqual([item["status"] for item in data["results"]], ["complete", "partial"])
        self.assertEqual(data["results"][1]["queries"][0]["warnings"], ["İlk 100 kayıt işlendi."])

    def test_watch_two_cycles_emit_one_envelope_each_and_preserve_evidence_deduplication(self):
        with patch("xti.interfaces.cli.time.sleep") as sleep:
            code, stdout, stderr = self.invoke("watch", "example.com", "--cycles", "2")
        self.assertEqual(code, 0, stderr)
        cycles = [json.loads(line) for line in stdout.splitlines()]
        self.assertEqual(len(cycles), 2)
        self.assertTrue(all(cycle["ok"] for cycle in cycles))
        self.assertTrue(all(len(cycle["data"]["results"]) == 2 for cycle in cycles))
        first, second = [cycle["data"]["results"] for cycle in cycles]
        self.assertEqual(sum(item["summary"]["observations_created"] for item in first), 2)
        self.assertEqual(sum(item["summary"]["observations_created"] for item in second), 0)
        self.assertEqual(sum(item["summary"]["findings_created"] for item in second), 0)
        self.assertEqual(len({item["job_id"] for item in first + second}), 4)
        self.assertEqual(len(self.success("jobs", "list")["jobs"]), 4)
        self.assertEqual(len(self.crt.calls), 4)
        self.assertEqual(len(self.urlscan.calls), 2)
        sleep.assert_called_once()

    def test_queue_all_then_worker_once_processes_only_one_saved_provider_each_time(self):
        queued = self.success("scan", "example.com", "--queue")["jobs"]
        self.assertEqual([job["provider"] for job in queued], ["crt.sh", "urlscan"])
        self.assertTrue(all(job["status"] == "queued" and job["attempt_count"] == 0 for job in queued))
        self.assertEqual(self.crt.calls + self.urlscan.calls, [])
        first = self.success("worker", "--once")
        self.assertEqual(first["job_id"], queued[0]["id"])
        self.assertEqual(first["provider"], "crt.sh")
        self.assertEqual(self.urlscan.calls, [])
        self.assertEqual(SQLiteJobRepository(self.database).get(queued[1]["id"]).job.status, "queued")
        second = self.success("worker", "--once")
        self.assertEqual(second["job_id"], queued[1]["id"])
        self.assertEqual(second["provider"], "urlscan")
        self.assertEqual(self.urlscan.calls, ["example*"])
        self.assertEqual(self.success("worker", "--once"), {"processed": 0})

    def test_queue_urlscan_then_crt_dispatches_first_queued_source_not_default(self):
        urlscan_job = self.success("scan", "example.com", "--source", "urlscan", "--queue")["job"]
        crt_job = self.success("scan", "example.com", "--source", "crt.sh", "--queue")["job"]
        first = self.success("worker", "--once")
        self.assertEqual(first["job_id"], urlscan_job["id"])
        self.assertEqual(first["provider"], "urlscan")
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(SQLiteJobRepository(self.database).get(crt_job["id"]).job.status, "queued")

    def test_retry_automatically_uses_saved_urlscan_provider_and_keeps_failed_attempt(self):
        failed = FakeUrlscanSource({"example*": SourceError("Geçici hata.")})
        code, stdout, stderr = self.invoke("scan", "example.com", "--source", "urlscan", urlscan=failed)
        self.assertEqual(code, 3, stderr)
        first = json.loads(stdout)["data"]
        second = self.success("jobs", "retry", first["job_id"])
        self.assertEqual(second["provider"], "urlscan")
        self.assertEqual(second["job_id"], first["job_id"])
        self.assertNotEqual(second["attempt_id"], first["attempt_id"])
        self.assertEqual(second["attempt_number"], 2)
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, ["example*"])
        history = self.success("jobs", "show", first["job_id"])
        self.assertEqual(history["job"]["provider"], "urlscan")
        self.assertEqual([item["status"] for item in history["attempts"]], ["failed", "complete"])
        self.assertEqual(history["attempts"][0]["queries"][0]["error"], "Geçici hata.")

    def test_jobs_show_preserves_both_recorded_results_without_network_or_database_mutation(self):
        result = self.success("scan", "example.com")
        self.crt.calls.clear()
        self.urlscan.calls.clear()
        before = self.database.read_bytes()
        for item in result["results"]:
            saved = self.success("jobs", "show", item["job_id"])
            self.assertEqual(saved["job"]["provider"], item["provider"])
            self.assertEqual(saved["attempts"][0]["id"], item["attempt_id"])
            self.assertEqual(saved["attempts"][0]["queries"], item["queries"])
            self.assertEqual(saved["attempts"][0]["status"], "complete")
        self.assertEqual(self.crt.calls + self.urlscan.calls, [])
        self.assertEqual(self.database.read_bytes(), before)

    def test_sources_is_the_canonical_governance_catalog_alias_without_network_activity(self):
        self.success("init")
        self.crt.calls.clear()
        self.urlscan.calls.clear()
        before = self.database.read_bytes()
        report = self.success("sources")
        self.assertEqual(report, self.success("sources", "catalog"))
        self.assertEqual(report["catalog_count"], 53)
        self.assertEqual((len(report["sources"]), report["has_more"], report["next_offset"]),
                         (50, True, 50))
        remaining = self.success("sources", "catalog", "--offset", "50")
        self.assertEqual((len(remaining["sources"]), remaining["has_more"]), (3, False))
        catalog = {
            item["identifier"]: item
            for item in (*report["sources"], *remaining["sources"])
        }
        self.assertEqual(len(catalog), 53)
        self.assertEqual(catalog["crt.sh"]["target_contact"], "provider_query")
        self.assertEqual(catalog["explicit-https-head"]["target_contact"], "direct_authorized")
        self.assertEqual(catalog["brand:brightdata-linkedin"]["cost_model"], "paid")
        self.assertEqual(catalog["credential:xposedornot-domain"]["integration_state"], "conditional")
        self.assertIn("ioc sync --source feodo", catalog["feodo-tracker"]["commands"])
        self.assertEqual(self.crt.calls + self.urlscan.calls, [])
        self.assertEqual(self.database.read_bytes(), before)

    def test_human_output_identifies_both_sources_and_escapes_external_text(self):
        source = FakeUrlscanSource({"example*": SourceError("Yanıt\x1b[31m bozuk.")})
        code, stdout, stderr = self.invoke("scan", "example.com", urlscan=source, as_json=False)
        self.assertEqual(code, 3)
        self.assertIn("crt.sh", stdout)
        self.assertIn("urlscan", stdout)
        self.assertIn("Yanıt", stdout)
        self.assertNotIn("\x1b", stdout + stderr)
        code, stdout, stderr = self.invoke("scan", "example.com", "--source", "urlscan", as_json=False)
        self.assertEqual(code, 0, stderr)
        self.assertIn(COVERAGE_NOTE, stdout)

    def test_invalid_target_is_rejected_before_initializing_or_querying_either_source(self):
        for selection in ("all", "urlscan"):
            with self.subTest(selection=selection):
                code, stdout, stderr = self.invoke("scan", "https://example.com", "--source", selection)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertFalse(json.loads(stderr)["ok"])
                self.assertFalse(self.data.exists())
                self.assertEqual(self.crt.calls + self.urlscan.calls, [])

    def test_busy_default_scan_preserves_both_queued_jobs_without_partial_execution(self):
        self.success("init")
        with LocalExecutionLock(self.database).acquire():
            code, stdout, stderr = self.invoke("scan", "example.com")
        self.assertEqual(code, 4)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"]["code"], "worker_busy")
        jobs = self.success("jobs", "list")["jobs"]
        self.assertEqual({job["provider"] for job in jobs}, {"crt.sh", "urlscan"})
        self.assertTrue(all(job["status"] == "queued" and job["attempt_count"] == 0 for job in jobs))
        self.assertEqual(self.crt.calls + self.urlscan.calls, [])


if __name__ == "__main__":
    unittest.main()

"""Personal workflow: discovery, bounded checks, review and portable evidence."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite_assessments import SQLiteAssessmentRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.enrichment import ProbeResult
from xti.interfaces.cli import main
from tests.test_discovery import FakeSource, batch, document
from tests.test_multi_source import FakeUrlscanSource, scoped_batch, urlscan_document


class FakeProbe:
    def __init__(self, *, failed=False):
        self.calls = []
        self.failed = failed

    def check(self, domain):
        self.calls.append(domain)
        now = datetime.now(timezone.utc).isoformat()
        result = ProbeResult(
            domain=domain, started_at=now, finished_at=now, policy_version="test-policy-v1",
            dns_status="resolved", addresses=("93.184.215.14",), tls_status="valid",
            http_status="responded", http_status_code=302, connected_address="93.184.215.14",
            errors=(), notes=("Yönlendirme izlenmedi.",),
        )
        return replace(result, http_status="failed", http_status_code=None,
                       errors=("Yanıt zaman aşımı.\x1b[31m",)) if self.failed else result


class EnrichmentCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "local data"
        self.database = self.data / "xti.db"
        self.crt = FakeSource({"%example%": batch(document("example-support.net"))})
        self.urlscan = FakeUrlscanSource({"example*": scoped_batch(urlscan_document())})
        self.probe = FakeProbe()

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("xti.interfaces.cli.CrtShSource", return_value=self.crt),
            patch("xti.interfaces.cli.UrlscanSource", return_value=self.urlscan),
            patch("xti.interfaces.cli.HttpsTargetProbe", return_value=self.probe),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def success(self, *arguments):
        code, stdout, stderr = self.invoke(*arguments)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        data = json.loads(stdout)
        self.assertTrue(data["ok"])
        return data["data"]

    def finding(self):
        return SQLiteFindingRepository(self.database).list_findings()[0]

    def test_default_scan_is_passive_then_explicit_check_and_read_only_report(self):
        self.success("scan", "example.com")
        finding = self.finding()
        self.assertEqual(self.probe.calls, [])
        before = self.success("triage")["items"][0]
        self.assertEqual(before["priority"]["freshness"], "unchecked")
        checked = self.success("findings", "check", finding.id)
        self.assertEqual(self.probe.calls, [finding.domain])
        self.assertEqual(checked["assessments"][0]["result"]["http_status_code"], 302)
        check_id = checked["assessments"][0]["id"]
        database_before = self.database.read_bytes()
        item = self.success("triage")["items"][0]
        self.assertEqual(item["priority"]["level"], "soon")
        details = self.success("findings", "show", finding.id)
        self.assertEqual(details["finding"]["status"], "new")
        self.assertEqual(details["assessments"][0]["id"], check_id)
        report = self.success("report", finding.id)
        self.assertEqual(report["format_version"], 1)
        self.assertEqual(report["finding"]["id"], finding.id)
        self.assertEqual(len(report["observations"]), 2)
        self.assertEqual(report["assessments"], details["assessments"])
        self.assertEqual(self.probe.calls, [finding.domain])
        self.assertEqual(self.database.read_bytes(), database_before)

    def test_scan_checks_after_both_sources_and_watch_reuses_fresh_attempts(self):
        with patch("xti.interfaces.cli.time.sleep"):
            code, stdout, stderr = self.invoke("watch", "example.com", "--check", "--cycles", "2")
        self.assertEqual(code, 0, stderr)
        outputs = [json.loads(line) for line in stdout.splitlines()]
        self.assertEqual(len(outputs), 2)
        self.assertEqual(len(outputs[0]["data"]["results"]), 2)
        self.assertEqual(len(outputs[0]["data"]["checks"]["assessments"]), 1)
        self.assertEqual(outputs[1]["data"]["checks"]["assessments"], [])
        self.assertEqual(outputs[1]["data"]["checks"]["skipped_fresh"], 1)
        self.assertEqual(self.probe.calls, ["example-support.net"])
        self.assertEqual(len(SQLiteAssessmentRepository(self.database).list(self.finding().id)), 1)

    def test_single_source_with_check_keeps_single_envelope_shape(self):
        data = self.success("scan", "example.com", "--source", "urlscan", "--check")
        self.assertEqual(data["provider"], "urlscan")
        self.assertNotIn("results", data)
        self.assertEqual(len(data["checks"]["assessments"]), 1)
        self.assertEqual(self.crt.calls, [])

    def test_review_preserved_rechecks_append_and_export_includes_every_record(self):
        self.success("scan", "example.com", "--check")
        finding = self.finding()
        self.success("findings", "review", finding.id, "--decision", "dismissed",
                     "--reason", "Manuel incelemede normal.")
        self.assertEqual(self.success("triage")["items"], [])
        self.assertEqual(self.success("triage", "--all")["items"][0]["priority"]["level"], "archived")
        self.assertEqual(self.success("findings", "check")["assessments"], [])
        self.success("findings", "check", finding.id)
        destination = self.root / "reports" / "evidence.json"
        saved = self.success("report", finding.id, "--output", str(destination))
        self.assertEqual(saved["output"], str(destination))
        report = json.loads(destination.read_text())
        self.assertEqual(report["finding"]["status"], "dismissed")
        self.assertEqual(len(report["assessments"]), 2)
        self.assertEqual(len(report["reviews"]), 1)
        self.assertEqual(len(report["observations"]), 2)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        original = destination.read_bytes()
        code, stdout, stderr = self.invoke("report", finding.id, "--output", str(destination))
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("validation_error", stderr)
        self.assertEqual(destination.read_bytes(), original)

    def test_partial_check_is_recorded_and_does_not_claim_success_or_change_review(self):
        self.probe.failed = True
        code, stdout, stderr = self.invoke("scan", "example.com", "--check")
        self.assertEqual(code, 3, stderr)
        output = json.loads(stdout)
        self.assertFalse(output["ok"])
        self.assertEqual(output["data"]["status"], "partial")
        self.assertEqual(output["data"]["checks"]["status"], "partial")
        self.assertTrue(all(item["status"] == "complete" for item in output["data"]["results"]))
        self.assertEqual(self.finding().status, "new")
        code, stdout, stderr = self.invoke("findings", "check", self.finding().id, as_json=False)
        self.assertEqual(code, 3)
        self.assertNotIn("\x1b", stdout + stderr)
        self.assertIn("Eksik kontrol", stdout)

    def test_limits_and_queue_combination_rejected_before_database_creation(self):
        invalid = [
            ("scan", "example.com", "--check", "--queue"),
            ("scan", "example.com", "--check-limit", "21"),
            ("findings", "check", "--limit", "0"),
            ("triage", "--limit", "501"),
        ]
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                code, stdout, stderr = self.invoke(*arguments)
                self.assertEqual(code, 2, stderr)
                self.assertEqual(stdout, "")
                self.assertFalse(self.data.exists())
        self.assertEqual(self.probe.calls + self.crt.calls + self.urlscan.calls, [])

    def test_missing_storage_read_and_check_do_not_create_data_or_connect(self):
        for arguments in [("findings", "check"), ("findings", "check", "missing"),
                          ("triage",), ("report", "missing")]:
            with self.subTest(arguments=arguments):
                code, stdout, stderr = self.invoke(*arguments)
                self.assertEqual(code, 1, stderr)
                self.assertEqual(stdout, "")
                self.assertFalse(self.data.exists())
        self.assertEqual(self.probe.calls, [])

    def test_busy_worker_prevents_checks_without_new_evidence(self):
        self.success("scan", "example.com")
        finding = self.finding()
        with LocalExecutionLock(self.database).acquire():
            code, stdout, stderr = self.invoke("findings", "check", finding.id)
        self.assertEqual(code, 4, stderr)
        self.assertEqual(self.probe.calls, [])
        self.assertEqual(SQLiteAssessmentRepository(self.database).list(finding.id), ())


if __name__ == "__main__":
    unittest.main()

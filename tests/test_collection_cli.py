"""End-to-end collection against disposable storage and offline sources."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.certpl_warning import parse_certpl_warning_response
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.domain.cti_feeds import CERTPL_POLICY
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError
from tests.test_certpl_warning import content
from tests.test_cti_feeds import raw, snapshot
from tests.test_discovery import FakeSource, batch, document


class CollectionCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "collection data"
        self.database = self.data / "xti.db"
        self.assets = SQLiteAssetRepository(self.database)
        self.assets.initialize()
        self.asset, _ = self.assets.add("example.com")
        self.crt = FakeSource({
            "%example%": batch(document("example-support.net", 1)),
            "%.example.com": batch(document("portal.example.com", 3)),
        })
        self.urlscan = FakeSource({
            "example*": batch(document("example-support.net", 2)),
        })
        self.enterContext(patch("xti.interfaces.cli.CrtShSource", return_value=self.crt))
        self.enterContext(patch("xti.interfaces.cli.UrlscanSource", return_value=self.urlscan))
        self.feodo = self.enterContext(patch(
            "xti.interfaces.cli.FeodoTrackerSource.fetch",
            side_effect=AssertionError("Unselected feeds must not be fetched."),
        ))
        self.certpl = self.enterContext(patch(
            "xti.interfaces.cli.CertPlWarningSource.fetch",
            side_effect=AssertionError("Unselected feeds must not be fetched."),
        ))
        self.harvester = self.enterContext(patch(
            "xti.interfaces.cli.TheHarvesterArchiveSource.search",
            side_effect=AssertionError("Optional archive must require selection."),
        ))
        self.probe = self.enterContext(patch(
            "xti.interfaces.cli.HttpsTargetProbe",
            side_effect=AssertionError("Collection must not probe target sites."),
        ))
        self.network = self.enterContext(patch(
            "socket.socket.connect",
            side_effect=AssertionError("Collection tests must remain offline."),
        ))

    def invoke(self, *arguments, as_json=True):
        stdout, stderr = StringIO(), StringIO()
        options = ["--data-dir", str(self.data)]
        if as_json:
            options.append("--json")
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*options, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def data_result(self, *arguments, expected_code=0):
        code, stdout, stderr = self.invoke(*arguments)
        self.assertEqual((code, stderr), (expected_code, ""))
        payload = json.loads(stdout)
        self.assertEqual(payload["ok"], expected_code == 0)
        return payload["data"]

    def file_state(self):
        return {
            str(path.relative_to(self.data)): path.read_bytes()
            for path in self.data.rglob("*") if path.is_file()
        }

    def test_default_collect_persists_distinct_runs_and_repeat_preserves_review(self):
        first = self.data_result("collect", "EXAMPLE.COM.")
        self.assertEqual(first["plan"]["asset_value"], "example.com")
        self.assertEqual(first["status"], "complete")
        self.assertEqual(
            [step["task"]["id"] for step in first["steps"]],
            ["scan-crtsh", "scan-urlscan", "discover-crtsh"],
        )
        self.assertEqual(self.crt.calls, ["%example%", "example%", "%.example.com"])
        self.assertEqual(self.urlscan.calls, ["example*"])
        attempts = [step["attempt"] for step in first["steps"][:2]]
        self.assertNotEqual(attempts[0]["id"], attempts[1]["id"])
        self.assertNotEqual(attempts[0]["job_id"], attempts[1]["job_id"])
        discovery = first["steps"][2]["discovery"]
        self.assertTrue(discovery["run_id"])
        self.assertEqual(discovery["candidate_domains"], ["portal.example.com"])
        self.assertEqual(first["analysis"]["findings"]["total"], 1)
        self.assertEqual(first["analysis"]["overview"]["candidate_counts"]["total"], 1)

        findings = SQLiteFindingRepository(self.database)
        finding = findings.list_findings()[0]
        self.data_result(
            "findings", "review", finding.id, "--decision", "uncertain",
            "--reason", "Adayın marka ilişkisi insan tarafından incelenecek.",
        )
        prior = findings.get_finding(finding.id)
        candidates = SQLiteSurfaceCandidateRepository(self.database)
        candidate_before = candidates.list_candidates(self.asset.id, status=None, limit=10)
        repeated = self.data_result("collect", "example.com")
        self.assertEqual(findings.get_finding(finding.id), prior)
        self.assertEqual(
            candidates.list_candidates(self.asset.id, status=None, limit=10),
            candidate_before,
        )
        for step in repeated["steps"][:2]:
            self.assertEqual(step["attempt"]["result"]["summary"]["findings_created"], 0)
            self.assertEqual(step["attempt"]["result"]["summary"]["observations_created"], 0)
        self.assertEqual(repeated["steps"][2]["discovery"]["candidates_created"], 0)
        self.assertEqual(repeated["steps"][2]["discovery"]["evidence_created"], 0)
        self.feodo.assert_not_called()
        self.certpl.assert_not_called()
        self.harvester.assert_not_called()
        self.probe.assert_not_called()
        self.network.assert_not_called()

    def test_plan_is_read_only_and_never_acquires_lock_or_contacts_sources(self):
        before = self.file_state()
        with patch(
            "xti.adapters.worker_lock.LocalExecutionLock.acquire",
            side_effect=AssertionError("Planning must not acquire a writing lock."),
        ):
            plan = self.data_result(
                "collect", "example.com", "--plan", "--task", "ioc-certpl",
                "--task", "scan-crtsh", "--task", "discover-theharvester",
            )
        self.assertEqual(
            [task["id"] for task in plan["tasks"]],
            ["scan-crtsh", "discover-theharvester", "ioc-certpl"],
        )
        self.assertEqual(plan["asset_value"], "example.com")
        self.assertTrue(plan["notes"])
        self.assertEqual(self.file_state(), before)
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])
        self.feodo.assert_not_called()
        self.certpl.assert_not_called()
        self.harvester.assert_not_called()
        self.network.assert_not_called()

    def test_source_failure_does_not_hide_successful_independent_sources(self):
        self.crt.responses["%example%"] = SourceError("Sertifika kaynağı kapalı.")
        self.crt.responses["example%"] = SourceError("Sertifika kaynağı kapalı.")
        result = self.data_result("collect", "example.com", expected_code=3)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(
            [step["status"] for step in result["steps"]],
            ["failed", "complete", "complete"],
        )
        self.assertIn("kapalı", result["steps"][0]["attempt"]["queries"][0]["error"])
        self.assertEqual(result["analysis"]["findings"]["total"], 1)
        self.assertEqual(result["analysis"]["overview"]["candidate_counts"]["total"], 1)

    def test_all_selected_sources_failing_stays_failed_despite_readable_analysis(self):
        for pattern in ("%example%", "example%", "%.example.com"):
            self.crt.responses[pattern] = SourceError("Geçici kaynak kesintisi.")
        self.urlscan.responses["example*"] = SourceError("Geçici kaynak kesintisi.")
        result = self.data_result("collect", "example.com", expected_code=3)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(all(step["status"] == "failed" for step in result["steps"]))
        self.assertEqual(result["analysis"]["asset_value"], "example.com")
        self.assertEqual(result["analysis"]["findings"]["total"], 0)
        self.assertEqual(result["steps"][2]["discovery"]["status"], "failed")

    def test_explicit_task_replaces_defaults_and_preserves_optional_archive_error(self):
        self.harvester.side_effect = SourceError("commoncrawl: connection-closed")
        result = self.data_result(
            "collect", "example.com", "--task", "discover-theharvester", expected_code=3,
        )
        self.assertEqual(len(result["steps"]), 1)
        step = result["steps"][0]
        self.assertEqual(step["task"]["id"], "discover-theharvester")
        self.assertEqual(step["discovery"]["provider"], "theharvester")
        self.assertIn("connection-closed", step["discovery"]["error"])
        self.harvester.assert_called_once_with("%.example.com")
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])
        self.feodo.assert_not_called()
        self.certpl.assert_not_called()

    def test_selected_feeds_refresh_before_analysis_and_failure_preserves_catalog(self):
        now = datetime.now(timezone.utc)
        cert = parse_certpl_warning_response(
            content("example.com", version=now.strftime("%Y%m%d%H%M")), fetched_at=now,
        )
        self.feodo.side_effect = None
        self.feodo.return_value = snapshot(raw("192.0.2.40"))
        self.certpl.side_effect = None
        self.certpl.return_value = cert
        first = self.data_result(
            "collect", "example.com", "--task", "ioc-certpl", "--task", "ioc-feodo",
        )
        self.assertEqual(
            [step["task"]["id"] for step in first["steps"]], ["ioc-feodo", "ioc-certpl"],
        )
        self.assertEqual(first["analysis"]["ioc_catalog_status"], "available")
        self.assertEqual(
            [match["value"] for match in first["analysis"]["ioc_matches"]], ["example.com"],
        )
        self.assertEqual(first["steps"][0]["feed"]["source_name"], "feodo-tracker")
        self.assertEqual(first["steps"][1]["feed"]["source_name"], "certpl-warning-list")
        self.assertNotEqual(first["steps"][0]["feed"]["id"], first["steps"][1]["feed"]["id"])
        self.certpl.side_effect = SourceError("Kaynak kesildi; önceki katalog korunuyor.")
        repeated = self.data_result(
            "collect", "example.com", "--task", "ioc-certpl", expected_code=3,
        )
        self.assertEqual(repeated["status"], "failed")
        self.assertEqual(repeated["steps"][0]["feed"]["status"], "failed")
        self.assertEqual(
            repeated["analysis"]["ioc_matches"], first["analysis"]["ioc_matches"],
        )
        state = SQLiteCtiFeedRepository(self.database, CERTPL_POLICY).status(run_limit=5)
        self.assertEqual(state.active_assertion_count, 1)
        self.assertEqual([run.status for run in state.recent_runs], ["failed", "complete"])
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])
        self.harvester.assert_not_called()

        code, stdout, _stderr = self.invoke(
            "collect", "example.com", "--task", "ioc-certpl", as_json=False,
        )
        self.assertEqual(code, 3)
        self.assertIn("Liste alınamadı", stdout)
        self.assertNotIn("Kaynak listesindeki gösterge: 0", stdout)
        self.assertIn("example.com", stdout)

    def test_invalid_input_does_not_write_or_start_any_selected_task(self):
        before = self.file_state()
        invalid = (
            ("unknown.example",),
            ("https://example.com",),
            ("example.com", "--task", "unknown"),
            ("example.com", "--task", "scan-crtsh", "--task", "scan-crtsh"),
            ("example.com", "--task", "ioc-feodo", "--typos"),
            ("example.com", "--finding-limit", "0"),
            ("example.com", "--stale-after-hours", "0"),
        )
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                code, stdout, stderr = self.invoke("collect", *arguments)
                self.assertEqual((code, stdout), (2, ""))
                self.assertFalse(json.loads(stderr)["ok"])
                self.assertEqual(self.file_state(), before)
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])
        self.feodo.assert_not_called()
        self.certpl.assert_not_called()
        self.harvester.assert_not_called()
        self.network.assert_not_called()

    def test_uninitialized_storage_is_not_created_for_plan_or_run(self):
        self.data = Path(self.temp.name) / "missing data"
        for suffix in ((), ("--plan",)):
            with self.subTest(suffix=suffix):
                code, stdout, stderr = self.invoke("collect", "example.com", *suffix)
                self.assertIn(code, (1, 2))
                self.assertEqual(stdout, "")
                self.assertFalse(json.loads(stderr)["ok"])
                self.assertFalse(self.data.exists())
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])

    def test_human_report_shows_concrete_candidates_and_escapes_source_error(self):
        self.crt.responses["%example%"] = SourceError("Kaynak\x1b[31m kesildi.")
        code, stdout, stderr = self.invoke("collect", "example.com", as_json=False)
        self.assertEqual(code, 3)
        self.assertNotIn("\x1b", stdout + stderr)
        self.assertIn("example-support.net", stdout)
        self.assertIn("portal.example.com", stdout)
        self.assertIn("kesildi", stdout)
        self.assertIn("crt.sh", stdout)
        self.assertIn("urlscan", stdout)
        self.assertIn("Kaynak denemelerinden sonra", stdout)
        self.assertNotIn("yeni internet bağlantısı yapılmadı", stdout)


if __name__ == "__main__":
    unittest.main()

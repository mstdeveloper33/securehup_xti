"""Exercise daily collection, review and case preservation without live sources."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.maigret_username import INTEGRATION_PROFILE
from xti.domain.brand_username import BrandProfileMatch, BrandUsernamePreview
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError
from tests.test_discovery import FakeSource, batch, document


class DailyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "daily use"
        self.database = self.data / "xti.db"
        self.source = FakeSource({
            "%example%": batch(document("example-support.net")),
        })
        for target, value in (
            ("xti.interfaces.cli.CrtShSource", self.source),
            ("xti.interfaces.cli.UrlscanSource", FakeSource()),
        ):
            self.enterContext(patch(target, return_value=value))
        self.target_probe = self.enterContext(patch(
            "xti.interfaces.cli.HttpsTargetProbe",
            side_effect=AssertionError("Daily passive workflow must not probe targets."),
        ))
        self.network = self.enterContext(patch(
            "socket.socket.connect",
            side_effect=AssertionError("Daily workflow tests must remain offline."),
        ))

    def invoke(self, *arguments, expected_code=0):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([
                "--data-dir", str(self.data), "--json", *arguments,
            ])
        self.assertEqual((code, stderr.getvalue()), (expected_code, ""))
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["ok"], expected_code == 0)
        return payload["data"]

    def test_scan_triage_case_and_repeat_preserve_evidence_and_timeline(self):
        first = self.invoke("scan", "example.com", "--source", "crt.sh")
        self.assertEqual(first["summary"]["findings_created"], 1)
        findings = self.invoke("findings", "list")["findings"]
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        finding_id = finding["id"]
        self.assertEqual(finding["domain"], "example-support.net")
        self.assertEqual(finding["status"], "new")
        triage = self.invoke("triage")
        self.assertEqual(triage["items"][0]["finding"]["id"], finding_id)
        details = self.invoke("findings", "show", finding_id)
        self.assertEqual(details["reviews"], [])
        self.assertEqual(details["assessments"], [])
        self.assertEqual(len(details["observations"]), 1)

        case_id = self.invoke(
            "cases", "create", "Example aday incelemesi",
            "--summary", "Kaynakta görülen benzer adresin inceleme kaydı.",
            "--priority", "low", "--reason", "Adayın kaynak kanıtını takip etmek için.",
        )["case"]["id"]
        link = self.invoke(
            "cases", "evidence-add", case_id,
            "--type", "finding", "--evidence-id", finding_id,
            "--reason", "Pasif kaynak kaydı bu incelemeye eklendi.",
        )["evidence"]
        self.invoke(
            "cases", "task-add", case_id, "Adayın marka ilişkisini doğrula",
            "--reason", "Kaynak eşleşmesi kesin taklit kararı değildir.",
        )
        report = self.invoke("cases", "report", case_id)
        self.assertEqual(report["active_evidence_count"], 1)
        self.assertEqual(report["open_task_count"], 1)
        self.assertEqual(report["total_activity_count"], 3)
        self.assertEqual(report["case"]["status"], "open")

        before_reads = self.database.read_bytes()
        self.invoke("analyze", "example.com")
        self.invoke("triage")
        self.invoke("inbox")
        self.assertEqual(self.invoke("cases", "report", case_id), report)
        self.assertEqual(self.database.read_bytes(), before_reads)

        repeated = self.invoke("scan", "example.com", "--source", "crt.sh")
        self.assertEqual(repeated["summary"]["findings_created"], 0)
        self.assertEqual(repeated["summary"]["observations_created"], 0)
        self.assertEqual(self.invoke("findings", "list")["findings"], findings)
        self.assertEqual(self.invoke("findings", "show", finding_id), details)
        repeated_link = self.invoke(
            "cases", "evidence-add", case_id,
            "--type", "finding", "--evidence-id", finding_id,
            "--reason", "Aynı kaynak kaydı tekrar kontrol edildi.",
        )
        self.assertEqual(repeated_link["action"], "unchanged")
        self.assertEqual(repeated_link["evidence"], link)
        self.assertEqual(self.invoke("cases", "report", case_id), report)
        self.target_probe.assert_not_called()
        self.network.assert_not_called()

    def test_social_baseline_failure_and_repeat_keep_previous_success(self):
        self.invoke("init")
        watch_id = self.invoke(
            "brand", "watch-add", "Example sosyal takip", "examplebrand",
            "--site", "GitHub",
        )["watch"]["id"]
        preview = BrandUsernamePreview(
            username="examplebrand", source="Maigret", source_version="0.6.6",
            integration_profile=INTEGRATION_PROFILE,
            checked_at=datetime.now(timezone.utc).isoformat(),
            requested_platforms=("GitHub",),
            matches=(BrandProfileMatch(
                "GitHub", "https://github.com/examplebrand", "found_unverified",
            ),),
            unreported_platforms=(),
            notes=("Sahiplik veya taklit kararı değildir.",),
        )
        with patch(
            "xti.interfaces.cli.MaigretUsernameSource.preview",
            side_effect=(preview, SourceError("Geçici kaynak hatası."), preview),
        ):
            baseline = self.invoke("brand", "watch-run", watch_id)
            failed = self.invoke("brand", "watch-run", watch_id, expected_code=3)
            repeated = self.invoke("brand", "watch-run", watch_id)
        self.assertTrue(baseline["is_baseline"])
        self.assertEqual(baseline["attention_count"], 0)
        self.assertEqual(failed["run"]["status"], "failed")
        self.assertFalse(repeated["is_baseline"])
        self.assertEqual(
            repeated["run"]["previous_complete_run_id"], baseline["run"]["id"],
        )
        self.assertEqual(repeated["items"][0]["action"], "unchanged_found")
        self.assertIsNone(repeated["items"][0]["current_review"])
        self.assertEqual(repeated["attention_count"], 0)
        history = self.invoke("brand", "watch-show", watch_id)
        self.assertEqual(history["total_run_count"], 3)
        self.assertEqual(self.invoke("cases", "list")["cases"], [])
        self.assertEqual(self.invoke("doctor")["notification_count"], 0)
        self.target_probe.assert_not_called()
        self.network.assert_not_called()


if __name__ == "__main__":
    unittest.main()

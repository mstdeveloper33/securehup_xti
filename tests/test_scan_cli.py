"""Public scan/watch commands with a fake source, never the real internet."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError

from tests.test_discovery import FakeSource, batch, document


class ScanCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data with spaces"

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

    def test_scan_initializes_and_saves_target_without_a_list_file(self):
        source = FakeSource({"%example%": batch(document("example-support.net"))})
        code, stdout, stderr = self.invoke("scan", "EXAMPLE.COM.", source=source)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        output = json.loads(stdout)
        self.assertIs(output["ok"], True)
        self.assertEqual(output["data"]["status"], "complete")
        self.assertEqual(output["data"]["candidate_domains"], ["example-support.net"])
        assets = SQLiteAssetRepository(self.data / "xti.db").list()
        self.assertEqual([asset.value for asset in assets], ["example.com"])
        findings = SQLiteFindingRepository(self.data / "xti.db").list_findings()
        self.assertEqual([finding.domain for finding in findings], ["example-support.net"])
        self.assertEqual(source.calls, ["%example%", "example%"])

    def test_scan_without_argument_uses_registered_targets(self):
        self.assertEqual(self.invoke("scan", "example.com")[0], 0)
        source = FakeSource({"example%": batch(document("example-support.net"))})
        code, stdout, stderr = self.invoke("scan", source=source)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["data"]["targets"], ["example.com"])
        self.assertEqual(source.calls, ["%example%", "example%"])

    def test_invalid_target_never_initializes_or_calls_source(self):
        for target in ("https://example.com", "abc.com", "co.uk", "xn--exmple-cua.com"):
            with self.subTest(target=target):
                source = FakeSource()
                code, stdout, stderr = self.invoke("scan", target, source=source)
                self.assertEqual(code, 2, stderr)
                self.assertEqual(stdout, "")
                self.assertFalse(json.loads(stderr)["ok"])
                self.assertFalse(self.data.exists())
                self.assertEqual(source.calls, [])

    def test_missing_registration_reports_error_without_inventing_a_target(self):
        source = FakeSource()
        code, stdout, stderr = self.invoke("scan", source=source)
        self.assertIn(code, (1, 2), stderr)
        self.assertEqual(stdout, "")
        self.assertFalse(json.loads(stderr)["ok"])
        self.assertFalse(self.data.exists())
        self.assertEqual(source.calls, [])

    def test_partial_and_total_source_failure_have_nonzero_exit_and_query_errors(self):
        for responses, expected_status in (
            ({"%example%": SourceError("Zaman aşımı.")}, "partial"),
            ({"%example%": SourceError("Zaman aşımı."),
              "example%": SourceError("Kaynak yanıt vermedi.")}, "failed"),
        ):
            with self.subTest(expected_status=expected_status):
                code, stdout, stderr = self.invoke("scan", "example.com", source=FakeSource(responses))
                self.assertEqual(code, 3, stderr)
                output = json.loads(stdout)
                self.assertIs(output["ok"], False)
                self.assertEqual(output["data"]["status"], expected_status)
                self.assertTrue(output["data"]["queries"][0]["error"])
                self.assertEqual(output["data"]["summary"]["findings_created"], 0)

    def test_human_output_escapes_external_source_error(self):
        source = FakeSource({"%example%": SourceError("Yanıt\x1b[31m bozuk.")})
        code, stdout, stderr = self.invoke("scan", "example.com", source=source, as_json=False)
        self.assertEqual(code, 3)
        self.assertNotIn("\x1b", stdout + stderr)
        self.assertIn("Yanıt", stdout + stderr)

    def test_watch_two_cycles_emits_json_per_cycle_and_preserves_deduplication(self):
        source = FakeSource({"%example%": batch(document("example-support.net"))})
        with patch("xti.interfaces.cli.time.sleep") as sleep:
            code, stdout, stderr = self.invoke(
                "watch", "example.com", "--interval", "300", "--cycles", "2", source=source,
            )
        self.assertEqual(code, 0, stderr)
        lines = [json.loads(line) for line in stdout.splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line["ok"] for line in lines))
        self.assertEqual(lines[0]["data"]["summary"]["findings_created"], 1)
        self.assertEqual(lines[1]["data"]["summary"]["findings_created"], 0)
        self.assertEqual(len(source.calls), 4)
        sleep.assert_called_once_with(300)

    def test_watch_invalid_schedule_is_rejected_before_initialization(self):
        for arguments in (("--interval", "299"), ("--cycles", "0"), ("--cycles", "-1")):
            with self.subTest(arguments=arguments):
                source = FakeSource()
                code, stdout, stderr = self.invoke("watch", "example.com", *arguments, source=source)
                self.assertEqual(code, 2, stderr)
                self.assertEqual(stdout, "")
                self.assertFalse(self.data.exists())
                self.assertEqual(source.calls, [])

    def test_watch_single_cycle_does_not_sleep_and_reports_source_failure(self):
        source = FakeSource({
            "%example%": SourceError("Kaynak kapalı."),
            "example%": SourceError("Kaynak kapalı."),
        })
        with patch("xti.interfaces.cli.time.sleep") as sleep:
            code, stdout, stderr = self.invoke("watch", "example.com", "--cycles", "1", source=source)
        self.assertEqual(code, 3, stderr)
        self.assertEqual(json.loads(stdout)["data"]["status"], "failed")
        sleep.assert_not_called()

    def test_watch_continues_after_source_failure_but_keeps_nonzero_exit(self):
        class RecoveringSource(FakeSource):
            def search(self, pattern):
                self.calls.append(pattern)
                if len(self.calls) <= 2:
                    raise SourceError("Geçici bağlantı hatası.")
                return batch(document("example-support.net"))

        with patch("xti.interfaces.cli.time.sleep") as sleep:
            code, stdout, stderr = self.invoke(
                "watch", "example.com", "--cycles", "2", source=RecoveringSource(),
            )
        self.assertEqual(code, 3, stderr)
        results = [json.loads(line) for line in stdout.splitlines()]
        self.assertEqual([item["data"]["status"] for item in results], ["failed", "complete"])
        self.assertEqual(results[1]["data"]["summary"]["findings_created"], 1)
        sleep.assert_called_once()

    def test_keyboard_interrupt_stops_watch_without_traceback(self):
        with patch("xti.interfaces.cli.time.sleep", side_effect=KeyboardInterrupt):
            code, stdout, stderr = self.invoke("watch", "example.com")
        self.assertEqual(code, 130)
        self.assertEqual(len(stdout.splitlines()), 1)
        self.assertTrue(json.loads(stdout)["ok"])
        self.assertEqual(json.loads(stderr)["error"]["code"], "interrupted")
        self.assertNotIn("Traceback", stderr)


if __name__ == "__main__":
    unittest.main()

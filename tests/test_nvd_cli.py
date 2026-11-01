"""Terminal-first single-CVE NVD synchronization and offline review."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.domain.vulnerability import (
    CvssMetric,
    NVD_CVE_SOURCE,
    NvdCve,
    NvdCveSnapshot,
    nvd_cve_url,
)
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


def snapshot():
    record = NvdCve(
        "CVE-2021-44228", "security@example.org",
        "2021-12-10T10:15:09.143000+00:00",
        "2026-08-11T19:33:44.513000+00:00", "Analyzed", "Example issue",
        (CvssMetric(
            "nvd@nist.gov", "Primary", "3.1", "CVSS:3.1/AV:N/AC:L",
            "10", "CRITICAL", "3.9", "6",
        ),),
        ("CWE-917",), 1,
    )
    raw = json.dumps({"id": record.cve_id}, sort_keys=True, separators=(",", ":"))
    return NvdCveSnapshot(
        NVD_CVE_SOURCE, nvd_cve_url(record.cve_id), "2.0",
        "2026-10-29T15:01:05.762000+00:00",
        hashlib.sha256(raw.encode()).hexdigest(), raw, record,
    )


class FakeSource:
    def __init__(self):
        self.value = snapshot()
        self.error = None
        self.calls = []

    def fetch(self, cve_id):
        self.calls.append(cve_id)
        if self.error:
            raise SourceError(self.error)
        return self.value


class NvdCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.database = self.data / "xti.db"
        self.source = FakeSource()
        self.ok("init")

    def invoke(self, *arguments, as_json=True, data=None):
        argv = ["--data-dir", str(data or self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("xti.interfaces.cli.NvdCveSource", return_value=self.source),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def ok(self, *arguments):
        code, stdout, stderr = self.invoke(*arguments)
        self.assertEqual((code, stderr), (0, ""))
        payload = json.loads(stdout)
        self.assertTrue(payload["ok"])
        return payload["data"]

    def test_sync_then_offline_status_list_show_are_read_only(self):
        synced = self.ok(
            "vuln", "sync", "--source", "nvd", "--cve", "cve-2021-44228",
        )
        self.assertEqual((synced["status"], synced["created_count"]), ("complete", 1))
        before = self.database.read_bytes()
        status = self.ok("vuln", "status", "--source", "nvd")
        listed = self.ok("vuln", "list", "--source", "nvd")
        shown = self.ok("vuln", "show", "CVE-2021-44228", "--source", "nvd")
        self.assertEqual(status["record_count"], 1)
        self.assertEqual(listed["items"][0]["record"]["cve_id"], "CVE-2021-44228")
        self.assertEqual(shown["record"]["record"]["cvss_metrics"][0]["base_score"], "10")
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.source.calls, ["CVE-2021-44228"])

        code, stdout, stderr = self.invoke(
            "vuln", "show", "CVE-2021-44228", "--source", "nvd", as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("CVSS 3.1", stdout)
        self.assertIn("eşleştirilmedi", stdout)

    def test_failure_preserves_record_and_missing_database_stops_source(self):
        self.ok("vuln", "sync", "--source", "nvd", "--cve", "CVE-2021-44228")
        self.source.error = "NVD geçici olarak yanıt vermedi."
        code, stdout, stderr = self.invoke(
            "vuln", "sync", "--source", "nvd", "--cve", "CVE-2021-44228",
        )
        self.assertEqual((code, stderr), (3, ""))
        self.assertFalse(json.loads(stdout)["ok"])
        self.assertEqual(self.ok("vuln", "status", "--source", "nvd")["record_count"], 1)

        missing = Path(self.temp.name) / "missing"
        calls = len(self.source.calls)
        code, stdout, stderr = self.invoke(
            "vuln", "sync", "--source", "nvd", "--cve", "CVE-2021-44228",
            data=missing,
        )
        self.assertEqual((code, stdout), (1, ""))
        self.assertEqual(json.loads(stderr)["error"]["code"], "storage_error")
        self.assertEqual(len(self.source.calls), calls)
        self.assertFalse(missing.exists())

    def test_invalid_options_do_not_write_or_call_source(self):
        before = self.database.read_bytes()
        for arguments in (
            ("vuln", "sync", "--source", "nvd"),
            ("vuln", "sync", "--source", "nvd", "--cve", "bad"),
            ("vuln", "sync", "--source", "kev", "--cve", "CVE-2021-44228"),
            ("vuln", "list", "--source", "nvd", "--all"),
        ):
            code, stdout, stderr = self.invoke(*arguments)
            self.assertEqual((code, stdout), (2, ""))
            self.assertTrue(stderr)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.source.calls, [])


if __name__ == "__main__":
    unittest.main()

"""Terminal-first FIRST EPSS synchronization and offline review."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.domain.vulnerability import (
    EpssCatalogSnapshot,
    EpssScore,
    FIRST_EPSS_SOURCE,
    FIRST_EPSS_URL,
)
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


def catalog(value="0.1234"):
    entries = (EpssScore("CVE-2021-44228", value, "0.9876"),)
    return EpssCatalogSnapshot(
        FIRST_EPSS_SOURCE, FIRST_EPSS_URL, "v2026.06.15", "2026-10-29",
        hashlib.sha256(value.encode()).hexdigest(), entries,
    )


class FakeSource:
    def __init__(self):
        self.value = catalog()
        self.error = None
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if self.error:
            raise SourceError(self.error)
        return self.value


class EpssCLITests(unittest.TestCase):
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
            patch("xti.interfaces.cli.FirstEpssSource", return_value=self.source),
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
        synced = self.ok("vuln", "sync", "--source", "epss")
        self.assertEqual((synced["status"], synced["created_count"]), ("complete", 1))
        before = self.database.read_bytes()
        status = self.ok("vuln", "status", "--source", "epss")
        listed = self.ok("vuln", "list", "--source", "epss")
        shown = self.ok("vuln", "show", "CVE-2021-44228", "--source", "epss")
        self.assertEqual(status["active_count"], 1)
        self.assertEqual(listed["items"][0]["score"]["epss"], "0.1234")
        self.assertEqual(shown["record"]["score"]["cve_id"], "CVE-2021-44228")
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.source.calls, 1)

        code, stdout, stderr = self.invoke(
            "vuln", "show", "CVE-2021-44228", "--source", "epss", as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("30 günde", stdout)
        self.assertIn("maruziyet", stdout)

    def test_failure_preserves_previous_catalog_and_missing_database_stops_source(self):
        self.ok("vuln", "sync", "--source", "epss")
        self.source.error = "FIRST geçici olarak yanıt vermedi."
        code, stdout, stderr = self.invoke("vuln", "sync", "--source", "epss")
        self.assertEqual((code, stderr), (3, ""))
        self.assertFalse(json.loads(stdout)["ok"])
        self.assertEqual(self.ok("vuln", "status", "--source", "epss")["active_count"], 1)

        missing = Path(self.temp.name) / "missing"
        calls = self.source.calls
        code, stdout, stderr = self.invoke(
            "vuln", "sync", "--source", "epss", data=missing,
        )
        self.assertEqual((code, stdout), (1, ""))
        self.assertEqual(json.loads(stderr)["error"]["code"], "storage_error")
        self.assertEqual(self.source.calls, calls)
        self.assertFalse(missing.exists())

    def test_invalid_inputs_do_not_write_or_call_source(self):
        before = self.database.read_bytes()
        for arguments in (
            ("vuln", "list", "--source", "epss", "--limit", "0"),
            ("vuln", "show", "not-a-cve", "--source", "epss"),
            ("vuln", "status", "--source", "epss", "--limit", "101"),
        ):
            code, stdout, stderr = self.invoke(*arguments)
            self.assertEqual((code, stdout), (2, ""))
            self.assertTrue(stderr)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.source.calls, 0)


if __name__ == "__main__":
    unittest.main()

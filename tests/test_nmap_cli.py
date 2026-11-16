"""Terminal acceptance for separately stored authorized Nmap evidence."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.domain.nmap_scan import (
    NMAP_POLICY_VERSION,
    NmapOpenPort,
    NmapScanResult,
    NmapStateCounts,
)
from xti.interfaces.cli import main


START = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
ADDRESS = "93.184.216.34"


class FakeNmapProbe:
    def __init__(self):
        self.calls = []
        self.readiness_calls = 0

    def readiness(self):
        self.readiness_calls += 1
        return "7.95", "/usr/bin/nmap"

    def check(self, domain, address, plan, execution_id):
        self.calls.append((domain, address, plan, execution_id))
        return NmapScanResult(
            execution_id, domain, address, START.isoformat(),
            (START + timedelta(seconds=1)).isoformat(), NMAP_POLICY_VERSION,
            "resolved", (address,), address, plan, "complete", "7.95",
            NmapStateCounts(1, plan.port_count - 1, 0),
            (NmapOpenPort(443, "syn-ack"),), False, "a" * 64, (),
            ("Sınırlı Nmap TCP kontrolü.",),
        )


class NmapCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.database = self.data / "xti.db"
        self.probe = FakeNmapProbe()
        self.ok("init")
        self.ok("assets", "add", "example.com")
        self.ok("surface", "approve", "example.com", "--reason", "Kendi domainim")

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("xti.interfaces.cli.NmapTcpConnectProbe", return_value=self.probe),
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

    def test_readiness_check_and_offline_show(self):
        ready = self.ok("surface", "nmap", "readiness")
        self.assertEqual(ready["version"], "7.95")
        checked = self.ok(
            "surface", "nmap", "check", "example.com", "--address", ADDRESS,
            "--reason", "Yönettiğim kesin sunucu", "--profile", "custom",
            "--ports", "80,443", "--timeout-seconds", "45", "--max-rate", "10",
            "--max-retries", "0", "--max-probes", "2",
        )
        self.assertEqual(checked["status"], "complete")
        self.assertEqual(checked["plan"]["port_spec"], "80,443")
        self.assertEqual(checked["checks"][0]["result"]["state_counts"]["open"], 1)
        before = self.database.read_bytes()
        history = self.ok("surface", "nmap", "show", "example.com")
        self.assertEqual(history["total_check_count"], 1)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(len(self.probe.calls), 1)

    def test_wide_or_multi_target_plan_is_rejected_before_probe(self):
        for arguments in (
            ("--profile", "full"),
            (
                "--profile", "safe", "--address", "8.8.8.8",
                "--target-limit", "2",
            ),
        ):
            code, stdout, stderr = self.invoke(
                "surface", "nmap", "check", "example.com", "--address", ADDRESS,
                "--reason", "Yetkili sunucular", *arguments,
            )
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertTrue(stderr)
        self.assertEqual(self.probe.calls, [])


if __name__ == "__main__":
    unittest.main()

"""Terminal workflow for bounded foreground surface monitoring."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.enrichment import ProbeResult
from xti.domain.mail import MailDnsResult
from xti.domain.services import (
    SERVICE_POLICY_VERSION,
    SERVICE_PORT_HINTS,
    SERVICE_PORTS,
    ServicePortResult,
    ServiceScanResult,
)
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
ADDRESS = "93.184.216.34"


def web_result(address):
    return ProbeResult(
        "example.com", NOW.isoformat(), NOW.isoformat(), "monitor-cli-test-v1",
        "resolved", (address,), "valid", "responded", 200, address, (),
        ("Sınırlı HEAD kontrolü.",),
    )


def mail_result(policy):
    return MailDnsResult(
        "example.com", NOW.isoformat(), NOW.isoformat(), "monitor-mail-test-v1",
        "present", ("10 mail.example.com",),
        "present", ("v=spf1 -all",),
        "present", (policy,), (), ("DKIM seçicisi tahmin edilmez.",),
    )


def service_result(opened):
    return ServiceScanResult(
        "example.com", ADDRESS, NOW.isoformat(),
        (NOW + timedelta(seconds=1)).isoformat(), SERVICE_POLICY_VERSION,
        "resolved", (ADDRESS,), ADDRESS,
        tuple(
            ServicePortResult(
                port, "open" if port in set(opened) else "closed",
                SERVICE_PORT_HINTS[port],
            )
            for port in SERVICE_PORTS
        ),
        (), ("Sabit sınırlı TCP kontrolü.",),
    )


class SequenceProbe:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def check(self, *arguments):
        self.calls.append(arguments)
        return self.results.pop(0)


class SurfaceMonitorCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.database = self.data / "xti.db"
        self.web = SequenceProbe([
            web_result(ADDRESS), web_result("93.184.216.35"),
        ])
        self.mail = SequenceProbe([
            mail_result("v=DMARC1; p=reject"),
            mail_result("v=DMARC1; p=quarantine"),
        ])
        self.services = SequenceProbe([
            service_result((22, 443)), service_result((443,)),
        ])
        self.ok("init")
        self.ok("assets", "add", "example.com")
        self.ok(
            "surface", "approve", "example.com", "--reason", "Kendi alan adım",
        )

    def invoke(self, *arguments, as_json=True):
        argv = ["--data-dir", str(self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("xti.interfaces.cli.HttpsTargetProbe", return_value=self.web),
            patch("xti.interfaces.cli.GoogleMailDnsProbe", return_value=self.mail),
            patch("xti.interfaces.cli.BoundedServicePortProbe", return_value=self.services),
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

    def error(self, *arguments, code=2):
        actual, stdout, stderr = self.invoke(*arguments)
        self.assertEqual(actual, code)
        self.assertEqual(stdout, "")
        return json.loads(stderr)

    def test_default_one_cycle_records_web_and_mail_without_service_probe(self):
        report = self.ok(
            "surface", "monitor", "example.com", "--cycles", "1",
            "--interval", "300", "--duration", "60",
        )
        self.assertEqual(report["checks"], ["web", "mail"])
        self.assertEqual((report["completed_cycles"], report["completed_checks"]), (1, 2))
        self.assertEqual(report["notifications_created"], 0)
        self.assertEqual(self.web.calls, [("example.com",)])
        self.assertEqual(self.mail.calls, [("example.com",)])
        self.assertEqual(self.services.calls, [])

    def test_three_selected_checks_reuse_change_notifications(self):
        arguments = (
            "surface", "monitor", "example.com", "--checks", "web", "mail", "services",
            "--service-address", ADDRESS,
            "--service-reason", "Yönettiğim sabit sunucu",
            "--cycles", "1", "--interval", "300", "--duration", "60",
        )
        first = self.ok(*arguments)
        second = self.ok(*arguments)
        self.assertEqual(first["notifications_created"], 0)
        self.assertEqual(second["notifications_created"], 3)
        self.assertEqual(
            [item["change_kind"] for item in second["steps"]],
            ["changed", "changed", "changed"],
        )
        inbox = self.ok("inbox", "list", "--status", "all")
        self.assertEqual((inbox["total_count"], inbox["unread_count"]), (3, 3))

    def test_service_options_and_duplicate_checks_fail_before_probe_or_write(self):
        before = self.database.read_bytes()
        self.error(
            "surface", "monitor", "example.com", "--checks", "services",
            "--cycles", "1", "--interval", "300", "--duration", "60",
        )
        self.error(
            "surface", "monitor", "example.com", "--checks", "web", "web",
            "--cycles", "1", "--interval", "300", "--duration", "60",
        )
        self.error(
            "surface", "monitor", "example.com", "--checks", "web",
            "--service-address", ADDRESS, "--service-reason", "Yetkiliyim",
            "--cycles", "1", "--interval", "300", "--duration", "60",
        )
        self.assertEqual((self.web.calls, self.mail.calls, self.services.calls), ([], [], []))
        self.assertEqual(self.database.read_bytes(), before)

    def test_shared_worker_lock_blocks_every_network_probe(self):
        with LocalExecutionLock(self.database).acquire():
            payload = self.error(
                "surface", "monitor", "example.com", "--cycles", "1",
                "--interval", "300", "--duration", "60", code=4,
            )
        self.assertEqual(payload["error"]["code"], "worker_busy")
        self.assertEqual((self.web.calls, self.mail.calls, self.services.calls), ([], [], []))

    def test_human_output_explains_foreground_limit_and_evidence(self):
        code, stdout, stderr = self.invoke(
            "surface", "monitor", "example.com", "--checks", "web",
            "--cycles", "1", "--interval", "300", "--duration", "60",
            as_json=False,
        )
        self.assertEqual(code, 0, stderr)
        self.assertIn("Dış yüzey izleme oturumu tamamlandı", stdout)
        self.assertIn("Kalıcı kontrol kanıtı: 1", stdout)
        self.assertIn("yalnız terminal açıkken çalışır", stdout)
        self.assertIn("Dış yüzey izleme 1/1", stderr)


if __name__ == "__main__":
    unittest.main()

"""Terminal workflow for bounded exact-IP TCP service inventory."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.domain.services import (
    SERVICE_POLICY_VERSION,
    SERVICE_PORT_HINTS,
    SERVICE_PORTS,
    ServicePortResult,
    ServiceScanResult,
)
from xti.interfaces.cli import main


START = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
ADDRESS = "93.184.216.34"


def result(*, dns_status="resolved", opened=(22, 443)):
    complete = dns_status == "resolved"
    return ServiceScanResult(
        "example.com", ADDRESS, START.isoformat(),
        (START + timedelta(seconds=1)).isoformat(), SERVICE_POLICY_VERSION,
        dns_status, (ADDRESS if complete else "8.8.8.8",), ADDRESS if complete else None,
        tuple(
            ServicePortResult(
                port, "open" if port in set(opened) else "closed",
                SERVICE_PORT_HINTS[port],
            )
            for port in SERVICE_PORTS
        ) if complete else (),
        (
            ()
            if complete
            else ("Onaylanan IP güncel DNS yanıtında yok; portlara bağlanılmadı.",)
        ),
        ("Sabit sınırlı TCP kontrolü.",),
    )


class FakeProbe:
    def __init__(self, value=None):
        self.value = value or result()
        self.calls = []

    def check(self, domain, address):
        self.calls.append((domain, address))
        return self.value


class ServiceCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.database = self.data / "xti.db"
        self.probe = FakeProbe()
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
            patch("xti.interfaces.cli.BoundedServicePortProbe", return_value=self.probe),
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

    def test_check_show_overview_and_technology_hints_keep_explainable_evidence(self):
        check = self.ok(
            "surface", "services", "check", "example.com",
            "--address", ADDRESS, "--reason", "Yönettiğim sabit sunucu",
        )
        self.assertEqual(check["status"], "complete")
        self.assertEqual(
            [item["port"] for item in check["check"]["result"]["ports"]
             if item["state"] == "open"],
            [22, 443],
        )
        self.assertEqual(self.probe.calls, [("example.com", ADDRESS)])
        before = self.database.read_bytes()
        history = self.ok("surface", "services", "show", "example.com")
        overview = self.ok("surface", "overview", "example.com")
        technologies = self.ok("surface", "technologies", "example.com")
        self.assertEqual(history["total_check_count"], 1)
        self.assertEqual(
            [item["target_value"] for item in overview["relations"]
             if item["kind"] == "offers_tcp_service"],
            [f"{ADDRESS}:22/tcp", f"{ADDRESS}:443/tcp"],
        )
        self.assertEqual(technologies["hint_count"], 2)
        self.assertEqual(technologies["cve_match_eligible_count"], 0)
        self.assertEqual(
            [item["port"] for item in technologies["hints"]], [22, 443],
        )
        self.assertTrue(all(
            item["vendor"] is None
            and item["product"] is None
            and item["version"] is None
            and not item["cve_match_eligible"]
            for item in technologies["hints"]
        ))
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.probe.calls, [("example.com", ADDRESS)])

        code, stdout, stderr = self.invoke(
            "surface", "technologies", "example.com", as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Teknoloji ve ürün ipuçları: example.com", stdout)
        self.assertIn("Ürün: bilinmiyor", stdout)
        self.assertIn("CVE eşleştirmesi: uygun değil", stdout)
        self.assertEqual(self.database.read_bytes(), before)

    def test_invalid_address_or_reason_stops_before_probe_and_write(self):
        before = self.database.read_bytes()
        for arguments in (
            ("--address", "127.0.0.1", "--reason", "Yerel"),
            ("--address", ADDRESS, "--reason", ""),
        ):
            code, stdout, stderr = self.invoke(
                "surface", "services", "check", "example.com", *arguments,
            )
            self.assertEqual(code, 2)
            self.assertEqual(stdout, "")
            self.assertTrue(stderr)
        self.assertEqual(self.probe.calls, [])
        self.assertEqual(self.database.read_bytes(), before)

    def test_dns_mismatch_is_saved_as_failed_evidence_without_port_results(self):
        self.probe.value = result(dns_status="address_mismatch")
        code, stdout, stderr = self.invoke(
            "surface", "services", "check", "example.com",
            "--address", ADDRESS, "--reason", "Yönettiğim sabit sunucu",
        )
        self.assertEqual((code, stderr), (3, ""))
        payload = json.loads(stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["data"]["status"], "failed")
        self.assertEqual(payload["data"]["check"]["result"]["ports"], [])
        self.assertEqual(self.ok(
            "surface", "services", "show", "example.com",
        )["total_check_count"], 1)

    def test_real_service_change_appears_once_in_local_inbox(self):
        self.ok(
            "surface", "services", "check", "example.com",
            "--address", ADDRESS, "--reason", "Yönettiğim sabit sunucu",
        )
        self.probe.value = result(opened=(443,))
        changed = self.ok(
            "surface", "services", "check", "example.com",
            "--address", ADDRESS, "--reason", "Yönettiğim sabit sunucu",
        )
        self.assertEqual(changed["check"]["change"]["kind"], "changed")
        self.assertTrue(changed["notification_created"])
        page = self.ok("inbox")
        self.assertEqual((page["total_count"], page["unread_count"]), (1, 1))
        item = page["items"][0]
        self.assertEqual(item["notification"]["event_type"], "surface_evidence_changed")
        self.assertEqual(item["change_evidence"]["evidence_type"], "service")
        self.assertEqual(
            item["change_evidence"]["port_changes"],
            [{"port": 22, "before": "open", "after": "closed"}],
        )
        code, stdout, stderr = self.invoke(
            "inbox", "show", item["notification"]["id"], as_json=False,
        )
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("TCP servis değişikliği", stdout)
        self.assertIn("22/tcp | Açık → Kapalı", stdout)
        self.assertIn("tek başına saldırı veya zafiyet kararı değildir", stdout)

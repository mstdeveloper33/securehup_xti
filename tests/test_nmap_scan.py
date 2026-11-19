"""Bounded Nmap policy, adapter, application and persistence acceptance."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import ssl
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from xti.adapters.nmap_scan import (
    NmapProcessResult, NmapTcpConnectProbe, SubprocessNmapRuntime,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite_nmap_scans import SQLiteNmapScanRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.nmap_scan import NmapSurfaceScanService
from xti.application.surface import SurfaceService
from xti.domain.assets import ValidationError
from xti.domain.nmap_scan import (
    NMAP_POLICY_VERSION,
    NmapOpenPort,
    NmapScanResult,
    NmapStateCounts,
    build_nmap_scan_plan,
)


START = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
ADDRESS = "93.184.216.34"


class Context:
    check_hostname = True
    verify_mode = ssl.CERT_REQUIRED

    def set_alpn_protocols(self, value):
        self.alpn = value


class Runtime:
    def __init__(self, xml: bytes, *, returncode=0, timed_out=False):
        self.xml = xml
        self.returncode = returncode
        self.timed_out = timed_out
        self.calls = []

    def readiness(self):
        return "7.95", "/usr/bin/nmap"

    def scan(self, address, plan):
        self.calls.append((address, plan))
        return NmapProcessResult(self.returncode, self.xml, b"", self.timed_out)


class FixtureProbe(NmapTcpConnectProbe):
    def __init__(self, answers, runtime):
        self.answers = answers
        super().__init__(
            runtime=runtime, context_factory=Context, monotonic=lambda: 100.0,
            now=lambda: START.isoformat(),
        )

    def _resolve(self, context, domain, record_type, overall_deadline):
        return self.answers[record_type]


def xml_result(*, filtered=False):
    second = b'<port protocol="tcp" portid="25"><state state="filtered" reason="no-response"/></port>' if filtered else b""
    closed = 8 if filtered else 9
    return (
        b'<?xml version="1.0"?><nmaprun scanner="nmap">'
        b'<host><status state="up"/><address addr="93.184.216.34" addrtype="ipv4"/>'
        b'<ports><extraports state="closed" count="' + str(closed).encode("ascii") + b'"/>'
        b'<port protocol="tcp" portid="443"><state state="open" reason="syn-ack"/></port>'
        + second + b'</ports></host><runstats><finished exit="success"/></runstats></nmaprun>'
    )


def evidence(execution_id="exec-1"):
    plan = build_nmap_scan_plan("safe", target_count=1)
    return NmapScanResult(
        execution_id, "example.com", ADDRESS, START.isoformat(),
        (START + timedelta(seconds=2)).isoformat(), NMAP_POLICY_VERSION,
        "resolved", (ADDRESS,), ADDRESS, plan, "complete", "7.95",
        NmapStateCounts(1, 9, 0), (NmapOpenPort(443, "syn-ack"),), False,
        "a" * 64, (), ("Sınırlı TCP bağlantısı.",),
    )


class PlanTests(unittest.TestCase):
    def test_profiles_and_custom_limits_are_bounded(self):
        plan = build_nmap_scan_plan(
            "custom", target_count=2, ports="443,80,80-81",
            timeout_seconds=90, max_rate_pps=40, max_retries=0,
            target_limit=2, max_probe_budget=10,
            confirm_multi_target=True,
        )
        self.assertEqual((plan.port_spec, plan.port_count), ("80-81,443", 3))
        self.assertEqual((plan.target_count, plan.probe_budget), (2, 6))
        self.assertEqual(plan.limits.max_rate_pps, 40)

    def test_wide_multi_target_and_probe_budget_need_explicit_space(self):
        with self.assertRaisesRegex(ValidationError, "confirm-wide-scan"):
            build_nmap_scan_plan("full", target_count=1)
        with self.assertRaisesRegex(ValidationError, "confirm-multi-target"):
            build_nmap_scan_plan("safe", target_count=2, target_limit=2)
        with self.assertRaisesRegex(ValidationError, "probe bütçesi"):
            build_nmap_scan_plan(
                "custom", target_count=1, ports="1-10", max_retries=1,
                max_probe_budget=19,
            )

    def test_raw_or_ambiguous_ports_are_rejected(self):
        for value in ("80 --script vuln", "0", "2-1", "1-70000", "80, 443"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                build_nmap_scan_plan("custom", target_count=1, ports=value)


class AdapterTests(unittest.TestCase):
    def test_subprocess_runtime_builds_fixed_argument_list_without_shell(self):
        observed = []

        def run(command, **kwargs):
            observed.append((command, kwargs))
            self.assertNotIn("shell", kwargs)
            if command[-1] == "--version":
                return SimpleNamespace(returncode=0, stdout=b"Nmap version 7.95\n")
            xml_path = Path(command[command.index("-oX") + 1])
            xml_path.write_bytes(
                b'<nmaprun scanner="nmap"><host><status state="up"/>'
                b'<address addr="93.184.216.34" '
                b'addrtype="ipv4"/><ports><extraports state="closed" count="1"/>'
                b'<port protocol="tcp" portid="443"><state state="open" '
                b'reason="syn-ack"/></port></ports></host><runstats>'
                b'<finished exit="success"/></runstats></nmaprun>'
            )
            return SimpleNamespace(returncode=0)

        plan = build_nmap_scan_plan(
            "custom", target_count=1, ports="80,443", timeout_seconds=45,
            max_rate_pps=10, max_retries=0, max_probe_budget=2,
        )
        with patch("xti.adapters.nmap_scan.subprocess.run", side_effect=run):
            result = SubprocessNmapRuntime("/usr/bin/nmap").scan(ADDRESS, plan)
        self.assertEqual((result.returncode, result.timed_out), (0, False))
        command = observed[1][0]
        self.assertEqual(command[0], "/usr/bin/nmap")
        for fixed in ("-sT", "-Pn", "-n", "--unprivileged", "--max-rate", "10"):
            self.assertIn(fixed, command)
        self.assertNotIn("-sV", command)
        self.assertNotIn("--script", command)
        self.assertNotIn("-oN", command)
        self.assertEqual(command[-1], ADDRESS)

    def test_exact_dns_target_produces_compact_open_port_evidence(self):
        runtime = Runtime(xml_result(filtered=True).replace(b"<nmaprun", b"<!DOCTYPE nmaprun><nmaprun", 1))
        probe = FixtureProbe({1: (0, (ADDRESS,)), 28: (0, ())}, runtime)
        result = probe.check(
            "example.com", ADDRESS, build_nmap_scan_plan("safe", target_count=1),
            "exec-1",
        )
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.state_counts, NmapStateCounts(1, 8, 1))
        self.assertEqual(result.open_ports, (NmapOpenPort(443, "syn-ack"),))
        self.assertEqual(runtime.calls[0][0], ADDRESS)
        self.assertEqual(len(result.output_sha256), 64)

    def test_dns_mismatch_and_private_answer_never_start_nmap(self):
        for answers, expected in (
            ({1: (0, ("8.8.8.8",)), 28: (0, ())}, "address_mismatch"),
            ({1: (0, (ADDRESS, "10.0.0.1")), 28: (0, ())}, "blocked"),
        ):
            runtime = Runtime(xml_result())
            result = FixtureProbe(answers, runtime).check(
                "example.com", ADDRESS,
                build_nmap_scan_plan("safe", target_count=1), "exec-1",
            )
            self.assertEqual(result.dns_status, expected)
            self.assertEqual(runtime.calls, [])

    def test_process_timeout_and_invalid_xml_do_not_claim_port_states(self):
        timeout_runtime = Runtime(b"", timed_out=True)
        timeout = FixtureProbe(
            {1: (0, (ADDRESS,)), 28: (0, ())}, timeout_runtime,
        ).check(
            "example.com", ADDRESS, build_nmap_scan_plan("safe", target_count=1),
            "exec-1",
        )
        self.assertEqual((timeout.status, timeout.state_counts), (
            "timeout", NmapStateCounts(0, 0, 0),
        ))
        invalid = FixtureProbe(
            {1: (0, (ADDRESS,)), 28: (0, ())}, Runtime(b"<!DOCTYPE x><nmaprun/>"),
        ).check(
            "example.com", ADDRESS, build_nmap_scan_plan("safe", target_count=1),
            "exec-1",
        )
        self.assertEqual(invalid.status, "failed")
        self.assertIsNone(invalid.output_sha256)

        class BrokenRuntime(Runtime):
            def scan(self, address, plan):
                raise ValidationError("unsafe local output")

        broken = FixtureProbe(
            {1: (0, (ADDRESS,)), 28: (0, ())}, BrokenRuntime(b""),
        ).check(
            "example.com", ADDRESS, build_nmap_scan_plan("safe", target_count=1),
            "exec-1",
        )
        self.assertEqual(broken.status, "failed")
        self.assertEqual(broken.state_counts, NmapStateCounts(0, 0, 0))

    def test_xml_cannot_claim_a_port_outside_the_approved_plan(self):
        xml = (
            b'<nmaprun scanner="nmap"><host><status state="up"/>'
            b'<address addr="93.184.216.34" '
            b'addrtype="ipv4"/><ports><extraports state="closed" count="1"/>'
            b'<port protocol="tcp" portid="444"><state state="open" '
            b'reason="syn-ack"/></port></ports></host><runstats>'
            b'<finished exit="success"/></runstats></nmaprun>'
        )
        result = FixtureProbe(
            {1: (0, (ADDRESS,)), 28: (0, ())}, Runtime(xml),
        ).check(
            "example.com", ADDRESS,
            build_nmap_scan_plan(
                "custom", target_count=1, ports="80,443", max_retries=0,
                max_probe_budget=2,
            ),
            "exec-1",
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.open_ports, ())
        self.assertIsNone(result.output_sha256)


class FakeProbe:
    def __init__(self):
        self.calls = []

    def readiness(self):
        return "7.95", "/usr/bin/nmap"

    def check(self, domain, address, plan, execution_id):
        self.calls.append((domain, address, plan, execution_id))
        return evidence(execution_id)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _ = self.storage.add("example.com")
        self.surface = SQLiteSurfaceRepository(self.path, clock=lambda: START)
        SurfaceService(
            self.storage, self.surface, clock=lambda: START,
        ).approve("example.com", "Kendi kurumsal domainim")
        self.repository = SQLiteNmapScanRepository(
            self.path, clock=lambda: START + timedelta(minutes=1),
        )

    def test_scan_is_append_only_and_scope_is_rechecked(self):
        probe = FakeProbe()
        service = NmapSurfaceScanService(
            self.storage, self.surface, self.repository, probe,
            id_factory=lambda: "exec-1",
        )
        checks = service.check(
            "example.com", (ADDRESS,), "Yönettiğim kesin IP",
            build_nmap_scan_plan("safe", target_count=1),
        )
        self.assertEqual(len(checks), 1)
        details = service.show("example.com")
        self.assertEqual(details.total_check_count, 1)
        self.assertEqual(details.checks[0], checks[0])
        self.assertEqual(self.storage.inspect()["surface_nmap_check_count"], 1)

    def test_corrupt_digest_fails_closed_and_backup_preserves_evidence(self):
        original = NmapSurfaceScanService(
            self.storage, self.surface, self.repository, FakeProbe(),
            id_factory=lambda: "exec-1",
        ).check(
            "example.com", (ADDRESS,), "Yönettiğim kesin IP",
            build_nmap_scan_plan("safe", target_count=1),
        )[0]
        backup = Path(self.temp.name) / "backup.db"
        self.storage.backup(backup)
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(
            SQLiteNmapScanRepository(restored).details(self.asset.id).checks[0],
            original,
        )
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                "UPDATE surface_nmap_checks SET state_sha256 = ?", ("0" * 64,),
            )
            connection.commit()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "Nmap kontrol geçmişi bozuk"):
            self.repository.details(self.asset.id)
        self.assertEqual(self.path.read_bytes(), before)

    def test_execution_index_cannot_disagree_with_immutable_result(self):
        NmapSurfaceScanService(
            self.storage, self.surface, self.repository, FakeProbe(),
            id_factory=lambda: "exec-1",
        ).check(
            "example.com", (ADDRESS,), "Yönettiğim kesin IP",
            build_nmap_scan_plan("safe", target_count=1),
        )
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                "UPDATE surface_nmap_checks SET execution_id = ?", ("exec-tampered",),
            )
            connection.commit()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "Nmap kontrol geçmişi bozuk"):
            self.repository.details(self.asset.id)
        self.assertEqual(self.path.read_bytes(), before)

    def test_schema_69_migration_backs_up_then_adds_empty_nmap_history(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("DROP INDEX surface_nmap_checks_execution_id")
            connection.execute("DROP INDEX surface_nmap_checks_asset_id")
            connection.execute("DROP TABLE surface_nmap_checks")
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(connection)
            connection.execute("PRAGMA user_version=69")
            connection.commit()
        migrated = self.storage.migrate()
        self.assertTrue(migrated["changed"])
        self.assertEqual((migrated["from_version"], migrated["to_version"]), (69, SCHEMA_VERSION))
        self.assertTrue(Path(migrated["backup"]).is_file())
        self.assertEqual(self.storage.inspect()["surface_nmap_check_count"], 0)
        self.assertEqual(self.storage.list()[0].value, "example.com")


if __name__ == "__main__":
    unittest.main()

"""Approved exact-domain CNAME evidence and non-owning dangling candidates."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import ssl
import tempfile
import unittest

from xti.adapters.https_probe import GoogleCnameDnsProbe, parse_cname_dns_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_freshness import SQLiteSurfaceFreshnessRepository
from xti.application.cname import SurfaceCnameService
from xti.application.surface_exposure import SurfaceExposureService
from xti.domain.assets import ValidationError
from xti.domain.cname import CNAME_POLICY_VERSION, CnameDnsResult, CnameHop


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


def cname_result(*, target_status="resolved", target="active.vendor.example"):
    addresses = ("93.184.216.34",) if target_status == "resolved" else ()
    return CnameDnsResult(
        "api.example.com", NOW.isoformat(), (NOW + timedelta(seconds=1)).isoformat(),
        CNAME_POLICY_VERSION, "present",
        (CnameHop("api.example.com", target),), target, target_status,
        addresses, (), ("Yalnız genel DNS kanıtı.",),
    )


def payload(name: str, record_type: int, *, status=0, answers=()):
    return json.dumps({
        "Status": status, "TC": False, "CD": False,
        "Question": [{"name": name + ".", "type": record_type}],
        "Answer": list(answers),
    }).encode()


class FakeContext:
    check_hostname = True
    verify_mode = ssl.CERT_REQUIRED

    def set_alpn_protocols(self, protocols):
        self.protocols = protocols


class FixtureCnameProbe(GoogleCnameDnsProbe):
    def __init__(self, responses):
        super().__init__(
            context_factory=FakeContext, monotonic=lambda: 100.0,
            now=lambda: NOW.isoformat(),
        )
        self.responses = responses
        self.calls = []

    def _dns_content(self, context, domain, record_type, overall_deadline):
        self.calls.append((domain, record_type))
        return self.responses[(domain, record_type)]


class CnameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.asset, _ = self.assets.add("api.example.com")
        self.surface = SQLiteSurfaceRepository(self.path, clock=lambda: NOW)
        self.repository = SQLiteSurfaceCnameRepository(
            self.path, clock=lambda: NOW + timedelta(minutes=1),
        )

    def approve(self):
        self.surface.activate(
            self.asset.id, self.asset.value, "Yönettiğim tam API adresi", NOW.isoformat(),
        )

    def service(self, probe=None):
        return SurfaceCnameService(
            self.assets, self.surface, self.repository, probe,
        )

    def test_parser_accepts_only_one_finite_related_chain(self):
        content = payload("api.example.com", 5, answers=(
            {"name": "api.example.com.", "type": 5, "data": "edge.vendor.example."},
            {"name": "edge.vendor.example.", "type": 5, "data": "final.vendor.example."},
        ))
        status, chain = parse_cname_dns_response(content, "api.example.com")
        self.assertEqual(status, 0)
        self.assertEqual(chain, (
            CnameHop("api.example.com", "edge.vendor.example"),
            CnameHop("edge.vendor.example", "final.vendor.example"),
        ))

        unrelated = payload("api.example.com", 5, answers=(
            {"name": "other.example.com.", "type": 5, "data": "target.example."},
        ))
        with self.assertRaisesRegex(Exception, "ilgisiz"):
            parse_cname_dns_response(unrelated, "api.example.com")

    def test_probe_marks_nxdomain_as_dns_fact_without_target_connection(self):
        target = "missing.vendor.example"
        probe = FixtureCnameProbe({
            ("api.example.com", 5): payload("api.example.com", 5, answers=(
                {"name": "api.example.com.", "type": 5, "data": target + "."},
            )),
            (target, 1): payload(target, 1, status=3),
            (target, 28): payload(target, 28, status=3),
        })
        result = probe.check("api.example.com")
        self.assertEqual((result.alias_status, result.target_status), ("present", "nxdomain"))
        self.assertEqual(result.target, target)
        self.assertEqual(probe.calls, [
            ("api.example.com", 5), (target, 1), (target, 28),
        ])
        self.assertIn("alınabilir olduğunu kanıtlamaz", result.notes[-1])

    def test_scope_required_and_append_only_change_history(self):
        probe = type("Probe", (), {"check": lambda _, domain: cname_result()})()
        with self.assertRaisesRegex(ValidationError, "kapsamına alınmamış"):
            self.service(probe).check("api.example.com")
        self.approve()
        first = self.service(probe).check("api.example.com")
        second = self.service(probe).check("api.example.com")
        dangling = type("Probe", (), {
            "check": lambda _, domain: cname_result(
                target_status="nxdomain", target="missing.vendor.example",
            ),
        })()
        third = self.service(dangling).check("api.example.com")
        self.assertEqual(
            [first.change.kind, second.change.kind, third.change.kind],
            ["baseline", "unchanged", "changed"],
        )
        self.assertEqual(
            third.change.changed_fields, ("chain", "target_status", "addresses"),
        )
        before = self.path.read_bytes()
        details = self.service().show("api.example.com")
        self.assertEqual(details.total_check_count, 3)
        self.assertEqual(self.path.read_bytes(), before)

    def test_exposure_candidate_is_inconclusive_and_never_claims_takeover(self):
        self.approve()
        check = self.repository.append_check(
            self.asset.id,
            cname_result(target_status="nxdomain", target="missing.vendor.example"),
        )
        before = self.path.read_bytes()
        report = SurfaceExposureService(
            self.assets, SQLiteSurfaceFreshnessRepository(self.path), clock=lambda: NOW,
        ).show("api.example.com")
        candidate = report.candidates[0]
        self.assertEqual(candidate.candidate_type, "dangling_cname_target_nxdomain")
        self.assertEqual(candidate.evidence_id, check.id)
        self.assertEqual(candidate.evidence_level, "inconclusive")
        self.assertIn("alınabilir olduğunu kanıtlamaz", candidate.limitations[0])
        coverage = {item.check_type: item for item in report.coverage}
        self.assertEqual(coverage["subdomain_takeover"].status, "clock_error")
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_history_fails_closed_and_backup_restore_preserves_checks(self):
        self.approve()
        original = self.repository.append_check(self.asset.id, cname_result())
        backup = Path(self.temp.name) / "backup.db"
        self.assets.backup(backup)
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(
            SQLiteSurfaceCnameRepository(restored).details(
                self.asset.id, history_limit=20,
            ).checks[0],
            original,
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE surface_cname_checks SET state_sha256 = ?", ("0" * 64,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "CNAME kontrol geçmişi bozuk"):
            self.service().show("api.example.com")
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.adapters.sqlite_surface_overview import SQLiteSurfaceOverviewRepository
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.application.surface import SurfaceOverviewService
from xti.domain.assets import ValidationError
from xti.domain.enrichment import CertificateEvidence, ProbeResult
from xti.domain.mail import MailDnsResult
from xti.domain.services import (
    SERVICE_POLICY_VERSION,
    SERVICE_PORT_HINTS,
    SERVICE_PORTS,
    ServicePortResult,
    ServiceScanResult,
)
from xti.domain.surface import SurfaceCandidateEvidence, SurfaceDiscoveryRunRequest


START = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


class SurfaceOverviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _ = self.storage.add("example.com")
        self.repository = SQLiteSurfaceOverviewRepository(self.path)
        self.service = SurfaceOverviewService(self.storage, self.repository)

    def populate(self):
        scope_time = START.isoformat()
        surface = SQLiteSurfaceRepository(
            self.path, clock=lambda: START + timedelta(minutes=1),
        )
        surface.activate(self.asset.id, self.asset.value, "Kendi alan adım", scope_time)
        certificate = CertificateEvidence(
            sha256="a" * 64, serial_number="01a2",
            not_before="2026-10-01T00:00:00+00:00",
            not_after="2027-10-01T00:00:00+00:00",
            issuer="Fixture CA", subject="example.com",
            dns_names=("*.example.com", "example.com"),
        )
        surface.append_check(self.asset.id, ProbeResult(
            domain="example.com", started_at=scope_time,
            finished_at=(START + timedelta(seconds=1)).isoformat(),
            policy_version="overview-test-v1", dns_status="resolved",
            addresses=("93.184.216.34", "2001:4860:4860::8888"),
            tls_status="valid", http_status="responded", http_status_code=200,
            connected_address="93.184.216.34", certificate=certificate,
            errors=(), notes=("Sınırlı test.",),
        ))

        mail = SQLiteSurfaceMailRepository(
            self.path, clock=lambda: START + timedelta(minutes=2),
        )
        mail.append_check(self.asset.id, MailDnsResult(
            domain="example.com", started_at=scope_time,
            finished_at=(START + timedelta(seconds=1)).isoformat(),
            policy_version="overview-mail-test-v1",
            mx_status="present", mx_records=("10 mail.example.com",),
            spf_status="present", spf_records=("v=spf1 -all",),
            dmarc_status="present", dmarc_records=("v=DMARC1; p=reject",),
            errors=(), notes=(),
        ))

        services = SQLiteSurfaceServiceScanRepository(
            self.path, clock=lambda: START + timedelta(minutes=2, seconds=30),
        )
        services.append_check(
            self.asset.id, "Yönettiğim sabit sunucu",
            ServiceScanResult(
                "example.com", "93.184.216.34", scope_time,
                (START + timedelta(seconds=1)).isoformat(), SERVICE_POLICY_VERSION,
                "resolved", ("93.184.216.34",), "93.184.216.34",
                tuple(
                    ServicePortResult(
                        port, "open" if port == 443 else "closed", SERVICE_PORT_HINTS[port],
                    )
                    for port in SERVICE_PORTS
                ),
                (), ("Sabit sınırlı TCP kontrolü.",),
            ),
        )

        candidates = SQLiteSurfaceCandidateRepository(self.path)
        observed = "2026-10-20T00:00:00+00:00"
        evidence = tuple(
            SurfaceCandidateEvidence(
                domain=domain, provider="crt.sh",
                source_name=f"https://crt.sh/?id={index}",
                source_sha256=hashlib.sha256(f"cert-{index}".encode()).hexdigest(),
                raw_domain=domain, observed_at=observed,
            )
            for index, domain in enumerate(
                ("api.example.com", "cdn.example.com", "vpn.example.com"), start=1,
            )
        )
        candidates.record_discovery(
            self.asset.id, self.asset.value, evidence,
            SurfaceDiscoveryRunRequest(
                "complete", "https://crt.sh/?q=%25.example.com",
                scope_time, (START + timedelta(minutes=3)).isoformat(),
                3, 0, 0, (), 3, None,
            ),
        )
        owned = candidates.list_candidates(self.asset.id, status=None, limit=10)[0]
        candidates.decide_candidate(
            owned.id, "owned", "Kurumsal API adresi",
            (START + timedelta(minutes=4)).isoformat(),
        )

    def test_registered_root_without_evidence_is_a_valid_empty_overview(self):
        before = self.path.read_bytes()
        overview = self.service.show("EXAMPLE.COM")
        self.assertIsNone(overview.scope)
        self.assertIsNone(overview.latest_check)
        self.assertIsNone(overview.latest_mail_check)
        self.assertIsNone(overview.latest_service_check)
        self.assertIsNone(overview.latest_discovery_run)
        self.assertEqual(overview.candidate_counts.total, 0)
        self.assertEqual(overview.relations, ())
        self.assertEqual(self.path.read_bytes(), before)

    def test_one_snapshot_builds_bounded_explainable_relationships(self):
        self.populate()
        before = self.path.read_bytes()
        overview = self.service.show("example.com", candidate_limit=2)
        self.assertTrue(overview.scope.active)
        self.assertEqual(
            (overview.candidate_counts.pending, overview.candidate_counts.owned,
             overview.candidate_counts.rejected, overview.candidate_counts.total),
            (2, 1, 0, 3),
        )
        self.assertEqual(len(overview.candidates), 2)
        self.assertEqual(overview.latest_discovery_run.status, "complete")
        kinds = [relation.kind for relation in overview.relations]
        self.assertEqual(kinds.count("discovered_subdomain"), 2)
        self.assertEqual(kinds.count("resolves_to"), 2)
        self.assertEqual(kinds.count("presents_certificate"), 1)
        self.assertEqual(kinds.count("certificate_covers"), 2)
        self.assertEqual(kinds.count("uses_mail_exchange"), 1)
        self.assertEqual(kinds.count("offers_tcp_service"), 1)
        mx = next(item for item in overview.relations if item.kind == "uses_mail_exchange")
        self.assertEqual((mx.target_value, mx.detail), ("mail.example.com", "preference=10"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_latest_evidence_fails_closed_without_rewrite(self):
        self.populate()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE surface_checks SET state_sha256 = ?", ("0" * 64,))
            connection.commit()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "kontrol geçmişi bozuk"):
            self.service.show("example.com")
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_limit_and_unknown_root_are_rejected(self):
        before = self.path.read_bytes()
        for limit in (0, 101, True):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValidationError, "sınırı"):
                    self.service.show("example.com", candidate_limit=limit)
        with self.assertRaisesRegex(ValidationError, "kayıtlı değil"):
            self.service.show("unknown.example")
        self.assertEqual(self.path.read_bytes(), before)


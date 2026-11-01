"""Passive CT subdomain inventory, evidence and explicit human classification."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.application.assets import AssetService
from xti.application.surface import SurfaceDiscoveryService
from xti.domain.assets import ValidationError
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.domain.surface import SurfaceCandidateEvidence, SurfaceDiscoveryRunRequest
from xti.ports.discovery import SourceError


START = datetime(2026, 10, 29, 10, tzinfo=timezone.utc)


def document(number, domain, *, raw=None, observed="2026-10-01T00:00:00+00:00"):
    digest = hashlib.sha256(f"certificate-{number}-{raw or domain}".encode()).hexdigest()
    return ImportDocument(
        source_name=f"https://crt.sh/?id={number}", sha256=digest,
        records=(DomainInput(domain, raw or domain, 1, observed),),
    )


class FakeSource:
    def __init__(self, batch=None, error=None):
        self.batch = batch
        self.error = error
        self.calls = []

    def search_url(self, pattern):
        return "https://crt.sh/?q=" + pattern

    def search(self, pattern):
        self.calls.append(pattern)
        if self.error is not None:
            raise self.error
        return self.batch


class SurfaceDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _ = AssetService(self.storage).add("example.com")
        self.repo = SQLiteSurfaceCandidateRepository(self.path)
        self.ticks = iter(START + timedelta(minutes=value) for value in range(100))

    def service(self, source=None):
        return SurfaceDiscoveryService(
            self.storage, self.repo, source, clock=lambda: next(self.ticks),
        )

    def batch(self):
        return SourceBatch(
            documents=(
                document(1, "api.example.com"),
                document(2, "vpn.example.com", raw="*.vpn.example.com",
                         observed="2026-10-02T00:00:00+00:00"),
                document(3, "example.com"),
                document(4, "unrelated.test"),
            ),
            skipped_names=0, record_count=4,
        )

    def test_passive_discovery_filters_to_strict_subdomains_and_starts_pending(self):
        source = FakeSource(self.batch())
        result = self.service(source).discover("EXAMPLE.COM")
        self.assertEqual(result.status, "complete")
        self.assertEqual(source.calls, ["%.example.com"])
        self.assertEqual(result.candidate_domains, ("api.example.com", "vpn.example.com"))
        self.assertEqual((result.candidates_created, result.evidence_created), (2, 2))
        self.assertEqual(result.ignored_names, 2)

        items = self.service().list("example.com")
        self.assertEqual([item.domain for item in items], ["api.example.com", "vpn.example.com"])
        self.assertTrue(all(item.status == "pending" for item in items))
        self.assertTrue(all(item.source_count == 1 for item in items))
        details = self.service().show(items[1].id)
        self.assertEqual(details.sources[0].raw_domain, "*.vpn.example.com")
        self.assertEqual([event.action for event in details.events], ["discovered"])

        # Passive discovery never registers or actively approves a discovered name.
        self.assertEqual([item.value for item in self.storage.list()], ["example.com"])
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM surface_scopes").fetchone()[0], 0)

    def test_repeat_is_idempotent_new_certificate_extends_evidence_and_keeps_decision(self):
        first = self.service(FakeSource(self.batch())).discover("example.com")
        candidate = next(
            item for item in self.service().list("example.com") if item.domain == "api.example.com"
        )
        owned, changed = self.service().decide(candidate.id, "owned", "Kurumsal API adresim")
        self.assertTrue(changed)
        self.assertEqual(owned.status, "owned")

        repeat = self.service(FakeSource(self.batch())).discover("example.com")
        self.assertEqual((repeat.candidates_created, repeat.candidates_existing), (0, 2))
        self.assertEqual((repeat.evidence_created, repeat.evidence_existing), (0, 2))

        later = SourceBatch(
            (document(5, "api.example.com", observed="2026-10-20T00:00:00+00:00"),),
            0, 1,
        )
        added = self.service(FakeSource(later)).discover("example.com")
        self.assertEqual((added.candidates_existing, added.evidence_created), (1, 1))
        refreshed = self.service().show(candidate.id)
        self.assertEqual(refreshed.candidate.status, "owned")
        self.assertEqual(refreshed.candidate.source_count, 2)
        self.assertEqual(refreshed.candidate.last_seen_at, "2026-10-20T00:00:00+00:00")
        self.assertEqual([event.action for event in refreshed.events], ["discovered", "owned"])
        self.assertEqual(first.candidate_domains, repeat.candidate_domains)

    def test_decisions_are_append_only_idempotent_and_do_not_authorize_network(self):
        self.service(FakeSource(SourceBatch((document(1, "api.example.com"),), 0, 1))).discover(
            "example.com"
        )
        candidate = self.service().list("example.com")[0]
        owned, changed = self.service().decide(candidate.id, "owned", "Bana ait API")
        self.assertTrue(changed)
        same, changed = self.service().decide(candidate.id, "owned", "Bana ait API")
        self.assertFalse(changed)
        updated, changed = self.service().decide(candidate.id, "owned", "Üretim API adresim")
        self.assertTrue(changed)
        pending, changed = self.service().decide(candidate.id, "pending", "Yeniden incelenecek")
        self.assertTrue(changed)
        rejected, changed = self.service().decide(candidate.id, "rejected", "Kuruma ait değil")
        self.assertTrue(changed)
        self.assertEqual((owned.id, same.id, updated.id, pending.id, rejected.id), (candidate.id,) * 5)
        self.assertEqual(
            [event.action for event in self.service().show(candidate.id).events],
            ["discovered", "owned", "updated", "reopened", "rejected"],
        )
        self.assertEqual(self.service().list("example.com", status="rejected")[0].id, candidate.id)
        self.assertEqual(self.service().list("example.com", status="owned"), ())
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM surface_scopes").fetchone()[0], 0)

    def test_source_failure_or_invalid_evidence_leaves_no_candidate(self):
        failed = self.service(FakeSource(error=SourceError("Kaynak geçici olarak yanıt vermedi."))).discover(
            "example.com"
        )
        self.assertEqual((failed.status, failed.error),
                         ("failed", "Kaynak geçici olarak yanıt vermedi."))
        self.assertEqual(self.service().list("example.com", status=None), ())

        malformed = SourceBatch(
            (document(9, "api.example.com"),), 0, 1, warnings=("bad\x1bwarning",),
        )
        malformed_result = self.service(FakeSource(malformed)).discover("example.com")
        self.assertEqual(malformed_result.status, "failed")
        self.assertIn("kapsam özeti", malformed_result.error)
        self.assertEqual(self.service().list("example.com", status=None), ())

        valid = SurfaceCandidateEvidence(
            "api.example.com", "crt.sh", "https://crt.sh/?id=1", "a" * 64,
            "api.example.com", "2026-10-01T00:00:00+00:00",
        )
        invalid = SurfaceCandidateEvidence(
            "sibling-example.com", "crt.sh", "https://crt.sh/?id=2", "b" * 64,
            "sibling-example.com", "2026-10-01T00:00:00+00:00",
        )
        with self.assertRaises(ValidationError):
            self.repo.record_discovery(
                self.asset.id, self.asset.value, (valid, invalid),
                SurfaceDiscoveryRunRequest(
                    "complete", "https://crt.sh/?q=%25.example.com",
                    START.isoformat(), START.isoformat(), 2, 0, 0, (), 2, None,
                ),
            )
        self.assertEqual(self.service().list("example.com", status=None), ())

    def test_corruption_fails_closed_and_backup_restore_preserves_everything(self):
        self.service(FakeSource(SourceBatch((document(1, "api.example.com"),), 0, 1))).discover(
            "example.com"
        )
        candidate = self.service().list("example.com")[0]
        self.service().decide(candidate.id, "owned", "Bana ait")
        before = self.service().show(candidate.id)
        backup = self.storage.backup(Path(self.temp.name) / "backup" / "xti.db")
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        restored_service = SurfaceDiscoveryService(
            SQLiteAssetRepository(restored), SQLiteSurfaceCandidateRepository(restored),
        )
        self.assertEqual(restored_service.show(candidate.id), before)

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE surface_candidate_sources SET source_sha256 = 'invalid' WHERE candidate_id = ?",
                (candidate.id,),
            )
        file_before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "kaynak kanıtı bozuk"):
            self.service().show(candidate.id)
        self.assertEqual(self.path.read_bytes(), file_before)


if __name__ == "__main__":
    unittest.main()

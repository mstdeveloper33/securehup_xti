"""Durable passive-run history and unified local candidate notifications."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.application.surface import SurfaceDiscoveryService
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument, MatchCandidate
from xti.ports.discovery import SourceError


START = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


def certificate(number: int, domain: str) -> ImportDocument:
    return ImportDocument(
        f"https://crt.sh/?id={number}",
        hashlib.sha256(f"certificate-{number}-{domain}".encode()).hexdigest(),
        (DomainInput(domain, domain, 1, "2026-10-20T00:00:00+00:00"),),
    )


class Source:
    def __init__(self, documents=(), *, warnings=(), error=None):
        self.documents = tuple(documents)
        self.warnings = tuple(warnings)
        self.error = error

    def search_url(self, pattern):
        return "https://crt.sh/?q=" + pattern

    def search(self, pattern):
        if self.error is not None:
            raise self.error
        return SourceBatch(self.documents, 0, len(self.documents), self.warnings)


class SurfaceDiscoveryHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _ = self.storage.add("example.com")
        self.repository = SQLiteSurfaceCandidateRepository(self.path)
        self.ticks = iter(START + timedelta(minutes=value) for value in range(100))

    def service(self, source=None):
        return SurfaceDiscoveryService(
            self.storage, self.repository, source, clock=lambda: next(self.ticks),
        )

    def test_run_candidate_evidence_and_one_notice_commit_together(self):
        source = Source((certificate(1, "api.example.com"), certificate(2, "vpn.example.com")))
        first = self.service(source).discover("example.com")
        self.assertIsNotNone(first.run_id)
        runs = self.service().runs("example.com")
        self.assertEqual([run.id for run in runs], [first.run_id])
        self.assertEqual((runs[0].status, runs[0].candidate_count), ("complete", 2))

        inbox = SQLiteInboxRepository(self.path)
        page = inbox.list("all", 100)
        self.assertEqual((page.total_count, page.unread_count), (2, 2))
        self.assertTrue(all(item.finding is None for item in page.items))
        self.assertEqual(
            {item.candidate.domain for item in page.items},
            {"api.example.com", "vpn.example.com"},
        )
        shown = inbox.get(page.items[0].notification.id)
        self.assertIsNone(shown.details)
        self.assertEqual(shown.candidate_details.candidate.id, page.items[0].candidate.id)
        inbox.mark((page.items[0].notification.id,), True, START.isoformat())

        repeated = self.service(source).discover("example.com")
        self.assertEqual((repeated.candidates_created, repeated.candidates_existing), (0, 2))
        self.assertEqual(inbox.list("all", 100).total_count, 2)
        self.assertEqual(len(self.service().runs("example.com")), 2)

        added = self.service(Source((certificate(3, "new.example.com"),))).discover("example.com")
        self.assertEqual(added.candidates_created, 1)
        self.assertEqual(inbox.list("all", 100).total_count, 3)
        self.assertEqual(self.storage.inspect()["surface_discovery_run_count"], 3)

        backup = self.storage.backup(Path(self.temp.name) / "backup" / "xti.db")
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        restored_runs = SQLiteSurfaceCandidateRepository(restored).list_discovery_runs(
            self.asset.id, limit=20,
        )
        self.assertEqual(restored_runs, self.service().runs("example.com"))
        restored_page = SQLiteInboxRepository(restored).list("all", 100)
        self.assertEqual(
            [(item.notification.id, item.notification.read_at) for item in restored_page.items],
            [(item.notification.id, item.notification.read_at)
             for item in inbox.list("all", 100).items],
        )

    def test_failed_and_partial_runs_remain_distinct_from_empty_success(self):
        failed = self.service(Source(error=SourceError("Kaynak yanıt vermedi."))).discover(
            "example.com"
        )
        self.assertEqual(failed.status, "failed")
        self.assertEqual(self.service().run(failed.run_id).error, "Kaynak yanıt vermedi.")
        self.assertEqual(SQLiteInboxRepository(self.path).list("all").total_count, 0)

        partial = self.service(Source(
            (certificate(1, "api.example.com"),), warnings=("Kaynak kapsamı sınırlı.",),
        )).discover("example.com")
        self.assertEqual(partial.status, "partial")
        self.assertEqual(self.service().run(partial.run_id).warnings, ("Kaynak kapsamı sınırlı.",))
        self.assertEqual([run.status for run in self.service().runs("example.com")], [
            "partial", "failed",
        ])

    def test_late_run_failure_rolls_back_candidate_notice_and_history(self):
        with patch.object(
            SQLiteSurfaceCandidateRepository, "_run", side_effect=StorageError("controlled"),
        ):
            with self.assertRaisesRegex(StorageError, "controlled"):
                self.service(Source((certificate(1, "api.example.com"),))).discover("example.com")
        with closing(sqlite3.connect(self.path)) as connection:
            for table in (
                "surface_candidates", "surface_candidate_sources", "surface_candidate_events",
                "surface_candidate_notifications", "surface_discovery_runs",
            ):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_finding_and_surface_notices_share_one_stable_sequence(self):
        findings = SQLiteFindingRepository(self.path)
        domain = "example-support.net"
        findings.save_import(
            ImportDocument("fixture:first", "a" * 64, (DomainInput(domain, domain, 1, None),)),
            (MatchCandidate(
                self.asset.id, self.asset.value, domain, "rules-v1", ("Test eşleşmesi",),
            ),),
        )
        self.service(Source((certificate(1, "api.example.com"),))).discover("example.com")
        second_domain = "example-login.net"
        findings.save_import(
            ImportDocument(
                "fixture:second", "b" * 64,
                (DomainInput(second_domain, second_domain, 1, None),),
            ),
            (MatchCandidate(
                self.asset.id, self.asset.value, second_domain, "rules-v1", ("Test eşleşmesi",),
            ),),
        )
        page = SQLiteInboxRepository(self.path).list("all", 100)
        self.assertEqual([item.notification.sequence for item in page.items], [3, 2, 1])
        self.assertEqual(
            [item.notification.event_type for item in page.items],
            ["finding_created", "surface_candidate_discovered", "finding_created"],
        )


if __name__ == "__main__":
    unittest.main()

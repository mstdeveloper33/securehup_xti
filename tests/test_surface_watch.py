"""Bounded, passive surface watching over durable discovery runs."""

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.application.assets import AssetService
from xti.application.surface import SurfaceDiscoveryService, SurfaceWatchService
from xti.domain.assets import ValidationError
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


def batch(*, warning: str | None = None) -> SourceBatch:
    domain = "api.example.com"
    document = ImportDocument(
        "https://crt.sh/?id=1", hashlib.sha256(b"certificate-1").hexdigest(),
        (DomainInput(domain, domain, 1, "2026-10-20T00:00:00+00:00"),),
    )
    return SourceBatch((document,), 0, 1, (warning,) if warning else ())


class SequenceSource:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def search_url(self, pattern):
        return "https://crt.sh/?q=" + pattern

    def search(self, pattern):
        self.calls.append(pattern)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class Timer:
    def __init__(self, *, interrupt=False):
        self.value = 100.0
        self.sleeps = []
        self.interrupt = interrupt

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        if self.interrupt:
            raise KeyboardInterrupt()
        self.sleeps.append(seconds)
        self.value += seconds


class SurfaceWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        AssetService(self.assets).add("example.com")
        self.repository = SQLiteSurfaceCandidateRepository(self.path)
        self.discovery_ticks = iter(NOW + timedelta(seconds=value) for value in range(100))

    def service(self, source, timer):
        discovery = SurfaceDiscoveryService(
            self.assets, self.repository, source,
            clock=lambda: next(self.discovery_ticks),
        )
        return SurfaceWatchService(
            discovery, clock=lambda: NOW,
            monotonic=timer.monotonic, sleeper=timer.sleep,
        )

    def test_repeated_cycles_keep_runs_but_deduplicate_candidate_and_notice(self):
        source = SequenceSource([batch(), batch(), batch()])
        timer = Timer()
        report = self.service(source, timer).run(
            "EXAMPLE.COM", max_cycles=3, interval_seconds=300,
            max_duration_seconds=1000,
        )
        self.assertEqual((report.stop_reason, report.completed_cycles), ("cycles", 3))
        self.assertEqual((report.complete, report.partial, report.failed), (3, 0, 0))
        self.assertEqual((report.candidates_created, report.evidence_created), (1, 1))
        self.assertEqual(source.calls, ["%.example.com"] * 3)
        self.assertEqual(sum(timer.sleeps), 600)
        self.assertEqual(len(self.repository.list_discovery_runs(
            self.assets.list()[0].id, limit=20,
        )), 3)
        self.assertEqual(SQLiteInboxRepository(self.path).list("all").total_count, 1)

    def test_failed_partial_and_complete_cycles_continue_and_are_summarized(self):
        source = SequenceSource([
            SourceError("Kaynak yanıt vermedi."), batch(warning="Kapsam sınırlı."), batch(),
        ])
        report = self.service(source, Timer()).run(
            "example.com", max_cycles=3, interval_seconds=300,
            max_duration_seconds=1000,
        )
        self.assertEqual((report.complete, report.partial, report.failed), (1, 1, 1))
        self.assertEqual([cycle.status for cycle in report.cycles], [
            "failed", "partial", "complete",
        ])
        self.assertEqual(
            [item.status for item in self.repository.list_discovery_runs(
                self.assets.list()[0].id, limit=20,
            )],
            ["complete", "partial", "failed"],
        )

    def test_duration_stops_new_cycle_and_completed_work_remains(self):
        source = SequenceSource([batch(), batch()])
        timer = Timer()
        report = self.service(source, timer).run(
            "example.com", max_cycles=3, interval_seconds=300,
            max_duration_seconds=300,
        )
        self.assertEqual((report.stop_reason, report.completed_cycles), ("duration", 1))
        self.assertEqual(source.calls, ["%.example.com"])
        self.assertEqual(sum(timer.sleeps), 300)
        self.assertEqual(SQLiteInboxRepository(self.path).list("all").total_count, 1)

    def test_ctrl_c_during_wait_propagates_after_preserving_completed_cycle(self):
        source = SequenceSource([batch(), batch()])
        with self.assertRaises(KeyboardInterrupt):
            self.service(source, Timer(interrupt=True)).run(
                "example.com", max_cycles=2, interval_seconds=300,
                max_duration_seconds=1000,
            )
        self.assertEqual(source.calls, ["%.example.com"])
        self.assertEqual(len(self.repository.list_discovery_runs(
            self.assets.list()[0].id, limit=20,
        )), 1)
        self.assertEqual(SQLiteInboxRepository(self.path).list("all").total_count, 1)

    def test_invalid_limits_are_rejected_before_source_access(self):
        source = SequenceSource([batch()])
        with self.assertRaisesRegex(ValidationError, "tur sayısı"):
            self.service(source, Timer()).run("example.com", max_cycles=0)
        self.assertEqual(source.calls, [])
        self.assertEqual(self.repository.list_discovery_runs(
            self.assets.list()[0].id, limit=20,
        ), ())


if __name__ == "__main__":
    unittest.main()

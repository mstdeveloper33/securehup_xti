"""Atomic KEV snapshots, source failures, history and corruption safety."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_vulnerability import SQLiteKevRepository
from xti.application.vulnerability import KevCatalogService
from xti.domain.vulnerability import (
    CISA_KEV_SOURCE,
    CISA_KEV_URL,
    KevCatalogSnapshot,
    KevEntry,
)
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


def kev(cve, *, product="Product", action="Patch now"):
    return KevEntry(
        cve, "Vendor", product, f"{product} vulnerability", "2026-10-01",
        "Short description.", action, "2026-10-21", "Unknown", "", ("CWE-20",),
    )


def snapshot(*entries, version="2026.10.29"):
    digest = hashlib.sha256((version + repr(entries)).encode()).hexdigest()
    return KevCatalogSnapshot(
        CISA_KEV_SOURCE, CISA_KEV_URL, "CISA KEV", version,
        "2026-10-29T12:00:00Z", digest,
        tuple(sorted(entries, key=lambda item: item.cve_id)),
    )


class Source:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if self.error:
            raise SourceError(self.error)
        return self.result


class KevCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.repository = SQLiteKevRepository(self.path)
        self.time = NOW

    def sync(self, value):
        source = Source(value)
        service = KevCatalogService(
            self.repository, source, clock=lambda: self.time,
        )
        run = service.sync()
        self.time += timedelta(minutes=1)
        return run

    def test_full_snapshots_track_add_update_deactivate_and_reactivate(self):
        first = self.sync(snapshot(
            kev("CVE-2026-1000", product="Alpha"),
            kev("CVE-2026-2000", product="Beta"),
        ))
        self.assertEqual((first.created_count, first.record_count), (2, 2))
        repeated = self.sync(snapshot(
            kev("CVE-2026-1000", product="Alpha"),
            kev("CVE-2026-2000", product="Beta"),
        ))
        self.assertEqual((repeated.unchanged_count, repeated.updated_count), (2, 0))

        changed = self.sync(snapshot(
            kev("CVE-2026-1000", product="Alpha 2"),
            kev("CVE-2026-3000", product="Gamma"),
        ))
        self.assertEqual(
            (changed.created_count, changed.updated_count, changed.deactivated_count),
            (1, 1, 1),
        )
        status = self.repository.status(run_limit=10)
        self.assertEqual((status.active_count, status.inactive_count), (2, 1))
        self.assertEqual(
            {item.entry.cve_id for item in self.repository.list(active_only=True, limit=10)},
            {"CVE-2026-1000", "CVE-2026-3000"},
        )

        reactivated = self.sync(snapshot(
            kev("CVE-2026-1000", product="Alpha 2"),
            kev("CVE-2026-2000", product="Beta"),
            kev("CVE-2026-3000", product="Gamma"),
        ))
        self.assertEqual(reactivated.reactivated_count, 1)
        details = self.repository.details("cve-2026-2000", event_limit=20)
        self.assertTrue(details.record.active)
        self.assertEqual(
            [event.action for event in reversed(details.events)],
            ["added", "deactivated", "reactivated"],
        )

    def test_source_failure_is_saved_without_emptying_previous_catalog(self):
        self.sync(snapshot(kev("CVE-2026-1000")))
        before_entry = self.repository.details("CVE-2026-1000", event_limit=20).record
        failing = KevCatalogService(
            self.repository, Source(error="CISA geçici olarak yanıt vermedi."),
            clock=lambda: self.time,
        ).sync()
        self.assertEqual(failing.status, "failed")
        self.assertIn("geçici", failing.error)
        after_entry = self.repository.details("CVE-2026-1000", event_limit=20).record
        self.assertEqual(before_entry, after_entry)
        status = self.repository.status(run_limit=10)
        self.assertEqual(status.latest_run.status, "failed")
        self.assertEqual(status.active_count, 1)

    def test_invalid_snapshot_is_atomic_and_corruption_fails_closed(self):
        self.sync(snapshot(kev("CVE-2026-1000")))
        before = self.path.read_bytes()
        invalid = KevCatalogSnapshot(
            CISA_KEV_SOURCE, CISA_KEV_URL, "CISA KEV", "v2",
            "2026-10-29", "0" * 64,
            (kev("CVE-2026-2000"), kev("CVE-2026-1000")),
        )
        with self.assertRaisesRegex(Exception, "geçersiz|sorted|sıralı"):
            self.repository.apply(
                invalid, started_at=NOW.isoformat(), finished_at=NOW.isoformat(),
            )
        self.assertEqual(self.path.read_bytes(), before)

        backup = Path(self.temp.name) / "backup.db"
        self.storage.backup(backup)
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(
            SQLiteKevRepository(restored).details(
                "CVE-2026-1000", event_limit=20,
            ).record,
            self.repository.details("CVE-2026-1000", event_limit=20).record,
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE kev_entries SET state_sha256 = ? WHERE cve_id = ?",
                ("0" * 64, "CVE-2026-1000"),
            )
        broken = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "bozuk"):
            self.repository.details("CVE-2026-1000", event_limit=20)
        self.assertEqual(self.path.read_bytes(), broken)


if __name__ == "__main__":
    unittest.main()

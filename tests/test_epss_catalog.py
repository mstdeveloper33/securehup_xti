"""Atomic current EPSS score lifecycle and source failures."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_epss import SQLiteEpssRepository
from xti.application.vulnerability import EpssCatalogService
from xti.domain.assets import ValidationError
from xti.domain.vulnerability import (
    EpssCatalogSnapshot,
    EpssScore,
    FIRST_EPSS_SOURCE,
    FIRST_EPSS_URL,
)
from xti.ports.discovery import SourceError


def snapshot(entries, *, model="v2026.06.15", score_date="2026-10-29"):
    values = tuple(sorted(entries, key=lambda item: item.cve_id))
    return EpssCatalogSnapshot(
        FIRST_EPSS_SOURCE, FIRST_EPSS_URL, model, score_date,
        hashlib.sha256(repr(values).encode()).hexdigest(), values,
    )


class Source:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error

    def fetch(self):
        if self.error:
            raise SourceError(self.error)
        return self.value


class EpssCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteEpssRepository(self.path)
        self.times = iter(range(20))

    def service(self, value=None, error=None):
        return EpssCatalogService(
            self.repository, Source(value, error),
            clock=lambda: datetime(2026, 10, 29, 12, next(self.times), tzinfo=timezone.utc),
        )

    def test_full_snapshots_track_add_update_deactivate_and_reactivate(self):
        one = EpssScore("CVE-2021-44228", "0.1", "0.9")
        two = EpssScore("CVE-2024-9999", "0.2", "0.8")
        first = self.service(snapshot((one, two))).sync()
        self.assertEqual((first.created_count, first.updated_count), (2, 0))
        repeat = self.service(snapshot((one, two), score_date="2026-10-30")).sync()
        self.assertEqual(repeat.unchanged_count, 2)
        changed = EpssScore(one.cve_id, "0.3", "0.95")
        third = self.service(snapshot((changed,), score_date="2026-10-31")).sync()
        self.assertEqual((third.updated_count, third.deactivated_count), (1, 1))
        fourth = self.service(snapshot((changed, two), score_date="2026-11-01")).sync()
        self.assertEqual(fourth.reactivated_count, 1)
        details = self.service().show(one.cve_id)
        self.assertEqual(details.record.score.epss, "0.3")
        self.assertEqual(details.record.score_date, "2026-11-01")
        self.assertEqual(self.service().status().active_count, 2)

    def test_failure_preserves_catalog_and_invalid_snapshot_is_atomic(self):
        valid = snapshot((EpssScore("CVE-2021-44228", "0.1", "0.9"),))
        self.service(valid).sync()
        failed = self.service(error="FIRST geçici olarak yanıt vermedi.").sync()
        self.assertEqual(failed.status, "failed")
        self.assertEqual(self.service().status().active_count, 1)
        before = self.path.read_bytes()
        invalid = EpssCatalogSnapshot(
            FIRST_EPSS_SOURCE, FIRST_EPSS_URL, "bad", "2026-10-29", "0" * 64,
            valid.entries,
        )
        with self.assertRaises(ValidationError):
            self.repository.apply(
                invalid, started_at="2026-10-29T12:00:00+00:00",
                finished_at="2026-10-29T12:01:00+00:00",
            )
        self.assertEqual(self.path.read_bytes(), before)

    def test_backup_restore_and_corruption_fail_closed(self):
        self.service(snapshot((EpssScore("CVE-2021-44228", "0.1", "0.9"),))).sync()
        backup = Path(self.temp.name) / "backup.db"
        SQLiteAssetRepository(self.path).backup(backup)
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteEpssRepository(restored).status(run_limit=1).active_count, 1)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE epss_scores SET state_sha256 = ?", ("0" * 64,),
            )
        with self.assertRaises(StorageError):
            self.repository.details("CVE-2021-44228")


if __name__ == "__main__":
    unittest.main()

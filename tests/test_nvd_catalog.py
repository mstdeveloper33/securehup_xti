"""Atomic requested NVD CVE lifecycle and source failures."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_nvd import SQLiteNvdRepository
from xti.application.vulnerability import NvdCatalogService
from xti.domain.assets import ValidationError
from xti.domain.vulnerability import (
    CvssMetric,
    NVD_CVE_SOURCE,
    NvdCve,
    NvdCveSnapshot,
    nvd_cve_url,
)
from xti.ports.discovery import SourceError


def snapshot(*, status="Analyzed", score="10", description="Example issue"):
    record = NvdCve(
        "CVE-2021-44228", "security@example.org",
        "2021-12-10T10:15:09.143000+00:00",
        "2026-08-11T19:33:44.513000+00:00",
        status, description,
        (CvssMetric(
            "nvd@nist.gov", "Primary", "3.1", "CVSS:3.1/AV:N/AC:L",
            score, "CRITICAL", "3.9", "6",
        ),),
        ("CWE-917",), 1,
    )
    raw = json.dumps(
        {"id": record.cve_id, "vulnStatus": status, "description": description,
         "score": score},
        ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    )
    return NvdCveSnapshot(
        NVD_CVE_SOURCE, nvd_cve_url(record.cve_id), "2.0",
        "2026-10-29T15:01:05.762000+00:00",
        hashlib.sha256(raw.encode()).hexdigest(), raw, record,
    )


class Source:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error

    def fetch(self, cve_id):
        if self.error:
            raise SourceError(self.error)
        return self.value


class NvdCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteNvdRepository(self.path)
        self.times = iter(range(20))

    def service(self, value=None, error=None):
        return NvdCatalogService(
            self.repository, Source(value, error),
            clock=lambda: datetime(2026, 10, 29, 12, next(self.times), tzinfo=timezone.utc),
        )

    def test_add_repeat_update_and_history_preserve_every_source_metric(self):
        first = self.service(snapshot()).sync("CVE-2021-44228")
        self.assertEqual((first.created_count, first.updated_count), (1, 0))
        repeat = self.service(snapshot()).sync("CVE-2021-44228")
        self.assertEqual(repeat.unchanged_count, 1)
        changed = self.service(snapshot(status="Modified", score="9.8")).sync(
            "CVE-2021-44228"
        )
        self.assertEqual(changed.updated_count, 1)
        details = self.service().show("CVE-2021-44228")
        self.assertEqual(details.record.record.vuln_status, "Modified")
        self.assertEqual(details.record.record.cvss_metrics[0].base_score, "9.8")
        self.assertEqual([event.action for event in details.events], ["updated", "added"])
        self.assertEqual(details.total_event_count, 2)
        self.assertEqual(self.service().status().record_count, 1)

    def test_failure_preserves_previous_record_and_invalid_snapshot_is_atomic(self):
        self.service(snapshot()).sync("CVE-2021-44228")
        failed = self.service(error="NVD geçici olarak yanıt vermedi.").sync(
            "CVE-2021-44228"
        )
        self.assertEqual(failed.status, "failed")
        before = self.path.read_bytes()
        invalid = snapshot()
        invalid = NvdCveSnapshot(
            invalid.source, invalid.source_url, "bad", invalid.response_timestamp,
            invalid.content_sha256, invalid.record_json, invalid.record,
        )
        with self.assertRaises(ValidationError):
            self.repository.apply(
                invalid, started_at="2026-10-29T12:00:00+00:00",
                finished_at="2026-10-29T12:01:00+00:00",
            )
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.service().show("CVE-2021-44228").record.record.vuln_status,
                         "Analyzed")

    def test_backup_restore_and_corruption_fail_closed(self):
        self.service(snapshot()).sync("CVE-2021-44228")
        backup = Path(self.temp.name) / "backup.db"
        SQLiteAssetRepository(self.path).backup(backup)
        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteNvdRepository(restored).status(run_limit=1).record_count, 1)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE nvd_cve_records SET state_sha256 = ?", ("0" * 64,),
            )
        with self.assertRaises(StorageError):
            self.repository.details("CVE-2021-44228", event_limit=1)


if __name__ == "__main__":
    unittest.main()

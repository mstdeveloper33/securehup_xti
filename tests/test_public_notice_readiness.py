"""Public catalog readiness remains local, source scoped and failure preserving."""

from contextlib import closing
from dataclasses import asdict
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.source_readiness import SQLiteSourceReadinessRepository
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.application.source_readiness import SourceReadinessService
from xti.application.sources import SourceCatalogService
from tests.test_public_notices import NOW, feed


class PublicNoticeReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.notices = SQLitePublicNoticeRepository(self.path)
        self.readiness = SQLiteSourceReadinessRepository(self.path, self.root / "project")

    def row(self, domain=None):
        with patch("socket.create_connection", side_effect=AssertionError("network")), \
                patch("subprocess.run", side_effect=AssertionError("external tool")):
            return next(row for row in self.readiness.snapshot(domain=domain).sources if row.identifier == "notices:hibp")

    def test_catalog_describes_free_metadata_not_paid_account_queries(self):
        entry = next(entry for entry in SourceCatalogService().list() if entry.identifier == "hibp-public-breach-catalog")
        self.assertFalse(entry.credential_required)
        self.assertFalse(entry.paid_dependency)
        self.assertFalse(entry.contacts_monitored_target)
        self.assertIn("notices refresh", entry.commands)
        self.assertEqual(entry.reference_url, "https://haveibeenpwned.com/API/v3")
        self.assertIn("Kota", entry.access)
        self.assertTrue(any("CC BY 4.0" in limit for limit in entry.limits))

    def test_uninitialized_and_never_refreshed_are_not_empty_success(self):
        row = self.row()
        self.assertEqual(row.installation, "builtin")
        self.assertEqual(row.latest_status, "never")
        self.assertIsNone(row.record_count)
        self.assertIsNone(row.last_attempt_at)
        self.assertFalse(self.path.parent.exists())
        self.storage.initialize()
        self.assertEqual(self.row().latest_status, "never")
        self.assertEqual(self.row().next_command, "./xti notices refresh")

    def test_first_failure_remains_no_success_and_preserves_source_error(self):
        self.storage.initialize()
        failed = self.notices.record_failure(started_at=NOW.isoformat(), finished_at=NOW.isoformat(), error="Kaynak HTTP 429 verdi.")
        row = self.row()
        self.assertEqual((row.latest_status, row.last_attempt_at), ("failed", failed.started_at))
        self.assertIsNone(row.last_success_at)
        self.assertIsNone(row.record_count)
        self.assertEqual(row.error, failed.error)

    def test_failure_after_success_keeps_catalog_count_not_domain_matching_count(self):
        self.storage.initialize()
        self.storage.add("unmatched.example")
        success = self.notices.apply(feed(), started_at=NOW.isoformat(), finished_at=NOW.isoformat()).run
        later = (NOW + timedelta(minutes=5)).isoformat()
        failure = self.notices.record_failure(started_at=later, finished_at=later, error="Kaynak erişimi tamamlanamadı.")
        before = self.path.read_bytes()
        row = self.row("unmatched.example")
        self.assertEqual((row.latest_status, row.record_count), ("failed", 1))
        self.assertEqual((row.last_attempt_at, row.last_success_at), (failure.started_at, success.finished_at))
        self.assertIn("domain filtresinden bağımsız", row.scope)
        self.assertTrue(any("eşleşme sayısı değildir" in note for note in row.notes))
        payload = json.dumps(asdict(row))
        self.assertIn("https://haveibeenpwned.com", payload)
        self.assertIn("CC BY 4.0", payload)
        report = SourceReadinessService(self.readiness, clock=lambda: NOW + timedelta(minutes=6)).show()
        rendered = next(item for item in report.sources if item.evidence.identifier == "notices:hibp")
        self.assertTrue(rendered.needs_attention)
        self.assertEqual(rendered.freshness, "current")
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_catalog_fails_instead_of_reporting_missing_source(self):
        self.storage.initialize()
        self.notices.apply(feed(), started_at=NOW.isoformat(), finished_at=NOW.isoformat())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DELETE FROM public_notice_changes")
        before = self.path.read_bytes()
        with self.assertRaises(StorageError): self.row()
        self.assertEqual(self.path.read_bytes(), before)

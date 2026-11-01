"""Time-bounded exact-domain exceptions expire without deleting their audit trail."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_allowlist import SQLiteAllowlistRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.application.allowlist import AllowlistService
from xti.application.assets import AssetService
from xti.application.findings import DomainImportService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import make_domain_matcher

from tests.test_allowlist import document


NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


class ExpiringAllowlistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "xti.db"
        self.now = [NOW]
        self.assets = SQLiteAssetRepository(self.database)
        self.assets.initialize()
        self.asset = AssetService(self.assets).add("example.com")[0]
        self.matcher = make_domain_matcher()
        self.allowlist = SQLiteAllowlistRepository(
            self.database, clock=lambda: self.now[0],
        )
        self.service = AllowlistService(
            self.assets, self.allowlist, self.matcher, clock=lambda: self.now[0],
        )
        self.findings = SQLiteFindingRepository(
            self.database, clock=lambda: self.now[0],
        )
        self.importer = DomainImportService(
            self.assets, self.findings, self.matcher, self.allowlist,
            clock=lambda: self.now[0],
        )

    def test_exact_expiry_releases_preserved_observation_without_a_read_write(self):
        entry, changed = self.service.add(
            "example.com", "example-support.net", "Bir günlük kampanya.", 1,
        )
        self.assertTrue(changed)
        self.assertEqual(entry.expires_at, (NOW + timedelta(days=1)).isoformat())
        self.assertTrue(entry.active)
        self.assertFalse(entry.expired)
        self.assertFalse(entry.revoked)

        first = self.importer.import_document(document(identity="expiring"))
        self.assertEqual((first.findings_suppressed, first.findings_created), (1, 0))
        self.assertEqual(self.assets.inspect()["observation_count"], 1)

        self.now[0] = NOW + timedelta(days=1)
        before = self.database.read_bytes()
        self.assertEqual(self.service.list(), ())
        expired = self.service.list(active_only=False)[0]
        self.assertFalse(expired.active)
        self.assertTrue(expired.expired)
        self.assertFalse(expired.revoked)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.allowlist.active_pairs((self.asset.id,)), frozenset())

        second = self.importer.import_document(document(identity="expiring"))
        self.assertEqual(second.observations_existing, 1)
        self.assertEqual((second.findings_suppressed, second.findings_created), (0, 1))
        self.assertEqual(len(self.findings.list_findings()), 1)
        self.assertEqual(self.assets.inspect()["notification_count"], 1)

    def test_active_expiry_update_and_expired_reactivation_keep_one_identity(self):
        entry, _ = self.service.add(
            "example.com", "example-support.net", "İlk süre.", 5,
        )
        repeated, changed = self.service.add(
            "example.com", "example-support.net", "Kaydedilmemeli.", 5,
        )
        self.assertFalse(changed)
        self.assertEqual(repeated, entry)

        updated, changed = self.service.add(
            "example.com", "example-support.net", "Süre uzatıldı.", 10,
        )
        self.assertTrue(changed)
        self.assertEqual(updated.id, entry.id)
        self.assertEqual(updated.expires_at, (NOW + timedelta(days=10)).isoformat())
        self.assertEqual(updated.reason, "Süre uzatıldı.")

        self.now[0] = NOW + timedelta(days=11)
        self.assertTrue(self.service.show(entry.id).entry.expired)
        reactivated, changed = self.service.add(
            "example.com", "example-support.net", "Yeniden geçici olarak onaylandı.", 2,
        )
        self.assertTrue(changed)
        self.assertEqual(reactivated.id, entry.id)
        self.assertTrue(reactivated.active)
        details = self.service.show(entry.id)
        self.assertEqual(
            tuple(event.action for event in details.events),
            ("added", "updated", "reactivated"),
        )
        self.assertEqual(
            tuple(event.expires_at for event in details.events),
            (
                (NOW + timedelta(days=5)).isoformat(),
                (NOW + timedelta(days=10)).isoformat(),
                (NOW + timedelta(days=13)).isoformat(),
            ),
        )

    def test_invalid_duration_or_corrupt_expiry_never_creates_partial_evidence(self):
        for value in (0, 3651, True):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.service.add(
                    "example.com", "example-support.net", "Geçersiz süre.", value,
                )
        self.assertEqual(self.service.list(active_only=False), ())

        self.service.add("example.com", "example-support.net", "Bozulma testi.", 1)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "UPDATE allowlist_entries SET expires_at = 'not-a-time' WHERE domain = ?",
                ("example-support.net",),
            )
            connection.commit()
        candidate = self.matcher.match(self.asset, "example-support.net")
        self.assertIsNotNone(candidate)
        with self.assertRaisesRegex(StorageError, "bitiş zamanı"):
            self.findings.save_import(document(identity="corrupt-expiry"), (candidate,))
        self.assertEqual(self.assets.inspect()["observation_count"], 0)
        self.assertEqual(self.findings.list_findings(), [])


if __name__ == "__main__":
    unittest.main()

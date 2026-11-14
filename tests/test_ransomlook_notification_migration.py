"""58 to 59 migration retains history and never backfills RansomLook notices."""

from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.domain.organizations import normalize_organization_target
from tests import test_ransomlook_notifications as fixtures
from tests.collection_v60_fixture import collection_layout_v60


def snapshot(path):
    with closing(sqlite3.connect(path)) as connection:
        return {table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in VERSION_TABLES[58]}


class RansomLookNotificationMigrationTests(unittest.TestCase):
    setUp = fixtures.RansomLookNotificationTests.setUp
    apply = fixtures.RansomLookNotificationTests.apply
    service = fixtures.RansomLookNotificationTests.service
    baseline = fixtures.RansomLookNotificationTests.baseline
    changed = fixtures.RansomLookNotificationTests.changed
    finding = fixtures.RansomLookNotificationTests.finding

    def legacy(self):
        finding = self.finding()
        SQLiteInboxRepository(self.path).mark((finding.id,), True, fixtures.NOW.isoformat())
        _, _, report = self.changed()
        organizations = SQLiteOrganizationRepository(self.path)
        org = organizations.add(name_key="example", display_name="Example", reason="Açık kuruluş seçimi.", recorded_at=fixtures.NOW.isoformat()).organization
        organizations.link(org.id, normalize_organization_target("domain", "example.com"), reason="Kullanıcı seçimi.", recorded_at=fixtures.NOW.isoformat())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            collection_layout_v60(connection)
            connection.execute("DROP TABLE IF EXISTS public_notice_changes")
            connection.execute("DROP TABLE IF EXISTS public_notice_runs")
            connection.execute("DROP TABLE ransomlook_watch_notifications")
            connection.execute("PRAGMA user_version=58")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 58)
        return finding, report

    def test_preserves_every_legacy_row_and_read_state_without_backfill(self):
        finding, report = self.legacy(); before = snapshot(self.path)
        result = SQLiteAssetRepository(self.path).migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (58, SCHEMA_VERSION))
        self.assertEqual(snapshot(self.path), before)
        self.assertEqual(snapshot(result["backup"]), before)
        with closing(sqlite3.connect(result["backup"])) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 58)
        old = SQLiteRansomLookWatchRepository(self.path).run_details(report.run.id, item_limit=100)
        self.assertIsNone(old.notification_id)
        self.assertEqual(old.attention_count, report.attention_count)
        page = SQLiteInboxRepository(self.path).list("all")
        self.assertEqual((page.total_count, page.unread_count), (1, 0))
        self.assertEqual(page.items[0].notification.id, finding.id)
        again = SQLiteAssetRepository(self.path).migrate()
        self.assertFalse(again["changed"])
        self.assertIsNone(again["backup"])

    def test_readonly_requires_explicit_migration_and_changes_nothing(self):
        _, report = self.legacy(); before = self.path.read_bytes()
        for operation in (lambda: SQLiteInboxRepository(self.path).list(),
                          lambda: self.watches.run_details(report.run.id, item_limit=100)):
            with self.assertRaisesRegex(StorageError, "migrate"): operation()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_failed_ddl_rolls_back_and_retains_unique_restorable_legacy_backups(self):
        self.legacy(); before = snapshot(self.path)
        def fail(connection):
            connection.execute("CREATE TABLE ransomlook_watch_notifications (id TEXT PRIMARY KEY NOT NULL)")
            raise sqlite3.OperationalError("controlled schema59 failure")
        with patch("xti.adapters.sqlite.create_ransomlook_notification_schema", side_effect=fail):
            for _ in range(2):
                with self.assertRaises(StorageError): SQLiteAssetRepository(self.path).migrate()
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), 58)
                self.assertEqual(snapshot(self.path), before)
        backups = list((self.path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 2)
        restored = Path(self.temp.name) / "restored.db"
        SQLiteAssetRepository.restore(backups[0], restored)
        with self.assertRaises(StorageError): SQLiteAssetRepository.restore(backups[0], restored)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(snapshot(restored), before)


if __name__ == "__main__":
    unittest.main()

"""Schema 48 to 49 adds empty, recoverable social-profile inbox links."""

from contextlib import closing
from datetime import timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_brand_username_reviews import (
    SQLiteBrandUsernameReviewRepository,
)
from xti.adapters.sqlite_brand_username_watches import (
    SQLiteBrandUsernameWatchRepository,
)
from xti.application.brand_username_reviews import BrandUsernameReviewService
from xti.application.brand_username_watches import BrandUsernameWatchService
from tests.test_brand_username_reviews import FakeSource, NOW, github


class BrandUsernameReviewNotificationMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "legacy" / "xti.db"

    def version_forty_eight(self, *, with_possible_review=False):
        SQLiteAssetRepository(self.path).initialize()
        if with_possible_review:
            watches = BrandUsernameWatchService(
                SQLiteBrandUsernameWatchRepository(self.path),
                FakeSource({"GitHub": github()}),
                clock=lambda: NOW + timedelta(minutes=10),
            )
            watch = watches.add(
                "Geçiş Markası", "samplebrand", platforms=("GitHub",),
            ).watch
            watches.run(watch.id)
            BrandUsernameReviewService(
                SQLiteBrandUsernameReviewRepository(self.path),
                clock=lambda: NOW + timedelta(minutes=20),
            ).decide(
                watch.id,
                "GitHub",
                decision="possible_impersonation",
                reason="Şema 48 geçmiş karar kanıtı",
            )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE brand_username_review_notifications")
            connection.execute(
                "ALTER TABLE brand_username_watches DROP COLUMN source_key"
            )
            connection.execute("DROP INDEX IF EXISTS supplier_candidate_resolutions_candidate_sequence")
            connection.execute("DROP INDEX IF EXISTS supplier_candidate_evidence_candidate_sequence")
            connection.execute("DROP INDEX IF EXISTS supplier_candidates_status_current")
            connection.execute("DROP TABLE IF EXISTS supplier_candidate_resolution_events")
            connection.execute("DROP TABLE IF EXISTS supplier_candidate_evidence")
            connection.execute("DROP TABLE IF EXISTS supplier_candidates")
            connection.execute("DROP INDEX IF EXISTS supplier_events_supplier_sequence")
            connection.execute("DROP INDEX IF EXISTS suppliers_active_name")
            connection.execute("DROP TABLE IF EXISTS supplier_events")
            connection.execute("DROP TABLE IF EXISTS suppliers")
            connection.execute("DROP TABLE IF EXISTS case_activities")
            connection.execute("DROP TABLE IF EXISTS case_tasks")
            connection.execute("DROP TABLE IF EXISTS case_evidence")
            connection.execute("DROP TABLE IF EXISTS cases")
            connection.execute("DROP TABLE IF EXISTS collection_profile_events")
            connection.execute("DROP TABLE IF EXISTS collection_profiles")
            connection.execute("DROP TABLE IF EXISTS collection_step_receipts")
            connection.execute("DROP TABLE IF EXISTS collection_session_steps")
            connection.execute("DROP TABLE IF EXISTS collection_sessions")
            connection.execute("PRAGMA user_version=48")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 48)
        return self.path

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v48_migrates_with_backup_and_empty_notification_storage(self):
        path = self.version_forty_eight()
        result = SQLiteAssetRepository(path).migrate()
        self.assertEqual(
            (result["from_version"], result["to_version"]),
            (48, SCHEMA_VERSION),
        )
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM brand_username_review_notifications"
            ).fetchone()[0], 0)
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 48)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 48)

    def test_migration_does_not_backfill_notice_from_existing_possible_review(self):
        path = self.version_forty_eight(with_possible_review=True)
        SQLiteAssetRepository(path).migrate()
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM brand_username_review_events"
            ).fetchone()[0], 1)
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM brand_username_review_notifications"
            ).fetchone()[0], 0)

    def test_failed_creation_rolls_back_and_keeps_valid_v48_backup(self):
        path = self.version_forty_eight()

        def incomplete(connection):
            connection.execute(
                "CREATE TABLE brand_username_review_notifications "
                "(id TEXT PRIMARY KEY)"
            )
            raise sqlite3.OperationalError("controlled failure")

        with patch(
            "xti.adapters.sqlite.create_brand_username_review_notification_schema",
            side_effect=incomplete,
        ):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 48)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual((len(backups), self.version(backups[0])), (1, 48))

    def test_v48_reads_never_migrate_or_create_notification_table(self):
        path = self.version_forty_eight()
        before = path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteInboxRepository(path).list()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.version(path), 48)


if __name__ == "__main__":
    unittest.main()

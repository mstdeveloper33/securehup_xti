"""Schema 49 social evidence migrates to immutable Maigret source identity."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.maigret_username import INTEGRATION_PROFILE
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_reviews import (
    SQLiteBrandUsernameReviewRepository,
)
from xti.adapters.sqlite_brand_username_watches import (
    SQLiteBrandUsernameWatchRepository,
)
from xti.application.brand_username_reviews import BrandUsernameReviewService
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.domain.brand_username import BrandProfileMatch, BrandUsernamePreview


NOW = datetime(2026, 10, 31, 18, tzinfo=timezone.utc)


class FakeMaigret:
    source_name = "Maigret"
    source_version = "0.6.6"
    integration_profile = INTEGRATION_PROFILE

    def preview(self, username, *, platforms, request_timeout):
        return BrandUsernamePreview(
            username=username,
            source=self.source_name,
            source_version=self.source_version,
            integration_profile=self.integration_profile,
            checked_at=NOW.isoformat(),
            requested_platforms=platforms,
            matches=(BrandProfileMatch(
                "GitHub", f"https://github.com/{username}", "found_unverified",
            ),),
            unreported_platforms=(),
            notes=("Sahiplik kanıtı değildir.",),
        )


class BrandUsernameSourceMigrationTests(unittest.TestCase):
    def test_migration_preserves_runs_reviews_and_backup_as_schema_49(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "xti.db"
            SQLiteAssetRepository(path).initialize()
            watches = BrandUsernameWatchService(
                SQLiteBrandUsernameWatchRepository(path),
                FakeMaigret(),
                clock=lambda: NOW + timedelta(minutes=10),
            )
            watch = watches.add(
                "Örnek marka", "samplebrand", platforms=("GitHub",),
            ).watch
            report = watches.run(watch.id)
            reviews = BrandUsernameReviewService(
                SQLiteBrandUsernameReviewRepository(path),
                clock=lambda: NOW + timedelta(minutes=20),
            )
            decision = reviews.decide(
                watch.id,
                "GitHub",
                decision="known_official",
                reason="Kuruluşun yayımladığı profil adresiyle doğrulandı.",
            )

            with closing(sqlite3.connect(path)) as connection, connection:
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
                connection.execute("PRAGMA user_version=49")

            result = SQLiteAssetRepository(path).migrate()

            self.assertEqual(
                (result["from_version"], result["to_version"]),
                (49, SCHEMA_VERSION),
            )
            backup = Path(result["backup"])
            self.assertTrue(backup.is_file())
            with closing(sqlite3.connect(backup)) as connection:
                self.assertEqual(connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0], 49)
                columns = {
                    row[1] for row in connection.execute(
                        "PRAGMA table_info(brand_username_watches)"
                    )
                }
                self.assertNotIn("source_key", columns)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute(
                    "SELECT source_key FROM brand_username_watches WHERE id=?",
                    (watch.id,),
                ).fetchone()[0], "maigret")
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM brand_username_watch_runs WHERE id=?",
                    (report.run.id,),
                ).fetchone()[0], 1)
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM brand_username_review_events WHERE candidate_id=?",
                    (decision.details.candidate.id,),
                ).fetchone()[0], 1)

            migrated = SQLiteBrandUsernameWatchRepository(path).get(watch.id)
            self.assertEqual(migrated.source_key, "maigret")
            review = SQLiteBrandUsernameReviewRepository(path).details(
                decision.details.candidate.id, event_limit=10,
            )
            self.assertEqual(review.current.decision, "known_official")

    def test_failed_source_column_migration_rolls_back_schema_49(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "xti.db"
            SQLiteAssetRepository(path).initialize()
            with closing(sqlite3.connect(path)) as connection, connection:
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
                connection.execute("PRAGMA user_version=49")

            with patch(
                "xti.adapters.sqlite.migrate_brand_username_watch_source_schema",
                side_effect=sqlite3.OperationalError("controlled failure"),
            ):
                with self.assertRaises(StorageError):
                    SQLiteAssetRepository(path).migrate()

            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0], 49)
                columns = {
                    row[1] for row in connection.execute(
                        "PRAGMA table_info(brand_username_watches)"
                    )
                }
                self.assertNotIn("source_key", columns)
            backups = list((path.parent / "backups").glob("*.db"))
            self.assertEqual(len(backups), 1)
            with closing(sqlite3.connect(backups[0])) as connection:
                self.assertEqual(connection.execute(
                    "PRAGMA user_version"
                ).fetchone()[0], 49)


if __name__ == "__main__":
    unittest.main()

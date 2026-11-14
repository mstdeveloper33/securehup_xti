"""Schema 50 widens passive-discovery providers without losing CT evidence."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tests.public_notice_watch_legacy_fixture import remove_public_notice_watch_schema

from xti.adapters.schema import (
    SCHEMA_VERSION,
    SURFACE_DISCOVERY_DDL,
    SURFACE_DISCOVERY_HISTORY_DDL,
    SURFACE_DISCOVERY_HISTORY_V50_DDL,
    SURFACE_DISCOVERY_V50_DDL,
    validate_schema,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_surface_candidates import SQLiteSurfaceCandidateRepository
from xti.domain.surface import SurfaceCandidateEvidence, SurfaceDiscoveryRunRequest


AT = "2026-10-31T10:00:00+00:00"


class SurfaceProviderMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"

    def version_fifty(self):
        storage = SQLiteAssetRepository(self.path)
        storage.initialize()
        asset, _ = storage.add("example.com")
        SQLiteSurfaceCandidateRepository(self.path).record_discovery(
            asset.id,
            asset.value,
            (
                SurfaceCandidateEvidence(
                    "api.example.com",
                    "crt.sh",
                    "https://crt.sh/?id=1",
                    "a" * 64,
                    "api.example.com",
                    AT,
                ),
            ),
            SurfaceDiscoveryRunRequest(
                "complete",
                "https://crt.sh/?q=%25.example.com",
                AT,
                AT,
                1,
                0,
                0,
                (),
                1,
                None,
            ),
        )
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            with connection:
                connection.execute("DROP INDEX surface_candidate_sources_candidate_id")
                connection.execute("DROP INDEX surface_discovery_runs_asset_sequence")
                connection.execute(
                    "ALTER TABLE surface_candidate_sources "
                    "RENAME TO surface_candidate_sources_v51"
                )
                connection.execute(
                    "ALTER TABLE surface_discovery_runs RENAME TO surface_discovery_runs_v51"
                )
                connection.execute(SURFACE_DISCOVERY_V50_DDL[1])
                connection.execute(SURFACE_DISCOVERY_HISTORY_V50_DDL[0])
                connection.execute(
                    "INSERT INTO surface_candidate_sources SELECT * "
                    "FROM surface_candidate_sources_v51"
                )
                connection.execute(
                    "INSERT INTO surface_discovery_runs SELECT * "
                    "FROM surface_discovery_runs_v51"
                )
                connection.execute(SURFACE_DISCOVERY_V50_DDL[4])
                connection.execute(SURFACE_DISCOVERY_HISTORY_V50_DDL[2])
                connection.execute("DROP TABLE surface_candidate_sources_v51")
                connection.execute("DROP TABLE surface_discovery_runs_v51")
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
                remove_public_notice_watch_schema(connection)
                connection.execute("DROP TABLE IF EXISTS public_notice_changes")
                connection.execute("DROP TABLE IF EXISTS public_notice_runs")
                connection.execute("DROP TABLE IF EXISTS ransomlook_watch_notifications")
                connection.execute("DROP TABLE IF EXISTS attack_catalog_changes")
                connection.execute("DROP TABLE IF EXISTS attack_catalog_phases")
                connection.execute("DROP TABLE IF EXISTS attack_catalog_relationships")
                connection.execute("DROP TABLE IF EXISTS attack_catalog_entities")
                connection.execute("DROP TABLE IF EXISTS attack_catalog_runs")
                connection.execute("DROP TABLE IF EXISTS organization_link_events")
                connection.execute("DROP TABLE IF EXISTS organization_links")
                connection.execute("DROP TABLE IF EXISTS organization_events")
                connection.execute("DROP TABLE IF EXISTS organizations")
                connection.execute("DROP TABLE IF EXISTS collection_step_receipts")
                connection.execute("DROP TABLE IF EXISTS collection_session_steps")
                connection.execute("DROP TABLE IF EXISTS collection_sessions")
                connection.execute("PRAGMA user_version=50")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 50)
        return asset

    @staticmethod
    def rows(path):
        with closing(sqlite3.connect(path)) as connection:
            return {
                "sources": connection.execute(
                    "SELECT * FROM surface_candidate_sources ORDER BY rowid"
                ).fetchall(),
                "runs": connection.execute(
                    "SELECT * FROM surface_discovery_runs ORDER BY sequence"
                ).fetchall(),
                "notices": connection.execute(
                    "SELECT * FROM surface_candidate_notifications ORDER BY sequence"
                ).fetchall(),
            }

    def test_v50_evidence_and_sequences_survive_and_new_provider_is_accepted(self):
        asset = self.version_fifty()
        before = self.rows(self.path)

        result = SQLiteAssetRepository(self.path).migrate()

        self.assertEqual((result["from_version"], result["to_version"]), (50, SCHEMA_VERSION))
        self.assertEqual(self.rows(self.path), before)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            source_sql = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name='surface_candidate_sources'"
            ).fetchone()[0]
            run_sql = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name='surface_discovery_runs'"
            ).fetchone()[0]
            self.assertIn("'theharvester'", source_sql)
            self.assertIn("'theharvester'", run_sql)

        repository = SQLiteSurfaceCandidateRepository(self.path)
        saved, run = repository.record_discovery(
            asset.id,
            asset.value,
            (
                SurfaceCandidateEvidence(
                    "archive.example.com",
                    "theharvester",
                    "theHarvester:commoncrawl@test",
                    "b" * 64,
                    "archive.example.com",
                    AT,
                ),
            ),
            SurfaceDiscoveryRunRequest(
                "complete", "https://example.invalid/source", AT, AT,
                1, 0, 0, (), 1, None, "theharvester",
            ),
        )
        self.assertEqual(
            (saved.candidates_created, run.sequence, run.provider),
            (1, 2, "theharvester"),
        )
        candidate = next(
            item for item in repository.list_candidates(asset.id, status=None, limit=10)
            if item.domain == "archive.example.com"
        )
        details = repository.candidate_details(candidate.id)
        self.assertEqual(
            [(item.provider, item.source_name) for item in details.sources],
            [("theharvester", "theHarvester:commoncrawl@test")],
        )

        backup = Path(result["backup"])
        self.assertEqual(self.rows(backup), before)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 50)
            self.assertNotIn(
                "'theharvester'",
                connection.execute(
                    "SELECT sql FROM sqlite_schema WHERE name='surface_candidate_sources'"
                ).fetchone()[0],
            )

    def test_failed_provider_widening_rolls_back_and_keeps_v50_backup(self):
        self.version_fifty()
        before = self.rows(self.path)

        def incomplete(connection):
            connection.execute("DROP INDEX surface_candidate_sources_candidate_id")
            raise sqlite3.OperationalError("controlled provider migration failure")

        with patch(
            "xti.adapters.sqlite.migrate_surface_discovery_provider_schema",
            side_effect=incomplete,
        ):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(self.path).migrate()

        self.assertEqual(self.rows(self.path), before)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 50)
        backups = list((self.path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.rows(backups[0]), before)


if __name__ == "__main__":
    unittest.main()

"""Schema 54 profile migration is explicit, backed up and recoverable."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from tests.case_evidence_v62_fixture import case_evidence_layout_v62
from tests.public_notice_watch_legacy_fixture import remove_public_notice_watch_schema

from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository


class CollectionProfileMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        storage = SQLiteAssetRepository(self.path)
        storage.initialize()
        self.asset, _ = storage.add("example.com")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE collection_profile_events")
            connection.execute("DROP TABLE collection_profiles")
            case_evidence_layout_v62(connection)
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
            connection.execute("PRAGMA user_version=54")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 54)

    def test_migration_preserves_asset_and_valid_legacy_snapshot(self):
        storage = SQLiteAssetRepository(self.path)
        result = storage.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (54, SCHEMA_VERSION))
        self.assertTrue(result["changed"])
        self.assertEqual(storage.list(), [self.asset])
        self.assertEqual(SQLiteCollectionProfileRepository(self.path).list(), ())
        with closing(sqlite3.connect(result["backup"])) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 54)
            self.assertEqual(connection.execute("SELECT id FROM assets").fetchone()[0], self.asset.id)
        repeated = storage.migrate()
        self.assertFalse(repeated["changed"])
        self.assertIsNone(repeated["backup"])
        self.assertEqual(len(list((self.path.parent / "backups").glob("*.db"))), 1)

    def test_legacy_read_refuses_without_mutation_or_automatic_migration(self):
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteCollectionProfileRepository(self.path).list()
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse((self.path.parent / "backups").exists())

    def test_failed_schema_creation_rolls_back_and_preserves_recoverable_backup(self):
        def incomplete(connection):
            connection.execute("CREATE TABLE collection_profiles (id TEXT PRIMARY KEY NOT NULL)")
            raise sqlite3.OperationalError("controlled migration failure")

        with patch("xti.adapters.sqlite.create_collection_profile_schema", side_effect=incomplete):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(self.path).migrate()
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 54)
            self.assertEqual(connection.execute("SELECT id FROM assets").fetchone()[0], self.asset.id)
        backups = list((self.path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 54)
        restored = self.path.parent / "recovered.db"
        SQLiteAssetRepository.restore(backups[0], restored)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(SQLiteAssetRepository(restored).list(), [self.asset])


if __name__ == "__main__":
    unittest.main()

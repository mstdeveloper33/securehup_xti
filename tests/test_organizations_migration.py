"""Schema57 preserves schema55 profiles and schema56 collection sessions."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import (
    SCHEMA_VERSION, VERSION_TABLES, create_collection_history_schema,
    create_organization_schema, validate_schema,
)
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.collection_history import CollectionFrozenPlan, CollectionFrozenUnit


NOW = "2026-11-14T12:00:00+00:00"
ORGANIZATION_TABLES = (
    "attack_catalog_changes", "attack_catalog_phases", "attack_catalog_relationships",
    "attack_catalog_entities", "attack_catalog_runs",
    "organization_link_events", "organization_links", "organization_events", "organizations",
)


def snapshot(path, version):
    with closing(sqlite3.connect(path)) as connection:
        return {table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in sorted(VERSION_TABLES[version])}


class OrganizationMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def legacy(self, version):
        path = self.root / f"v{version}.db"
        storage = SQLiteAssetRepository(path)
        storage.initialize()
        storage.add("example.com")
        definition = CollectionProfileDefinition("example.com", task_ids=("ioc-feodo",))
        SQLiteCollectionProfileRepository(path).save("Daily profile", definition, recorded_at=NOW)
        if version == 56:
            plan = CollectionFrozenPlan(definition, (
                CollectionFrozenUnit("ioc-feodo", "ioc", "feodo", "example.com", None, "feed-v1"),
            ))
            SQLiteCollectionHistoryRepository(path).begin(plan, started_at=NOW)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_notifications")
            for table in ORGANIZATION_TABLES:
                connection.execute(f"DROP TABLE {table}")
            if version == 55:
                for table in ("collection_step_receipts", "collection_session_steps", "collection_sessions"):
                    connection.execute(f"DROP TABLE {table}")
            connection.execute(f"PRAGMA user_version={version}")
            self.assertEqual(validate_schema(connection, allow_legacy=True), version)
        return path

    def test_56_to_57_keeps_every_existing_row_and_full_collection_session(self):
        path = self.legacy(56)
        before = snapshot(path, 56)
        storage = SQLiteAssetRepository(path)
        result = storage.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (56, SCHEMA_VERSION))
        self.assertEqual(snapshot(path, 56), before)
        self.assertEqual(SQLiteOrganizationRepository(path).list().total_count, 0)
        self.assertEqual(len(SQLiteCollectionHistoryRepository(path).list().sessions), 1)
        backup = Path(result["backup"])
        self.assertEqual(snapshot(backup, 56), before)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 56)
        repeated = storage.migrate()
        self.assertFalse(repeated["changed"])
        self.assertIsNone(repeated["backup"])

    def test_55_upgrade_applies_56_then_57_without_inventing_old_sessions_or_groups(self):
        path = self.legacy(55)
        before = snapshot(path, 55)
        order = []
        def history(connection):
            order.append(56)
            create_collection_history_schema(connection)
        def organizations(connection):
            order.append(57)
            create_organization_schema(connection)
        with patch("xti.adapters.sqlite.create_collection_history_schema", side_effect=history), \
             patch("xti.adapters.sqlite.create_organization_schema", side_effect=organizations):
            result = SQLiteAssetRepository(path).migrate()
        self.assertEqual(order, [56, 57])
        self.assertEqual(snapshot(path, 55), before)
        self.assertEqual(SQLiteCollectionHistoryRepository(path).list().sessions, ())
        self.assertEqual(SQLiteOrganizationRepository(path).list().organizations, ())
        with closing(sqlite3.connect(result["backup"])) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 55)

    def test_legacy_reads_require_explicit_migration_and_preserve_files(self):
        for version in (55, 56):
            path = self.legacy(version)
            before = path.read_bytes()
            with self.assertRaisesRegex(StorageError, "migrate"):
                SQLiteOrganizationRepository(path).list()
            self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / "backups").exists())

    def test_failure_rolls_back_both_migrations_and_keeps_recovery_backups(self):
        for version in (55, 56):
            with self.subTest(version=version):
                path = self.legacy(version)
                before = snapshot(path, version)
                def broken(connection):
                    connection.execute("CREATE TABLE organizations (id TEXT PRIMARY KEY NOT NULL)")
                    raise sqlite3.OperationalError("controlled organization migration failure")
                with patch("xti.adapters.sqlite.create_organization_schema", side_effect=broken):
                    with self.assertRaises(StorageError): SQLiteAssetRepository(path).migrate()
                self.assertEqual(snapshot(path, version), before)
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), version)
                backups = list((self.root / "backups").glob(f"v{version}.pre-v{SCHEMA_VERSION}-*.db"))
                self.assertEqual(len(backups), 1)
                self.assertEqual(snapshot(backups[0], version), before)
                restored = self.root / f"restored-{version}.db"
                SQLiteAssetRepository.restore(backups[0], restored)
                SQLiteAssetRepository(restored).migrate()
                self.assertEqual(snapshot(restored, version), before)


if __name__ == "__main__":
    unittest.main()

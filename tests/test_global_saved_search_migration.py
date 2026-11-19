"""Schema64 to 65 preserves old evidence and supports explicit recovery only."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.global_saved_search_schema import GLOBAL_SAVED_SEARCH_DDL
from xti.adapters.global_saved_search_schema_metadata import LEGACY_TABLES as NEW_TABLES
from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from tests.global_saved_search_legacy_fixture import remove_global_saved_search_schema


from tests.collection_v68_fixture import legacy_collection_manifest_entry


def legacy_manifest(path):
    """Every legacy row, rowid, column and SQL declaration, not a count sample."""
    with closing(sqlite3.connect(Path(path).absolute().as_uri() + "?mode=ro", uri=True)) as connection:
        manifest = {}
        for table in sorted(VERSION_TABLES[64]):
            quoted = '"' + table.replace('"', '""') + '"'
            manifest[table] = (
                connection.execute(f"PRAGMA table_info({quoted})").fetchall(),
                connection.execute(f"SELECT rowid,* FROM {quoted} ORDER BY rowid").fetchall(),
                connection.execute(
                    "SELECT type,name,sql FROM sqlite_schema WHERE tbl_name=? ORDER BY name", (table,),
                ).fetchall(),
            )
        manifest["sqlite_sequence"] = connection.execute(
            "SELECT name,seq FROM sqlite_sequence ORDER BY name"
        ).fetchall()
        for table in ("collection_session_steps", "collection_step_receipts", "case_evidence"):
            if table in manifest:
                manifest[table] = legacy_collection_manifest_entry(table, manifest[table])
        return manifest


class GlobalSavedSearchMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data" / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        SQLiteAssetRepository(self.path).add("example.com")

    def legacy(self, *, rich=False):
        if rich:
            from tests.test_stabilization_data import StabilizationDataTests
            fixture = StabilizationDataTests()
            self.addCleanup(fixture.doCleanups)
            fixture.setUp()
            fixture.richer_seed()
            self.path, self.root = fixture.database, fixture.root
            with closing(sqlite3.connect(self.path)) as connection, connection:
                # Include non-contiguous rowids and read state in preservation proof.
                connection.execute("UPDATE case_evidence SET rowid=rowid+100")
                connection.execute("UPDATE notifications SET read_at=created_at")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            remove_global_saved_search_schema(connection)
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(connection)
            connection.execute("PRAGMA user_version=64")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 64)
        return SQLiteAssetRepository(self.path)

    def test_additive_migration_preserves_all_old_rows_rowids_sql_sequences_and_read_state(self):
        storage = self.legacy(rich=True)
        before = legacy_manifest(self.path)
        result = storage.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (64, SCHEMA_VERSION))
        self.assertEqual(VERSION_TABLES[65] - VERSION_TABLES[64], NEW_TABLES.keys())
        self.assertEqual(legacy_manifest(self.path), before)
        self.assertEqual(legacy_manifest(result["backup"]), before)
        with closing(sqlite3.connect(result["backup"])) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 64)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            for table in NEW_TABLES:
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        repeated = storage.migrate()
        self.assertFalse(repeated["changed"])
        self.assertIsNone(repeated["backup"])
        self.assertEqual(len(list((self.path.parent / "backups").glob("*.db"))), 1)
        self.assertEqual(legacy_manifest(self.path), before)

    def test_partial_ddl_failure_rolls_back_and_never_replaces_previous_backup(self):
        storage = self.legacy()
        before = legacy_manifest(self.path)

        def fail(connection):
            for statement in GLOBAL_SAVED_SEARCH_DDL[:3]:
                connection.execute(statement)
            raise sqlite3.OperationalError("controlled schema65 failure")

        backups = {}
        with patch("xti.adapters.sqlite.create_global_saved_search_schema", side_effect=fail):
            for attempt in (1, 2):
                with self.assertRaises(StorageError):
                    storage.migrate()
                self.assertEqual(legacy_manifest(self.path), before)
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), 64)
                paths = sorted((self.path.parent / "backups").glob("*.db"))
                self.assertEqual(len(paths), attempt)
                for path, content in backups.items():
                    self.assertEqual(path.read_bytes(), content)
                backups = {path: path.read_bytes() for path in paths}
        restored = self.root / "recovered" / "xti.db"
        SQLiteAssetRepository.restore(next(iter(backups)), restored)
        self.assertEqual(legacy_manifest(restored), before)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(next(iter(backups)), restored)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(legacy_manifest(restored), before)
        # Recovery never modifies the failed source or its pre-migration backup.
        self.assertEqual(legacy_manifest(self.path), before)
        for path, content in backups.items():
            self.assertEqual(path.read_bytes(), content)

    def test_old_reads_and_initialization_require_explicit_migrate_without_writes(self):
        storage = self.legacy()
        before = self.path.read_bytes()
        with patch("socket.socket.connect", side_effect=AssertionError("No network")):
            for operation in (storage.inspect, storage.list, storage.initialize):
                with self.subTest(operation=operation):
                    with self.assertRaisesRegex(StorageError, "migrate"):
                        operation()
                    self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_old_version_number_cannot_hide_new_tables_or_trigger_partial_migration(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(connection)
            connection.execute("PRAGMA user_version=64")
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            SQLiteAssetRepository(self.path).migrate()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_changed_notification_constraints_are_rejected(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE global_saved_search_notifications")
            statement = GLOBAL_SAVED_SEARCH_DDL[4].replace(
                "CHECK (event_type='global_saved_search_changed')", "",
            )
            connection.execute(statement)
            connection.execute(GLOBAL_SAVED_SEARCH_DDL[-1])
        with self.assertRaises(StorageError):
            SQLiteAssetRepository(self.path).inspect()

    def test_fixture_refuses_to_discard_populated_new_feature_evidence(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO global_search_snapshots VALUES (?, ?)", ("a" * 64, "{}"))
            before = connection.execute("SELECT name,sql FROM sqlite_schema ORDER BY name").fetchall()
            with self.assertRaisesRegex(ValueError, "schema65"):
                remove_global_saved_search_schema(connection)
            self.assertEqual(connection.execute("SELECT name,sql FROM sqlite_schema ORDER BY name").fetchall(), before)
            self.assertEqual(connection.execute("SELECT * FROM global_search_snapshots").fetchall(), [("a" * 64, "{}")])

    def test_notification_ownership_counts_and_foreign_keys_are_structural_constraints(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO global_saved_search_notifications VALUES (1,'notice','missing-run','missing-search',"
                    "'global_saved_search_changed','new','2026-11-15T12:00:00+00:00',NULL)"
                )
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM global_saved_search_notifications").fetchone()[0], 0)
        report = SQLiteAssetRepository(self.path).inspect()
        self.assertEqual(report["global_saved_search_count"], 0)
        self.assertEqual(report["global_saved_search_notification_count"], 0)
        self.assertEqual(report["unread_global_saved_search_notification_count"], 0)


if __name__ == "__main__":
    unittest.main()

"""Schema64 adds empty watches without rewriting any pre-existing evidence."""
from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from tests.supplier_watch_legacy_fixture import remove_supplier_watch_schema
from tests import test_cases as fixtures
from tests.test_public_notices import feed
from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.supplier_watch_schema import SUPPLIER_WATCH_DDL
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository


NEW_TABLES = frozenset({
    "supplier_watches", "supplier_watch_events", "supplier_watch_runs", "supplier_watch_notifications",
})


from tests.collection_v68_fixture import legacy_collection_manifest_entry


def manifest(path):
    with closing(sqlite3.connect(path)) as connection:
        result = {table: (
            connection.execute(f"PRAGMA table_info({table})").fetchall(),
            connection.execute(f"SELECT rowid,* FROM {table} ORDER BY rowid").fetchall(),
            connection.execute(
                "SELECT type,name,sql FROM sqlite_schema WHERE tbl_name=? ORDER BY name", (table,),
            ).fetchall(),
        ) for table in sorted(VERSION_TABLES[63])}
        result["sqlite_sequence"] = connection.execute(
            "SELECT name,seq FROM sqlite_sequence ORDER BY name"
        ).fetchall()
        for table in ("collection_session_steps", "collection_step_receipts"):
            if table in result:
                result[table] = legacy_collection_manifest_entry(table, result[table])
        return result


class SupplierWatchMigrationTests(unittest.TestCase):
    setUp = fixtures.CaseTests.setUp
    create_case = fixtures.CaseTests.create_case
    insert_finding = fixtures.CaseTests.insert_finding

    def legacy(self):
        case = self.create_case()
        self.service.add_evidence(case.id, "finding", self.insert_finding(), reason="Korunacak eski kanıt.")
        self.service.add_note(case.id, "Tarihî insan incelemesi korunur.", kind="observation")
        self.supplier_service.add(
            "Legacy supplier", domain="vendor.example", relationship_type="cloud", criticality="high",
            reason="Eski tedarikçi kaydı korunur.",
        )
        notices = SQLitePublicNoticeRepository(self.path)
        response = feed()
        notices.apply(response, started_at=response.fetched_at, finished_at=response.fetched_at)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("UPDATE notifications SET read_at=created_at")
            connection.execute("UPDATE case_evidence SET rowid=rowid+100")
            remove_supplier_watch_schema(connection)
            connection.execute("PRAGMA user_version=63")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 63)
        return SQLiteAssetRepository(self.path)

    def test_explicit_additive_migration_preserves_all_old_rows_rowids_sql_and_sequences(self):
        storage = self.legacy()
        before = manifest(self.path)
        result = storage.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (63, SCHEMA_VERSION))
        self.assertEqual(VERSION_TABLES[64] - VERSION_TABLES[63], NEW_TABLES)
        self.assertEqual(manifest(self.path), before)
        self.assertEqual(manifest(result["backup"]), before)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            for table in NEW_TABLES:
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertFalse(storage.migrate()["changed"])

    def test_partial_migration_rolls_back_and_backups_restore_only_to_new_destination(self):
        storage = self.legacy()
        before = manifest(self.path)
        def fail(connection):
            for statement in SUPPLIER_WATCH_DDL[:2]:
                connection.execute(statement)
            raise sqlite3.OperationalError("controlled schema64 failure")
        with patch("xti.adapters.sqlite.create_supplier_watch_schema", side_effect=fail):
            for _ in range(2):
                with self.assertRaises(StorageError):
                    storage.migrate()
                self.assertEqual(manifest(self.path), before)
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), 63)
        backups = sorted((self.path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 2)
        restored = self.path.with_name("restored.db")
        SQLiteAssetRepository.restore(backups[0], restored)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(backups[0], restored)
        self.assertEqual(manifest(restored), before)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(manifest(restored), before)

    def test_old_database_requires_migrate_without_implicit_writes_or_network(self):
        storage = self.legacy()
        before = self.path.read_bytes()
        with patch("socket.socket.connect", side_effect=AssertionError("No network")):
            with self.assertRaisesRegex(StorageError, "migrate"):
                storage.inspect()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_old_version_number_cannot_hide_current_tables(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA user_version=63")
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            SQLiteAssetRepository(self.path).migrate()
        self.assertEqual(self.path.read_bytes(), before)

    def test_changed_supplier_watch_constraints_are_rejected(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE supplier_watch_notifications")
            connection.execute(SUPPLIER_WATCH_DDL[3].replace("CHECK (event_type='supplier_watch_changed')", ""))
            connection.execute(SUPPLIER_WATCH_DDL[-1])
        with self.assertRaises(StorageError):
            SQLiteAssetRepository(self.path).inspect()

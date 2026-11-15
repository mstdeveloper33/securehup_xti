"""Schema67→68 preserves source and watch evidence with explicit recoverable migration."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.mention_group_schema import MENTION_GROUP_DDL
from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
from xti.adapters.sqlite_mention_groups import SQLiteMentionGroupRepository
from xti.adapters.sqlite_mentions import SQLiteMentionRepository
from xti.domain.mention_groups import MentionGroupDefinition
from xti.domain.mentions import MentionResponse, build_query
from tests.mention_groups_legacy_fixture import remove_mention_group_schema, legacy_search_manifest_entry
from tests.test_mentions_storage import request, hit

T0 = "2026-11-15T12:00:00+00:00"


def manifest(path):
    with closing(sqlite3.connect(Path(path).absolute().as_uri() + "?mode=ro", uri=True)) as connection:
        result = {}
        for table in sorted(VERSION_TABLES[67]):
            name = '"' + table.replace('"', '""') + '"'
            entry = (
                connection.execute(f"PRAGMA table_info({name})").fetchall(),
                connection.execute(f"SELECT rowid,* FROM {name} ORDER BY rowid").fetchall(),
                connection.execute("SELECT type,name,sql FROM sqlite_schema WHERE tbl_name=? ORDER BY name", (table,)).fetchall(),
            )
            result[table] = legacy_search_manifest_entry(entry) if table == "global_saved_searches" else entry
        result["sqlite_sequence"] = connection.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name").fetchall()
        return result


class MentionGroupMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()

    def legacy(self):
        self.storage.add("example.com")
        scope = request()
        self.source = SQLiteMentionRepository(self.path).apply(scope,
            MentionResponse(build_query(scope.target), None, (hit(),), 1), started_at=T0, finished_at=T0)
        watches = SQLiteGlobalSavedSearchRepository(self.path)
        search = watches.upsert(name_key="old scope", display_name="Old scope", query="example.com",
            kinds=("mention",), include_inactive=False, recorded_at=T0).saved_search
        self.search_run = watches.run(search.id, executed_at=T0, offset=0, limit=50).run
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE assets SET rowid=rowid+100")
            remove_mention_group_schema(connection)
            connection.execute("PRAGMA user_version=67")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 67)

    def test_migration_preserves_old_rows_rowids_ddl_and_source_watch_evidence(self):
        self.legacy()
        before = manifest(self.path)
        result = self.storage.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (67, 68))
        self.assertEqual(VERSION_TABLES[68] - VERSION_TABLES[67], {"mention_group_events", "mention_notification_operations"})
        self.assertEqual(manifest(self.path), before)
        self.assertEqual(manifest(result["backup"]), before)
        self.assertEqual(SQLiteMentionRepository(self.path).run_show(self.source.id), self.source)
        self.assertEqual(SQLiteGlobalSavedSearchRepository(self.path).run_details(self.search_run.id, offset=0, limit=50).run,
                         self.search_run)
        self.assertEqual(SQLiteMentionGroupRepository(self.path).list(), ())
        self.assertEqual(self.storage.inspect()["mention_group_event_count"], 0)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertFalse(self.storage.migrate()["changed"])

    def test_interrupted_additive_migration_rolls_back_and_preserves_unique_backups(self):
        self.legacy()
        before = manifest(self.path)
        def fail(connection):
            connection.execute(MENTION_GROUP_DDL[0])
            raise sqlite3.OperationalError("Controlled schema68 interruption")
        previous = {}
        with patch("xti.adapters.sqlite.create_mention_group_schema", side_effect=fail):
            for count in (1, 2):
                with self.assertRaises(StorageError):
                    self.storage.migrate()
                self.assertEqual(manifest(self.path), before)
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), 67)
                backups = list((self.path.parent / "backups").glob("*.db"))
                self.assertEqual(len(backups), count)
                for path, contents in previous.items():
                    self.assertEqual(path.read_bytes(), contents)
                previous = {path: path.read_bytes() for path in backups}
        restored = self.root / "restored" / "xti.db"
        SQLiteAssetRepository.restore(next(iter(previous)), restored)
        self.assertEqual(manifest(restored), before)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(next(iter(previous)), restored)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(manifest(restored), before)
        self.assertEqual(manifest(self.path), before)

    def test_legacy_reads_require_explicit_migration_without_touching_files(self):
        self.legacy()
        before = self.path.read_bytes()
        with patch("socket.socket.connect", side_effect=AssertionError("No network")):
            for operation in (self.storage.initialize, self.storage.inspect,
                              SQLiteMentionGroupRepository(self.path).list,
                              SQLiteMentionRepository(self.path).catalog):
                with self.subTest(operation=operation), self.assertRaisesRegex(StorageError, "migrate"):
                    operation()
                self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_false_legacy_version_cannot_hide_new_tables(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA user_version=67")
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.storage.migrate()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_constraints_and_scope_column_are_checked(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE mention_group_events")
            connection.execute(MENTION_GROUP_DDL[0].replace("CHECK (length(payload_sha256)=64)", ""))
            for statement in MENTION_GROUP_DDL[1:]:
                connection.execute(statement)
        with self.assertRaises(StorageError):
            self.storage.inspect()

    def test_legacy_fixture_never_drops_group_evidence(self):
        SQLiteMentionGroupRepository(self.path).save("Acme izleme", MentionGroupDefinition(str(uuid4())), recorded_at=T0)
        before = self.path.read_bytes()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            with self.assertRaisesRegex(ValueError, "schema68"):
                remove_mention_group_schema(connection)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

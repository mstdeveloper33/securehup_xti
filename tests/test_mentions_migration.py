"""Explicit schema66→67 migration preserves old evidence and recovery snapshots."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.mentions_schema import MENTIONS_DDL
from xti.adapters.mentions_schema_metadata import TABLES as MENTION_TABLES
from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_mentions import SQLiteMentionRepository
from xti.adapters.sqlite_news import SQLiteNewsRepository
from xti.domain.news import NewsFeed
from tests.mentions_legacy_fixture import remove_mentions_schema
from tests.mention_groups_legacy_fixture import legacy_search_manifest_entry
from tests.test_news_storage import article
from tests.test_mentions_storage import request, hit
from xti.domain.mentions import MentionResponse, build_query


from tests.collection_v68_fixture import legacy_collection_manifest_entry


def manifest(path):
    with closing(sqlite3.connect(Path(path).absolute().as_uri() + "?mode=ro", uri=True)) as connection:
        result = {}
        for table in sorted(VERSION_TABLES[66]):
            name = '"' + table.replace('"', '""') + '"'
            result[table] = (
                connection.execute(f"PRAGMA table_info({name})").fetchall(),
                connection.execute(f"SELECT rowid,* FROM {name} ORDER BY rowid").fetchall(),
                connection.execute("SELECT type,name,sql FROM sqlite_schema WHERE tbl_name=? ORDER BY name", (table,)).fetchall(),
            )
            if table == 'global_saved_searches':
                result[table] = legacy_search_manifest_entry(result[table])
        result["sqlite_sequence"] = connection.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name").fetchall()
        for table in ("collection_session_steps", "collection_step_receipts", "case_evidence"):
            if table in result:
                result[table] = legacy_collection_manifest_entry(table, result[table])
        return result


class MentionMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()

    def legacy(self):
        self.storage.add("example.com")
        at = datetime.now(timezone.utc).isoformat()
        self.news = SQLiteNewsRepository(self.path).apply(
            NewsFeed("cisa", at, "a" * 64, (article(),)), started_at=at, finished_at=at)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE assets SET rowid=rowid+100")
            remove_mentions_schema(connection)
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(connection)
            connection.execute("PRAGMA user_version=66")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 66)

    def test_additive_migration_preserves_every_old_row_rowid_ddl_and_news_evidence(self):
        self.legacy()
        before = manifest(self.path)
        migration = self.storage.migrate()
        self.assertEqual((migration["from_version"], migration["to_version"]), (66, SCHEMA_VERSION))
        self.assertEqual(VERSION_TABLES[67] - VERSION_TABLES[66], MENTION_TABLES.keys())
        self.assertEqual(manifest(self.path), before)
        self.assertEqual(manifest(migration["backup"]), before)
        self.assertEqual(SQLiteNewsRepository(self.path).run_show(self.news.run.id), self.news)
        self.assertEqual(SQLiteMentionRepository(self.path).catalog().runs, ())
        self.assertEqual(self.storage.inspect()["mention_run_count"], 0)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        with closing(sqlite3.connect(migration["backup"])) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 66)
        repeated = self.storage.migrate()
        self.assertFalse(repeated["changed"])
        self.assertIsNone(repeated["backup"])

    def test_failed_migration_rolls_back_and_keeps_unique_recovery_copies(self):
        self.legacy()
        before = manifest(self.path)
        previous = {}
        def fail(connection):
            connection.execute(MENTIONS_DDL[0])
            raise sqlite3.OperationalError("Controlled schema67 interruption")
        with patch("xti.adapters.sqlite.create_mentions_schema", side_effect=fail):
            for count in (1, 2):
                with self.assertRaises(StorageError):
                    self.storage.migrate()
                self.assertEqual(manifest(self.path), before)
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), 66)
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

    def test_legacy_reads_require_explicit_migration_without_mutation_or_network(self):
        self.legacy()
        before = self.path.read_bytes()
        for operation in (self.storage.initialize, self.storage.inspect, SQLiteMentionRepository(self.path).catalog):
            with self.subTest(operation=operation), patch("socket.socket.connect", side_effect=AssertionError("No network")):
                with self.assertRaisesRegex(StorageError, "migrate"):
                    operation()
                self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_fake_version_cannot_hide_new_table_or_trigger_backup(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(connection)
            connection.execute("PRAGMA user_version=66")
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.storage.migrate()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_schema_constraints_are_validated_not_only_column_names(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE mentions_runs")
            connection.execute(MENTIONS_DDL[0].replace("CHECK (status IN ('complete','failed'))", ""))
            connection.execute(MENTIONS_DDL[1])
        with self.assertRaises(StorageError):
            self.storage.inspect()

    def test_fixture_refuses_to_discard_company_search_evidence(self):
        scope = request()
        response = MentionResponse(build_query(scope.target), None, (hit(),), 1)
        at = datetime.now(timezone.utc).isoformat()
        SQLiteMentionRepository(self.path).apply(scope, response, started_at=at, finished_at=at)
        before = self.path.read_bytes()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            with self.assertRaisesRegex(ValueError, "schema67"):
                remove_mentions_schema(connection)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

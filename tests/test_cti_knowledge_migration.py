"""Schema 34 to 35 adds empty CTI knowledge tables with recovery safety."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.schema import SCHEMA_VERSION, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository


_TABLES = (
    "cti_saved_search_notes", "cti_saved_search_tag_events", "cti_saved_search_tags",
    "cti_saved_search_notifications",
    "cti_saved_search_run_items", "cti_saved_search_runs",
    "cti_saved_search_events", "cti_saved_searches",
    "cti_relationship_assertion_events", "cti_relationship_assertions",
    "cti_relationships", "cti_entity_assertion_events", "cti_entity_assertions",
    "cti_entities",
)


class CtiKnowledgeMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def version_thirty_four(self):
        path = self.root / "legacy" / "xti.db"
        storage = SQLiteAssetRepository(path)
        storage.initialize()
        storage.add("example.com")
        with closing(sqlite3.connect(path)) as connection, connection:
            for table in _TABLES:
                connection.execute(f"DROP TABLE {table}")
            for table in ("webhook_delivery_attempts", "webhook_deliveries", "webhook_destination_events", "webhook_destinations"):
                connection.execute(f"DROP TABLE IF EXISTS {table}")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_cycle_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_cycles")
            connection.execute("DROP TABLE IF EXISTS ransomware_identity_review_events")
            connection.execute("DROP TABLE IF EXISTS ransomware_monitor_sessions")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_notifications")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomware_watch_events")
            connection.execute("DROP TABLE IF EXISTS ransomware_watches")
            connection.execute("DROP TABLE IF EXISTS ransomware_claim_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomware_claim_runs")
            connection.execute("DROP TABLE IF EXISTS ransomlook_claim_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomlook_claim_runs")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_runs")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watch_events")
            connection.execute("DROP TABLE IF EXISTS ransomlook_watches")
            connection.execute("DROP TABLE IF EXISTS ransomware_source_review_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_review_notifications")
            connection.execute("DROP TABLE IF EXISTS brand_username_review_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_run_items")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_runs")
            connection.execute("DROP TABLE IF EXISTS brand_username_watch_events")
            connection.execute("DROP TABLE IF EXISTS brand_username_watches")
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
            connection.execute("PRAGMA user_version=34")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 34)
        return path

    @staticmethod
    def version(path):
        with closing(sqlite3.connect(path)) as connection:
            return connection.execute("PRAGMA user_version").fetchone()[0]

    def test_v34_migrates_with_backup_and_empty_knowledge_graph(self):
        path = self.version_thirty_four()
        result = SQLiteAssetRepository(path).migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (34, SCHEMA_VERSION))
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(
                tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in reversed(_TABLES)),
                (0,) * len(_TABLES),
            )
            self.assertEqual(connection.execute("SELECT value FROM assets").fetchall(),
                             [("example.com",)])
        backup = Path(result["backup"])
        self.assertEqual(self.version(backup), 34)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 34)

    def test_failed_creation_rolls_back_and_keeps_valid_v34_backup(self):
        path = self.version_thirty_four()

        def incomplete(connection):
            connection.execute("CREATE TABLE cti_entities (id TEXT PRIMARY KEY NOT NULL)")
            raise sqlite3.OperationalError("controlled failure")

        with patch("xti.adapters.sqlite.create_cti_knowledge_schema", side_effect=incomplete):
            with self.assertRaises(StorageError):
                SQLiteAssetRepository(path).migrate()
        self.assertEqual(self.version(path), 34)
        with closing(sqlite3.connect(path)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 34)
        backups = list((path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.version(backups[0]), 34)

    def test_v34_read_never_migrates_or_creates_knowledge_tables(self):
        path = self.version_thirty_four()
        before = path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            SQLiteCtiKnowledgeRepository(path).list_entities(
                entity_type=None, active_only=True, limit=10,
            )
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.version(path), 34)


if __name__ == "__main__":
    unittest.main()

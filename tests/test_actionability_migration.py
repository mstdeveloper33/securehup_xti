"""Schema94 to schema95 migration and recovery acceptance for P06."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.actionability_schema import TABLES as ACTION_TABLES
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_COLUMNS, CASE_EVIDENCE_INDEX_DDL
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.telemetry_schema import CASE_EVIDENCE_DDL as CURRENT_CASE_DDL


class ActionabilityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.repository = SQLiteAssetRepository(self.path)
        self.repository.initialize()
        self.repository.add("example.com")
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            current_case = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name='case_evidence'"
            ).fetchone()[0]
            self.assertEqual(" ".join(current_case.split()), " ".join(CURRENT_CASE_DDL.split()))
            from tests.case_evidence_v94_fixture import case_evidence_layout_v94
            case_evidence_layout_v94(connection)
            connection.execute("PRAGMA user_version=94")
            connection.commit()

    def test_upgrade_publishes_recovery_snapshot_and_preserves_old_data(self):
        result = self.repository.migrate()
        self.assertEqual((result["from_version"], result["to_version"], result["changed"]),
                         (94, SCHEMA_VERSION, True))
        self.assertEqual([item.value for item in self.repository.list()], ["example.com"])
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        self.assertTrue(set(ACTION_TABLES) <= tables)
        backup = Path(result["backup"])
        self.assertTrue(backup.is_file())
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 94)
            self.assertEqual(connection.execute("SELECT value FROM assets").fetchone()[0], "example.com")
            old_tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        self.assertFalse(set(ACTION_TABLES) & old_tables)

        restored = Path(self.temp.name) / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        second = SQLiteAssetRepository(restored).migrate()
        self.assertEqual((second["from_version"], second["to_version"]), (94, SCHEMA_VERSION))
        self.assertEqual([item.value for item in SQLiteAssetRepository(restored).list()], ["example.com"])


if __name__ == "__main__":
    unittest.main()

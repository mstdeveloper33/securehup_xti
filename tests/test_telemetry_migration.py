"""Schema97 to schema98 telemetry migration and recovery acceptance."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from tests.case_evidence_v97_fixture import telemetry_layout_v97
from xti.adapters.schema import SCHEMA_VERSION
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.telemetry_schema import CASE_EVIDENCE_DDL, TABLES


class TelemetryMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "data" / "xti.db"
        self.repository = SQLiteAssetRepository(self.path); self.repository.initialize()
        now = "2026-11-23T08:00:00+00:00"
        case_id, evidence_id, link_id = str(uuid4()), str(uuid4()), str(uuid4())
        snapshot = json.dumps({"kind": "legacy-fixture"}, sort_keys=True, separators=(",", ":"))
        checksum = hashlib.sha256(snapshot.encode("ascii")).hexdigest()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                "INSERT INTO cases (id,title,summary,status,priority,resolution,created_at,updated_at,closed_at) "
                "VALUES (?,?,?,'open','medium',NULL,?,?,NULL)",
                (case_id, "Legacy case", "Existing schema97 evidence", now, now),
            )
            connection.execute(
                "INSERT INTO case_evidence (id,case_id,evidence_type,evidence_id,display_value,"
                "source_reference,snapshot_json,snapshot_sha256,active,added_reason,added_at,updated_at,"
                "removed_reason,removed_at) VALUES (?,?,?,?,?,?,?,?,1,?,?,?,NULL,NULL)",
                (link_id, case_id, "finding", evidence_id, "Legacy finding", "findings show",
                 snapshot, checksum, "Existing case evidence", now, now),
            )
            before = connection.execute(
                "SELECT rowid,* FROM case_evidence WHERE id=?", (link_id,),
            ).fetchone()
            connection.execute("PRAGMA foreign_keys=OFF")
            telemetry_layout_v97(connection)
            connection.execute("PRAGMA user_version=97")
            connection.commit()
        self.before, self.link_id = before, link_id

    def test_upgrade_preserves_case_rowid_and_publishes_recoverable_backup(self):
        result = self.repository.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (97, SCHEMA_VERSION))
        with closing(sqlite3.connect(self.path)) as connection:
            after = connection.execute(
                "SELECT rowid,* FROM case_evidence WHERE id=?", (self.link_id,),
            ).fetchone()
            self.assertEqual(after, self.before)
            current = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE type='table' AND name='case_evidence'"
            ).fetchone()[0]
            self.assertEqual(" ".join(current.split()), " ".join(CASE_EVIDENCE_DDL.split()))
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )}
            self.assertTrue(set(TABLES) <= tables)
            self.assertFalse(any(connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
                                 for table in TABLES))
        backup = Path(result["backup"])
        self.assertTrue(backup.is_file())
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 97)
            self.assertFalse(set(TABLES) & {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )})
        restored = self.path.parent.parent / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        second = SQLiteAssetRepository(restored).migrate()
        self.assertEqual((second["from_version"], second["to_version"]), (97, SCHEMA_VERSION))


if __name__ == "__main__":
    unittest.main()

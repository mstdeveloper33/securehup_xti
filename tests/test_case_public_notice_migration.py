"""Schema63 retains historical case evidence while adding two explicit types."""

from contextlib import closing
from datetime import timedelta
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.case_public_notice_schema import (
    CASE_EVIDENCE_DDL, CASE_EVIDENCE_INDEX_DDL, CASE_EVIDENCE_V62_DDL,
    migrate_case_public_notice_schema,
)
from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, SchemaError, validate_schema
from xti.adapters.supplier_watch_schema import SUPPLIER_WATCH_DDL
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from tests import test_cases as fixtures
from tests.case_evidence_v62_fixture import case_evidence_layout_v62
from tests.collection_v60_fixture import collection_layout_v60
from tests.public_notice_watch_legacy_fixture import remove_public_notice_watch_schema


def columns(path, version):
    with closing(sqlite3.connect(path)) as connection:
        return {table: tuple(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))
                for table in sorted(VERSION_TABLES[version])}


def rows(path, layout):
    with closing(sqlite3.connect(path)) as connection:
        return {table: connection.execute(
            f"SELECT rowid, {', '.join(names)} FROM {table} ORDER BY rowid"
        ).fetchall() for table, names in layout.items()}


def declarations(path):
    with closing(sqlite3.connect(path)) as connection:
        return {
            (kind, name): declaration for kind, name, declaration in connection.execute(
                "SELECT type,name,sql FROM sqlite_schema ORDER BY type,name"
            )
        }


class CasePublicNoticeMigrationTests(unittest.TestCase):
    setUp = fixtures.CaseTests.setUp
    create_case = fixtures.CaseTests.create_case
    insert_finding = fixtures.CaseTests.insert_finding

    def legacy(self, version=62):
        case = self.create_case()
        finding_id = self.insert_finding()
        evidence = self.service.add_evidence(
            case.id, "finding", finding_id, reason="Korunacak eski bulgu kanıtı.",
        ).evidence
        self.service.remove_evidence(case.id, evidence.id, reason="Tarihî bağ kaldırıldı.")
        self.service.add_evidence(case.id, "finding", finding_id, reason="Tarihî bağ yeniden etkin.")
        supplier = self.supplier_service.add(
            "Legacy vendor", domain="vendor.example", relationship_type="cloud", criticality="high",
            reason="Korunacak tedarikçi ilişkisi.",
        ).supplier
        supplier_link = self.service.add_evidence(
            case.id, "supplier", supplier.id, reason="Korunacak ayrı türde kart.",
        ).evidence
        self.service.remove_evidence(case.id, supplier_link.id, reason="Eski pasif kanıt korunur.")
        self.service.add_note(case.id, "Korunacak karar kaydı.", kind="decision")
        task = self.service.add_task(
            case.id, "Kanıtları incele", due_at=(fixtures.NOW + timedelta(days=1)).isoformat(),
            reason="Korunacak görev kaydı.",
        ).task
        self.service.update_task(case.id, task.id, status="done", reason="Görev tamamlandı.")
        self.service.set_status(case.id, "closed", reason="İnceleme tamamlandı.", resolution="Eski kanıtlar korunarak kapatıldı.")
        # Non-contiguous old rowids make accidental renumbering observable.
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE case_evidence SET rowid=rowid+100")
        before = self.service.show(case.id)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            case_evidence_layout_v62(connection)
            if version < 62:
                remove_public_notice_watch_schema(connection)
            if 56 <= version < 61:
                collection_layout_v60(connection)
            if version < 56:
                for table in ("collection_step_receipts", "collection_session_steps", "collection_sessions"):
                    connection.execute(f"DROP TABLE {table}")
            if version < 60:
                connection.execute("DROP TABLE public_notice_changes")
                connection.execute("DROP TABLE public_notice_runs")
            if version < 59:
                connection.execute("DROP TABLE ransomlook_watch_notifications")
            if version < 58:
                for table in ("attack_catalog_changes", "attack_catalog_phases", "attack_catalog_relationships", "attack_catalog_entities", "attack_catalog_runs"):
                    connection.execute(f"DROP TABLE {table}")
            if version < 57:
                for table in ("organization_link_events", "organization_links", "organization_events", "organizations"):
                    connection.execute(f"DROP TABLE {table}")
            if version < 55:
                connection.execute("DROP TABLE collection_profile_events")
                connection.execute("DROP TABLE collection_profiles")
            connection.execute(f"PRAGMA user_version={version}")
            self.assertEqual(validate_schema(connection, allow_legacy=True), version)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        return before

    def test_all54_through62_preserve_rows_hashes_ids_and_case_timeline(self):
        for version in range(54, 63):
            with self.subTest(version=version):
                self.setUp()
                case = self.legacy(version)
                layout = columns(self.path, version)
                before = rows(self.path, layout)
                with closing(sqlite3.connect(self.path)) as connection:
                    sequence_before = connection.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name").fetchall()
                result = self.storage.migrate()
                self.assertEqual((result["from_version"], result["to_version"]), (version, SCHEMA_VERSION))
                self.assertEqual(rows(self.path, layout), before)
                self.assertEqual(rows(result["backup"], layout), before)
                self.assertEqual(self.service.show(case.case.id), case)
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
                    self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                    self.assertEqual(connection.execute("SELECT name,seq FROM sqlite_sequence ORDER BY name").fetchall(), sequence_before)
                    self.assertFalse(connection.execute("SELECT name FROM sqlite_temp_schema WHERE name='xti_case_evidence_v62_copy'").fetchall())
                with closing(sqlite3.connect(result["backup"])) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), version)
                self.assertFalse(self.storage.migrate()["changed"])

    def test_v62_only_case_evidence_declaration_changes_and_no_new_rows_are_invented(self):
        self.legacy()
        before = declarations(self.path)
        self.storage.migrate()
        after = declarations(self.path)
        self.assertTrue(before.keys() <= after.keys())
        changed = {key for key in before if before[key] != after.get(key)}
        self.assertEqual(changed, {("table", "case_evidence")})
        added = {key: value for key, value in after.items() if key not in before}
        # Include SQLite's constraint auto-indexes as well as named declarations.
        with closing(sqlite3.connect(":memory:")) as expected_connection:
            for statement in SUPPLIER_WATCH_DDL:
                expected_connection.execute(statement)
            expected_added = {
                (kind, name): declaration for kind, name, declaration in expected_connection.execute(
                    "SELECT type,name,sql FROM sqlite_schema ORDER BY type,name"
                ) if (kind, name) not in before
            }
        self.assertEqual(added, expected_added)
        self.assertEqual(before[("table", "case_evidence")], CASE_EVIDENCE_V62_DDL)
        self.assertEqual(after[("table", "case_evidence")], CASE_EVIDENCE_DDL)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM case_evidence WHERE evidence_type IN ('public_notice','public_notice_watch')"
            ).fetchone()[0], 0)

    def test_mid_copy_failure_rolls_back_rowids_history_schema_and_keeps_unique_recovery_backups(self):
        case = self.legacy()
        layout = columns(self.path, 62)
        before = rows(self.path, layout)
        old_ddl = declarations(self.path)
        class FailAtCopy:
            def __init__(self, connection): self.connection = connection
            @property
            def in_transaction(self): return self.connection.in_transaction
            def execute(self, sql, *arguments):
                if sql.startswith("INSERT INTO case_evidence"):
                    raise sqlite3.OperationalError("controlled case evidence copy failure")
                return self.connection.execute(sql, *arguments)
        def fail(connection):
            migrate_case_public_notice_schema(FailAtCopy(connection))
        with patch("xti.adapters.sqlite.migrate_case_public_notice_schema", side_effect=fail):
            for _ in range(2):
                with self.assertRaises(StorageError):
                    self.storage.migrate()
                self.assertEqual(rows(self.path, layout), before)
                self.assertEqual(declarations(self.path), old_ddl)
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), 62)
        backups = sorted((self.data / "backups").glob("*.db"))
        self.assertEqual(len(backups), 2)
        for backup in backups:
            self.assertEqual(rows(backup, layout), before)
        restored = Path(self.temp.name) / "restored.db"
        SQLiteAssetRepository.restore(backups[0], restored)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(backups[0], restored)
        self.assertEqual(rows(restored, layout), before)
        self.assertEqual(declarations(restored), old_ddl)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(rows(restored, layout), before)
        self.storage.migrate()
        self.assertEqual(self.service.show(case.case.id), case)

    def test_legacy_reads_never_migrate_and_fake_legacy_version_is_rejected(self):
        self.legacy()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            self.storage.inspect()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.data / "backups").exists())
        self.storage.migrate()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA user_version=62")
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.storage.migrate()
        self.assertEqual(self.path.read_bytes(), before)

    def test_sql_accepts_exact_new_types_and_preserves_unique_fk_and_activity_constraints(self):
        self.legacy()
        self.storage.migrate()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            evidence_id = connection.execute("SELECT id FROM case_evidence ORDER BY rowid LIMIT 1").fetchone()[0]
            for evidence_type in ("public_notice", "public_notice_watch"):
                connection.execute("UPDATE case_evidence SET evidence_type=? WHERE id=?", (evidence_type, evidence_id))
            for column, invalid in (("evidence_type", "arbitrary"), ("case_id", "missing"), ("active", 0)):
                with self.subTest(column=column), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(f"UPDATE case_evidence SET {column}=? WHERE id=?", (invalid, evidence_id))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO case_evidence SELECT * FROM case_evidence WHERE id=?", (evidence_id,))
            connection.execute("DROP TABLE case_evidence")
            connection.execute(CASE_EVIDENCE_DDL.replace("ON DELETE RESTRICT", "ON DELETE CASCADE"))
            connection.execute(CASE_EVIDENCE_INDEX_DDL)
            with self.assertRaises(SchemaError):
                validate_schema(connection)

    def test_rebuild_requires_existing_transaction_before_any_ddl(self):
        with closing(sqlite3.connect(self.path)) as connection:
            before = declarations(self.path)
            with self.assertRaises(sqlite3.OperationalError):
                migrate_case_public_notice_schema(connection)
            self.assertEqual(declarations(self.path), before)

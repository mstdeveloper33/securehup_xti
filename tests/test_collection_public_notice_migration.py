"""Schema61 preserves exact historical sessions, receipts and recovery behavior."""

from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from tests.case_evidence_v62_fixture import case_evidence_layout_v62
from tests.public_notice_watch_legacy_fixture import remove_public_notice_watch_schema

from xti.adapters.collection_public_notice_schema import (
    COLLECTION_HISTORY_V60_DDL, COLLECTION_RECEIPT_V60_COLUMNS,
    migrate_collection_public_notice_schema,
)
from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from tests.collection_v60_fixture import collection_layout_v60
from tests import test_collection_history_storage as fixtures
from tests.test_collection_history_storage import NOW, LATER
from tests.test_public_notices import feed


def snapshot(path: Path, version: int):
    """Select legacy columns explicitly; the new nullable FK is not an old value."""
    with closing(sqlite3.connect(path)) as connection:
        result = {}
        for table in sorted(VERSION_TABLES[version]):
            columns = ", ".join(COLLECTION_RECEIPT_V60_COLUMNS) if table == "collection_step_receipts" else "*"
            result[table] = connection.execute(f"SELECT rowid, {columns} FROM {table} ORDER BY rowid").fetchall()
        return result


class CollectionPublicNoticeMigrationTests(unittest.TestCase):
    setUp = fixtures.CollectionHistoryStorageTests.setUp
    begin = fixtures.CollectionHistoryStorageTests.begin
    receipt = fixtures.CollectionHistoryStorageTests.receipt
    ransomware_plan = fixtures.CollectionHistoryStorageTests.ransomware_plan

    def populate(self):
        plan = self.ransomware_plan()
        profiles = SQLiteCollectionProfileRepository(self.path)
        profile = profiles.save("Retained daily plan", plan.definition, recorded_at=NOW).profile
        plan = replace(plan, origin=self.repo.profile_origin(profile))
        parent = self.begin(plan)
        self.receipt(parent, "ioc-feodo")
        refresh = self.receipt(parent, "ransomware-refresh:threatcluster")
        self.receipt(parent, plan.units[2].step_key, source_run_id=refresh.result_id)
        self.repo.finish_session(parent.session.id, analysis_status="pending", finished_at=NOW, stop_reason="interrupted")
        child = self.repo.begin(plan, started_at=LATER, parent_id=parent.session.id)
        self.repo.finish_session(child.session.id, analysis_status="pending", finished_at=LATER, stop_reason="interrupted")
        return tuple(self.repo.get(identifier) for identifier in (parent.session.id, child.session.id))

    def legacy(self, version=60):
        before = self.populate()
        if version == 60:
            value = feed()
            SQLitePublicNoticeRepository(self.path).apply(value, started_at=value.fetched_at, finished_at=value.fetched_at)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            case_evidence_layout_v62(connection)
            remove_public_notice_watch_schema(connection)
            collection_layout_v60(connection)
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
            connection.execute(f"PRAGMA user_version={version}")
            self.assertEqual(validate_schema(connection, allow_legacy=True), version)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        return before

    def test_all56_through60_exact_layouts_upgrade_without_rewriting_history(self):
        # Separate existing databases for all source versions preserve nonempty
        # dependent steps, failed/retained sessions and eight-kind legacy receipts.
        base_path, base_storage, base_repo = self.path, self.storage, self.repo
        for version in (56, 57, 58, 59, 60):
            with self.subTest(version=version):
                self.path = base_path.with_name(f"v{version}.db")
                self.storage = SQLiteAssetRepository(self.path)
                self.storage.initialize()
                self.asset, _ = self.storage.add("example.com")
                self.repo = SQLiteCollectionHistoryRepository(self.path)
                typed_before = self.legacy(version)
                old_rows = snapshot(self.path, version)
                result = self.storage.migrate()
                self.assertEqual((result["from_version"], result["to_version"]), (version, SCHEMA_VERSION))
                self.assertEqual(snapshot(self.path, version), old_rows)
                self.assertEqual(snapshot(Path(result["backup"]), version), old_rows)
                self.assertEqual(tuple(self.repo.get(item.session.id) for item in typed_before), typed_before)
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
                    self.assertEqual(connection.execute("SELECT public_notice_run_id FROM collection_step_receipts").fetchall(), [(None,)] * 3)
                    self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                    self.assertFalse(connection.execute("SELECT name FROM sqlite_temp_schema WHERE name LIKE 'xti_collection_%'").fetchall())
                with closing(sqlite3.connect(result["backup"])) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), version)
                self.assertFalse(self.storage.migrate()["changed"])
        self.path, self.storage, self.repo = base_path, base_storage, base_repo

    def test_legacy_read_is_unchanged_and_requires_explicit_migration(self):
        typed = self.legacy()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            self.repo.get(typed[0].session.id)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_mid_copy_failure_rolls_back_links_rows_and_schema_and_retains_unique_backups(self):
        self.legacy()
        before = snapshot(self.path, 60)
        class FailOnReceiptCopy:
            def __init__(self, connection): self.connection = connection
            @property
            def in_transaction(self): return self.connection.in_transaction
            def execute(self, sql, *args):
                if sql.startswith("INSERT INTO collection_step_receipts"):
                    raise sqlite3.OperationalError("controlled receipt copy failure")
                return self.connection.execute(sql, *args)
        def fail(connection):
            migrate_collection_public_notice_schema(FailOnReceiptCopy(connection))
        with patch("xti.adapters.sqlite.migrate_collection_public_notice_schema", side_effect=fail):
            for _ in range(2):
                with self.assertRaises(StorageError): self.storage.migrate()
                self.assertEqual(snapshot(self.path, 60), before)
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), 60)
                    self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        backups = list((self.path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 2)
        self.assertEqual(snapshot(backups[0], 60), before)
        restored = self.path.parent / "restored.db"
        SQLiteAssetRepository.restore(backups[0], restored)
        with self.assertRaises(StorageError): SQLiteAssetRepository.restore(backups[0], restored)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(snapshot(restored, 60), before)

    def test_legacy_validator_rejects_new_layout_under_old_version_number(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA user_version=60")
        before = self.path.read_bytes()
        with self.assertRaises(StorageError): self.storage.migrate()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_current_constraints_accept_59th_public_step_and_single_unique_source_receipt(self):
        details = self.begin()
        self.receipt(details, "ioc-feodo")
        run = SQLitePublicNoticeRepository(self.path).record_failure(started_at=NOW, finished_at=NOW, error="Controlled source failure.")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            values = (str(uuid4()), details.session.id, 59, "notices-hibp", "public_notice", "hibp", "a" * 64, "pending")
            connection.execute("INSERT INTO collection_session_steps (id,session_id,ordinal,step_key,kind,source,target_sha256,status) VALUES (?,?,?,?,?,?,?,?)", values)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK"):
                connection.execute("UPDATE collection_session_steps SET ordinal=60 WHERE id=?", (values[0],))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK"):
                connection.execute("UPDATE collection_step_receipts SET public_notice_run_id=?", (run.id,))
            receipt_sql = "INSERT INTO collection_step_receipts (step_id,recorded_at,result_status,summary_json,summary_sha256,public_notice_run_id) VALUES (?,?,?,?,?,?)"
            receipt = (values[0], NOW, "failed", "{}", "b"*64, run.id)
            connection.execute(receipt_sql, receipt)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "FOREIGN KEY"):
                connection.execute("DELETE FROM public_notice_runs WHERE id=?", (run.id,))
            second = (str(uuid4()), details.session.id, 58, "other-fixture", "public_notice", "hibp", "c" * 64, "pending")
            connection.execute("INSERT INTO collection_session_steps (id,session_id,ordinal,step_key,kind,source,target_sha256,status) VALUES (?,?,?,?,?,?,?,?)", second)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE"):
                connection.execute(receipt_sql, (second[0], *receipt[1:]))
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_legacy_constraints_do_not_accept_new_task_kind_or_new_ordinal(self):
        details = self.begin()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            case_evidence_layout_v62(connection)
            remove_public_notice_watch_schema(connection)
            collection_layout_v60(connection)
            for update in ("kind='public_notice'", "source='hibp'", "ordinal=59"):
                with self.assertRaisesRegex(sqlite3.IntegrityError, "CHECK"):
                    connection.execute(f"UPDATE collection_session_steps SET {update}")
            declaration = connection.execute("SELECT sql FROM sqlite_schema WHERE name='collection_session_steps'").fetchone()[0]
            self.assertEqual(" ".join(declaration.split()), " ".join(COLLECTION_HISTORY_V60_DDL[1].split()))

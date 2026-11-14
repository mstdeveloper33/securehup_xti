"""Explicit additive schema60 migration and recoverable rollback from schema59."""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from xti.adapters.public_notice_schema import PUBLIC_NOTICE_DDL
from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.application.public_notices import PublicNoticeService


def rows(path):
    with closing(sqlite3.connect(path)) as connection:
        return {table: connection.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                for table in sorted(VERSION_TABLES[59])}


class PublicNoticeMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.storage.add("example.com")
        SQLiteOrganizationRepository(self.path).add(
            name_key="example", display_name="Example", reason="Explicit local organization.",
            recorded_at="2026-11-14T15:00:00+00:00",
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE public_notice_changes")
            connection.execute("DROP TABLE public_notice_runs")
            connection.execute("PRAGMA user_version=59")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 59)

    def test_migration_preserves_all59_rows_and_backup_without_invented_source_evidence(self):
        before = rows(self.path)
        result = self.storage.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (59, SCHEMA_VERSION))
        self.assertEqual(rows(self.path), before)
        self.assertEqual(rows(result["backup"]), before)
        status = SQLitePublicNoticeRepository(self.path).status()
        self.assertEqual(status.total_run_count, 0)
        self.assertIsNone(status.latest_complete_run)
        self.assertFalse(self.storage.migrate()["changed"])
        with closing(sqlite3.connect(result["backup"])) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 59)

    def test_legacy_reads_and_refresh_fail_before_network_or_implicit_migration(self):
        source = Mock()
        service = PublicNoticeService(SQLitePublicNoticeRepository(self.path), source)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "migrate"):
            service.refresh()
        with self.assertRaisesRegex(StorageError, "migrate"):
            service.status()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root / "backups").exists())
        source.fetch.assert_not_called()

    def test_partial_migration_rolls_back_and_recovery_never_overwrites_existing_file(self):
        before = rows(self.path)
        def fail(connection):
            connection.execute(PUBLIC_NOTICE_DDL[0])
            raise sqlite3.OperationalError("controlled migration failure")
        with patch("xti.adapters.sqlite.create_public_notice_schema", side_effect=fail):
            with self.assertRaises(StorageError): self.storage.migrate()
        self.assertEqual(rows(self.path), before)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 59)
        backups = list((self.root / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        restored = self.root / "restored.db"
        SQLiteAssetRepository.restore(backups[0], restored)
        self.assertEqual(rows(restored), before)
        with self.assertRaises(StorageError): SQLiteAssetRepository.restore(backups[0], restored)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(rows(restored), before)

    def test_current_schema_rejects_changed_catalog_constraints(self):
        self.storage.migrate()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE public_notice_changes")
            connection.execute(PUBLIC_NOTICE_DDL[1].replace("ON DELETE RESTRICT", "ON DELETE CASCADE"))
            connection.execute(PUBLIC_NOTICE_DDL[2])
            connection.execute(PUBLIC_NOTICE_DDL[3])
        before = self.path.read_bytes()
        source = Mock()
        with self.assertRaises(StorageError):
            PublicNoticeService(SQLitePublicNoticeRepository(self.path), source).refresh()
        self.assertEqual(self.path.read_bytes(), before)
        source.fetch.assert_not_called()

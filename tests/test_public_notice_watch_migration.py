"""Schema62 is additive, explicit, reversible, and preserves complete v61 evidence."""

from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.public_notice_watch_schema import PUBLIC_NOTICE_WATCH_DDL
from xti.adapters.case_public_notice_schema import CASE_EVIDENCE_DDL, CASE_EVIDENCE_V62_DDL
from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, SchemaError, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.sqlite_status import SQLiteStatusRepository
from xti.domain.collection_history import CollectionFrozenPlan, CollectionFrozenUnit
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.findings import DomainInput, ImportDocument, MatchCandidate
from xti.domain.organizations import normalize_organization_target
from xti.domain.public_notices import HIBP_CONTRACT_VERSION
from tests import test_collection_public_notice_migration as collection_fixtures
from tests.case_evidence_v62_fixture import case_evidence_layout_v62
from tests.public_notice_watch_legacy_fixture import remove_public_notice_watch_schema
from tests.test_collection_history_storage import NOW, LATER
from tests.test_public_notices import feed


NEW_TABLES = (
    "public_notice_watches", "public_notice_watch_events",
    "public_notice_watch_runs", "public_notice_watch_notifications",
)


from tests.collection_v68_fixture import legacy_collection_manifest_entry


def legacy_snapshot(path):
    """All old SQL, columns, rowids, values, indexes, and sequence counters."""
    with closing(sqlite3.connect(path)) as connection:
        def declarations(table):
            # Later schema63 intentionally widens only this existing CHECK.
            # Keep this schema62 test focused on every other legacy declaration.
            return [
                (kind, name, CASE_EVIDENCE_V62_DDL if sql == CASE_EVIDENCE_DDL else sql)
                for kind, name, sql in connection.execute(
                    "SELECT type, name, sql FROM sqlite_schema WHERE tbl_name=? ORDER BY name", (table,),
                )
            ]
        result = {
            table: (
                connection.execute(f"PRAGMA table_info({table})").fetchall(),
                connection.execute(f"SELECT rowid, * FROM {table} ORDER BY rowid").fetchall(),
                declarations(table),
            ) for table in sorted(VERSION_TABLES[61])
        }
        result["sqlite_sequence"] = connection.execute(
            "SELECT name, seq FROM sqlite_sequence WHERE name NOT IN (?, ?) ORDER BY name",
            ("public_notice_watch_events", "public_notice_watch_runs"),
        ).fetchall()
        for table in ("collection_session_steps", "collection_step_receipts"):
            if table in result:
                result[table] = legacy_collection_manifest_entry(table, result[table])
        return result


class PublicNoticeWatchMigrationTests(unittest.TestCase):
    setUp = collection_fixtures.CollectionPublicNoticeMigrationTests.setUp
    begin = collection_fixtures.CollectionPublicNoticeMigrationTests.begin
    receipt = collection_fixtures.CollectionPublicNoticeMigrationTests.receipt
    ransomware_plan = collection_fixtures.CollectionPublicNoticeMigrationTests.ransomware_plan
    populate = collection_fixtures.CollectionPublicNoticeMigrationTests.populate

    def legacy(self):
        old_sessions = self.populate()
        organizations = SQLiteOrganizationRepository(self.path)
        organization = organizations.add(
            name_key="fixture", display_name="Fixture", reason="Açık test kuruluşu.", recorded_at=NOW,
        ).organization
        organizations.link(
            organization.id, normalize_organization_target("domain", "example.com"),
            reason="Açık test domain bağlantısı.", recorded_at=NOW,
        )
        definition = CollectionProfileDefinition("example.com", task_ids=("notices-hibp",))
        profile = SQLiteCollectionProfileRepository(self.path).save(
            "HIBP legacy profile", definition, recorded_at=NOW,
        ).profile
        plan = CollectionFrozenPlan(definition, (
            CollectionFrozenUnit("notices-hibp", "public_notice", "hibp", "example.com", None, HIBP_CONTRACT_VERSION),
        ), origin=self.repo.profile_origin(profile))
        session = self.repo.begin(plan, started_at=NOW)
        operation = self.repo.start_step(session.session.id, session.steps[0].id, started_at=NOW)
        notices = SQLitePublicNoticeRepository(self.path)
        response = feed()
        source_run = notices.apply(
            response, started_at=NOW, finished_at=response.fetched_at, operation=operation,
        ).run
        self.repo.finish_session(
            session.session.id, analysis_status="pending", finished_at=response.fetched_at, stop_reason="interrupted",
        )
        notices.record_failure(started_at=response.fetched_at, finished_at=response.fetched_at, error="Korunan kaynak hatası.")
        SQLiteFindingRepository(self.path).save_import(
            ImportDocument("fixture:legacy", "legacy:fixture", (DomainInput("example-support.net", "example-support.net", 1, None),)),
            (MatchCandidate(self.asset.id, self.asset.value, "example-support.net", "rules-v1", ("Test eşleşmesi",)),),
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE notifications SET read_at=?", (LATER,))
            connection.execute("PRAGMA foreign_keys=ON")
            case_evidence_layout_v62(connection)
            remove_public_notice_watch_schema(connection)
            connection.execute("PRAGMA user_version=61")
            self.assertEqual(validate_schema(connection, allow_legacy=True), 61)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        return old_sessions, organization, source_run, session.session.id

    def test_v61_all_existing_rows_ids_hashes_links_read_state_and_ddl_survive(self):
        old_sessions, organization, source_run, session_id = self.legacy()
        before = legacy_snapshot(self.path)
        result = self.storage.migrate()
        self.assertEqual((result["from_version"], result["to_version"]), (61, SCHEMA_VERSION))
        self.assertEqual(legacy_snapshot(self.path), before)
        self.assertEqual(legacy_snapshot(result["backup"]), before)
        self.assertEqual(VERSION_TABLES[62] - VERSION_TABLES[61], frozenset(NEW_TABLES))
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            for table in NEW_TABLES:
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual(tuple(self.repo.get(run.session.id) for run in old_sessions), old_sessions)
        self.assertEqual(self.repo.get(session_id).receipts[0].result_id, source_run.id)
        self.assertEqual(SQLiteOrganizationRepository(self.path).show(organization.id).organization, organization)
        self.assertEqual(SQLitePublicNoticeRepository(self.path).status().latest_complete_run.id, source_run.id)
        self.assertFalse(self.storage.migrate()["changed"])
        with closing(sqlite3.connect(result["backup"])) as connection:
            self.assertEqual(validate_schema(connection, allow_legacy=True), 61)

    def test_legacy_read_fails_before_implicit_migration_or_network(self):
        self.legacy()
        before = self.path.read_bytes()
        with patch("socket.socket.connect", side_effect=AssertionError("No network")):
            for operation in (self.storage.inspect, SQLitePublicNoticeRepository(self.path).status):
                with self.assertRaisesRegex(StorageError, "migrate"):
                    operation()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_partial_addition_rolls_back_and_unique_backups_restore_without_overwrite(self):
        self.legacy()
        before = legacy_snapshot(self.path)
        def fail(connection):
            for statement in PUBLIC_NOTICE_WATCH_DDL[:2]:
                connection.execute(statement)
            raise sqlite3.OperationalError("controlled schema62 failure")
        with patch("xti.adapters.sqlite.create_public_notice_watch_schema", side_effect=fail):
            for _ in range(2):
                with self.assertRaises(StorageError):
                    self.storage.migrate()
                self.assertEqual(legacy_snapshot(self.path), before)
                with closing(sqlite3.connect(self.path)) as connection:
                    self.assertEqual(validate_schema(connection, allow_legacy=True), 61)
        backups = sorted((self.path.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 2)
        for backup in backups:
            self.assertEqual(legacy_snapshot(backup), before)
        restored = self.path.with_name("restored.db")
        SQLiteAssetRepository.restore(backups[0], restored)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(backups[0], restored)
        self.assertEqual(legacy_snapshot(restored), before)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(legacy_snapshot(restored), before)

    def test_old_version_number_cannot_disguise_new_or_missing_schema(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA user_version=61")
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.storage.migrate()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / "backups").exists())

    def test_current_validator_rejects_weakened_watch_constraints(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DROP TABLE public_notice_watch_notifications")
            connection.execute(PUBLIC_NOTICE_WATCH_DDL[3].replace("ON DELETE RESTRICT", "ON DELETE CASCADE"))
            connection.execute(PUBLIC_NOTICE_WATCH_DDL[-1])
            with self.assertRaises(SchemaError):
                validate_schema(connection)

    def test_new_constraints_require_real_unique_source_and_one_notification_per_run(self):
        _, organization, source_run, _ = self.legacy()
        self.storage.migrate()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("INSERT INTO public_notice_watches VALUES ('watch', ?, 1, 1, ?, ?)", (organization.id, NOW, NOW))
            connection.execute(
                "INSERT INTO public_notice_watch_events (id, watch_id, organization_id, action, revision, reason, recorded_at) "
                "VALUES ('event', 'watch', ?, 'enabled', 1, 'Explicit', ?)", (organization.id, NOW),
            )
            columns = "id, watch_id, organization_id, source_run_id, watch_event_id, previous_run_id, recorded_at, scope_json, scope_sha256, result_sha256, matched_count, baseline_count, added_count, updated_count, removed_count, unchanged_count"
            values = ("run", "watch", organization.id, source_run.id, "event", None, NOW, "{}", "a" * 64, "b" * 64, 1, 1, 0, 0, 0, 0)
            insert = f"INSERT INTO public_notice_watch_runs ({columns}) VALUES ({','.join('?' for _ in values)})"
            connection.execute(insert, values)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(insert, ("duplicate", *values[1:]))
            for column, invalid in (("source_run_id", "missing"), ("previous_run_id", "missing"), ("baseline_count", 0)):
                with self.subTest(column=column, invalid=invalid), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(f"UPDATE public_notice_watch_runs SET {column}=? WHERE id='run'", (invalid,))
            for invalid in (-1, 10001):
                with self.subTest(bounded_counts=invalid), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "UPDATE public_notice_watch_runs SET matched_count=?, baseline_count=? WHERE id='run'",
                        (invalid, invalid),
                    )
            notification = (100, "notification", "run", "watch", organization.id, "public_notice_watch_changed", "new", NOW, None)
            connection.execute("INSERT INTO public_notice_watch_notifications VALUES (?,?,?,?,?,?,?,?,?)", notification)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO public_notice_watch_notifications VALUES (?,?,?,?,?,?,?,?,?)", (101, "other", *notification[2:]))
            for column, invalid in (("sequence", 0), ("run_id", "missing"), ("event_type", "invented"), ("origin", "backfill")):
                with self.subTest(column=column, invalid=invalid), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(f"UPDATE public_notice_watch_notifications SET {column}=? WHERE id='notification'", (invalid,))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM public_notice_runs WHERE id=?", (source_run.id,))
        details = self.storage.inspect()
        snapshot = SQLiteStatusRepository(self.path).snapshot(("crt.sh",), None, 10)
        self.assertEqual((details["notification_count"], details["unread_notification_count"]), (2, 1))
        self.assertEqual((snapshot.notification_count, snapshot.unread_notification_count), (2, 1))
        self.assertEqual(details["public_notice_watch_notification_count"], 1)

"""Schema68→69 preserves typed watches, budgets and every legacy row verbatim."""

from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from xti.adapters.collection_news_schema import migrate_collection_news_schema
from xti.adapters.schema import SCHEMA_VERSION, VERSION_TABLES, validate_schema
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_mention_notifications import SQLiteMentionNotificationBridge
from xti.adapters.sqlite_news import SQLiteNewsRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.domain.collection_history import CollectionFrozenPlan, CollectionFrozenUnit
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.news import NewsFeed
from xti.domain.public_notices import HIBP_CONTRACT_VERSION
from tests.collection_v68_fixture import collection_layout_v68, legacy_collection_manifest_entry
from tests import test_mention_groups_storage as fixtures
from tests.test_news_storage import article


def manifest(path):
    with closing(sqlite3.connect(path)) as connection:
        result = {}
        for table in sorted(VERSION_TABLES[68]):
            entry = (connection.execute(f'PRAGMA table_info({table})').fetchall(),
                     connection.execute(f'SELECT rowid,* FROM {table} ORDER BY rowid').fetchall(),
                     connection.execute('SELECT type,name,sql FROM sqlite_schema WHERE tbl_name=? ORDER BY name',
                                        (table,)).fetchall())
            result[table] = legacy_collection_manifest_entry(table, entry)
        result['sqlite_sequence'] = connection.execute('SELECT name,seq FROM sqlite_sequence ORDER BY name').fetchall()
        return result


class CollectionNewsMigrationTests(unittest.TestCase):
    setUp = fixtures.MentionGroupStorageTests.setUp
    begin = fixtures.MentionGroupStorageTests.begin
    success = fixtures.MentionGroupStorageTests.success
    fail = fixtures.MentionGroupStorageTests.fail

    def legacy(self):
        run = self.begin()
        operation, source = self.success(run, 0)
        self.fail(run, 1)
        self.notification = SQLiteMentionNotificationBridge(self.path).notify(group_id=self.group.id,
            request=self.requests[0], mention_run_id=source.id, operation_id=operation.attempt_id,
            executed_at=fixtures.T1)
        self.groups.record_notification(run.id, 0, notification_run_id=self.notification.run.id, recorded_at=fixtures.T1)
        self.group_run = self.groups.finish(run.id, finished_at=fixtures.T1)
        self.storage.add('example.com')
        self.news_run = SQLiteNewsRepository(self.path).apply(
            NewsFeed('cisa', fixtures.T0, 'a' * 64, (article(),)),
            started_at=fixtures.T0, finished_at=fixtures.T0).run
        history = SQLiteCollectionHistoryRepository(self.path)
        plan = CollectionFrozenPlan(CollectionProfileDefinition('example.com', task_ids=('notices-hibp',)),
            (CollectionFrozenUnit('notices-hibp', 'public_notice', 'hibp', 'example.com', None, HIBP_CONTRACT_VERSION),))
        session = history.begin(plan, started_at=fixtures.T0)
        token = history.start_step(session.session.id, session.steps[0].id, started_at=fixtures.T0)
        SQLitePublicNoticeRepository(self.path).record_failure(started_at=fixtures.T0, finished_at=fixtures.T0,
                                                             error='Retained failed source', operation=token)
        self.collection = history.finish_session(session.session.id, analysis_status='complete', finished_at=fixtures.T1)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('UPDATE collection_session_steps SET rowid=rowid+100')
            connection.execute('UPDATE collection_step_receipts SET rowid=rowid+200')
            collection_layout_v68(connection)
            from tests.case_evidence_v79_fixture import case_evidence_layout_v79
            case_evidence_layout_v79(connection)
            connection.execute('PRAGMA user_version=68')
            self.assertEqual(validate_schema(connection, allow_legacy=True), 68)

    def test_migration_preserves_all_rows_hashes_rowids_typed_watch_and_budget(self):
        self.legacy()
        before = manifest(self.path)
        result = self.storage.migrate()
        self.assertEqual((result['from_version'], result['to_version']), (68, SCHEMA_VERSION))
        self.assertEqual(manifest(self.path), before)
        self.assertEqual(manifest(result['backup']), before)
        self.assertEqual(SQLiteCollectionHistoryRepository(self.path).get(self.collection.session.id), self.collection)
        self.assertEqual(self.groups.run_show(self.group_run.id), self.group_run)
        self.assertEqual(self.groups.budget(self.group.id, at=fixtures.T1).used_queries, 2)
        self.assertEqual(SQLiteNewsRepository(self.path).run_show(self.news_run.id).run, self.news_run)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(validate_schema(connection), SCHEMA_VERSION)
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertFalse(self.storage.migrate()['changed'])

    def test_rebuild_failure_rolls_back_exactly_and_unique_backups_restore(self):
        self.legacy()
        before = manifest(self.path)
        def fail_after_rebuild(connection):
            migrate_collection_news_schema(connection)
            raise sqlite3.OperationalError('Controlled schema69 failure')
        with patch('xti.adapters.sqlite.migrate_collection_news_schema', side_effect=fail_after_rebuild):
            for _ in range(2):
                with self.assertRaises(StorageError):
                    self.storage.migrate()
                self.assertEqual(manifest(self.path), before)
        backups = tuple((self.path.parent / 'backups').glob('*.db'))
        self.assertEqual(len(backups), 2)
        for backup in backups:
            self.assertEqual(manifest(backup), before)
            with closing(sqlite3.connect(backup)) as connection:
                self.assertEqual(validate_schema(connection, allow_legacy=True), 68)
        restored = self.path.parent / 'restored.db'
        SQLiteAssetRepository.restore(backups[0], restored)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(backups[0], restored)
        SQLiteAssetRepository(restored).migrate()
        self.assertEqual(manifest(restored), before)

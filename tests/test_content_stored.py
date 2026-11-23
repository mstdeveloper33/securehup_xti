"""Existing source catalogs join the content pipeline without external requests."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.content_sources import PublicContentSources
from xti.adapters.content_monitoring_schema import create
from xti.adapters.schema import validate_schema, SCHEMA_VERSION
from xti.adapters.sqlite import SQLiteAssetRepository
from tests.case_evidence_v89_fixture import case_evidence_layout_v89


class StoredContentTests(unittest.TestCase):
    def test_local_news_reports_and_mentions_read_actual_catalogs_without_network(self):
        from tests.test_reports import ReportTests
        from tests.test_mentions_storage import MentionStorageTests, hit
        report = ReportTests(); report.setUp(); self.addCleanup(report.doCleanups)
        report.capture()
        mentions = MentionStorageTests(); mentions.setUp(); self.addCleanup(mentions.doCleanups)
        mentions.apply(hit())
        with patch('socket.socket.connect', side_effect=AssertionError('No network')):
            for provider, path in [('local-news', report.path), ('local-reports', report.path), ('local-mentions', mentions.path)]:
                with self.subTest(provider=provider):
                    documents = []
                    outcome = PublicContentSources(path).collect({'definition': {'provider': provider}}, {},
                        {'max_items': 5, 'max_operations': 1, 'seconds': 5}, documents.append)
                    self.assertEqual(outcome['status'], 'complete'); self.assertEqual(len(documents), 1)
                    self.assertEqual(outcome['network_requests'], 0)
                    documents[0].validate(); self.assertTrue(documents[0].content)

    def test_schema90_interruption_rolls_back_and_retains_unique_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'data' / 'xti.db'
            storage = SQLiteAssetRepository(path); storage.initialize(); storage.add('example.com')
            with closing(sqlite3.connect(path)) as connection, connection:
                case_evidence_layout_v89(connection); connection.execute('PRAGMA user_version=89')
                self.assertEqual(validate_schema(connection, allow_legacy=True), 89)
            before = path.read_bytes()
            def interrupted(connection): create(connection); raise KeyboardInterrupt('Controlled interruption')
            with patch('xti.adapters.sqlite.create_content_monitoring_schema', side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt): storage.migrate()
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(list((path.parent / 'backups').glob('*.db'))), 1)
            self.assertEqual(storage.migrate()['to_version'], SCHEMA_VERSION)


if __name__ == '__main__': unittest.main()

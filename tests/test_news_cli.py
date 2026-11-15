"""Actual news commands separate remote refresh from local evidence and watches."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_news import SQLiteNewsRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.interfaces.cli import build_parser, main
from xti.interfaces.news import detail_lines
from xti.application.news import NewsService
from xti.ports.discovery import SourceError
from tests.test_news_integration import article, feed


class NewsCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'data with spaces'
        self.path = self.data / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.articles = (article(), article(entry='entry:two', title='Example second bulletin',
                                          url='https://publisher.example/news/two'))
        self.calls = []
        self.error = None
        self.addCleanup(patch.stopall)
        patch('socket.socket.connect', side_effect=AssertionError('No live network')).start()
        patch('socket.getaddrinfo', side_effect=AssertionError('No live DNS')).start()
        patch('xti.adapters.rss_atom_news.RssAtomNewsSource.fetch', side_effect=self.fetch).start()

    def fetch(self, source_key):
        self.calls.append(source_key)
        if self.error:
            raise self.error
        return feed(self.articles, source=source_key, at=datetime.now(timezone.utc).isoformat())

    def invoke(self, *arguments, json_output=True, data=None):
        out, err = StringIO(), StringIO()
        prefix = ['--data-dir', str(data or self.data)]
        if json_output:
            prefix.append('--json')
        with redirect_stdout(out), redirect_stderr(err):
            code = main([*prefix, *arguments])
        return code, out.getvalue(), err.getvalue()

    def result(self, *arguments):
        code, out, err = self.invoke(*arguments)
        self.assertEqual((code, err), (0, ''), out + err)
        self.assertTrue(json.loads(out)['ok'])
        return json.loads(out)['data']

    def files(self):
        return {path.relative_to(self.data).as_posix(): path.read_bytes()
                for path in self.data.rglob('*') if path.is_file()}

    def test_sources_need_no_database_dependency_or_network_and_missing_reads_do_not_initialize(self):
        missing = self.root / 'absent'
        with patch('xti.adapters.rss_atom_news._parser', side_effect=AssertionError('Parser must stay optional')):
            code, out, err = self.invoke('news', 'sources', data=missing)
            self.assertEqual((code, err), (0, ''))
            self.assertEqual({source['key'] for source in json.loads(out)['data']['sources']}, {'cisa', 'ncsc', 'cert-fr'})
            for arguments in (('news', 'list'), ('news', 'status'),
                              ('news', 'refresh', '--source', 'cisa')):
                code, out, err = self.invoke(*arguments, data=missing)
                self.assertEqual(code, 1, out + err)
                self.assertIn('storage_error', err)
        self.assertFalse(missing.exists())
        self.assertEqual(self.calls, [])

    def test_refresh_stores_full_feed_and_local_pages_preserve_filters_and_data_directory(self):
        refresh = self.result('news', 'refresh', '--source', 'cisa', '--limit', '1')
        self.assertEqual((refresh['run']['article_count'], refresh['total_change_count'], len(refresh['changes'])), (2, 2, 1))
        self.assertEqual(self.calls, ['cisa'])
        before = self.files()
        with patch('xti.adapters.rss_atom_news._parser', side_effect=AssertionError('Read must not need parser')):
            page = self.result('news', 'list', 'Example', '--source', 'cisa', '--limit', '1')
            self.assertEqual((page['total_count'], len(page['articles']), page['has_more']), (2, 1, True))
            detail = self.result('news', 'show', page['articles'][0]['article']['id'])
            self.assertEqual(detail['source']['source']['key'], 'cisa')
            self.assertEqual(self.result('news', 'run-show', refresh['run']['id'], '--offset', '1', '--limit', '1')['total_change_count'], 2)
            code, text, err = self.invoke('news', 'list', 'Example', '--source', 'cisa', '--limit', '1', json_output=False)
            self.assertEqual((code, err), (0, ''))
            command = next(line.split(': ', 1)[1] for line in text.splitlines() if line.startswith('Sonraki haber sayfası:'))
            parsed = build_parser().parse_args(shlex.split(command)[1:])
            self.assertEqual((parsed.query, parsed.source, parsed.offset, parsed.limit, parsed.data_dir),
                             ('Example', 'cisa', 1, 1, str(self.data)))
            self.assertIn('Özgün haber:', text)
            self.assertIn('Kaynak yayın zamanı:', text)
            self.assertIn('İlk toplama:', text)
            code, global_text, err = self.invoke('search', 'example', '--kind', 'news', '--limit', '1', json_output=False)
            self.assertEqual((code, err), (0, ''))
            next_search = next(line.split(': ', 1)[1] for line in global_text.splitlines() if line.startswith('Sonraki sayfa:'))
            parsed_search = build_parser().parse_args(shlex.split(next_search)[1:])
            self.assertEqual((parsed_search.data_dir, parsed_search.offset, parsed_search.kinds), (str(self.data), 1, ['news']))
            show_news = next(line.strip().split(': ', 1)[1] for line in global_text.splitlines() if line.strip().startswith('Haber ayrıntısı:'))
            self.assertEqual(build_parser().parse_args(shlex.split(show_news)[1:]).data_dir, str(self.data))
            empty = self.result('news', 'list', '--offset', '100')
            self.assertEqual((empty['total_count'], empty['articles']), (2, []))
        self.assertEqual(self.files(), before)
        self.assertEqual(self.calls, ['cisa'])

    def test_failure_keeps_previous_news_and_is_not_reported_as_empty_success(self):
        first = self.result('news', 'refresh', '--source', 'cisa')
        self.error = SourceError('Publisher returned HTTP 503.')
        code, out, err = self.invoke('news', 'refresh', '--source', 'cisa')
        self.assertEqual((code, err), (3, ''))
        failed = json.loads(out)
        self.assertFalse(failed['ok'])
        self.assertEqual(failed['data']['run']['status'], 'failed')
        listing = self.result('news', 'list', '--source', 'cisa')
        self.assertEqual(listing['total_count'], 2)
        self.assertEqual(listing['sources'][0]['latest_complete_run']['id'], first['run']['id'])
        self.assertEqual(listing['sources'][0]['latest_run']['status'], 'failed')
        self.assertEqual(self.result('news', 'run-show', failed['data']['run']['id'])['run']['status'], 'failed')
        code, text, err = self.invoke('news', 'status', '--source', 'cisa', '--limit', '1', json_output=False)
        self.assertEqual((code, err), (0, ''))
        self.assertIn('önceki başarılı kanıt korunuyor', text)
        command = next(line.split(': ', 1)[1] for line in text.splitlines() if line.startswith('Sonraki çalışma sayfası:'))
        parsed = build_parser().parse_args(shlex.split(command)[1:])
        self.assertEqual((parsed.source, parsed.offset, parsed.limit, parsed.data_dir), ('cisa', 1, 1, str(self.data)))

    def test_refresh_needs_explicit_watch_comparison_before_a_notification(self):
        watch = self.result('search-watch', 'add', 'Example news', 'example.com', '--kind', 'news')['saved_search']
        baseline = self.result('search-watch', 'run', watch['id'])
        self.assertEqual(baseline['run']['total_count'], 0)
        self.result('news', 'refresh', '--source', 'cisa')
        self.assertEqual(self.result('inbox')['total_count'], 0)
        comparison = self.result('search-watch', 'run', watch['id'])
        self.assertEqual(comparison['run']['added_count'], 2)
        notice = comparison['notification_id']
        self.assertIsNotNone(notice)
        details = self.result('inbox', 'show', notice)
        self.assertEqual(details['global_search_change']['run']['id'], comparison['run']['id'])
        repeat_refresh = self.result('news', 'refresh', '--source', 'cisa')
        self.assertEqual(repeat_refresh['total_change_count'], 2)
        self.assertEqual([change['action'] for change in repeat_refresh['changes']], ['unchanged', 'unchanged'])
        self.assertEqual(self.result('news', 'run-show', repeat_refresh['run']['id'])['changes'], repeat_refresh['changes'])
        repeated = self.result('search-watch', 'run', watch['id'])
        self.assertIsNone(repeated['notification_id'])
        self.assertEqual(repeated['run']['unchanged_count'], 2)

    def test_busy_writer_invalid_arguments_and_empty_pages_do_not_collect(self):
        before = self.path.read_bytes()
        with LocalExecutionLock(self.path).acquire():
            code, out, err = self.invoke('news', 'refresh', '--source', 'cisa')
            self.assertEqual(code, 4, out + err)
            self.assertIn('worker_busy', err)
        for arguments in (('news', 'refresh', '--source', 'cisa', '--limit', '0'),
                          ('news', 'list', 'x'), ('news', 'list', '--offset', '-1'),
                          ('news', 'show', '../not-an-id'), ('news', 'run-show', 'not-a-uuid')):
            code, out, err = self.invoke(*arguments)
            self.assertEqual(code, 2, out + err)
            self.assertIn('validation_error', err)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.calls, [])
        code, text, err = self.invoke('news', 'list', json_output=False)
        self.assertEqual((code, err), (0, ''))
        self.assertIn('Henüz toplanmadı', text)
        self.assertIn('Başarılı toplama yok', text)

    def test_historical_pages_and_terminal_escaping_keep_evidence_visible(self):
        initial = self.result('news', 'refresh', '--source', 'cisa')
        self.articles = tuple(replace(value, summary='Updated example.com report') for value in self.articles)
        changed = self.result('news', 'refresh', '--source', 'cisa', '--limit', '1')
        code, text, err = self.invoke('news', 'run-show', changed['run']['id'], '--limit', '1', json_output=False)
        self.assertEqual((code, err), (0, ''))
        self.assertIn('Önce:', text)
        self.assertIn('Sonra:', text)
        self.assertIn('The report mentions', text)
        command = next(line.split(': ', 1)[1] for line in text.splitlines() if line.startswith('Sonraki kanıt sayfası:'))
        parsed = build_parser().parse_args(shlex.split(command)[1:])
        self.assertEqual((parsed.run_id, parsed.offset, parsed.limit, parsed.data_dir), (changed['run']['id'], 1, 1, str(self.data)))
        old = self.result('news', 'run-show', initial['run']['id'])
        self.assertTrue(all(change['after']['summary'] == 'The report mentions example.com.' for change in old['changes']))
        detail = NewsService(SQLiteNewsRepository(self.path)).show(self.articles[0].id)
        malicious = replace(detail, record=replace(detail.record, article=replace(detail.record.article,
            title='[bold]Title[/bold]\x1b[31m', summary='Untrusted\nsummary\x1b]0;title\x07')))
        rendered = '\n'.join(detail_lines(malicious, data_dir=self.data))
        self.assertNotIn('\x1b', rendered)
        self.assertNotIn('\x07', rendered)
        self.assertNotIn('Untrusted\nsummary', rendered)
        self.assertIn('[bold]Title[/bold]', rendered)


if __name__ == '__main__':
    unittest.main()

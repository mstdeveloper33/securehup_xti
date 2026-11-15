"""Offline acceptance of explicit publisher collection and saved news searches."""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.worker_lock import LocalExecutionLock
from xti.ports.discovery import SourceError
from tests import test_collection_watch_cli as fixtures
from tests.test_news_integration import article, feed


SOURCES = ('cisa', 'ncsc', 'cert-fr')
NEWS_OPTIONS = tuple(value for source in SOURCES for value in ('--news-source', source))


class CollectionNewsCLITests(unittest.TestCase):
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files

    def setUp(self):
        fixtures.CollectionWatchCLITests.setUp(self)
        self.calls = []
        self.errors = {}
        self.entries = {source: (article(source),) for source in SOURCES}
        self.enterContext(patch('xti.adapters.rss_atom_news.RssAtomNewsSource.fetch', side_effect=self.fetch))

    def fetch(self, source_key):
        self.calls.append(source_key)
        if source_key in self.errors:
            raise self.errors[source_key]
        return feed(self.entries[source_key], source=source_key, at=datetime.now(timezone.utc).isoformat())

    def watch(self, *extra):
        return self.result('search-watch', 'add', 'Marka haberleri', 'example.com',
                           '--kind', 'news', *extra)['saved_search']['id']

    def collect(self, watch=None, *, expected_code=0):
        options = ('--search-watch', watch) if watch else ()
        return self.result('collect', 'example.com', '--only-news', *NEWS_OPTIONS,
                           *options, expected_code=expected_code)

    def test_default_collection_does_not_fetch_news_or_run_existing_news_watch(self):
        watch = self.watch()
        result = self.result('collect', 'example.com')
        self.assertEqual([step['task']['id'] for step in result['steps']],
                         ['scan-crtsh', 'scan-urlscan', 'discover-crtsh'])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.result('search-watch', 'show', watch)['total_run_count'], 0)

    def test_news_profile_and_plan_are_read_only_and_defaults_stay_explicit(self):
        watch = self.watch()
        saved = self.result('profiles', 'save', 'Haberler', 'example.com', '--only-news',
                            *NEWS_OPTIONS, '--search-watch', watch)
        definition = saved['profile']['definition']
        self.assertEqual(definition['task_ids'], [])
        self.assertEqual(set(definition['news_sources']), set(SOURCES))
        self.assertEqual(definition['search_watch_ids'], [watch])
        before = self.files()
        with patch.object(LocalExecutionLock, 'acquire', side_effect=AssertionError('Read must not lock')):
            plan = self.result('collect', '--profile', 'Haberler', '--plan')
            self.result('profiles', 'show', 'Haberler')
            code, text, error = self.invoke('collect', '--profile', 'Haberler', '--plan', as_json=False)
        self.assertEqual((code, error), (0, ''))
        self.assertIn('Marka haberleri', text)
        self.assertEqual(Counter(task['kind'] for task in plan['tasks']),
                         Counter({'news_refresh': 3, 'search_watch': 1}))
        self.assertEqual(self.files(), before)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])

    def test_single_source_refresh_records_receipt_without_domain_threat_claim(self):
        collected = self.result('collect', 'example.com', '--only-news', '--news-source', 'cisa')
        self.assertEqual(self.calls, ['cisa'])
        self.assertEqual(collected['analysis']['findings']['total'], 0)
        history = self.result('collections', 'show', collected['session_id'])
        self.assertEqual(len(history['receipts']), 1)
        receipt = history['receipts'][0]
        self.assertEqual(receipt['result_kind'], 'news_run')
        self.assertEqual(receipt['result_status'], 'complete')
        source = self.result('news', 'run-show', receipt['result_id'])
        self.assertEqual(source['run']['article_count'], 1)
        before = self.files()
        code, text, error = self.invoke('collections', 'show', collected['session_id'], as_json=False)
        self.assertEqual((code, error), (0, ''))
        self.assertIn('news run-show', text)
        self.assertEqual(self.files(), before)

    def test_first_baseline_is_silent_later_new_news_notifies_and_identical_repeat_does_not(self):
        watch = self.watch()
        self.collect(watch)
        self.assertEqual(self.result('inbox')['total_count'], 0)
        self.entries['cisa'] += (article('cisa', entry='second', title='Second example bulletin',
                                        url='https://publisher.example/news/two'),)
        second = self.collect(watch)
        self.assertEqual(self.result('inbox')['total_count'], 1)
        history = self.result('collections', 'show', second['session_id'])
        self.assertEqual(Counter(item['result_kind'] for item in history['receipts']),
                         Counter({'news_run': 3, 'saved_search_run': 1}))
        self.collect(watch)
        self.assertEqual(self.result('inbox')['total_count'], 1)
        self.assertEqual(self.result('search-watch', 'show', watch)['total_run_count'], 3)
        self.assertEqual(Counter(self.calls), Counter({source: 3 for source in SOURCES}))

    def test_failed_feed_blocks_comparison_and_resume_keeps_successful_source_work(self):
        watch = self.watch()
        self.collect(watch)
        self.entries['cisa'] += (article('cisa', entry='second', title='New example report',
                                        url='https://publisher.example/news/two'),)
        self.errors['ncsc'] = SourceError('Publisher temporarily unavailable.')
        failed = self.collect(watch, expected_code=3)
        self.assertEqual(self.result('search-watch', 'show', watch)['total_run_count'], 1)
        self.assertEqual(self.result('inbox')['total_count'], 0)
        before_calls = Counter(self.calls)
        old_history = self.result('collections', 'show', failed['session_id'])
        plan = self.result('collections', 'resume', failed['session_id'], '--plan')
        self.assertEqual({unit['kind'] for unit in plan['units']}, {'news_refresh', 'search_watch'})
        self.assertEqual({unit['source'] for unit in plan['units'] if unit['kind'] == 'news_refresh'}, {'ncsc'})
        del self.errors['ncsc']
        resumed = self.result('collections', 'resume', failed['session_id'])
        self.assertEqual(resumed['history']['session']['status'], 'complete')
        self.assertEqual(Counter(self.calls), before_calls + Counter({'ncsc': 1}))
        self.assertEqual(self.result('inbox')['total_count'], 1)
        self.assertEqual(self.result('collections', 'show', failed['session_id']), old_history)

    def test_bad_selection_and_profile_overrides_fail_before_any_write_or_fetch(self):
        watch = self.watch()
        mixed = self.result('search-watch', 'add', 'Mixed', 'example.com', '--kind', 'news',
                            '--kind', 'mention')['saved_search']['id']
        self.result('profiles', 'save', 'Haberler', 'example.com', '--only-news', *NEWS_OPTIONS)
        before = self.files()
        for arguments in (
            ('collect', 'example.com', '--only-news'),
            ('collect', 'example.com', '--only-news', '--task', 'scan-crtsh', '--news-source', 'cisa'),
            ('collect', 'example.com', '--only-news', '--news-source', 'cisa', '--search-watch', watch),
            ('collect', 'example.com', '--only-news', *NEWS_OPTIONS, '--search-watch', mixed),
            ('collect', 'example.com', '--only-news', *NEWS_OPTIONS, '--search-watch', str(uuid4())),
            ('collect', '--profile', 'Haberler', '--only-news'),
            ('collect', '--profile', 'Haberler', '--news-source', 'cisa'),
            ('collect', '--profile', 'Haberler', '--search-watch', watch),
        ):
            with self.subTest(arguments=arguments):
                self.assertNotEqual(self.invoke(*arguments)[0], 0)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.crt.calls, [])

    def test_news_profile_uses_existing_schedule_without_activating_it_or_reading_sources(self):
        watch = self.watch()
        self.result('profiles', 'save', 'Haberler', 'example.com', '--only-news',
                    *NEWS_OPTIONS, '--search-watch', watch)
        before = self.files()
        output = self.data.parent / 'news schedule'
        with patch('subprocess.run', side_effect=AssertionError('No automatic service activation')):
            generated = self.result('schedule', 'generate', 'Haberler', '--output', str(output),
                                    '--at', '09:00', '--timezone', 'Europe/Istanbul')
        self.assertEqual(self.files(), before)
        service = Path(generated['service_file']).read_text()
        self.assertIn('--profile', service)
        self.assertIn('Haberler', service)
        self.assertEqual(self.calls, [])

    def test_terminal_shows_source_evidence_search_and_skipped_comparison(self):
        watch = self.watch()
        arguments = ('collect', 'example.com', '--only-news', *NEWS_OPTIONS, '--search-watch', watch)
        code, text, progress = self.invoke(*arguments, as_json=False)
        self.assertEqual(code, 0, text + progress)
        self.assertIn('Haber toplama:', text)
        self.assertIn('Marka haberleri', text)
        self.assertIn(str(self.data), text)
        self.assertIn('Toplama:', progress)
        self.errors['ncsc'] = SourceError('Publisher unavailable.')
        code, text, progress = self.invoke(*arguments, as_json=False)
        self.assertEqual(code, 3, text + progress)
        self.assertIn('Atlandı', text)
        self.assertIn('eski katalogdan yeni bildirim üretilmedi', text)


if __name__ == '__main__':
    unittest.main()

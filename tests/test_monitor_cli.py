"""Bounded internet monitoring through the public CLI with fixture sources."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.monitoring import MonitorService
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError
from tests.test_discovery import FakeSource, batch, document
from tests.test_multi_source import FakeUrlscanSource, scoped_batch, urlscan_document


class Timer:
    value = 0.0
    interrupt = False

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        if self.interrupt:
            raise KeyboardInterrupt
        self.value += seconds


class MonitorCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / 'monitor data with spaces'
        self.database = self.data / 'xti.db'
        self.crt = FakeSource({'%example%': batch(document('example-support.net'))})
        self.urlscan = FakeUrlscanSource({'example*': scoped_batch(urlscan_document())})
        self.timer = Timer()

    def invoke(self, *args, as_json=True):
        timer = self.timer

        class TestMonitor(MonitorService):
            def __init__(self, repository, jobs=None):
                super().__init__(repository, jobs, clock=lambda: datetime(2026, 10, 29, tzinfo=timezone.utc),
                                 monotonic=timer.monotonic, sleeper=timer.sleep)

        out, err = StringIO(), StringIO()
        with (
            patch('xti.interfaces.cli.CrtShSource', return_value=self.crt),
            patch('xti.interfaces.cli.UrlscanSource', return_value=self.urlscan),
            patch('xti.interfaces.cli.MonitorService', TestMonitor),
            redirect_stdout(out), redirect_stderr(err),
        ):
            code = main(['--data-dir', str(self.data), *(['--json'] if as_json else []), *args])
        return code, out.getvalue(), err.getvalue()

    def success(self, *args, **kwargs):
        code, out, err = self.invoke(*args, **kwargs)
        self.assertEqual(code, 0, err)
        self.assertEqual(err, '')
        data = json.loads(out)
        self.assertTrue(data['ok'])
        return data['data']

    def start(self, *extra):
        return self.success('monitor', 'start', 'example.com', '--cycles', '2', '--interval', '300', *extra)

    def test_two_cycles_keep_attribution_and_do_not_repeat_findings(self):
        result = self.start()
        report = result['report']
        self.assertEqual(report['completed_cycles'], 2)
        self.assertEqual(report['run']['stop_reason'], 'cycles')
        self.assertEqual(report['run']['elapsed_seconds'], 300)
        self.assertEqual([s['complete'] for s in report['sources']], [2, 2])
        self.assertEqual([s['not_started'] for s in report['sources']], [0, 0])
        self.assertEqual(sum(s['findings_created'] for s in report['sources']), 1)
        self.assertEqual(self.success('inbox')['total_count'], 1)
        details = self.success('monitor', 'show', report['run']['id'])
        self.assertEqual(details['report'], report)
        self.assertEqual(details['total_entries'], 4)
        self.assertEqual([e['cycle'] for e in details['entries']], [1, 1, 2, 2])
        self.assertEqual(shlex.split(result['show_command']), ['./xti', '--data-dir', str(self.data.resolve()), 'monitor', 'show', report['run']['id']])

    def test_partial_sources_are_saved_and_start_exit_differs_from_read(self):
        self.crt.responses['%example%'] = SourceError('Kontrollü kaynak kesintisi.')
        code, out, err = self.invoke('monitor', 'start', 'example.com', '--cycles', '1')
        self.assertEqual(code, 3, err)
        payload = json.loads(out)
        self.assertFalse(payload['ok'])
        report = payload['data']['report']
        self.assertEqual(report['run']['status'], 'completed')
        self.assertEqual(report['sources'][0]['partial'], 1)
        self.assertEqual(report['sources'][1]['complete'], 1)
        self.assertEqual(report['completed_cycles'], 1)
        self.assertEqual(self.success('monitor', 'show', report['run']['id'])['report'], report)

    def test_duration_prevents_second_provider_start_without_cutting_existing_query(self):
        original = self.crt.search

        def slow_search(pattern):
            self.timer.value += 2
            return original(pattern)

        self.crt.search = slow_search
        result = self.start('--duration', '1')
        report = result['report']
        self.assertEqual(report['run']['stop_reason'], 'duration')
        self.assertGreater(report['run']['elapsed_seconds'], 1)
        self.assertEqual(report['completed_cycles'], 0)
        self.assertEqual(report['sources'][0]['complete'], 1)
        self.assertEqual(report['sources'][1]['started_attempts'], 0)
        self.assertEqual(self.urlscan.calls, [])

    def test_interrupt_while_waiting_preserves_completed_results_and_releases_lock(self):
        self.timer.interrupt = True
        code, out, err = self.invoke('monitor', 'start', 'example.com', '--cycles', '2')
        self.assertEqual(code, 130, err)
        self.assertEqual(out, '')
        run = self.success('monitor', 'list')['runs'][0]
        report = self.success('monitor', 'show', run['id'])['report']
        self.assertEqual(run['status'], 'interrupted')
        self.assertEqual(run['stop_reason'], 'cancelled')
        self.assertEqual(report['completed_cycles'], 1)
        self.assertEqual(sum(s['findings_created'] for s in report['sources']), 1)
        with LocalExecutionLock(self.database).acquire():
            pass
        self.assertEqual(self.success('monitor', 'recover')['recovered_runs'], 0)

    def test_reading_and_restore_keep_group_counts_and_inbox_unchanged(self):
        run = self.start()['report']['run']
        notice = self.success('inbox')['items'][0]
        self.success('inbox', 'read', notice['notification']['id'])
        before = self.database.read_bytes()
        files = sorted(self.data.iterdir())
        self.crt.calls.clear()
        self.urlscan.calls.clear()
        with patch('xti.interfaces.cli.make_jobs', side_effect=AssertionError('Read must not wire live sources')):
            details = self.success('monitor', 'show', run['id'], '--limit', '1')
            self.success('monitor', 'list')
        self.assertEqual(details['total_entries'], 4)
        self.assertEqual(len(details['entries']), 1)
        self.assertEqual(details['entries'][0]['cycle'], 2)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(sorted(self.data.iterdir()), files)
        self.assertEqual(self.crt.calls + self.urlscan.calls, [])
        backup = self.data.parent / 'monitor-backup.db'
        self.success('backup', '--output', str(backup))
        self.data = self.data.parent / 'restored'
        self.database = self.data / 'xti.db'
        self.success('restore', str(backup))
        restored = self.success('monitor', 'show', run['id'])
        self.assertEqual(restored['report'], details['report'])
        self.assertEqual(self.success('inbox')['unread_count'], 0)

    def test_worker_and_retry_do_not_steal_monitor_work(self):
        report = self.start()['report']
        entry = self.success('monitor', 'show', report['run']['id'])['entries'][0]
        before = self.database.read_bytes()
        code, out, err = self.invoke('jobs', 'retry', entry['job']['id'])
        self.assertEqual(code, 2, err)
        self.assertEqual(out, '')
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(self.success('monitor', 'show', report['run']['id'])['report'], report)

    def test_active_worker_prevents_new_monitor_session(self):
        self.success('init')
        self.success('assets', 'add', 'example.com')
        with LocalExecutionLock(self.database).acquire():
            code, out, err = self.invoke('monitor', 'start', 'example.com', '--cycles', '1')
        self.assertEqual(code, 4, err)
        self.assertEqual(out, '')
        self.assertEqual(self.success('monitor', 'list')['runs'], [])
        self.assertEqual(self.crt.calls + self.urlscan.calls, [])

    def test_invalid_bounds_or_domain_do_not_create_record_area(self):
        for args in (('--cycles', '0'), ('--cycles', '1001'), ('--interval', '299'),
                     ('--duration', '0'), ('--duration', '604801')):
            with self.subTest(args=args):
                code, out, err = self.invoke('monitor', 'start', 'example.com', *args)
                self.assertEqual(code, 2, err)
                self.assertFalse(self.data.exists())
        code, out, err = self.invoke('monitor', 'start', 'https://example.com')
        self.assertEqual(code, 2, err)
        self.assertFalse(self.data.exists())
        for args in (('list',), ('show', 'missing'), ('recover',)):
            code, out, err = self.invoke('monitor', *args)
            self.assertEqual(code, 1, err)
            self.assertFalse(self.data.exists())

    def test_human_output_escapes_source_errors_and_custom_paths(self):
        self.data = self.data.parent / 'monitor\x1b[2J path'
        self.database = self.data / 'xti.db'
        self.crt.responses['%example%'] = SourceError('error\x1b[2J\nforged')
        code, out, err = self.invoke('monitor', 'start', 'example.com', '--cycles', '1')
        self.assertEqual(code, 3, err)
        run_id = json.loads(out)['data']['report']['run']['id']
        code, out, err = self.invoke('monitor', 'show', run_id, as_json=False)
        self.assertEqual(code, 0, err)
        self.assertNotIn('\x1b', out)
        self.assertIn(r'error\u001b[2J\u000aforged', out)
        self.assertIn(r'monitor\u001b[2J path', out)


if __name__ == '__main__':
    unittest.main()

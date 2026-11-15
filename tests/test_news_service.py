"""Input, lock ownership and source failure behavior for explicit news collection."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from xti.application.news import NewsService
from xti.domain.assets import ValidationError
from xti.domain.collection_history import CollectionOperationToken
from xti.domain.news import NEWS_SOURCES, NewsFeed
from xti.ports.discovery import SourceError
from uuid import uuid4


NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


class Lock:
    def __init__(self):
        self.held, self.acquisitions = False, 0

    @contextmanager
    def acquire(self):
        if self.held:
            raise AssertionError('Nested lock')
        self.held, self.acquisitions = True, self.acquisitions + 1
        try:
            yield
        finally:
            self.held = False


class NewsServiceTests(unittest.TestCase):
    def setUp(self):
        self.repo, self.source, self.lock = Mock(), Mock(), Lock()
        self.source.fetch.return_value = NewsFeed('cisa', NOW.isoformat(), 'a' * 64, ())
        self.service = NewsService(self.repo, self.source, self.lock, clock=lambda: NOW)

    def test_invalid_inputs_stop_before_network_storage_or_lock(self):
        for action in (lambda: self.service.refresh('unknown'), lambda: self.service.refresh('cisa', limit=True),
                       lambda: self.service.list('x'), lambda: self.service.list(source_key='unknown'),
                       lambda: self.service.status(offset=-1), lambda: self.service.show('wrong'),
                       lambda: self.service.run_show('wrong')):
            with self.assertRaises(ValidationError):
                action()
        self.assertEqual(self.repo.mock_calls, [])
        self.assertEqual(self.source.mock_calls, [])
        self.assertEqual(self.lock.acquisitions, 0)

    def test_full_refresh_holds_shared_writer_lock_and_validates_before_http(self):
        events = []
        def validate():
            self.assertTrue(self.lock.held)
            events.append('validate')
        def fetch(key):
            self.assertTrue(self.lock.held)
            events.append('fetch')
            return NewsFeed(key, NOW.isoformat(), 'a' * 64, ())
        def apply(feed, **kwargs):
            self.assertTrue(self.lock.held)
            self.assertEqual(kwargs['started_at'], NOW.isoformat())
            events.append('apply')
        self.repo.validate.side_effect, self.source.fetch.side_effect, self.repo.apply.side_effect = validate, fetch, apply
        self.service.refresh('cisa')
        self.assertEqual(events, ['validate', 'fetch', 'apply'])
        self.assertFalse(self.lock.held)

    def test_bad_storage_prevents_fetch_and_failed_source_records_one_attempt(self):
        self.repo.validate.side_effect = RuntimeError('Corrupt local evidence')
        with self.assertRaises(RuntimeError):
            self.service.refresh('cisa')
        self.source.fetch.assert_not_called()
        self.assertFalse(self.lock.held)
        self.repo.validate.side_effect = None
        self.source.fetch.side_effect = SourceError('Publisher unavailable')
        self.repo.record_failure.return_value = SimpleNamespace(status='failed')
        report = self.service.refresh('cisa')
        self.assertEqual(report.run.status, 'failed')
        self.assertEqual(report.changes, ())
        self.repo.record_failure.assert_called_once()
        self.repo.apply.assert_not_called()
        self.assertFalse(self.lock.held)

    def test_foreign_source_feed_and_invalid_metadata_never_reach_apply(self):
        self.repo.record_failure.return_value = SimpleNamespace(status='failed')
        for feed in (replace(self.source.fetch.return_value, source_key='ncsc'),
                     replace(self.source.fetch.return_value, content_sha256='not-a-hash')):
            self.source.fetch.return_value = feed
            report = self.service.refresh('cisa')
            self.assertEqual(report.run.status, 'failed')
        self.repo.apply.assert_not_called()

    def test_clock_is_sampled_only_while_lock_is_held_and_bad_clock_releases_it(self):
        def clock():
            self.assertTrue(self.lock.held)
            return NOW
        self.service.clock = clock
        self.service.refresh('cisa')
        self.service.clock = lambda: NOW.replace(tzinfo=None)
        self.source.reset_mock()
        with self.assertRaises(ValidationError):
            self.service.refresh('cisa')
        self.source.fetch.assert_not_called()
        self.assertFalse(self.lock.held)

    def test_source_catalog_and_read_status_have_no_writes_lock_or_fetch(self):
        self.assertEqual(self.service.sources(), NEWS_SOURCES)
        self.assertEqual(self.repo.mock_calls, [])
        self.service.status(source_key='ncsc', offset=2, limit=4)
        self.repo.status.assert_called_once_with(source_key='ncsc', offset=2, limit=4)
        self.assertEqual(self.lock.acquisitions, 0)
        self.assertEqual(self.source.mock_calls, [])

    def test_collection_operation_is_validated_before_http_without_nested_lock(self):
        operation = CollectionOperationToken(str(uuid4()), str(uuid4()), 'a' * 64, None)
        events = []
        self.repo.validate_operation.side_effect = lambda *args: events.append('operation')
        self.source.fetch.side_effect = lambda key: (events.append('fetch') or NewsFeed(key, NOW.isoformat(), 'a' * 64, ()))
        with self.lock.acquire():
            self.service.refresh('cisa', operation=operation)
        self.assertEqual(events, ['operation', 'fetch'])
        self.assertEqual(self.lock.acquisitions, 1)
        self.assertEqual(self.repo.apply.call_args.kwargs['operation'], operation)

    def test_invalid_collection_operation_never_fetches_and_failure_receipt_keeps_token(self):
        operation = CollectionOperationToken(str(uuid4()), str(uuid4()), 'a' * 64, None)
        self.repo.validate_operation.side_effect = ValidationError('Invalid collection operation')
        with self.assertRaises(ValidationError):
            self.service.refresh('cisa', operation=operation)
        self.source.fetch.assert_not_called()
        self.repo.validate_operation.side_effect = None
        self.source.fetch.side_effect = SourceError('Publisher unavailable')
        self.repo.record_failure.return_value = SimpleNamespace(status='failed')
        self.service.refresh('cisa', operation=operation)
        self.assertEqual(self.repo.record_failure.call_args.kwargs['operation'], operation)


if __name__ == '__main__':
    unittest.main()

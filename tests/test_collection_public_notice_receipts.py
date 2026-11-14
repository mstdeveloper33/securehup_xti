"""Public catalog commits and collection receipts are one auditable transaction."""
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_collection_receipts import record_collection_step_receipt, summary_json
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.application.public_notices import PublicNoticeService
from xti.domain.assets import ValidationError
from xti.domain.collection_history import (
    CollectionFrozenPlan, CollectionFrozenUnit, CollectionOperationToken, sha256_text,
)
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.public_notices import HIBP_ATTRIBUTION, HIBP_CONTRACT_VERSION, HIBP_LICENSE
from xti.ports.discovery import SourceError
from tests.test_public_notices import NOW, feed, item


class ReceiptFailure(RuntimeError):
    pass


class FakeSource:
    def __init__(self, response=None):
        self.response = response if response is not None else feed()
        self.calls = 0
        self.before_return = lambda: None

    def fetch(self):
        self.calls += 1
        self.before_return()
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class CollectionPublicNoticeReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.storage.add('example.com')
        self.history = SQLiteCollectionHistoryRepository(self.path)
        self.repository = SQLitePublicNoticeRepository(self.path)
        self.definition = CollectionProfileDefinition('example.com', task_ids=('notices-hibp',))
        self.plan = CollectionFrozenPlan(self.definition, (
            CollectionFrozenUnit('notices-hibp', 'public_notice', 'hibp', 'example.com', None, HIBP_CONTRACT_VERSION),
        ))
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('No network in receipt tests')))

    def start(self, plan=None, *, at=NOW, parent=None):
        details = self.history.begin(plan or self.plan, started_at=at.isoformat(), parent_id=parent)
        token = self.history.start_step(details.session.id, details.steps[0].id, started_at=at.isoformat())
        return details, token

    def service(self, source):
        return PublicNoticeService(self.repository, source, clock=lambda: NOW + timedelta(seconds=1))

    def counts(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return tuple(connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in (
                'public_notice_runs', 'public_notice_changes', 'collection_step_receipts',
            ))

    def test_complete_receipt_references_full_catalog_not_display_page_or_selected_domain(self):
        details, token = self.start()
        source = FakeSource(feed(item(), item('Other', 'other.example')))
        before = self.path.read_bytes()
        self.repository.validate(operation=token)
        self.assertEqual(self.path.read_bytes(), before)
        result = self.service(source).refresh(item_limit=1, operation=token)
        self.assertEqual((source.calls, len(result.changes), result.total_change_count), (1, 1, 2))
        saved = self.history.get(details.session.id)
        receipt = saved.receipts[0]
        self.assertEqual((receipt.result_kind, receipt.result_id, receipt.result_status), ('public_notice_run', result.run.id, 'complete'))
        self.assertEqual(receipt.recorded_at, result.run.finished_at)
        self.assertEqual(dict(receipt.summary), {'notice_count': 2, 'added_count': 2, 'updated_count': 0,
                                                'unchanged_count': 0, 'removed_count': 0, 'is_baseline': 1})
        self.assertEqual(saved.steps[0].status, 'complete')
        self.assertIsNone(receipt.source_run_id)
        self.assertEqual((receipt.source_attribution, receipt.source_license, receipt.source_scope),
                         (HIBP_ATTRIBUTION, HIBP_LICENSE, 'global-catalog'))
        self.assertEqual(len(self.repository.latest_snapshot().notices), 2)
        before = self.path.read_bytes()
        with self.assertRaises((ValidationError, StorageError)):
            self.service(source).refresh(operation=token)
        self.assertEqual(source.calls, 1)
        self.assertEqual(self.path.read_bytes(), before)

    def test_complete_and_failed_receipt_errors_roll_back_source_and_step_together(self):
        for response, status in ((feed(), 'complete'), (SourceError('Kaynak erişim hatası.'), 'failed')):
            with self.subTest(status=status):
                details, token = self.start()
                before = self.counts()
                def reject(connection, operation, *, result_kind, result_id, result_status):
                    self.assertEqual((operation, result_kind, result_status), (token, 'public_notice_run', status))
                    self.assertTrue(connection.in_transaction)
                    self.assertIsNotNone(connection.execute('SELECT id FROM public_notice_runs WHERE id=?', (result_id,)).fetchone())
                    receipt = record_collection_step_receipt(
                        connection, operation, result_kind=result_kind, result_id=result_id, result_status=result_status,
                    )
                    self.assertEqual(receipt.source_scope, 'global-catalog')
                    self.assertEqual(connection.execute('SELECT status FROM collection_session_steps WHERE id=?', (token.step_id,)).fetchone()[0], status)
                    with closing(sqlite3.connect(self.path)) as outside:
                        self.assertIsNone(outside.execute('SELECT id FROM public_notice_runs WHERE id=?', (result_id,)).fetchone())
                        self.assertIsNone(outside.execute('SELECT step_id FROM collection_step_receipts WHERE step_id=?', (token.step_id,)).fetchone())
                        self.assertEqual(outside.execute('SELECT status FROM collection_session_steps WHERE id=?', (token.step_id,)).fetchone()[0], 'running')
                    raise ReceiptFailure('Controlled receipt failure after all source/receipt writes')
                with patch('xti.adapters.sqlite_public_notices.record_collection_step_receipt', side_effect=reject):
                    with self.assertRaises(ReceiptFailure):
                        self.service(FakeSource(response)).refresh(operation=token)
                self.assertEqual(self.counts(), before)
                self.assertEqual(self.history.get(details.session.id).steps[0].status, 'running')
                self.history.recover_interrupted(recorded_at=(NOW + timedelta(seconds=2)).isoformat())

    def test_failure_receipt_keeps_last_catalog_and_retry_preserves_failed_run(self):
        baseline = self.repository.apply(feed(), started_at=NOW.isoformat(), finished_at=NOW.isoformat())
        details, token = self.start()
        failed = self.service(FakeSource(SourceError('Kaynak süre sınırı.'))).refresh(operation=token)
        saved = self.history.get(details.session.id)
        self.assertEqual((saved.steps[0].status, saved.receipts[0].result_id), ('failed', failed.run.id))
        self.assertTrue(all(value == 0 for _, value in saved.receipts[0].summary))
        self.assertEqual(self.repository.latest_snapshot().latest_complete_run.id, baseline.run.id)
        self.history.finish_session(details.session.id, analysis_status='complete', finished_at=(NOW + timedelta(seconds=2)).isoformat())
        plan = self.history.resume_plan(details.session.id)
        self.assertEqual(plan.units, self.plan.units)
        child, new_token = self.start(parent=details.session.id)
        source = FakeSource(feed(item(Title='Updated catalog title')))
        updated = self.service(source).refresh(operation=new_token)
        self.assertEqual(source.calls, 1)
        self.assertNotEqual(updated.run.id, failed.run.id)
        self.assertEqual(self.history.get(details.session.id).receipts[0].result_id, failed.run.id)
        self.assertEqual(self.history.get(child.session.id).receipts[0].result_id, updated.run.id)
        self.assertFalse(updated.is_baseline)
        self.assertEqual(dict(self.history.get(child.session.id).receipts[0].summary)["is_baseline"], 0)

    def test_failure_before_first_success_does_not_consume_initial_catalog_baseline(self):
        first, token = self.start()
        self.service(FakeSource(SourceError('İlk kaynak isteği başarısız.'))).refresh(operation=token)
        receipt = self.history.get(first.session.id).receipts[0]
        self.assertEqual(dict(receipt.summary)['is_baseline'], 0)
        self.history.finish_session(first.session.id, analysis_status='complete', finished_at=(NOW + timedelta(seconds=2)).isoformat())
        child, token = self.start(parent=first.session.id)
        successful = self.service(FakeSource()).refresh(operation=token)
        self.assertTrue(successful.is_baseline)
        self.assertEqual(dict(self.history.get(child.session.id).receipts[0].summary)['is_baseline'], 1)

    def test_commit_then_outer_interrupt_is_retained_without_another_fetch(self):
        details, token = self.start()
        source = FakeSource()
        apply = self.repository.apply
        def interrupted(*args, **kwargs):
            apply(*args, **kwargs)
            raise KeyboardInterrupt
        with patch.object(self.repository, 'apply', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.service(source).refresh(operation=token)
        saved = self.history.get(details.session.id)
        receipt = saved.receipts[0]
        self.assertEqual(saved.steps[0].status, 'complete')
        self.history.recover_interrupted(recorded_at=(NOW + timedelta(seconds=2)).isoformat())
        self.assertEqual(self.history.resume_plan(details.session.id).units, ())
        child = self.history.begin(self.plan, started_at=(NOW + timedelta(seconds=3)).isoformat(), parent_id=details.session.id)
        self.assertEqual(child.steps, ())
        complete = self.history.finish_session(child.session.id, analysis_status='complete', finished_at=(NOW + timedelta(seconds=4)).isoformat())
        self.assertEqual(complete.session.status, 'complete')
        self.assertEqual(complete.retained[0].receipt, receipt)
        self.assertEqual(source.calls, 1)
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_invalid_tokens_fail_before_source_call_and_without_any_write(self):
        details, valid = self.start()
        invalid = (
            object(), replace(valid, session_id=str(uuid4())), replace(valid, step_id=str(uuid4())),
            replace(valid, target_sha256='0' * 64), replace(valid, target_sha256='NOT-A-HASH'),
            replace(valid, depends_on_step_id=str(uuid4())),
            replace(valid, session_id=valid.session_id.upper()),
        )
        before = self.path.read_bytes()
        for token in invalid:
            with self.subTest(token=token):
                source = FakeSource()
                with self.assertRaises((ValidationError, StorageError)):
                    self.service(source).refresh(operation=token)
                self.assertEqual(source.calls, 0)
                self.assertEqual(self.path.read_bytes(), before)
        self.history.finish_session(details.session.id, analysis_status='pending', finished_at=NOW.isoformat(), stop_reason='interrupted')
        with self.assertRaises((ValidationError, StorageError)):
            self.service(FakeSource()).refresh(operation=valid)

    def test_pending_wrong_source_and_wrong_contract_are_not_preflight_authorized(self):
        for plan, start_step in (
            (self.plan, False),
            (CollectionFrozenPlan(CollectionProfileDefinition('example.com', task_ids=('ioc-feodo',)), (
                CollectionFrozenUnit('ioc-feodo', 'ioc', 'feodo', 'example.com', None, 'feed-v1'),
            )), True),
            (replace(self.plan, units=(replace(self.plan.units[0], contract_version='wrong-public-contract'),)), True),
        ):
            with self.subTest(kind=plan.units[0].kind, contract=plan.units[0].contract_version, started=start_step):
                details = self.history.begin(plan, started_at=NOW.isoformat())
                step = details.steps[0]
                token = (self.history.start_step(details.session.id, step.id, started_at=NOW.isoformat()) if start_step
                         else CollectionOperationToken(details.session.id, step.id, step.target_sha256))
                source = FakeSource()
                before = self.path.read_bytes()
                with self.assertRaises((ValidationError, StorageError)):
                    self.service(source).refresh(operation=token)
                self.assertEqual(source.calls, 0)
                self.assertEqual(self.path.read_bytes(), before)
                self.history.recover_interrupted(recorded_at=(NOW + timedelta(seconds=2)).isoformat())

    def test_changed_operation_after_preflight_cannot_save_a_source_result(self):
        details, token = self.start()
        source = FakeSource()
        source.before_return = lambda: self.history.stop_step_without_result(
            token, status='interrupted', error_code='interrupted', finished_at=NOW.isoformat(),
        )
        with self.assertRaises((StorageError, ValidationError)):
            self.service(source).refresh(operation=token)
        self.assertEqual((source.calls, self.counts()), (1, (0, 0, 0)))
        self.assertEqual(self.history.get(details.session.id).steps[0].status, 'interrupted')

    def test_source_integrity_failure_blocks_network_and_collection_history_read(self):
        details, token = self.start()
        result = self.service(FakeSource()).refresh(operation=token)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE public_notice_runs SET snapshot_sha256=? WHERE id=?', ('0' * 64, result.run.id))
        before = self.path.read_bytes()
        source = FakeSource()
        with self.assertRaises(StorageError):
            self.service(source).refresh()
        self.assertEqual(source.calls, 0)
        for action in (lambda: self.history.get(details.session.id),
                       lambda: self.history.recover_interrupted(recorded_at=NOW.isoformat())):
            with self.assertRaises(StorageError):
                action()
        self.assertEqual(self.path.read_bytes(), before)

    def test_receipt_summary_cannot_be_rehashed_to_fake_catalog_counts(self):
        details, token = self.start()
        self.service(FakeSource()).refresh(operation=token)
        receipt = self.history.get(details.session.id).receipts[0]
        counters = dict(receipt.summary)
        counters['notice_count'] = 99
        encoded = summary_json(counters.items())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE collection_step_receipts SET summary_json=?,summary_sha256=? WHERE step_id=?',
                               (encoded, sha256_text(encoded), token.step_id))
        with self.assertRaises(StorageError):
            self.history.get(details.session.id)

    def test_wrong_result_kind_status_or_noncanonical_id_cannot_complete_notice_step(self):
        old = self.repository.apply(feed(), started_at=NOW.isoformat(), finished_at=NOW.isoformat())
        details, token = self.start()
        for kind, identifier, status in (
            ('feed_run', old.run.id, 'complete'), ('public_notice_run', old.run.id, 'failed'),
            ('public_notice_run', old.run.id.upper(), 'complete'),
        ):
            with self.subTest(kind=kind, status=status, identifier=identifier):
                with self.storage._connection() as connection:
                    connection.execute('BEGIN IMMEDIATE')
                    with self.assertRaises((ValidationError, StorageError)):
                        record_collection_step_receipt(connection, token, result_kind=kind,
                                                       result_id=identifier, result_status=status)
                    connection.rollback()
        self.assertEqual(self.history.get(details.session.id).steps[0].status, 'running')
        self.assertEqual(self.counts(), (1, 1, 0))

    def test_run_predating_step_cannot_be_attached_as_a_new_collection_result(self):
        old = self.repository.apply(feed(), started_at=NOW.isoformat(), finished_at=NOW.isoformat())
        details, token = self.start(at=NOW + timedelta(seconds=2))
        with self.storage._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            with self.assertRaises(StorageError):
                record_collection_step_receipt(connection, token, result_kind='public_notice_run',
                                               result_id=old.run.id, result_status='complete')
            connection.rollback()
        self.assertEqual(self.history.get(details.session.id).receipts, ())

    def test_standalone_refresh_remains_supported_without_collection_tables_changing(self):
        result = self.service(FakeSource()).refresh(item_limit=1)
        self.assertEqual(self.counts(), (1, 1, 0))
        self.assertEqual(self.repository.latest_snapshot().latest_complete_run.id, result.run.id)
        self.assertEqual(self.history.list().sessions, ())

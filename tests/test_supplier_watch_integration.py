"""Supplier evidence joins inbox and collection atomically, without external delivery."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import unittest
from unittest.mock import patch

from tests import test_supplier_watches as fixtures
from tests.test_public_notices import NOW, item
from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_status import SQLiteStatusRepository
from xti.domain.collection_history import CollectionFrozenPlan, CollectionFrozenUnit
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.domain.public_notices import HIBP_CONTRACT_VERSION
from xti.interfaces.cli import main
from xti.interfaces.inbox import detail_lines, page_lines


class SupplierWatchIntegrationTests(unittest.TestCase):
    setUp = fixtures.SupplierWatchTests.setUp
    add_supplier = fixtures.SupplierWatchTests.add_supplier
    configure = fixtures.SupplierWatchTests.configure
    apply = fixtures.SupplierWatchTests.apply
    last = fixtures.SupplierWatchTests.last
    execute = fixtures.SupplierWatchTests.execute
    counts = fixtures.SupplierWatchTests.counts

    def notification(self):
        watch = self.configure()
        self.apply()
        self.apply(item(PwnCount=23456), item('New', 'example.com'))
        report = self.last(watch)
        return watch, report, SQLiteInboxRepository(self.path)

    def test_inbox_preserves_before_after_read_state_and_status_totals(self):
        _, report, inbox = self.notification()
        before = self.path.read_bytes()
        page = inbox.list()
        self.assertEqual((page.total_count, page.unread_count, page.matching_count), (1, 1, 1))
        self.assertEqual(page.items[0].supplier_change, report)
        details = inbox.get(report.notification_id)
        self.assertEqual(details.notification.supplier_watch_run_id, report.run.id)
        self.assertEqual(details.notification.event_type, 'supplier_watch_changed')
        self.assertEqual(details.supplier_change, report)
        text = '\n'.join(detail_lines(details))
        for value in ('12345', '23456', 'Example Holding', 'Have I Been Pwned', report.run.source_run_id):
            self.assertIn(value, text)
        self.assertIn('Tedarikçi', '\n'.join(page_lines(page, status='unread', next_command=None)))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.storage.inspect()['notification_count'], 1)
        status = SQLiteStatusRepository(self.path).snapshot(('crtsh',), None, 20)
        self.assertEqual((status.notification_count, status.unread_notification_count), (1, 1))
        self.assertEqual(self.storage.inspect()['supplier_watch_notification_count'], 1)
        self.assertEqual(inbox.mark((report.notification_id,), True, NOW.isoformat()).changed_count, 1)
        self.assertEqual(inbox.mark((report.notification_id,), True, NOW.isoformat()).changed_count, 0)
        self.assertEqual(inbox.list().unread_count, 0)
        self.assertEqual(self.storage.inspect()['unread_notification_count'], 0)
        self.assertEqual(SQLiteStatusRepository(self.path).snapshot(('crtsh',), None, 20).unread_notification_count, 0)
        self.assertEqual(inbox.get(report.notification_id).supplier_change, report)
        self.assertEqual(inbox.mark((report.notification_id,), False, NOW.isoformat()).changed_count, 1)

    def test_historical_inbox_is_unchanged_after_supplier_rename_and_source_removal(self):
        _, report, inbox = self.notification()
        self.suppliers.update(self.supplier.id, name='Renamed supplier', reason='Current display name changed.')
        self.apply(item('Other', 'other.example'))
        historical = inbox.get(report.notification_id).supplier_change
        self.assertEqual(historical, report)
        self.assertEqual(historical.scope['supplier']['display_name'], 'Example Holding')
        self.assertEqual(inbox.list().total_count, 1)

    def test_corrupt_historical_supplier_evidence_prevents_mark_and_http(self):
        _, report, inbox = self.notification()
        self.execute('UPDATE supplier_watch_runs SET scope_sha256=? WHERE sequence=1', ('0' * 64,))
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            inbox.mark((report.notification_id,), True, NOW.isoformat())
        for arguments in (('notices', 'refresh'), ('ransomware', 'refresh'),
                          ('ransomware', 'refresh', '--source', 'ransomlook')):
            output, errors = StringIO(), StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                code = main(['--data-dir', str(self.data), '--json', *arguments])
            # A socket call would raise AssertionError from the offline fixture.
            self.assertEqual(code, 1, (arguments, output.getvalue(), errors.getvalue()))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIsNone(self.execute('SELECT read_at FROM supplier_watch_notifications')[0][0])

    def test_missing_source_binding_is_rejected_before_inbox_marks(self):
        _, report, inbox = self.notification()
        self.execute("UPDATE supplier_watch_runs SET public_notice_run_id='00000000-0000-0000-0000-000000000001' WHERE sequence=2")
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            inbox.mark((report.notification_id,), True, NOW.isoformat())
        self.assertEqual(self.path.read_bytes(), before)

    def test_receipt_failure_rolls_back_already_inserted_source_watch_and_notification(self):
        self.configure(); self.apply()
        self.storage.add('example.com')
        history = SQLiteCollectionHistoryRepository(self.path)
        definition = CollectionProfileDefinition('example.com', task_ids=('notices-hibp',))
        plan = CollectionFrozenPlan(definition, (
            CollectionFrozenUnit('notices-hibp', 'public_notice', 'hibp', 'example.com', None, HIBP_CONTRACT_VERSION),
        ))
        session = history.begin(plan, started_at=NOW.isoformat())
        token = history.start_step(session.session.id, session.steps[0].id, started_at=NOW.isoformat())
        before = self.counts()
        def fail(connection, *args, **kwargs):
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM public_notice_runs').fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM supplier_watch_runs').fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM supplier_watch_notifications').fetchone()[0], 1)
            raise RuntimeError('Controlled receipt failure after source/watch writes')
        with patch('xti.adapters.sqlite_public_notices.record_collection_step_receipt', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'Controlled receipt failure'):
                self.apply(item(PwnCount=23456), operation=token)
        self.assertEqual(self.counts(), before)
        self.assertEqual(history.get(session.session.id).receipts, ())
        source_run = self.apply(item(PwnCount=23456), operation=token).run
        self.assertEqual(history.get(session.session.id).receipts[0].result_id, source_run.id)
        self.assertEqual(SQLiteInboxRepository(self.path).list().total_count, 1)

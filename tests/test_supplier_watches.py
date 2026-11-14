"""Offline supplier epochs, source evidence, pagination and atomic notification tests."""
from contextlib import closing, redirect_stdout, redirect_stderr
from dataclasses import asdict
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_suppliers import SQLiteSupplierRepository
from xti.adapters.sqlite_supplier_history import read_supplier_history
from xti.adapters.sqlite_supplier_watches import SQLiteSupplierWatchRepository, process_supplier_watches
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.application.suppliers import SupplierService
from xti.application.public_notices import PublicNoticeService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from xti.interfaces.supplier_watches import watch_run_lines
from tests.test_public_notices import NOW, feed, item
from tests.test_threatcluster_ransomware import claim, content as threat_content
from tests.test_ransomlook_ransomware import post, content as ransom_content


class SupplierWatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name) / 'data'
        self.path = self.data / 'xti.db'
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.suppliers = SupplierService(SQLiteSupplierRepository(self.path), clock=lambda: NOW)
        self.supplier = self.add_supplier()
        self.repository = SQLiteSupplierWatchRepository(self.path)
        self.hibp = SQLitePublicNoticeRepository(self.path)
        self.threatcluster = SQLiteRansomwareClaimRepository(self.path)
        self.ransomlook = SQLiteRansomLookClaimRepository(self.path)
        self.enterContext(patch('socket.socket.connect', side_effect=AssertionError('Offline tests')))

    def add_supplier(self, name='Example Holding', domain='example.com'):
        return self.suppliers.add(name, domain=domain, relationship_type='cloud', criticality='high',
                                  reason='Explicit supplier relationship.').supplier

    def configure(self, source='hibp', enabled=True, supplier=None):
        return self.repository.configure((supplier or self.supplier).id, source=source, enabled=enabled,
            reason='Explicit source monitoring choice.', recorded_at=NOW.isoformat()).watch

    def apply(self, *records, **kwargs):
        return self.hibp.apply(feed(*(records or [item()])), started_at=NOW.isoformat(), finished_at=NOW.isoformat(), **kwargs)

    def apply_threat(self, *records):
        value = parse_threatcluster_ransomware_response(threat_content(list(records or [claim()]),
            generated_at=NOW.isoformat()), fetched_at=NOW)
        return self.threatcluster.apply(value, started_at=NOW.isoformat(), finished_at=NOW.isoformat(), item_limit=1)

    def apply_ransom(self, *records):
        value = parse_ransomlook_ransomware_response(ransom_content(list(records or [post(discovered=NOW.isoformat())])), fetched_at=NOW)
        return self.ransomlook.apply(value, started_at=NOW.isoformat(), finished_at=NOW.isoformat(), item_limit=1)

    def last(self, watch, **kwargs):
        runs = self.repository.show(watch.id).runs
        return self.repository.run_show(runs[0].id, **kwargs)

    def execute(self, sql, params=()):
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(sql, params).fetchall()
            connection.commit()
            return rows

    def counts(self):
        return tuple(self.execute(f'SELECT COUNT(*) FROM {table}')[0][0] for table in (
            'public_notice_runs', 'public_notice_changes', 'supplier_watch_runs', 'supplier_watch_notifications'))

    def test_opt_in_initial_baseline_exact_domain_and_full_catalog_not_preview(self):
        self.apply()
        self.assertEqual(self.repository.list().total_count, 0)
        watch = self.configure()
        self.apply(item(), item('Child', 'sub.example.com'), item('NameGuess', '', Title='Example Holding'),
                   item('SecondExact', 'example.com'), item('Other', 'other.example'), item_limit=1)
        report = self.last(watch)
        self.assertEqual((report.run.matched_count, report.run.baseline_count), (2, 2))
        self.assertEqual({value.record_id for value in report.items}, {'Example', 'SecondExact'})
        self.assertIsNone(report.notification_id)
        self.assertEqual({value.match_after for value in report.items}, {('domain:exact',)})
        self.apply(item(), item('SecondExact', 'example.com'))
        self.assertEqual(self.last(watch).run.unchanged_count, 2)
        self.assertIsNone(self.last(watch).notification_id)

    def test_added_updated_before_after_flags_source_identity_and_single_notification(self):
        watch = self.configure(); self.apply()
        self.apply(item(PwnCount=23456, IsVerified=False, IsFabricated=True), item('New', 'example.com'))
        report = self.last(watch)
        self.assertEqual((report.run.added_count, report.run.updated_count), (1, 1))
        self.assertEqual(self.counts()[-1], 1)
        self.assertEqual(report.source.source_key, 'hibp')
        update = next(value for value in report.items if value.action == 'updated')
        self.assertEqual((update.before['pwn_count'], update.after['pwn_count']), (12345, 23456))
        self.assertFalse(update.after['is_verified']); self.assertTrue(update.after['is_fabricated'])
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            evidence = self.repository.notification_evidence(connection, report.notification_id)
        self.assertEqual(evidence, report)
        self.assertEqual(report.source_run['id'], report.run.source_run_id)
        self.assertEqual(report.previous_source_run['id'], self.repository.run_show(report.run.previous_run_id).run.source_run_id)

    def test_supplier_metadata_update_keeps_comparison_and_historical_identity(self):
        watch = self.configure(); self.apply()
        first = self.last(watch)
        self.suppliers.update(self.supplier.id, criticality='critical', reason='Priority reviewed locally.')
        self.apply(item(PwnCount=23456))
        report = self.last(watch)
        self.assertEqual(report.run.updated_count, 1)
        self.assertEqual(report.scope['supplier']['criticality'], 'critical')
        self.assertEqual(self.repository.run_show(first.run.id), first)
        self.assertEqual(first.scope['supplier']['criticality'], 'high')

    def test_rename_and_return_to_former_name_are_quiet_new_identity_epochs(self):
        watch = self.configure(); self.apply()
        self.suppliers.update(self.supplier.id, name='Renamed Company', reason='Name corrected locally.')
        self.apply(item(PwnCount=23456))
        self.assertEqual(self.last(watch).run.baseline_count, 1)
        self.suppliers.update(self.supplier.id, name='Temporary Name', reason='Name corrected locally.')
        self.suppliers.update(self.supplier.id, name='Renamed Company', reason='Name corrected locally.')
        self.apply(item(PwnCount=34567))
        self.assertEqual(self.last(watch).run.baseline_count, 1)
        self.assertIsNone(self.last(watch).notification_id)

    def test_disabled_and_reenabled_watch_then_supplier_revocation_reactivation(self):
        watch = self.configure(); self.apply()
        self.configure(enabled=False); self.apply(item(PwnCount=23456))
        self.assertEqual(self.repository.show(watch.id).total_run_count, 1)
        self.configure(); self.apply(item(PwnCount=34567))
        self.assertEqual(self.last(watch).run.baseline_count, 1)
        self.suppliers.revoke(self.supplier.id, reason='Supplier relation withdrawn.')
        self.apply(item(PwnCount=45678))
        self.assertEqual(self.repository.show(watch.id).total_run_count, 2)
        with self.assertRaises(ValidationError):
            self.configure()
        self.add_supplier(); self.apply(item(PwnCount=56789))
        self.assertEqual(self.last(watch).run.baseline_count, 1)
        self.assertIsNone(self.last(watch).notification_id)

    def test_removed_only_failure_and_same_exact_source_run_are_silent(self):
        watch = self.configure(); self.apply()
        self.apply(item('Other', 'other.example'))
        report = self.last(watch)
        self.assertEqual(report.run.removed_count, 1)
        self.assertIsNone(report.notification_id)
        before = self.counts()
        self.hibp.record_failure(started_at=NOW.isoformat(), finished_at=NOW.isoformat(), error='Catalog unavailable.')
        details = self.repository.show(watch.id)
        self.assertEqual(details.source.latest_run['status'], 'failed')
        self.assertEqual(details.source.latest_complete_run['id'], report.run.source_run_id)
        self.assertEqual(self.counts()[1:], before[1:])
        applied = self.apply()
        self.assertEqual(self.last(watch).run.added_count, 1)
        before = self.counts()
        with self.storage._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            process_supplier_watches(connection, 'hibp', applied.run.id)
            connection.commit()
        self.assertEqual(self.counts(), before)

    def test_independent_sources_exact_matches_and_same_name_ambiguity(self):
        other = self.add_supplier(domain='other.example')
        first = self.configure('threatcluster'); second = self.configure('ransomlook'); third = self.configure()
        self.configure('threatcluster', supplier=other)
        self.apply_threat(claim(website='www.example.com'), claim('Different name', group='other', website='example.com'),
                         claim('Example Holding Ltd', website='example.com.evil.example'))
        self.assertEqual(self.repository.show(second.id).total_run_count, 0)
        report = self.last(first)
        self.assertEqual(report.run.matched_count, 2)
        self.assertEqual(report.scope['same_name_supplier_count'], 2)
        self.assertEqual({value.match_after for value in report.items}, {('victim:exact', 'website:subdomain'), ('website:exact',)})
        self.apply_ransom(post(discovered=NOW.isoformat()), post('Example Holding Ltd', group='other', discovered=NOW.isoformat()))
        self.assertEqual(self.last(second).run.matched_count, 1)
        self.apply(); self.assertEqual(self.last(third).run.matched_count, 1)
        self.apply_threat(claim(website='www.example.com', country='GB'), claim('Different name', group='other', website='example.com'))
        self.assertEqual(self.last(first).run.updated_count, 1)
        self.assertEqual(self.repository.show(second.id).total_run_count, 1)
        self.assertEqual(self.repository.show(third.id).total_run_count, 1)
        self.assertIn('Ad eşleşmesi belirsiz', '\n'.join(watch_run_lines(self.last(first))))

    def test_readonly_pagination_full_counts_and_bounded_inbox_details(self):
        watch = self.configure(); self.apply()
        self.apply(item(), *(item(f'Entry{index:02d}', 'example.com') for index in range(23)))
        before = self.path.read_bytes()
        first = self.last(watch); remaining = self.repository.run_show(first.run.id, offset=20)
        self.assertEqual((first.total_item_count, len(first.items), len(remaining.items)), (24, 20, 4))
        self.assertEqual(len({value.record_id for value in first.items + remaining.items}), 24)
        self.assertEqual(self.repository.show(watch.id, run_limit=1, run_offset=1).total_run_count, 2)
        self.assertEqual(self.repository.list(offset=1).watches, ())
        self.assertEqual(self.path.read_bytes(), before)
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            evidence = self.repository.notification_evidence(connection, first.notification_id)
        self.assertEqual(evidence, first)

    def test_notification_insert_failure_rolls_back_source_catalog_and_watch(self):
        self.configure(); self.apply()
        before = self.counts()
        def fail_after_writes(connection):
            self.assertTrue(connection.in_transaction)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM public_notice_runs').fetchone()[0], before[0] + 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM supplier_watch_runs').fetchone()[0], before[2] + 1)
            raise StorageError('Injected notification persistence failure.')
        with patch('xti.adapters.sqlite_supplier_watches.next_notification_sequence', side_effect=fail_after_writes) as allocator:
            with self.assertRaises(StorageError):
                self.apply(item(PwnCount=23456))
            allocator.assert_called_once()
        self.assertEqual(self.counts(), before)
        self.apply(item(PwnCount=23456))
        self.assertEqual(self.counts()[-1], 1)

    def test_record_leaving_match_preserves_new_source_metadata(self):
        watch = self.configure(); self.apply()
        self.apply(item(domain='outside.example'))
        report = self.last(watch)
        self.assertEqual(report.run.removed_count, 1)
        self.assertEqual(report.items[0].before['domain'], 'example.com')
        self.assertEqual(report.items[0].after['domain'], 'outside.example')
        self.assertEqual(report.items[0].match_after, ())
        self.assertIsNone(report.notification_id)

    def test_corrupted_hidden_history_fails_closed_and_no_read_writes(self):
        watch = self.configure(); self.apply(); self.apply(item(PwnCount=23456))
        self.execute("UPDATE supplier_watch_runs SET scope_sha256=? WHERE sequence=1", ('0' * 64,))
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.repository.list(offset=500)
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(StorageError):
            self.apply(item(PwnCount=34567))
        self.assertEqual(self.path.read_bytes(), before)

    def test_deleted_final_history_and_missing_notification_are_detected(self):
        watch = self.configure(); self.apply(); self.apply(item(PwnCount=23456))
        self.execute('DELETE FROM supplier_watch_notifications')
        with self.assertRaises(StorageError):
            self.repository.show(watch.id)
        self.execute('DELETE FROM supplier_watch_runs WHERE sequence=2')
        with self.assertRaises(StorageError):
            self.repository.show(watch.id)

    def test_supplier_history_rejects_materialized_tampering_and_retains_clock_rollback(self):
        watch = self.configure(); self.apply()
        rolled = SupplierService(SQLiteSupplierRepository(self.path), clock=lambda: NOW - timedelta(days=1))
        rolled.update(self.supplier.id, criticality='critical', reason='Backdated local clock update.')
        self.apply(item(PwnCount=23456))
        self.assertEqual(self.last(watch).run.updated_count, 1)
        self.execute("UPDATE suppliers SET display_name='Changed without event' WHERE id=?", (self.supplier.id,))
        with self.assertRaises(StorageError):
            self.repository.list()

    def test_cli_enable_is_local_and_historical_json_and_text_expose_records(self):
        def command(*args):
            output, error = StringIO(), StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                code = main(['--data-dir', str(self.data), *args])
            self.assertEqual(code, 0, error.getvalue())
            return output.getvalue()
        result = json.loads(command('--json', 'suppliers', 'watch', 'enable', self.supplier.id, '--source', 'hibp'))['data']
        watch_id = result['watch']['id']
        self.assertEqual(self.counts(), (0, 0, 0, 0))
        # CLI uses wall-clock; source fixture must follow its explicit enable timestamp.
        timestamp = result['watch']['updated_at']
        self.hibp.apply(feed(), started_at=timestamp, finished_at=timestamp)
        report = self.repository.show(watch_id)
        value = json.loads(command('--json', 'suppliers', 'watch-run-show', report.runs[0].id))['data']
        self.assertEqual(value['items'][0]['record_id'], 'Example')
        rendered = command('suppliers', 'watch-run-show', report.runs[0].id)
        self.assertIn('12345', rendered); self.assertIn('Have I Been Pwned', rendered)
        self.assertIn(watch_id, command('suppliers', 'watch', 'show', watch_id))

    def test_invalid_source_or_limits_do_not_write(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.configure('other')
        for kwargs in ({'limit': 0}, {'offset': -1}, {'active_only': 1}):
            with self.assertRaises(ValidationError):
                self.repository.list(**kwargs)
        self.assertEqual(self.path.read_bytes(), before)

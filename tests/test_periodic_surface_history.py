"""Observed values preserve baseline provenance and never turn failed probes into removals."""
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
import json
import sqlite3
import unittest

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.adapters.sqlite_cname import SQLiteSurfaceCnameRepository
from xti.application.surface import SurfaceService
from xti.domain.cname import CnameHop
from xti.interfaces.periodic_changes import periodic_changes_lines
from tests import test_periodic_changes as base
from tests.test_surface import result as web_result, certificate
from tests.test_mail import result as mail_result
from tests.test_services import scan_result
from tests.test_cname import cname_result
from tests.test_brand_username_watches import NOW, github
from xti.ports.discovery import SourceError


class PeriodicSurfaceHistoryTests(unittest.TestCase):
    report = base.PeriodicChangesTests.report
    social = base.PeriodicChangesTests.social

    def setUp(self):
        base.PeriodicChangesTests.setUp(self)
        self.surface = SQLiteSurfaceRepository(self.path, clock=lambda: NOW)
        SurfaceService(self.storage, self.surface, clock=lambda: NOW).approve('example.com', 'Yetkili kapsam.')

    def section(self):
        return next(section for section in self.report(domain='example.com').sections if section.family == 'surface')

    def test_web_failure_keeps_last_complete_baseline_and_exact_changed_values(self):
        first = self.surface.append_check(self.asset.id, replace(web_result(), certificate=certificate()))
        self.surface._clock = lambda: NOW + timedelta(minutes=1)
        failed_result = replace(web_result(), dns_status='failed', addresses=(),
                                tls_status='not_checked', http_status='not_checked',
                                http_status_code=None, connected_address=None, errors=('DNS: kaynak yanıt vermedi.',))
        failed = self.surface.append_check(self.asset.id, failed_result)
        self.surface._clock = lambda: NOW + timedelta(minutes=2)
        last = self.surface.append_check(self.asset.id, replace(web_result(addresses=('1.1.1.1',)), certificate=certificate(fingerprint='b' * 64)))
        section = self.section()
        self.assertEqual((section.total_baseline_count, section.total_change_count, section.total_failure_count), (1, 1, 1))
        current, failure = section.changes[0], section.failures[0]
        self.assertEqual((current.record_id, current.previous_record_id, current.previous_run_id), (last.id, first.id, failed.id))
        self.assertEqual((failure.record_id, failure.previous_record_id, failure.value_changes), (failed.id, first.id, ()))
        values = {value.field: (value.before, value.after) for value in current.value_changes}
        self.assertEqual(values['addresses'], (('93.184.216.34',), ('1.1.1.1',)))
        self.assertEqual(values['certificate.sha256'], ('a' * 64, 'b' * 64))
        self.assertEqual(current.source_observed_at, last.result.finished_at)
        self.assertIn('son 100 kontrolün geçmişidir', current.evidence_note)
        rendered = '\n'.join(periodic_changes_lines(self.report(domain='example.com')))
        for value in (first.id, last.id, failed.id, '93.184.216.34 → 1.1.1.1'):
            self.assertIn(value, rendered)

    def test_mail_missing_records_are_observed_changes_but_query_failure_is_not(self):
        repo = SQLiteSurfaceMailRepository(self.path, clock=lambda: NOW)
        first = repo.append_check(self.asset.id, mail_result())
        repo._clock = lambda: NOW + timedelta(minutes=1)
        failed = repo.append_check(self.asset.id, mail_result(mx=(), spf=(), dmarc=(), errors=(
            'MX: timeout', 'SPF: timeout', 'DMARC: timeout',
        )))
        repo._clock = lambda: NOW + timedelta(minutes=2)
        missing = repo.append_check(self.asset.id, mail_result(dmarc=()))
        section = self.section()
        self.assertEqual(section.failures[0].record_id, failed.id)
        current = section.changes[0]
        self.assertEqual((current.record_id, current.previous_record_id), (missing.id, first.id))
        values = {value.field: (value.before, value.after) for value in current.value_changes}
        self.assertEqual(values['dmarc_status'], ('present', 'missing'))
        self.assertEqual(values['dmarc_records'], (('v=DMARC1; p=reject',), ()))
        self.assertEqual(section.failures[0].value_changes, ())

    def test_service_ports_and_cname_targets_keep_actual_source_values(self):
        services = SQLiteSurfaceServiceScanRepository(self.path, clock=lambda: NOW)
        first = services.append_check(self.asset.id, 'Kesin IP için yetkiliyim.', scan_result(opened=(443,)))
        services._clock = lambda: NOW + timedelta(minutes=1)
        changed = services.append_check(self.asset.id, 'Kesin IP için yetkiliyim.', scan_result(opened=(22,), address='1.1.1.1'))
        cname = SQLiteSurfaceCnameRepository(self.path, clock=lambda: NOW)
        def result(target):
            return replace(cname_result(target=target), domain='example.com', chain=(CnameHop('example.com', target),))
        alias = cname.append_check(self.asset.id, result('active.vendor.example'))
        cname._clock = lambda: NOW + timedelta(minutes=1)
        new_alias = cname.append_check(self.asset.id, result('new.vendor.example'))
        changes = {row.evidence_type: row for row in self.section().changes}
        service_row = changes['service']
        self.assertEqual((service_row.record_id, service_row.previous_record_id), (changed.id, first.id))
        values = {value.field: (value.before, value.after) for value in service_row.value_changes}
        self.assertEqual(values['ports.443'], ('open', 'closed'))
        self.assertEqual(values['ports.22'], ('closed', 'open'))
        self.assertIn('aynı sunucunun değiştiği anlamına gelmez', service_row.evidence_note)
        alias_row = changes['cname']
        self.assertEqual((alias_row.record_id, alias_row.previous_record_id), (new_alias.id, alias.id))
        self.assertIn(('target', 'active.vendor.example', 'new.vendor.example'),
                      [(value.field, value.before, value.after) for value in alias_row.value_changes])

    def test_reordered_dns_answers_do_not_invent_changes_and_policy_change_is_new_baseline(self):
        first = web_result(addresses=('1.1.1.1', '8.8.8.8'))
        self.surface.append_check(self.asset.id, first)
        self.surface._clock = lambda: NOW + timedelta(minutes=1)
        self.surface.append_check(self.asset.id, replace(first, addresses=tuple(reversed(first.addresses))))
        self.surface._clock = lambda: NOW + timedelta(minutes=2)
        changed = self.surface.append_check(self.asset.id, replace(first, policy_version='surface-test-v2'))
        section = self.section()
        self.assertEqual((section.total_change_count, section.total_baseline_count), (0, 2))
        latest = next(row for row in section.baselines if row.record_id == changed.id)
        self.assertIsNone(latest.previous_record_id)
        self.assertTrue(all(value.before is None for value in latest.value_changes))
        self.assertIn('politikası değişti', latest.evidence_note)

    def test_last_complete_time_distinguishes_stale_success_from_recent_failure(self):
        self.surface._clock = lambda: NOW - timedelta(days=3)
        complete = self.surface.append_check(self.asset.id, web_result())
        self.surface._clock = lambda: NOW
        failed = self.surface.append_check(self.asset.id, replace(web_result(), errors=('HTTP: süre sınırı.',)))
        report = self.report(domain='example.com')
        coverage = next(item for item in report.coverage if item.source == 'stored-web')
        self.assertEqual((coverage.coverage_state, coverage.window_run_count, coverage.complete_count), ('incomplete', 1, 0))
        self.assertEqual((coverage.last_run_id, coverage.last_complete_run_id), (failed.id, complete.id))
        self.assertEqual(coverage.last_complete_recorded_at, (NOW - timedelta(days=3)).isoformat())
        self.assertIn('Son tamamlanan kayıt: ' + complete.id, '\n'.join(periodic_changes_lines(report)))

    def test_surface_change_forgery_fails_closed_without_modifying_evidence(self):
        first = self.surface.append_check(self.asset.id, web_result())
        self.surface._clock = lambda: NOW + timedelta(minutes=1)
        second = self.surface.append_check(self.asset.id, web_result(addresses=('1.1.1.1',)))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            # Both encoded changes individually validate, but the replacement
            # contradicts the actual preceding result. The report must catch it.
            baseline = connection.execute('SELECT change FROM surface_checks WHERE id=?', (first.id,)).fetchone()[0]
            connection.execute('UPDATE surface_checks SET change=? WHERE id=?', (baseline, second.id))
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.report(domain='example.com')
        self.assertEqual(before, self.path.read_bytes())

    def test_social_profile_transition_embeds_previous_item_and_failed_run_has_no_values(self):
        service = self.social({'GitHub': github()}, SourceError('Kaynak hatası.'), {})
        watch = service.add('Profile evidence', 'samplebrand', platforms=('GitHub',)).watch
        first = service.run(watch.id)
        service.clock = lambda: NOW + timedelta(minutes=1)
        failure = service.run(watch.id)
        service.clock = lambda: NOW + timedelta(minutes=2)
        last = service.run(watch.id)
        section = next(item for item in self.report().sections if item.family == 'username')
        row = section.changes[0]
        self.assertEqual((row.run_id, row.previous_run_id), (last.run.id, first.run.id))
        self.assertEqual(row.previous_record_id, first.items[0].id)
        values = {value.field: (value.before, value.after) for value in row.value_changes}
        self.assertEqual(values['profile_url'], ('https://github.com/samplebrand', None))
        self.assertEqual(section.failures[0].run_id, failure.run.id)
        self.assertEqual(section.failures[0].value_changes, ())

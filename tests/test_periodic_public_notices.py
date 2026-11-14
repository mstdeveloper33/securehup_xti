"""Exact public Domain evidence, baseline semantics and source attribution in periods."""
from contextlib import closing
from dataclasses import asdict, replace
from datetime import timedelta
import hashlib
import json
import sqlite3
import unittest

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.domain.public_notices import PublicNotice, PublicNoticeFeed, HIBP_ATTRIBUTION, HIBP_LICENSE
from xti.interfaces.periodic_changes import periodic_changes_lines
from tests import test_organization_periodic_changes as org_fixture
from tests.test_brand_username_watches import NOW


def notice(identifier='Example', domain='example.com', **changes):
    return replace(PublicNotice(
        identifier, identifier, domain, '2025-01-02', '2025-02-03T04:05:00+00:00',
        '2025-02-03T04:05:00+00:00', 123, ('Email addresses',),
        True, False, False, False, False, False, False, 'Public contributor',
        f'https://haveibeenpwned.com/api/v3/breach/{identifier}',
    ), **changes)


class PeriodicPublicNoticesTests(unittest.TestCase):
    report = org_fixture.OrganizationPeriodicChangesTests.report
    link = org_fixture.OrganizationPeriodicChangesTests.link

    def setUp(self):
        org_fixture.OrganizationPeriodicChangesTests.setUp(self)
        self.notices = SQLitePublicNoticeRepository(self.path)
        self.link()

    def apply(self, *values, minute=0):
        at = NOW + timedelta(minutes=minute)
        digest = hashlib.sha256(json.dumps([asdict(value) for value in values], sort_keys=True).encode()).hexdigest()
        return self.notices.apply(PublicNoticeFeed(at.isoformat(), digest, values),
                                  started_at=at.isoformat(), finished_at=at.isoformat())

    def section(self, **kwargs):
        return next(section for section in self.report(organization_id=self.organization.id, **kwargs).sections if section.family == 'notices')

    def test_first_catalog_is_baseline_with_exact_domain_and_all_source_flags(self):
        selected = notice(is_verified=False, is_fabricated=True, is_stealer_log=True)
        source = self.apply(selected, notice('Other', 'other.example'), notice('example_com', None), notice('Child', 'sub.example.com'))
        section = self.section()
        self.assertEqual((section.total_baseline_count, section.total_change_count), (1, 0))
        row = section.baselines[0]
        self.assertEqual((row.target_record_id, row.run_id, row.source_run_id, row.asset_value), ('Example', source.run.id, source.run.id, 'example.com'))
        flags = dict(row.source_classification)
        self.assertFalse(flags['is_verified'])
        self.assertTrue(flags['is_fabricated'])
        self.assertTrue(flags['is_stealer_log'])
        self.assertEqual((row.source_attribution, row.source_license), (HIBP_ATTRIBUTION, HIBP_LICENSE))
        self.assertEqual(row.source_observed_at, selected.modified_at)
        self.assertEqual(row.recorded_at, NOW.isoformat())
        self.assertEqual(row.commands, (('./xti', 'notices', 'run-show', source.run.id),))
        rendered = '\n'.join(periodic_changes_lines(self.report(organization_id=self.organization.id)))
        for value in (HIBP_ATTRIBUTION, HIBP_LICENSE, 'is_fabricated=True'):
            self.assertIn(value, rendered)
        encoded = json.dumps(asdict(section))
        self.assertNotIn('other.example', encoded)
        self.assertNotIn('sub.example.com', encoded)
        self.assertNotIn('example_com', encoded)

    def test_update_failure_remove_reappear_keep_actual_previous_records_and_global_context(self):
        first = self.apply(notice(), notice('Other', 'other.example'))
        repeat = self.apply(notice(), notice('Other', 'other.example'), minute=1)
        changed_notice = notice(pwn_count=456, modified_at='2025-02-04T04:05:00+00:00')
        update = self.apply(changed_notice, notice('Other', 'other.example'), minute=2)
        failed = self.notices.record_failure(started_at=(NOW + timedelta(minutes=3)).isoformat(),
                                            finished_at=(NOW + timedelta(minutes=3)).isoformat(), error='Kaynak süre sınırı.')
        removal = self.apply(notice('Other', 'other.example'), minute=4)
        reappear = self.apply(changed_notice, notice('Other', 'other.example'), minute=5)
        section = self.section()
        self.assertEqual((section.total_baseline_count, section.total_change_count, section.total_failure_count), (1, 3, 1))
        rows = {row.run_id: row for row in section.changes}
        changed = rows[update.run.id]
        self.assertEqual((changed.previous_record_id, changed.previous_run_id), (first.run.id + ':Example', repeat.run.id))
        self.assertIn(('pwn_count', 123, 456), [(c.field, c.before, c.after) for c in changed.value_changes])
        removed = rows[removal.run.id]
        self.assertEqual((removed.action, removed.previous_record_id, removed.previous_run_id), ('removed', update.run.id + ':Example', update.run.id))
        self.assertIn(('presence', 'reported', 'not_reported'), [(c.field, c.before, c.after) for c in removed.value_changes])
        self.assertFalse(rows[reappear.run.id].is_baseline)
        failure = section.failures[0]
        self.assertEqual((failure.run_id, failure.asset_value, failure.value_changes), (failed.id, None, ()))
        self.assertTrue(failure.shared_scope)
        coverage = [row for row in self.report(organization_id=self.organization.id).coverage if row.family == 'notices']
        self.assertEqual(len(coverage), 1)
        self.assertEqual((coverage[0].scope_kind, coverage[0].complete_count, coverage[0].failed_count), ('global-source', 5, 1))

    def test_publisher_domain_reassignment_preserves_old_exact_relation_without_title_matching(self):
        first = self.apply(notice(), notice('Other', 'other.example'))
        last = self.apply(notice(domain='other.example'), notice('Other', 'other.example'), minute=1)
        section = self.section()
        row = section.changes[0]
        self.assertEqual((row.asset_value, row.target_record_id, row.previous_record_id), ('example.com', 'Example', first.run.id + ':Example'))
        self.assertIn(('domain', 'example.com', 'other.example'), [(c.field, c.before, c.after) for c in row.value_changes])
        self.assertEqual(row.run_id, last.run.id)
        domain_section = next(s for s in self.report(domain='example.com').sections if s.family == 'notices')
        self.assertEqual(domain_section, section)

    def test_notice_category_paging_has_exact_totals_and_corrupt_source_stops_report(self):
        self.apply(*(notice('Example' + str(i)) for i in range(4)))
        page_one = self.section(limit=2)
        page_two = self.section(limit=2, offset=2)
        self.assertEqual((page_one.total_baseline_count, page_two.total_baseline_count), (4, 4))
        self.assertEqual(len({row.record_id for row in page_one.baselines + page_two.baselines}), 4)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE public_notice_changes SET state_sha256=?', ('0' * 64,))
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.report(organization_id=self.organization.id)
        self.assertEqual(before, self.path.read_bytes())

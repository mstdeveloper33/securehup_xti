"""Historical case links survive source changes and complete offline exports."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from io import StringIO
import json
import unittest
from unittest.mock import patch

from xti.adapters.html_report_writer import AtomicHtmlReportWriter
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.adapters.sqlite_organization_report import SQLiteOrganizationReportRepository
from xti.application.cases import CaseEvidenceResolverService, CaseService
from xti.application.organization_export import OrganizationExportService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from xti.interfaces.html_organization_report import HtmlOrganizationReportRenderer
from tests import test_public_notice_watches as fixtures
from tests.test_public_notices import NOW, item


class PublicNoticeExportIntegrationTests(unittest.TestCase):
    add_organization = fixtures.PublicNoticeWatchTests.add_organization
    link_domain = fixtures.PublicNoticeWatchTests.link_domain
    configure = fixtures.PublicNoticeWatchTests.configure
    apply = fixtures.PublicNoticeWatchTests.apply
    show = fixtures.PublicNoticeWatchTests.show
    last = fixtures.PublicNoticeWatchTests.last

    def setUp(self):
        fixtures.PublicNoticeWatchTests.setUp(self)
        self.path = self.path.resolve()
        self.reports = SQLiteOrganizationReportRepository(self.path)
        self.cases = CaseService(SQLiteCaseRepository(self.path), CaseEvidenceResolverService(
            SQLiteCaseEvidenceSourceRepository(self.path)), clock=lambda: NOW)
        self.exporter = OrganizationExportService(self.reports, HtmlOrganizationReportRenderer(),
                                                  AtomicHtmlReportWriter(), clock=lambda: NOW)

    def snapshot(self, organization=None):
        return self.reports.read_complete((organization or self.organization).id,
                                         observed_at=NOW.isoformat(), stale_after_hours=24)

    def invoke(self, *arguments, as_json=True):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(['--data-dir', str(self.path.parent), *(['--json'] if as_json else []), *arguments])
        self.assertEqual(code, 0, errors.getvalue() + output.getvalue())
        return json.loads(output.getvalue())['data'] if as_json else output.getvalue()

    def test_source_and_org_watch_links_preserve_history_and_isolate_shared_case(self):
        other = self.add_organization('Other organization')
        self.link_domain('example.com', other)
        self.configure(); self.configure(organization=other)
        first = self.apply()
        run_a, run_b = self.last(), self.last(other)
        case = self.cases.create('PRIVATE TITLE', summary='PRIVATE SUMMARY', priority='high',
                                 reason='Manual review.').case
        links = []
        for kind, run in (('public_notice', first.run), ('public_notice_watch', run_a.run),
                          ('public_notice_watch', run_b.run)):
            links.append(self.cases.add_evidence(case.id, kind, f'{run.id}:Example',
                                                 reason='Historical source review.').evidence)
        self.apply(item('OtherNotice', 'other.example'))  # Example removed from current catalog.
        snapshot = self.snapshot()
        source_links = next(page for page in snapshot.report.targets[0].sections if page.kind == 'case_links')
        self.assertEqual([record.id for record in source_links.items], [links[0].id])
        self.assertEqual([record.id for record in snapshot.report.public_notice_case_links.items], [links[1].id])
        encoded = json.dumps(asdict(snapshot))
        for forbidden in (other.id, links[2].id, 'PRIVATE TITLE', 'PRIVATE SUMMARY'):
            self.assertNotIn(forbidden, encoded)
        self.organizations.unlink(self.organization.id, self.link.id, reason='Current scope removed.',
                                  recorded_at=NOW.isoformat())
        before = self.path.read_bytes()
        snapshot = self.snapshot()
        self.assertEqual(snapshot.report.targets, ())
        self.assertEqual([record.id for record in snapshot.report.public_notice_case_links.items], [links[1].id])
        self.assertEqual(snapshot.public_notice_watch_runs[-1].scope.members[0].domain, 'example.com')
        evidence = self.invoke('cases', 'evidence-show', case.id, links[1].id)
        self.assertEqual(evidence['snapshot_sha256'], links[1].snapshot_sha256)
        output = self.path.parent / 'organization.html'
        result = self.invoke('organizations', 'export', self.organization.id, '--output', str(output))
        html = output.read_text()
        self.assertIn(links[1].id, html)
        self.assertNotIn(links[2].id, html)
        self.assertIn('Example', html)
        self.assertIn('CC BY 4.0', html)
        self.assertEqual(result['public_notice_watch_run_count'], 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_export_includes_more_than_terminal_limits_and_all_historical_watch_items(self):
        self.configure()
        records = tuple(item(f'Notice{index:04d}') for index in range(510))
        self.apply(*records)
        self.apply(*(dict(record, PwnCount=23456) for record in records))
        snapshot = self.snapshot()
        notices = next(page for page in snapshot.report.targets[0].sections if page.kind == 'public_notices')
        self.assertEqual(len(notices.items), 510)
        self.assertEqual([len(run.items) for run in snapshot.public_notice_watch_runs], [510, 510])
        destination = self.path.parent / 'all.html'
        self.exporter.export(self.organization.id, destination=str(destination))
        content = destination.read_text()
        for record in records:
            self.assertIn(record['Name'], content)
        before = destination.read_bytes()
        with self.assertRaises((ValidationError, OSError)):
            self.exporter.export(self.organization.id, destination=str(destination))
        self.assertEqual(destination.read_bytes(), before)

    def test_all_targets_after_default_first_page_and_capacity_fails_without_artifact(self):
        for index in range(51):
            self.link_domain(f'brand{index:02d}.example')
        snapshot = self.snapshot()
        self.assertEqual((len(snapshot.report.targets), snapshot.report.total_target_count), (52, 52))
        destination = self.path.parent / 'too-large.html'
        before = self.path.read_bytes()
        with patch('xti.adapters.sqlite_organization_report.MAX_EXPORT_TARGETS', 50):
            with self.assertRaises(ValidationError):
                self.exporter.export(self.organization.id, destination=str(destination))
        self.assertFalse(destination.exists())
        self.assertEqual(self.path.read_bytes(), before)

    def test_whole_export_uses_one_read_transaction(self):
        self.configure(); self.apply()
        original = self.reports._storage._connection
        calls = []

        def connection(*args, **kwargs):
            calls.append(kwargs)
            return original(*args, **kwargs)

        with patch.object(self.reports._storage, '_connection', side_effect=connection):
            self.snapshot()
        self.assertEqual(calls, [{'readonly': True}])

"""One mixed collection session never imports unrelated units into an organization."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import unittest

from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_periodic_changes import SQLitePeriodicChangesRepository
from xti.application.organizations import OrganizationService
from xti.application.periodic_changes import PeriodicChangesService
from xti.ports.discovery import SourceError
from tests import test_collection_watch_cli as fixture
from tests.test_organizations_core import RecordingLock


class OrganizationCollectionChangesTests(unittest.TestCase):
    invoke = fixture.CollectionWatchCLITests.invoke
    result = fixture.CollectionWatchCLITests.result
    add_tc = fixture.CollectionWatchCLITests.add_tc

    def setUp(self):
        fixture.CollectionWatchCLITests.setUp(self)
        self.orgs = OrganizationService(SQLiteOrganizationRepository(self.database), RecordingLock())
        self.org = self.orgs.add('Selected organization', reason='Kullanıcının açık seçimi.').organization

    def report(self):
        return PeriodicChangesService(
            SQLitePeriodicChangesRepository(self.database),
            clock=lambda: datetime.now(timezone.utc) + timedelta(minutes=1),
        ).show(organization_id=self.org.id)

    def link(self, kind, value):
        self.orgs.link(self.org.id, kind=kind, value=value, reason='Açık kapsam seçimi.')

    def test_selected_watch_in_unrelated_domain_session_retains_only_its_failed_dependency(self):
        selected = self.add_tc('Selected TC')
        outside = self.add_tc('Unrelated TC', 'Outside Company')
        self.link('ransomware-watch', selected.id)
        self.threatcluster.value = SourceError('Küresel kaynak yenilenemedi.')
        self.result('collect', 'example.com', '--task', 'discover-crtsh',
                    '--ransomware-watch', selected.id, '--ransomware-watch', outside.id,
                    expected_code=3)
        report = self.report()
        section = next(item for item in report.sections if item.family == 'collection')
        self.assertEqual(section.total_failure_count, 1)
        row = section.failures[0]
        self.assertEqual((row.watch_id, row.asset_value, row.action), (selected.id, None, 'skipped'))
        self.assertTrue(row.shared_scope)
        self.assertIn('kuruluş dışı hedefleri', row.evidence_note)
        self.assertIn(row.run_id, row.commands[0])
        encoded = json.dumps(asdict(report))
        self.assertNotIn(outside.id, encoded)
        self.assertNotIn('Outside Company', encoded)
        self.assertFalse(any(item.scope_kind == 'domain' for item in report.coverage))
        source = next(item for item in report.coverage if item.scope_kind == 'global-source')
        self.assertEqual((source.source, source.failed_count, source.complete_count), ('threatcluster', 1, 0))
        watch = next(item for item in report.coverage if item.scope_kind == 'watch')
        self.assertEqual((watch.scope_id, watch.coverage_state), (selected.id, 'no_history'))

    def test_domain_link_does_not_import_failed_unlinked_watch_from_same_session(self):
        outside = self.add_tc('Unlinked TC', 'Outside Company')
        self.link('domain', 'example.com')
        self.threatcluster.value = SourceError('Küresel kaynak yenilenemedi.')
        self.result('collect', 'example.com', '--task', 'discover-crtsh',
                    '--ransomware-watch', outside.id, expected_code=3)
        report = self.report()
        for item in report.sections:
            self.assertEqual(item.total_failure_count, 0)
        self.assertNotIn(outside.id, json.dumps(asdict(report)))
        self.assertFalse(any(item.source == 'threatcluster' for item in report.coverage))
        discovery = next(item for item in report.coverage if item.family == 'surface' and item.source == 'crt.sh')
        self.assertEqual((discovery.scope_id, discovery.complete_count), ('example.com', 1))

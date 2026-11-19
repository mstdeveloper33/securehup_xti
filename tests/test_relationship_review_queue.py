"""Changed and missing evidence asks for review without overwriting human decisions."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from xti.domain.assets import ValidationError
from xti.domain.reports import ReportError
from tests import test_evidence_delivery as evidence


class RelationshipQueueTests(unittest.TestCase):
    def setUp(self):
        self.f = evidence.EvidenceTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.row = self.f.candidate()
        self.f.review(self.row)

    def queue(self, **options):
        return self.f.service.execute('relationships.queue', **options)

    def change_report(self):
        self.f.f.f.apply(replace(self.f.f.item, summary='Corrected text with 192.0.2.10 and suspect[.]example'))
        self.f.f.capture('corrected')

    def test_changed_evidence_enters_queue_then_explicit_re_review_resolves_it(self):
        self.assertEqual(self.queue()['pending_in_window'], 0)
        self.change_report()
        before = self.f.f.path.read_bytes()
        data = self.queue()
        self.assertEqual(data['pending_in_window'], 1)
        row = data['records'][0]
        self.assertEqual(row['reason'], 'historical_evidence')
        self.assertEqual(row['previous']['decision'], 'accepted')
        self.assertFalse(row['automatic_decision'])
        self.assertEqual(before, self.f.f.path.read_bytes())
        current = next(row for row in self.f.service.execute('relationships.candidates', **evidence.ROOT)['records'] if row['id'] == self.row['id'])
        self.f.review(current, expected_revision=1, decision='uncertain', idempotency_key='review-corrected')
        self.assertEqual(self.queue()['records'], [])
        history = self.f.service.execute('relationships.show', identifier=self.row['id'])['record']['history']
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]['request']['evidence_sha256'], self.row['evidence_sha256'])

    def test_partial_missing_proof_is_indeterminate_and_decision_is_preserved(self):
        with patch('xti.adapters.sqlite_evidence.relationship_rows', return_value=([], SimpleNamespace(limitations=('node_limit',)))):
            row = self.queue()['records'][0]
        self.assertEqual(row['reason'], 'indeterminate')
        self.assertFalse(row['review_available'])
        self.assertEqual(row['previous']['decision'], 'accepted')
        with patch('xti.adapters.sqlite_evidence.relationship_rows', return_value=([], SimpleNamespace(limitations=()))):
            self.assertEqual(self.queue()['records'][0]['reason'], 'evidence_outside_current_view')

    def test_withdrawal_removes_queue_item_and_invalidates_decision_page_token(self):
        self.change_report()
        snapshot = self.queue()['snapshot_id']
        self.f.review(self.row, expected_revision=1, decision='withdrawn', idempotency_key='withdraw')
        self.assertEqual(self.queue()['records'], [])
        with self.assertRaises(ReportError):
            self.queue(expected_snapshot=snapshot)

    def test_source_change_keeps_decision_cursor_but_updates_evidence_snapshot(self):
        first = self.queue()
        self.change_report()
        after = self.queue(expected_snapshot=first['snapshot_id'])
        self.assertNotEqual(after['evidence_snapshot_id'], first['evidence_snapshot_id'])
        self.assertEqual(after['pagination_basis'], 'review_records_examined')

    def test_root_filter_and_window_validate_without_scanning_other_scopes(self):
        self.change_report()
        self.assertEqual(self.queue(indicator_type='ipv4', value='192.0.2.11')['total_review_count'], 0)
        for values in ({'indicator_type': 'ipv4'}, {'value': '192.0.2.10'}, {'limit': 21}, {'limit': True}, {'offset': -1}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.queue(**values)

"""Time, exact scope, missing evidence and lifecycle are separate from conflict."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from xti.domain.research import ResearchEvidence
from xti.domain.source_conflicts import assessments

NOW = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
URL = 'https://example.social/acme'


def proof(identifier, *, value='found', source='page', at=NOW, kind='social_page', current=True, url=URL):
    return ResearchEvidence(kind, identifier, source, url,
        'source_claim' if kind in ('social_source_claim', 'cti_indicator') else 'source_context' if kind == 'social_provider' else 'observation',
        value, at.isoformat(), at.isoformat(), 'controlled proof', current=current, state_sha256=identifier,
        time_basis='response_received_at')


class SourceConflictTests(unittest.TestCase):
    def assess(self, rows, **kw):
        return assessments(rows, subject='selected-indicator', checked_at=NOW.isoformat(), **kw)

    def test_near_opposite_claims_keep_full_provenance_and_do_not_choose_truth(self):
        positive = proof('tool', source='tool', value='reported_present', kind='social_source_claim')
        negative = proof('page', value='not_found')
        item = self.assess([positive, negative])[0]
        self.assertEqual(item['state'], 'conflict_candidate')
        self.assertTrue(item['needs_review'])
        self.assertEqual(len(item['candidate_pairs']), 1)
        self.assertEqual({row['record_id'] for row in item['observations']}, {'tool', 'page'})
        self.assertIsNone(item['independent_source_count'])

    def test_access_failure_is_unknown_not_negative(self):
        for value in ('inconclusive', 'failed', 'blocked', 'timeout', 'candidate'):
            item = self.assess([proof('one'), proof('two', source='other', value=value)])[0]
            self.assertEqual(item['state'], 'verification_gap')
            self.assertFalse(item['candidate_pairs'])

    def test_time_separation_and_superseded_same_source_are_not_conflicts(self):
        old = proof('old', at=NOW - timedelta(hours=2))
        negative = proof('new', value='not_found', source='other')
        self.assertEqual(self.assess([old, negative])[0]['state'], 'time_separated')
        same = replace(negative, source='page')
        item = self.assess([old, same])[0]
        self.assertEqual(item['state'], 'single_source')
        self.assertEqual(next(row for row in item['observations'] if row['record_id'] == 'old')['excluded_reason'], 'superseded')

    def test_stale_historical_future_and_incomplete_evidence_cannot_confirm_conflict(self):
        negative = proof('negative', source='negative', value='not_found')
        for positive, options, expected in (
                (proof('old', at=NOW - timedelta(days=2)), {}, 'single_source'),
                (proof('historical', current=False), {}, 'single_source'),
                (proof('future', at=NOW + timedelta(minutes=1)), {}, 'future_time'),
                (proof('positive'), {'total': 3}, 'insufficient_evidence')):
            item = self.assess([positive, negative], **options)[0]
            self.assertEqual(item['state'], expected)
            self.assertFalse(item['state'] == 'conflict_candidate')

    def test_latest_unknown_does_not_resurrect_old_positive_for_conflict(self):
        rows = [proof('old', at=NOW - timedelta(minutes=10)), proof('now', value='inconclusive'),
                proof('negative', source='other', value='not_found')]
        item = self.assess(rows)[0]
        self.assertEqual(item['state'], 'verification_gap')
        self.assertFalse(item['candidate_pairs'])

    def test_different_addresses_and_duplicates_do_not_create_votes(self):
        positive = proof('positive')
        rows = [positive, positive, proof('negative', source='other', url=URL+'2', value='not_found')]
        items = self.assess(rows)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item['state'] == 'single_source' for item in items))
        self.assertEqual(sum(len(item['observations']) for item in items), 2)

    def test_provider_wrong_identity_is_separate_from_presence_and_cti_withdrawal(self):
        item = self.assess([proof('provider', value='conflicting', kind='social_provider')])[0]
        self.assertEqual(item['state'], 'identity_mismatch')
        item = self.assess([proof('active', kind='cti_indicator', value='active', source='a'),
                            proof('revoked', kind='cti_indicator', value='revoked', source='b')])[0]
        self.assertEqual(item['state'], 'lifecycle_difference')
        self.assertFalse(item['needs_review'])
        self.assertFalse(item['candidate_pairs'])

    def test_time_order_uses_instants_not_timezone_strings(self):
        latest = proof('new', value='not_found')
        old = proof('old', at=(NOW - timedelta(minutes=15)).astimezone(timezone(timedelta(hours=5))))
        item = self.assess([old, latest])[0]
        self.assertEqual(item['state'], 'single_source')
        self.assertEqual(next(row for row in item['observations'] if row['record_id'] == 'old')['excluded_reason'], 'superseded')

    def test_same_source_same_time_opposites_require_source_review_not_independent_conflict(self):
        item = self.assess([proof('one'), proof('two', value='not_found')])[0]
        self.assertEqual(item['state'], 'same_source_ambiguity')
        self.assertFalse(item['candidate_pairs'])

    def test_unmodeled_text_and_human_decisions_do_not_become_automatic_claims(self):
        self.assertEqual(self.assess([proof('human', kind='social_review_decision'),
                                    proof('report', kind='report_text_mention')]), [])

"""Immutable public source/watch records linked to human-managed local cases."""
from contextlib import closing
from dataclasses import replace
from datetime import timedelta
import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_case_evidence import SQLiteCaseEvidenceSourceRepository
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.application.cases import CaseService, CaseEvidenceResolverService
from xti.domain.assets import ValidationError
from xti.domain.cases import canonical_snapshot, public_notice_case_evidence_id, parse_public_notice_case_evidence_id
from xti.interfaces.cases import evidence_detail_lines, detail_lines, report_lines
from tests import test_public_notice_watches as watch_fixtures
from tests.test_public_notices import NOW, item


class PublicNoticeCaseTests(unittest.TestCase):
    def setUp(self):
        self.w = watch_fixtures.PublicNoticeWatchTests('runTest')
        self.w.setUp()
        self.addCleanup(self.w.doCleanups)
        self.path = self.w.path
        self.repository = SQLiteCaseRepository(self.path)
        self.resolver = CaseEvidenceResolverService(SQLiteCaseEvidenceSourceRepository(self.path))
        self.service = CaseService(self.repository, self.resolver, clock=lambda: NOW + timedelta(days=1))
        self.case = self.service.create('Public source review', summary='Human evaluation of exact public source evidence.',
                                        reason='Review source metadata without presuming breach.').case

    def add(self, run_id, name='Example', kind='public_notice', case_id=None):
        return self.service.add_evidence(case_id or self.case.id, kind, public_notice_case_evidence_id(run_id, name),
                                         reason='Explicit human linkage of historical metadata.')

    def payload(self, evidence):
        return json.loads(evidence.snapshot_json)

    def test_source_baseline_then_updates_preserve_case_snapshot_and_human_decision(self):
        baseline = self.w.apply()
        first = self.add(baseline.run.id)
        frozen = first.evidence
        self.service.set_status(self.case.id, 'investigating', reason='Human review underway.')
        self.service.add_note(self.case.id, 'No incident confirmation from metadata alone.', kind='decision')
        before = self.service.show(self.case.id)
        updated = self.w.apply(item(PwnCount=54321, IsVerified=False, IsFabricated=True))
        self.assertEqual(self.service.show(self.case.id), before)
        self.assertEqual(self.service.evidence_show(self.case.id, frozen.id), frozen)
        repeated = self.add(baseline.run.id)
        self.assertEqual((repeated.action, repeated.evidence), ('unchanged', frozen))
        second = self.add(updated.run.id).evidence
        self.assertNotEqual(frozen.evidence_id, second.evidence_id)
        payload = self.payload(second)
        self.assertEqual(payload['source_run']['id'], updated.run.id)
        self.assertEqual(payload['previous_source_run']['id'], baseline.run.id)
        self.assertEqual((payload['items'][0]['before']['pwn_count'], payload['items'][0]['after']['pwn_count']), (12345, 54321))
        self.assertFalse(payload['items'][0]['after']['is_verified'])
        self.assertTrue(payload['items'][0]['after']['is_fabricated'])
        self.assertTrue(self.payload(frozen)['is_source_baseline'])
        self.assertEqual(self.service.show(self.case.id).case.status, 'investigating')

    def test_exact_record_outside_first_500_is_selected_and_unchanged_run_is_supported(self):
        rows = [item(f'Notice{index:04d}', 'example.com') for index in range(601)]
        first = self.w.apply(*rows, item_limit=1)
        self.assertNotIn('Notice0600', {change.notice.id for change in first.changes})
        result = self.add(first.run.id, 'Notice0600')
        self.assertEqual(self.payload(result.evidence)['items'][0]['after']['id'], 'Notice0600')
        second = self.w.apply(*rows, item_limit=1)
        self.assertEqual(second.changes, ())
        unchanged = self.add(second.run.id, 'Notice0600').evidence
        self.assertEqual(self.payload(unchanged)['items'][0]['action'], 'unchanged')
        self.assertEqual(self.service.show(self.case.id, evidence_limit=1).total_evidence_count, 2)
        self.assertEqual(self.service.evidence_show(self.case.id, result.evidence.id), result.evidence)

    def test_removed_and_unknown_or_failed_source_records_are_distinct(self):
        self.w.apply()
        removed_run = self.w.apply(item('Other', 'other.example'))
        removed = self.add(removed_run.run.id).evidence
        entry = self.payload(removed)['items'][0]
        self.assertEqual(entry['action'], 'removed')
        self.assertIsNotNone(entry['before'])
        self.assertIsNone(entry['after'])
        failed = self.w.source.record_failure(started_at=NOW.isoformat(), finished_at=NOW.isoformat(), error='Source unavailable.')
        for run_id, name in ((failed.id, 'Example'), (removed_run.run.id, 'NeverSeen'), (str(uuid4()), 'Example')):
            with self.subTest(run_id=run_id, name=name), self.assertRaises(ValidationError):
                self.add(run_id, name)
        self.assertEqual(self.service.show(self.case.id).total_evidence_count, 1)

    def test_source_and_watch_ids_cannot_be_confused_or_normalized_loosely(self):
        self.w.configure(); source = self.w.apply()
        watch = self.w.last()
        with self.assertRaises(ValidationError):
            self.add(source.run.id, kind='public_notice_watch')
        with self.assertRaises(ValidationError):
            self.add(watch.run.id, kind='public_notice')
        for key in ('Example', source.run.id + ':Example:extra', source.run.id.upper() + ':Example', source.run.id + ': bad '):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                parse_public_notice_case_evidence_id(key)

    def test_watch_scope_and_double_domain_effects_stay_historical_after_reconfiguration(self):
        self.w.link_domain('unrelated.example')
        self.w.configure(); self.w.apply()
        self.w.link_domain('new.example')
        self.w.apply(item(domain='new.example'))
        report = self.w.last()
        frozen = self.add(report.run.id, kind='public_notice_watch').evidence
        payload = self.payload(frozen)
        self.assertEqual([(row['action'], row['domain']) for row in payload['items']],
                         [('baseline', 'new.example'), ('removed', 'example.com')])
        watch = payload['watch']
        self.assertEqual(watch['scope_member_count'], 3)
        self.assertFalse(watch['scope_complete'])
        self.assertEqual({member['domain'] for member in watch['scope']['members']}, {'example.com', 'new.example'})
        self.assertEqual(watch['scope_sha256'], report.run.scope_sha256)
        self.w.organizations.rename(self.w.organization.id, name_key='new organization name', display_name='New organization name',
                                    reason='Rename current group.', recorded_at=NOW.isoformat())
        self.w.configure(False)
        self.w.apply(item(PwnCount=99999))
        self.assertEqual(self.service.evidence_show(self.case.id, frozen.id), frozen)
        self.assertEqual(self.add(report.run.id, kind='public_notice_watch').action, 'unchanged')
        self.assertEqual(watch['scope']['organization_name'], 'Example group')

    def test_watch_selection_never_uses_other_organization_or_inferred_title(self):
        self.w.configure()
        other = self.w.add_organization('Other group')
        self.w.link_domain('other.example', organization=other)
        self.w.configure(organization=other)
        self.w.apply(item(), item('Other', 'other.example'), item('NameGuess', '', Title='Example group'))
        own, other_run = self.w.last(), self.w.last(other)
        with self.assertRaises(ValidationError):
            self.add(own.run.id, 'Other', kind='public_notice_watch')
        with self.assertRaises(ValidationError):
            self.add(own.run.id, 'NameGuess', kind='public_notice_watch')
        selected = self.add(other_run.run.id, 'Other', kind='public_notice_watch').evidence
        self.assertEqual(self.payload(selected)['watch']['organization_id'], other.id)

    def test_writes_revalidate_real_source_not_just_supplied_snapshot_hash(self):
        source = self.w.apply()
        snapshot = self.resolver.resolve('public_notice', public_notice_case_evidence_id(source.run.id, 'Example'))
        payload = json.loads(snapshot.snapshot_json)
        payload['items'][0]['after']['pwn_count'] = 99999
        encoded, digest = canonical_snapshot(payload)
        forged = replace(snapshot, snapshot_json=encoded, snapshot_sha256=digest)
        with self.assertRaises(ValidationError):
            self.repository.add_evidence(self.case.id, snapshot=forged, reason='Attempt forged metadata.', recorded_at=(NOW + timedelta(days=1)).isoformat())
        self.assertEqual(self.service.show(self.case.id).total_evidence_count, 0)
        self.w.execute("UPDATE public_notice_runs SET notice_count=notice_count+1, added_count=added_count+1")
        with self.assertRaises(StorageError):
            self.repository.add_evidence(self.case.id, snapshot=snapshot, reason='Source was corrupted.', recorded_at=(NOW + timedelta(days=1)).isoformat())
        self.assertEqual(self.service.show(self.case.id).total_evidence_count, 0)

    def test_mutable_link_identity_and_changed_snapshot_cannot_bypass_activity_binding(self):
        source = self.w.apply()
        evidence = self.add(source.run.id).evidence
        original = self.path.read_bytes()
        other_case = self.service.create('Another review', summary='Separate human-managed case.', reason='Separate review.').case
        original = self.path.read_bytes()
        for sql, values in (
            ('UPDATE case_evidence SET evidence_id=? WHERE id=?', (public_notice_case_evidence_id(source.run.id, 'Other'), evidence.id)),
            ('UPDATE case_evidence SET case_id=? WHERE id=?', (other_case.id, evidence.id)),
            ('UPDATE case_evidence SET source_reference=? WHERE id=?', ('notices show Example', evidence.id)),
        ):
            with self.subTest(sql=sql):
                self.path.write_bytes(original)
                self.w.execute(sql, values)
                with self.assertRaises(StorageError):
                    self.service.show(self.case.id)
                with self.assertRaises(StorageError):
                    self.service.evidence_show(self.case.id, evidence.id)
        self.path.write_bytes(original)
        payload = self.payload(evidence)
        payload['items'][0]['after']['pwn_count'] = 45678
        encoded, digest = canonical_snapshot(payload)
        self.w.execute('UPDATE case_evidence SET snapshot_json=?,snapshot_sha256=? WHERE id=?', (encoded, digest, evidence.id))
        with self.assertRaises(StorageError):
            self.service.evidence_show(self.case.id, evidence.id)

    def test_remove_reactivate_and_closed_case_preserve_source_and_snapshot(self):
        source = self.w.apply()
        linked = self.add(source.run.id).evidence
        before_source = self.w.counts()
        removed = self.service.remove_evidence(self.case.id, linked.id, reason='Human evidence no longer active.').evidence
        self.assertEqual(removed.snapshot_json, linked.snapshot_json)
        self.assertFalse(removed.active)
        restored = self.add(source.run.id)
        self.assertEqual(restored.action, 'reactivated')
        self.assertEqual(restored.evidence.snapshot_json, linked.snapshot_json)
        self.assertEqual(self.w.counts(), before_source)
        self.service.set_status(self.case.id, 'closed', reason='Human review finished.', resolution='No incident conclusion based only on metadata.')
        with self.assertRaises(ValidationError):
            self.add(source.run.id)

    def test_activity_failure_rolls_back_evidence_binding_and_leaves_source_unchanged(self):
        source = self.w.apply()
        before = self.w.counts()
        with patch.object(SQLiteCaseRepository, '_insert_activity', side_effect=RuntimeError('Interrupted evidence event')):
            with self.assertRaises(RuntimeError):
                self.add(source.run.id)
        self.assertEqual(self.service.show(self.case.id).total_evidence_count, 0)
        self.assertEqual(self.w.counts(), before)

    def test_terminal_frozen_evidence_has_values_flags_license_and_exact_navigation(self):
        self.w.apply()
        source = self.w.apply(item(PwnCount=54321, IsVerified=False, IsFabricated=True, IsStealerLog=True))
        evidence = self.add(source.run.id).evidence
        before = self.path.read_bytes()
        for rendered in ('\n'.join(evidence_detail_lines(self.service.evidence_show(self.case.id, evidence.id))),
                         '\n'.join(detail_lines(self.service.show(self.case.id))), '\n'.join(report_lines(self.service.show(self.case.id)))):
            self.assertIn('12345', rendered)
            self.assertIn('54321', rendered)
            self.assertIn('Have I Been Pwned', rendered)
            self.assertIn('CC BY 4.0', rendered)
            self.assertIn('uydurma', rendered)
            self.assertIn('stealer-log', rendered)
            self.assertIn('notices run-show ' + source.run.id, rendered)
        self.assertEqual(self.path.read_bytes(), before)
        unrelated = self.service.create('Unrelated case', summary='Other human-managed review.', reason='Independent review.').case
        with self.assertRaises(ValidationError):
            self.service.evidence_show(unrelated.id, evidence.id)

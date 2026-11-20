"""Accumulated unchanged work, indexed reads, integrity and atomic rebuilding."""
import json
from unittest import TestCase
from unittest.mock import patch

from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_groups import mutate
from xti.adapters.sqlite_group_projection import guard, current, audit, event_row
from xti.domain.reports import ReportError
from tests import test_research_groups as fixtures


class GroupCapacityTests(TestCase):
    def setUp(self):
        self.f = fixtures.GroupTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.first = self.f.capture(self.f.pair())

    def grow(self, count):
        with self.f.repo.storage._connection() as c, c:
            c.execute('BEGIN IMMEDIATE')
            value = current(c, self.first['id'])
            with patch('xti.adapters.sqlite_groups.preview_in', return_value=([value['group']], {'coverage_complete': True, 'limitations': []})):
                for _ in range(count):
                    request = dict(identifier=value['id'], expected_revision=value['revision'],
                        idempotency_key='growth:' + str(value['revision']), response_mode='current')
                    value = mutate(c, self.f.path, 'groups.refresh', request, self.f.at.isoformat())['record']
            return value

    def test_unchanged_history_surpasses_old_group_limit_and_reads_only_selected_proof(self):
        value = self.grow(1100)
        self.assertEqual(value['revision'], 1101)
        self.assertEqual(value['change_count'], 0)
        self.assertEqual(value['group'], self.first['group'])
        self.assertNotIn('history', value)
        with self.f.repo.storage._connection(readonly=True) as c:
            bodies = [json.loads(row[0]) for row in c.execute('SELECT payload_json FROM research_group_journal')]
            self.assertTrue(all(set(e['snapshot']) == {'same_as_previous'} for e in bodies[1:]))
            self.assertLess(len(json.dumps(bodies[-1])), len(json.dumps(bodies[0])))
            self.assertEqual(audit(c)['event_count'], 1101)
        before = self.f.files()
        with patch('xti.adapters.sqlite_group_projection.event_row', wraps=event_row) as reader:
            actual = self.f.groups.execute('groups.current', identifier=value['id'])['record']
            self.assertLessEqual(reader.call_count, 3)
            self.assertEqual(actual, value)
        page = self.f.groups.execute('groups.history', identifier=value['id'], offset=1080, limit=20)
        self.assertEqual((len(page['records']), page['total_count'], page['next_offset']), (20, 1101, 1100))
        with self.assertRaises(ReportError) as error:
            self.f.groups.execute('groups.show', identifier=value['id'])
        self.assertEqual(error.exception.code, 'history_requires_pagination')
        self.assertEqual(self.f.files(), before)
        original = self.f.groups.execute('groups.refresh', identifier=value['id'], expected_revision=1,
            idempotency_key='growth:1', response_mode='current')
        self.assertTrue(original['replayed'])
        self.assertEqual(original['record']['revision'], 2)
        self.assertEqual(self.f.groups.execute('groups.current', identifier=value['id'])['record'], value)
        from types import SimpleNamespace
        from xti.interfaces.platform_jobs import initialize_jobs, make_job_service
        from xti.interfaces.source_jobs import make_source_job_service
        context = SimpleNamespace(data_dir=self.f.data, database=self.f.path)
        initialize_jobs(context)
        jobs, worker = make_source_job_service(context), make_job_service(context)
        plan = jobs.plan(indicator_type='domain', value='example.com', sources=['group-refresh'], group_id=value['id'])
        job = jobs.submit(**plan['plan'], plan_sha256=plan['plan_sha256'], idempotency_key='long-history-worker')
        completed = worker.work_one(job.id)
        self.assertEqual(completed.status, 'complete')
        self.assertEqual(completed.steps[0]['receipt']['revision'], 1102)
        self.assertEqual(jobs.status(job.id).to_dict(), completed.to_dict())

    def test_paged_history_changes_and_generation_reject_mixed_snapshots(self):
        old = self.f.groups.execute('groups.history', identifier=self.first['id'], limit=1)
        self.f.dns('third.example')
        changed = self.f.refresh(self.first)
        with self.assertRaises(ReportError) as error:
            self.f.groups.execute('groups.history', identifier=self.first['id'], offset=1, expected_snapshot=old['snapshot_id'])
        self.assertEqual(error.exception.code, 'snapshot_changed')
        proof = self.f.groups.execute('groups.changes', identifier=self.first['id'])['records'][0]
        self.assertEqual(proof['change']['added'], [['domain', 'third.example']])
        self.assertEqual(proof['after']['state_sha256'], changed['state_sha256'])
        self.assertEqual(self.f.groups.execute('groups.audit')['change_count'], 1)

    def test_out_of_band_state_change_stops_reads_and_backed_up_rebuild_preserves_events(self):
        value = self.grow(5)
        with self.f.repo.storage._connection() as c, c:
            original = c.execute('SELECT * FROM research_group_journal').fetchall()
            c.execute("UPDATE research_group_states SET state_json='{}' WHERE event_id=?", (value['last_event_id'],))
        with self.assertRaises(StorageError):
            self.f.groups.execute('groups.current', identifier=value['id'])
        with self.assertRaises(StorageError):
            self.f.groups.execute('groups.audit')
        restored = self.f.groups.execute('groups.rebuild')
        self.assertEqual(restored['event_count'], 6)
        from pathlib import Path
        self.assertTrue(Path(restored['backup']).is_file())
        self.assertEqual(self.f.groups.execute('groups.current', identifier=value['id'])['record'], value)
        with self.f.repo.storage._connection(readonly=True) as c:
            self.assertEqual(c.execute('SELECT * FROM research_group_journal').fetchall(), original)
            guard(c)

    def test_corrupt_original_journal_cannot_be_laundered_by_rebuild(self):
        self.grow(3)
        with self.f.repo.storage._connection() as c, c:
            c.execute("UPDATE research_group_journal SET payload_json='{}' WHERE sequence=1")
        before = self.f.path.read_bytes()
        with self.assertRaises(StorageError):
            self.f.groups.execute('groups.rebuild')
        self.assertEqual(self.f.path.read_bytes(), before)

    def test_indexed_inbox_does_not_replay_group_history(self):
        self.f.dns('third.example')
        self.f.refresh(self.first)
        self.grow(25)
        from xti.adapters.sqlite_inbox import SQLiteInboxRepository
        with patch('xti.adapters.sqlite_groups.read_groups', side_effect=AssertionError('Full replay')):
            inbox = SQLiteInboxRepository(self.f.path)
            item = inbox.list(limit=1).items[0]
            self.assertEqual(item.group_change['snapshot']['change']['added'], [['domain', 'third.example']])
            inbox.mark([item.notification.id], True, self.f.at.isoformat())
            self.assertIsNotNone(inbox.get(item.notification.id).notification.read_at)

    def test_response_presentation_does_not_change_idempotent_identity(self):
        replay = self.f.groups.execute('groups.capture', **self.first['history'][0]['request'], response_mode='current')
        self.assertTrue(replay['replayed'])
        self.assertNotIn('history', replay['record'])
        self.assertEqual(replay['record']['state_sha256'], self.first['state_sha256'])

    def test_migration_manifest_only_allows_exact_reviewed_guard_triggers(self):
        from tests.test_linux_upgrade_acceptance import acceptance
        from xti.adapters.group_projection_schema import TRIGGERS
        helper = acceptance()
        name = 'research_group_journal'
        columns, rows, objects = [('id', 'TEXT')], [(1, 'original')], [('table', name, 'original ddl')]
        added = [('trigger', s.split()[2], s) for s in TRIGGERS if s.split()[6] == name]
        actual = (columns, rows, sorted(objects+added, key=lambda row: row[1]))
        self.assertTrue(helper._preserved_group_guard_upgrade(name, (columns, rows, objects), actual))
        self.assertFalse(helper._preserved_group_guard_upgrade(name, (columns, rows, objects), (columns, [(1, 'changed')], actual[2])))
        self.assertFalse(helper._preserved_group_guard_upgrade(name, (columns, rows, objects), (columns, rows, actual[2] + [('trigger', 'unknown', 'bad')])))

"""Real terminal/JSON boundaries for archived jobs and source assessments."""
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime
from io import StringIO
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from xti.adapters.company_workspaces import resolve_company_workspace
from xti.adapters.sqlite_engine_jobs import SQLiteEngineJobRepository
from xti.adapters.sqlite_research import SQLiteResearchRepository
from xti.application.research import ResearchService, priority_data
from xti.domain.research_history import freeze
from xti.domain.research import ResearchSnapshotChanged
from xti.interfaces.entrypoint import main
from tests import test_platform_engine as platform_fixtures
from tests import test_social_tracking as social_fixtures
from tests.test_social_discovery import HN, SCOPE


class JobHistoryPlatformTests(unittest.TestCase):
    def setUp(self):
        self.f = platform_fixtures.PlatformEngineTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_archived_admission_replay_and_history_preserve_company_fence(self):
        f = self.f
        _, data = f.submit()
        job_id = data['data']['job_id']
        self.assertEqual(f.invoke(request=f.request('jobs.cancel', {'job_id': job_id}))[0], 0)
        before = (f.context.data_dir / 'engine-jobs.sqlite3').read_bytes()
        with patch.object(SQLiteEngineJobRepository, 'validate', side_effect=AssertionError('Normal reads must not audit all history')):
            code, history = f.invoke(request=f.request('jobs.history'))
            self.assertEqual(code, 0, history)
            self.assertEqual(history['data']['items'][0]['job_id'], job_id)
            self.assertEqual(f.invoke(request=f.request('jobs.capacity'))[1]['data']['archived_jobs'], 1)
            self.assertEqual(f.submit()[1]['data']['status'], 'cancelled')
        self.assertEqual(before, (f.context.data_dir / 'engine-jobs.sqlite3').read_bytes())
        self.assertEqual(f.invoke(request=f.request('jobs.audit'))[1]['data']['state'], 'verified')
        out = StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(['platform', 'provision', '--root', str(f.root), '--company', 'other']), 0)
        response = StringIO()
        with patch('sys.stdin', StringIO(json.dumps(f.request('jobs.result', {'job_id': job_id})))), redirect_stdout(response):
            self.assertEqual(main(['platform', 'request', '--root', str(f.root), '--company', 'other']), 3)
        self.assertEqual(json.loads(response.getvalue())['error']['code'], 'not_found')
        self.assertEqual(f.invoke(request=f.request('jobs.history', {'company': 'other'}))[0], 2)


class ConflictDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.f = social_fixtures.TrackingTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.research = ResearchService(SQLiteResearchRepository(self.f.path), clock=lambda: datetime.fromisoformat(self.f.at))

    def invoke(self, *args, request=None):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch('sys.stdin', StringIO(json.dumps(request))):
            code = main(['--data-dir', str(self.f.path.parent), *args])
        return code, out.getvalue(), err.getvalue()

    def test_real_social_evidence_cli_engine_and_priority_keep_original_reviews(self):
        options = dict(indicator_type='domain', value='acme.example')
        before = self.f.path.read_bytes()
        report = self.research.conflicts(**options)
        hn = next(row for row in report['items'] if row['subject'] == HN)
        self.assertEqual(hn['state'], 'conflict_candidate')
        priorities = priority_data(self.research.full_priorities(**options))
        self.assertTrue(any(reason['code'] == 'source_conflict_candidate' for item in priorities['items'] for reason in item['reasons']))
        frozen = freeze(priorities)
        with patch('xti.application.research.ResearchService._now', return_value=self.f.at):
            code, out, err = self.invoke('research', 'acme.example', '--type', 'domain', '--conflicts')
            self.assertEqual(code, 0, err)
            self.assertIn('karşıt varlık iddiaları', out)
            request = {'contract_version': 1, 'request_id': 'conflict', 'operation': 'research.conflicts', 'parameters': options}
            code, out, err = self.invoke('engine', request=request)
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)['data']['items'], report['items'])
        self.assertEqual(before, self.f.path.read_bytes())
        self.f.later()
        self.f.discovery.execute('brand.discovery.run', **SCOPE, idempotency_key='next-discovery')
        self.assertEqual(freeze(priorities), frozen)

    def test_cursor_and_company_scope_do_not_mix_social_evidence(self):
        options = dict(indicator_type='domain', value='acme.example')
        first = self.research.conflicts(**options, limit=1)
        second = self.research.conflicts(**options, limit=1, offset=1, expected_snapshot=first['snapshot_id'])
        self.assertNotEqual(first['items'][0]['id'], second['items'][0]['id'])
        self.f.later()
        self.f.discovery.execute('brand.discovery.run', **SCOPE, idempotency_key='changed')
        with self.assertRaises(ResearchSnapshotChanged):
            self.research.conflicts(**options, limit=1, offset=1, expected_snapshot=first['snapshot_id'])
        root = self.f.path.parent / 'platform'
        for company in ('one', 'two'):
            with redirect_stdout(StringIO()):
                self.assertEqual(main(['platform', 'provision', '--root', str(root), '--company', company]), 0)
        context = resolve_company_workspace(root, 'one')
        shutil.copyfile(self.f.path, context.database)
        request = {'contract_version': 1, 'request_id': 'compare', 'operation': 'research.conflicts', 'parameters': options}
        counts = []
        for company in ('one', 'two'):
            out = StringIO()
            with redirect_stdout(out), patch('sys.stdin', StringIO(json.dumps(request))):
                self.assertEqual(main(['platform', 'request', '--root', str(root), '--company', company]), 0)
            response = json.loads(out.getvalue())
            counts.append(response['data']['assessment_count'])
            self.assertEqual(response['scope']['company_id'], company)
        self.assertGreater(counts[0], 0)
        self.assertEqual(counts[1], 0)

    def test_incompatible_views_fail_before_reading(self):
        code, out, err = self.invoke('research', 'acme.example', '--type', 'domain', '--conflicts', '--groups')
        self.assertEqual(code, 2)

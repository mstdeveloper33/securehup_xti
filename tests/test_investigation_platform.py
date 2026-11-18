"""Actual company protocol, write fences, backup and preserved decisions."""

import unittest
from uuid import uuid4

from xti.adapters.platform_backup import backup_platform_workspace, restore_platform_workspace
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.interfaces.investigation import make_investigation_service
from tests import test_platform_engine as platform_fixtures


class InvestigationPlatformTests(unittest.TestCase):
    def setUp(self):
        self.fixture = platform_fixtures.PlatformEngineTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        cti = CtiKnowledgeService(SQLiteCtiKnowledgeRepository(self.fixture.context.database))
        entities = [cti.add_entity('threat-actor', name, source_name='fixture', source_reference='report:' + name,
            confidence=40, aliases=(), description='Controlled source record').entity for name in ('Alpha actor', 'Beta actor')]
        self.parameters = {'left': {'kind': 'entity', 'id': entities[0].id},
            'right': {'kind': 'entity', 'id': entities[1].id}, 'evidence': ['https://publisher.example/report'],
            'reason': 'Evidence reviewed by operator', 'idempotency_key': 'platform-proposal',
            'expected_workspace_id': self.fixture.context.workspace_id}

    def call(self, action, parameters):
        return self.fixture.invoke(request=self.fixture.request('investigation.' + action, parameters))

    def test_actual_platform_propose_decide_list_and_read_contract(self):
        code, result = self.call('propose', self.parameters)
        self.assertEqual(code, 0, result)
        record = result['data']['record']
        code, result = self.call('decide', {'identifier': record['id'], 'decision': 'accepted',
            'reason': 'Explicit analyst approval', 'expected_revision': 1, 'idempotency_key': 'platform-accept',
            'expected_workspace_id': self.fixture.context.workspace_id})
        self.assertEqual(code, 0, result)
        self.assertEqual(result['data']['record']['decision'], 'accepted')
        self.assertEqual(self.call('show', {'identifier': record['id']})[1]['data'], {'record': result['data']['record']})
        self.assertEqual(self.call('list', {})[1]['data']['records'][0]['revision'], 2)

    def test_wrong_workspace_unknown_subject_and_writer_lock_do_not_write(self):
        code, result = self.call('propose', {**self.parameters, 'expected_workspace_id': str(uuid4())})
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error']['code'], 'scope_mismatch')
        with LocalExecutionLock(self.fixture.context.database).acquire():
            code, result = self.call('propose', self.parameters)
            self.assertNotEqual(code, 0)
        self.assertEqual(self.call('list', {})[1]['data']['total_count'], 0)
        code, result = self.call('show', {'identifier': str(uuid4())})
        self.assertNotEqual(code, 0)

    def test_backup_restore_preserves_review_and_rejects_old_workspace(self):
        record = self.call('propose', self.parameters)[1]['data']['record']
        backup = backup_platform_workspace(self.fixture.context, self.fixture.root.parent / 'backup')
        restored = restore_platform_workspace(self.fixture.root.parent / 'restored', 'example', backup)
        self.assertEqual(make_investigation_service(restored.database).show(record['id'])['record'], record)
        self.fixture.root, self.fixture.context = self.fixture.root.parent / 'restored', restored
        code, result = self.call('propose', self.parameters)
        self.assertNotEqual(code, 0)
        self.assertEqual(result['error']['code'], 'scope_mismatch')

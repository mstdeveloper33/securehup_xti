"""Real hot-journal recovery, explicit scope and no repair by read operations."""
import subprocess
import sys
import unittest

from xti.adapters.company_workspaces import disable_company_workspace
from xti.adapters.worker_lock import LocalExecutionLock
from xti.interfaces.platform_jobs import jobs_database
from tests import test_platform_engine as fixture
from tests.test_linux_upgrade_acceptance import acceptance


CRASH = '''
import os, sqlite3, sys
assert sys.argv[2] in ('assets', 'engine_jobs')
c=sqlite3.connect(sys.argv[1])
c.execute('PRAGMA cache_size=1')
c.execute('BEGIN IMMEDIATE')
c.execute('DELETE FROM '+sys.argv[2])
c.execute('CREATE TABLE rollback_probe (value BLOB)')
c.execute('INSERT INTO rollback_probe VALUES (zeroblob(1048576))')
os._exit(17)
'''


class PlatformStorageRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.PlatformEngineTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.manifest = acceptance().database_manifest

    def crash(self, path, table):
        result = subprocess.run([sys.executable, '-c', CRASH, str(path), table],
                                capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stderr), (17, b''))
        journal = path.with_name(path.name + '-journal')
        self.assertGreater(journal.stat().st_size, 0)
        return journal

    def test_core_crash_requires_explicit_recovery_then_preserves_all_rows(self):
        f = self.fixture
        before = self.manifest(f.context.database)
        journal = self.crash(f.context.database, 'assets')
        damaged = f.context.database.read_bytes(), journal.read_bytes()
        code, result = f.invoke()
        self.assertEqual((code, result['error']['code']), (1, 'storage_error'))
        self.assertEqual((f.context.database.read_bytes(), journal.read_bytes()), damaged)
        code, result = f.invoke('recover')
        self.assertEqual((code, result['data']), (0, []))
        self.assertEqual(self.manifest(f.context.database), before)
        self.assertEqual(f.invoke()[0], 0)

    def test_queue_crash_keeps_queued_job_and_idempotency_key_without_running_it(self):
        f = self.fixture
        code, accepted = f.submit()
        self.assertEqual(code, 0)
        path = jobs_database(f.context)
        before = self.manifest(path)
        self.crash(path, 'engine_jobs')
        self.assertEqual(f.invoke()[1]['error']['code'], 'storage_error')
        code, result = f.invoke('recover')
        self.assertEqual((code, result['data']), (0, []))
        self.assertEqual(self.manifest(path), before)
        self.assertEqual(f.submit()[1]['data'], accepted['data'])

    def test_busy_or_disabled_workspace_never_repairs_the_core_journal(self):
        f = self.fixture
        journal = self.crash(f.context.database, 'assets')
        before = f.context.database.read_bytes(), journal.read_bytes()
        for database in (f.context.database, jobs_database(f.context)):
            with self.subTest(database=database.name), LocalExecutionLock(database).acquire():
                code, result = f.invoke('recover')
                self.assertEqual((code, result['error']['code']), (1, 'busy'))
                self.assertEqual((f.context.database.read_bytes(), journal.read_bytes()), before)
        disable_company_workspace(f.root, 'example')
        self.assertEqual(f.invoke('recover')[1]['error']['code'], 'scope_unavailable')
        self.assertEqual((f.context.database.read_bytes(), journal.read_bytes()), before)

"""A killed source worker must not lose quota headers already received."""

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.ports.jobs import WorkerBusyError


_CHILD = """
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.urlscan import UrlscanSource
from xti.adapters.worker_lock import LocalExecutionLock
from xti.ports.discovery import SourceError

database = Path(sys.argv[1])
mode = sys.argv[2]
repository = SQLiteCooldownRepository(database)
requests = []
wall = lambda: datetime(2026, 10, 28, 12, tzinfo=timezone.utc)

class BlockingResponse:
    headers = {'X-Rate-Limit-Remaining': '0', 'X-Rate-Limit-Reset-After': '60'}
    def getcode(self):
        return 200
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        # This callback is reached only after the quota header has been saved.
        print('HEADERS_SAVED', flush=True)
        sys.stdin.read()
        raise AssertionError('Collector should have been killed during body read')
    read1 = read

def opener(*args, **kwargs):
    requests.append(1)
    if mode == 'collect':
        return BlockingResponse()
    raise AssertionError('Restart sent a request before the persisted quota reset')

with LocalExecutionLock(database).acquire():
    source = UrlscanSource(opener=opener, cooldowns=repository, wall_clock=wall)
    if mode == 'collect':
        source.search('example*')
    else:
        try:
            source.search('another*')
        except SourceError as error:
            print(json.dumps({'requests': len(requests), 'blocked': str(error),
                              'saved': asdict(repository.get('urlscan'))}), flush=True)
        else:
            raise AssertionError('Restart should have been blocked by saved quota')
"""


class CooldownProcessTests(unittest.TestCase):
    def test_kill_after_quota_headers_preserves_wait_and_blocks_fresh_process(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "xti.db"
            SQLiteAssetRepository(database).initialize()
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            child = subprocess.Popen(
                [sys.executable, "-c", _CHILD, str(database), "collect"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=environment,
            )
            try:
                ready, _, _ = select.select([child.stdout], [], [], 5)
                self.assertTrue(ready, "Source worker did not reach body read in time")
                self.assertEqual(child.stdout.readline().strip(), "HEADERS_SAVED")
                saved = SQLiteCooldownRepository(database).get("urlscan")
                self.assertIsNotNone(saved)
                self.assertEqual(datetime.fromisoformat(saved.not_before),
                                 datetime(2026, 10, 28, 12, 1, tzinfo=timezone.utc))
                database_before = database.read_bytes()
                with self.assertRaises(WorkerBusyError):
                    with LocalExecutionLock(database).acquire():
                        self.fail("Collector must still hold the worker lock")

                child.kill()
                _, stderr = child.communicate(timeout=5)
                self.assertEqual(child.returncode, -signal.SIGKILL, stderr)

                restarted = subprocess.run(
                    [sys.executable, "-c", _CHILD, str(database), "restart"],
                    stdin=subprocess.DEVNULL, capture_output=True, text=True,
                    env=environment, timeout=5,
                )
                self.assertEqual(restarted.returncode, 0, restarted.stderr)
                self.assertEqual(restarted.stderr, "")
                result = json.loads(restarted.stdout)
                self.assertEqual(result["requests"], 0)
                self.assertIn("bekleme süresi", result["blocked"])
                self.assertEqual(result["saved"], asdict(saved))
                self.assertEqual(SQLiteCooldownRepository(database).get("urlscan"), saved)
                self.assertEqual(database.read_bytes(), database_before)
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()

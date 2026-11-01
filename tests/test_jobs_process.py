"""Recover a genuinely killed scan worker without losing durable history."""

import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import unittest

from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.assets import AssetService
from xti.application.discovery import DiscoveryService
from xti.application.findings import DomainImportService, FindingService
from xti.application.inbox import InboxService
from xti.application.jobs import JobService
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.domain.matching import DomainMatcher
from xti.ports.jobs import WorkerBusyError


_CHILD = """
from pathlib import Path
import sys
from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.discovery import DiscoveryService
from xti.application.jobs import JobService
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.domain.matching import DomainMatcher

class BlockingSource:
    calls = 0
    def search_url(self, pattern):
        return 'https://crt.sh/?fixture=' + pattern
    def search(self, pattern):
        self.calls += 1
        if self.calls == 2:
            # The first query callback has already committed before we arrive.
            print('READY', flush=True)
            sys.stdin.read()
            raise RuntimeError('Test worker should have been killed')
        document = ImportDocument(
            'https://crt.sh/?id=1001', '1' * 64,
            (DomainInput('example-support.net', 'example-support.net', 1, None),),
        )
        return SourceBatch((document,), 0, 1)

database = Path(sys.argv[1])
service = JobService(
    SQLiteJobRepository(database),
    DiscoveryService(SQLiteAssetRepository(database), SQLiteFindingRepository(database),
                     DomainMatcher(PublicSuffixResolver()), BlockingSource()),
    LocalExecutionLock(database),
)
service.run(sys.argv[2])
"""


class FixtureSource:
    def __init__(self, document):
        self.document = document
        self.calls = []

    def search_url(self, pattern):
        return "https://crt.sh/?fixture=" + pattern

    def search(self, pattern):
        self.calls.append(pattern)
        return SourceBatch((self.document,), 0, 1)


class JobsProcessTests(unittest.TestCase):
    def test_killed_worker_keeps_query_history_and_can_recover_and_retry(self):
        for mark_read in (False, True):
            with self.subTest(mark_read=mark_read):
                self._exercise_killed_worker(mark_read)

    def _exercise_killed_worker(self, mark_read):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "xti.db"
            assets = SQLiteAssetRepository(database)
            assets.initialize()
            AssetService(assets).add("example.com")
            findings = SQLiteFindingRepository(database)
            matcher = DomainMatcher(PublicSuffixResolver())
            document = ImportDocument(
                "https://crt.sh/?id=1001", "1" * 64,
                (DomainInput("example-support.net", "example-support.net", 1, None),),
            )
            # Existing evidence and the user's decision must survive both processes.
            DomainImportService(assets, findings, matcher).import_document(document)
            finding = findings.list_findings()[0]
            inbox = InboxService(SQLiteInboxRepository(database))
            page = inbox.list(status="all")
            self.assertEqual(page.total_count, 1)
            self.assertEqual(page.unread_count, 1)
            self.assertEqual(len(page.items), 1)
            notification = page.items[0].notification
            self.assertEqual(notification.finding_id, finding.id)
            self.assertEqual(notification.event_type, "finding_created")
            self.assertEqual(notification.origin, "new")
            self.assertIsNone(notification.read_at)
            if mark_read:
                marked = inbox.mark([notification.id])
                self.assertEqual(marked.changed_count, 1)
                self.assertIsNotNone(marked.notifications[0].read_at)
            notification_before = inbox.show(notification.id).notification
            FindingService(findings).review(finding.id, "uncertain", "İnceleme sürüyor.")
            evidence_before = findings.get_finding(finding.id)

            def assert_inbox_unchanged():
                # A fresh adapter must preserve explicit read state and one event
                # through review, a killed worker, recovery and retry.
                reopened = InboxService(SQLiteInboxRepository(database))
                current = reopened.list(status="all")
                self.assertEqual(current.total_count, 1)
                self.assertEqual(current.unread_count, 0 if mark_read else 1)
                self.assertEqual(len(current.items), 1)
                self.assertEqual(current.items[0].notification, notification_before)
                details = reopened.show(notification.id)
                self.assertEqual(details.notification, notification_before)
                self.assertEqual(details.details, evidence_before)

            assert_inbox_unchanged()
            jobs = SQLiteJobRepository(database)
            source = FixtureSource(document)
            service = JobService(
                jobs, DiscoveryService(assets, findings, matcher, source),
                LocalExecutionLock(database),
            )
            job = service.enqueue()
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            child = subprocess.Popen(
                [sys.executable, "-c", _CHILD, str(database), job.id],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=environment,
            )
            try:
                ready, _, _ = select.select([child.stdout], [], [], 5)
                self.assertTrue(ready, "Child worker did not reach its second query in time")
                self.assertEqual(child.stdout.readline().strip(), "READY")
                active = jobs.get(job.id)
                self.assertEqual(active.job.status, "running")
                self.assertEqual(len(active.attempts), 1)
                self.assertEqual(len(active.attempts[0].queries), 1)
                first_query = active.attempts[0].queries[0]
                self.assertEqual(first_query.pattern, "%example%")
                self.assertEqual(first_query.status, "complete")
                assert_inbox_unchanged()
                with self.assertRaises(WorkerBusyError):
                    service.recover()

                child.kill()
                _, stderr = child.communicate(timeout=5)
                self.assertEqual(child.returncode, -signal.SIGKILL, stderr)
                # A read alone must not claim that an abandoned process was recovered.
                abandoned = SQLiteJobRepository(database).get(job.id)
                self.assertEqual(abandoned, active)
                self.assertIsNone(abandoned.attempts[0].finished_at)
                self.assertIsNone(abandoned.attempts[0].result)
                assert_inbox_unchanged()

                restarted_jobs = SQLiteJobRepository(database)
                restarted_source = FixtureSource(document)
                restarted = JobService(
                    restarted_jobs,
                    DiscoveryService(SQLiteAssetRepository(database), SQLiteFindingRepository(database),
                                     DomainMatcher(PublicSuffixResolver()), restarted_source),
                    LocalExecutionLock(database),
                )
                self.assertEqual(restarted.recover(), 1)
                interrupted = restarted_jobs.get(job.id).attempts[0]
                self.assertEqual(interrupted.status, "interrupted")
                self.assertEqual(interrupted.queries, (first_query,))
                self.assertTrue(interrupted.finished_at)
                self.assertTrue(interrupted.error)
                self.assertEqual(restarted_source.calls, [])
                assert_inbox_unchanged()

                retry = restarted.retry(job.id)
                self.assertEqual(retry.status, "complete")
                self.assertEqual(retry.number, 2)
                self.assertNotEqual(retry.id, interrupted.id)
                self.assertEqual(restarted_source.calls, ["%example%", "example%"])
                self.assertEqual(retry.result.summary.observations_created, 0)
                self.assertEqual(retry.result.summary.findings_created, 0)
                self.assertEqual(retry.result.summary.observations_existing, 1)
                self.assertEqual(retry.result.summary.findings_existing, 1)
                final = restarted_jobs.get(job.id)
                self.assertEqual(final.job.status, "complete")
                self.assertEqual(final.job.attempt_count, 2)
                self.assertEqual(final.attempts, (interrupted, retry))
                self.assertEqual(findings.get_finding(finding.id), evidence_before)
                self.assertEqual(assets.inspect()["observation_count"], 1)
                self.assertEqual(assets.inspect()["finding_count"], 1)
                self.assertEqual(assets.inspect()["notification_count"], 1)
                assert_inbox_unchanged()
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()

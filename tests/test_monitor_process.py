"""Real process death preserves session attribution and never releases orphan work."""

import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.sqlite_monitoring import SQLiteMonitorRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.assets import AssetService
from xti.application.discovery import DiscoveryService
from xti.application.findings import DomainImportService, FindingService
from xti.application.inbox import InboxService
from xti.application.jobs import JobService
from xti.application.monitoring import MonitorService
from xti.domain.assets import ValidationError
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.domain.matching import DomainMatcher
from xti.domain.monitoring import MonitorSpec
from xti.ports.jobs import WorkerBusyError


_CHILD = """
from pathlib import Path
import sys
from unittest.mock import patch
from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.sqlite_monitoring import SQLiteMonitorRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.discovery import DiscoveryService
from xti.application.jobs import JobService
from xti.application.monitoring import MonitorService
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.domain.matching import DomainMatcher
from xti.domain.monitoring import MonitorSpec

def block():
    print('READY', flush=True)
    sys.stdin.read()
    raise RuntimeError('Test process should have been killed')

def document(domain, number):
    return ImportDocument(
        'https://crt.sh/?id=' + str(number), str(number) * 64,
        (DomainInput(domain, domain, 1, None),),
    )

class BlockingSource:
    def search_url(self, pattern):
        return 'https://crt.sh/?fixture=' + pattern
    def search(self, pattern):
        return SourceBatch((document('example-support.net', 1),
                            document('example-help.net', 2)), 0, 2)

class PauseAfterEvidence(SQLiteFindingRepository):
    def save_import(self, document, candidates):
        result = super().save_import(document, candidates)
        if document.sha256 == '2' * 64:
            # Both query callbacks and the new finding/notification committed;
            # the job's complete ScanResult has not been persisted yet.
            block()
        return result

class PauseAfterEnqueue(SQLiteMonitorRepository):
    def enqueue(self, *args):
        job = super().enqueue(*args)
        # The job and session link are durable, but no attempt exists yet.
        block()
        return job

database = Path(sys.argv[1])
matcher = DomainMatcher(PublicSuffixResolver())
discovery = DiscoveryService(SQLiteAssetRepository(database), PauseAfterEvidence(database),
                             matcher, BlockingSource())
jobs = JobService(SQLiteJobRepository(database), discovery, LocalExecutionLock(database))
repository = (PauseAfterEnqueue if sys.argv[2] == 'queued' else SQLiteMonitorRepository)(database)
monitor = MonitorService(repository, jobs)
spec = MonitorSpec(('example.com',), ('crt.sh',), False, matcher.rule_version, 1, 300, 30)
with patch('socket.socket', side_effect=AssertionError('Network forbidden in process test')):
    monitor.start(spec)
"""


def fixture_document(domain: str, number: int) -> ImportDocument:
    return ImportDocument(
        "https://crt.sh/?id=" + str(number), str(number) * 64,
        (DomainInput(domain, domain, 1, None),),
    )


class RepeatedSource:
    def __init__(self):
        self.calls = []

    def search_url(self, pattern):
        return "https://crt.sh/?fixture=" + pattern

    def search(self, pattern):
        self.calls.append(pattern)
        return SourceBatch((fixture_document("example-support.net", 1),
                            fixture_document("example-help.net", 2)), 0, 2)


class MonitorProcessTests(unittest.TestCase):
    def test_sigkill_after_evidence_commit_and_atomic_enqueue_preserves_session_history(self):
        for phase in ("committed", "queued"):
            with self.subTest(phase=phase):
                self._exercise(phase)

    def _exercise(self, phase):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "xti.db"
            assets = SQLiteAssetRepository(database)
            assets.initialize()
            AssetService(assets).add("example.com")
            matcher = DomainMatcher(PublicSuffixResolver())
            findings = SQLiteFindingRepository(database)
            DomainImportService(assets, findings, matcher).import_document(
                fixture_document("example-support.net", 1),
            )
            old_finding = findings.list_findings()[0]
            FindingService(findings).review(old_finding.id, "uncertain", "Önceki inceleme korunmalı.")
            old_details = findings.get_finding(old_finding.id)
            inbox = InboxService(SQLiteInboxRepository(database))
            old_notification = inbox.list(status="all").items[0].notification
            inbox.mark([old_notification.id])
            old_notice = inbox.show(old_notification.id).notification

            def services():
                source = RepeatedSource()
                jobs = JobService(
                    SQLiteJobRepository(database),
                    DiscoveryService(SQLiteAssetRepository(database), SQLiteFindingRepository(database),
                                     DomainMatcher(PublicSuffixResolver()), source),
                    LocalExecutionLock(database),
                )
                return MonitorService(SQLiteMonitorRepository(database), jobs), jobs, source

            monitor, jobs, source = services()
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            child = subprocess.Popen(
                [sys.executable, "-c", _CHILD, str(database), phase],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=environment,
            )
            try:
                ready, _, _ = select.select([child.stdout], [], [], 10)
                self.assertTrue(ready, "Monitor child did not reach the durable checkpoint")
                line = child.stdout.readline().strip()
                if line != "READY":
                    _, stderr = child.communicate(timeout=5)
                    self.fail(f"Child did not pause: {line!r}; {stderr}")
                running = monitor.list()[0]
                active = monitor.details(running.id)
                self.assertEqual(running.status, "running")
                self.assertEqual(len(active.entries), 1)
                entry = active.entries[0]
                if phase == "committed":
                    self.assertEqual(entry.attempt.status, "running")
                    self.assertEqual(entry.attempt.query_count, 2)
                    self.assertIsNone(entry.attempt.summary)
                    self.assertEqual(len(findings.list_findings()), 2)
                else:
                    self.assertEqual(entry.job.status, "queued")
                    self.assertIsNone(entry.attempt)
                    self.assertEqual(len(findings.list_findings()), 1)
                notices_at_checkpoint = inbox.list(status="all")
                self.assertEqual(inbox.show(old_notice.id).notification, old_notice)
                self.assertEqual(findings.get_finding(old_finding.id), old_details)
                bytes_at_checkpoint = database.read_bytes()
                with self.assertRaises(WorkerBusyError):
                    monitor.recover()
                with self.assertRaises(WorkerBusyError):
                    jobs.run()
                self.assertEqual(database.read_bytes(), bytes_at_checkpoint)

                child.kill()
                _, stderr = child.communicate(timeout=5)
                self.assertEqual(child.returncode, -signal.SIGKILL, stderr)
                restarted, ordinary, restarted_source = services()
                before_reads = database.read_bytes()
                self.assertEqual(restarted.list()[0], running)
                self.assertEqual(restarted.details(running.id), active)
                self.assertEqual(restarted.show(running.id).outcome, "running")
                self.assertEqual(database.read_bytes(), before_reads)
                self.assertEqual(InboxService(SQLiteInboxRepository(database)).list(status="all"),
                                 notices_at_checkpoint)

                if phase == "queued":
                    # The normal worker must not start a session's orphan job.
                    self.assertIsNone(ordinary.run())
                    self.assertEqual(restarted_source.calls, [])
                    self.assertEqual(restarted.details(running.id), active)
                    with self.assertRaises(ValidationError):
                        ordinary.retry(entry.job.id)
                    self.assertEqual(restarted.details(running.id), active)

                self.assertEqual(restarted.recover(), 1)
                recovered = restarted.details(running.id)
                self.assertEqual(recovered.run.status, "interrupted")
                self.assertEqual(recovered.run.stop_reason, "recovered")
                self.assertIsNone(recovered.run.elapsed_seconds)
                self.assertIsNotNone(recovered.run.finished_at)
                retired = recovered.entries[0]
                self.assertEqual(retired.job.status, "interrupted")
                report = restarted.show(running.id)
                self.assertEqual(report.sources[0].unknown_result_count, int(phase == "committed"))
                self.assertEqual(report.sources[0].findings_created, 0)
                if phase == "committed":
                    self.assertEqual(retired.attempt.id, entry.attempt.id)
                    self.assertEqual(retired.attempt.status, "interrupted")
                    self.assertEqual(retired.attempt.query_count, 2)
                    original_attempt = SQLiteJobRepository(database).get(entry.job.id).attempts[0]
                    self.assertEqual(original_attempt.queries[0].pattern, "%example%")
                    self.assertEqual(original_attempt.queries[0].status, "complete")
                    self.assertIsNone(original_attempt.result)
                else:
                    self.assertIsNone(retired.attempt)
                    self.assertEqual(retired.job.attempt_count, 0)
                self.assertEqual(restarted_source.calls, [])
                self.assertEqual(InboxService(SQLiteInboxRepository(database)).list(status="all"),
                                 notices_at_checkpoint)
                self.assertEqual(restarted.recover(), 0)
                with self.assertRaises(ValidationError):
                    ordinary.retry(entry.job.id)
                self.assertEqual(restarted.details(running.id), recovered)

                spec = MonitorSpec(("example.com",), ("crt.sh",), False, matcher.rule_version, 1, 300, 30)
                with patch("socket.socket", side_effect=AssertionError("No real network")):
                    new_report = restarted.start(spec)
                self.assertEqual(new_report.outcome, "complete")
                self.assertNotEqual(new_report.run.id, running.id)
                self.assertEqual(new_report.sources[0].findings_created, int(phase == "queued"))
                self.assertEqual(restarted.details(running.id), recovered)
                self.assertEqual(findings.get_finding(old_finding.id), old_details)
                self.assertEqual(len(findings.list_findings()), 2)
                final_inbox = InboxService(SQLiteInboxRepository(database))
                self.assertEqual((final_inbox.list(status="all").total_count,
                                  final_inbox.list(status="all").unread_count), (2, 1))
                self.assertEqual(final_inbox.show(old_notice.id).notification, old_notice)
                if phase == "committed":
                    self.assertEqual(final_inbox.list(status="all"), notices_at_checkpoint)
                self.assertEqual(source.calls, [])
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()

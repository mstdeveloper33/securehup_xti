"""Durable scan requests, interruption history and idempotent retries."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.application.assets import AssetService
from xti.application.discovery import DiscoveryService
from xti.application.findings import FindingService
from xti.application.jobs import JobService
from xti.domain.assets import ValidationError
from xti.domain.matching import DomainMatcher
from xti.ports.discovery import SourceError
from xti.ports.jobs import WorkerBusyError

from tests.test_discovery import FakeSource, batch, document


class TrackingLock:
    def __init__(self, busy=False):
        self.busy = busy
        self.held = False
        self.acquisitions = 0

    @contextmanager
    def acquire(self):
        if self.busy:
            raise WorkerBusyError("Başka bir kontrol çalışıyor.")
        self.held = True
        self.acquisitions += 1
        try:
            yield
        finally:
            self.held = False


class JobServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "xti.db"
        self.assets = SQLiteAssetRepository(self.database)
        self.assets.initialize()
        AssetService(self.assets).add("example.com")
        self.findings = SQLiteFindingRepository(self.database)
        self.jobs = SQLiteJobRepository(self.database)
        self.resolver = PublicSuffixResolver()
        self.matcher = DomainMatcher(self.resolver)
        self.lock = TrackingLock()

    def service(self, source=None, *, matcher=None, lock=None, provider="crt.sh"):
        discovery = DiscoveryService(
            self.assets, self.findings, matcher or self.matcher, source or FakeSource(),
        )
        return JobService(self.jobs, discovery, lock or self.lock, provider=provider)

    def test_queue_survives_new_repository_and_service_without_network(self):
        source = FakeSource()
        job = self.service(source).enqueue(["EXAMPLE.COM."], typos=True)
        self.assertEqual(job.targets, ("example.com",))
        self.assertTrue(job.typos)
        self.assertEqual(job.provider, "crt.sh")
        self.assertEqual(job.rule_version, self.matcher.rule_version)
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.attempt_count, 0)
        self.assertEqual(source.calls, [])
        reopened = SQLiteJobRepository(self.database)
        self.assertEqual(reopened.get(job.id).job, job)
        self.assertEqual(reopened.get(job.id).attempts, ())
        self.assertEqual(self.service().run().job_id, job.id)
        self.assertEqual(reopened.get(job.id).job.status, "complete")

    def test_completed_attempt_keeps_result_and_each_source_query(self):
        source = FakeSource({"%example%": batch(document("example-support.net"))})
        service = self.service(source)
        job = service.enqueue()
        progress = []
        attempt = service.run(job.id, progress=progress.append)
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.status, "complete")
        self.assertEqual(attempt.number, 1)
        self.assertEqual(attempt.result.summary.findings_created, 1)
        self.assertEqual(attempt.queries, attempt.result.queries)
        self.assertTrue(all(query.source_url.startswith("https://crt.sh/?") for query in attempt.queries))
        self.assertTrue(attempt.finished_at)
        self.assertTrue(progress)
        saved = SQLiteJobRepository(self.database).get(job.id)
        self.assertEqual(saved.attempts, (attempt,))
        self.assertEqual(saved.job.status, "complete")
        self.assertEqual(saved.job.attempt_count, 1)
        self.assertFalse(self.lock.held)

    def test_partial_retry_appends_attempt_and_preserves_finding_decision(self):
        source = FakeSource({
            "%example%": SourceError("Geçici kaynak hatası."),
            "example%": batch(document("example-support.net")),
        })
        service = self.service(source)
        job = service.enqueue()
        first = service.run(job.id)
        self.assertEqual(first.status, "partial")
        self.assertEqual(first.result.summary.findings_created, 1)
        finding = self.findings.list_findings()[0]
        FindingService(self.findings).review(finding.id, "dismissed", "Kontrollü örnek alan.")
        evidence_before = self.findings.get_finding(finding.id)
        recovered_source = FakeSource({"%example%": batch(document("example-support.net"))})
        second = self.service(recovered_source).run(job.id)
        self.assertEqual(second.status, "complete")
        self.assertEqual(second.number, 2)
        self.assertNotEqual(second.id, first.id)
        self.assertEqual(second.result.summary.findings_created, 0)
        self.assertEqual(second.result.summary.findings_existing, 1)
        self.assertEqual(self.findings.get_finding(finding.id), evidence_before)
        details = self.jobs.get(job.id)
        self.assertEqual(details.attempts, (first, second))
        self.assertEqual(details.job.attempt_count, 2)
        self.assertEqual(details.attempts[0].queries[0].error, "Geçici kaynak hatası.")

    def test_source_outage_is_saved_as_failed_with_query_errors(self):
        source = FakeSource({
            "%example%": SourceError("Kaynak kapalı."),
            "example%": SourceError("Kaynak kapalı."),
        })
        service = self.service(source)
        job = service.enqueue()
        attempt = service.run(job.id)
        self.assertEqual(attempt.status, "failed")
        self.assertEqual(self.jobs.get(job.id).job.status, "failed")
        self.assertTrue(all(query.status == "failed" and query.error for query in attempt.queries))
        self.assertEqual(attempt.result.summary.total_records, 0)
        self.assertEqual(self.assets.inspect()["observation_count"], 0)

    def test_interrupt_during_second_query_keeps_first_query_before_retry(self):
        class InterruptedSource(FakeSource):
            def search(self, pattern):
                if self.calls:
                    self.calls.append(pattern)
                    raise KeyboardInterrupt
                return super().search(pattern)

        source = InterruptedSource({"%example%": batch(document("example-support.net"))})
        service = self.service(source)
        job = service.enqueue()
        with self.assertRaises(KeyboardInterrupt):
            service.run(job.id)
        details = self.jobs.get(job.id)
        interrupted = details.attempts[0]
        self.assertEqual(details.job.status, "interrupted")
        self.assertEqual(interrupted.status, "interrupted")
        self.assertTrue(interrupted.finished_at)
        self.assertTrue(interrupted.error)
        self.assertEqual(len(interrupted.queries), 1)
        self.assertEqual(interrupted.queries[0].pattern, "%example%")
        self.assertEqual(interrupted.queries[0].status, "complete")
        self.assertIsNone(interrupted.result)
        self.assertFalse(self.lock.held)
        retry = self.service(FakeSource({"%example%": batch(document("example-support.net"))})).run(job.id)
        self.assertEqual(retry.number, 2)
        self.assertEqual(retry.status, "complete")
        self.assertEqual(self.jobs.get(job.id).attempts[0], interrupted)

    def test_retry_after_interrupted_write_does_not_duplicate_saved_evidence(self):
        source = FakeSource({"%example%": batch(document("example-support.net"))})
        service = self.service(source)
        job = service.enqueue()
        original_save = self.findings.save_import

        def commit_then_interrupt(*arguments):
            original_save(*arguments)
            raise KeyboardInterrupt

        with patch.object(self.findings, "save_import", side_effect=commit_then_interrupt):
            with self.assertRaises(KeyboardInterrupt):
                service.run(job.id)
        self.assertEqual(self.assets.inspect()["observation_count"], 1)
        self.assertEqual(self.jobs.get(job.id).job.status, "interrupted")
        finding = self.findings.list_findings()[0]
        FindingService(self.findings).review(finding.id, "uncertain", "İnceleme sürüyor.")
        before = self.findings.get_finding(finding.id)
        retry = service.run(job.id)
        self.assertEqual(retry.result.summary.observations_created, 0)
        self.assertEqual(retry.result.summary.findings_created, 0)
        self.assertEqual(self.findings.get_finding(finding.id), before)

    def test_unexpected_error_is_retained_and_original_exception_propagates(self):
        source = FakeSource({"%example%": RuntimeError("İşleme beklenmedik biçimde durdu.")})
        service = self.service(source)
        job = service.enqueue()
        with self.assertRaises(RuntimeError):
            service.run(job.id)
        details = self.jobs.get(job.id)
        self.assertEqual(details.job.status, "failed")
        self.assertEqual(details.attempts[0].status, "failed")
        self.assertTrue(details.attempts[0].error)
        self.assertIsNone(details.attempts[0].result)
        self.assertFalse(self.lock.held)

    def test_changed_rules_fail_before_http_instead_of_relabelling_the_request(self):
        job = self.service().enqueue()
        changed = DomainMatcher(self.resolver, rule_version="future-rule-version")
        source = FakeSource()
        with self.assertRaises(ValidationError):
            self.service(source, matcher=changed).run(job.id)
        self.assertEqual(source.calls, [])
        details = self.jobs.get(job.id)
        self.assertEqual(details.job.rule_version, self.matcher.rule_version)
        self.assertEqual(details.job.status, "failed")
        self.assertTrue(details.attempts[0].error)

    def test_changed_provider_cannot_execute_stored_source_request(self):
        job = self.service().enqueue()
        source = FakeSource()
        with self.assertRaises(ValidationError):
            self.service(source, provider="another-provider").run(job.id)
        self.assertEqual(source.calls, [])
        self.assertEqual(self.jobs.get(job.id).job.status, "failed")

    def test_busy_worker_leaves_queued_request_without_an_attempt(self):
        source = FakeSource()
        service = self.service(source, lock=TrackingLock(busy=True))
        job = service.enqueue()
        with self.assertRaises(WorkerBusyError):
            service.run(job.id)
        details = self.jobs.get(job.id)
        self.assertEqual(details.job.status, "queued")
        self.assertEqual(details.attempts, ())
        self.assertEqual(source.calls, [])

    def test_reading_history_does_not_recover_a_running_attempt(self):
        service = self.service()
        job = service.enqueue()
        running = self.jobs.start(job.id)
        before = self.jobs.get(job.id)
        self.assertEqual(service.show(job.id), before)
        self.assertEqual(service.list(status="running"), [before.job])
        self.assertEqual(self.jobs.get(job.id).attempts, (running,))
        self.assertEqual(self.lock.acquisitions, 0)

    def test_recovery_requires_lock_and_preserves_old_attempt_before_next_queued_job(self):
        source = FakeSource()
        service = self.service(source)
        abandoned = service.enqueue()
        running = self.jobs.start(abandoned.id)
        pending = service.enqueue()
        original_recover = self.jobs.recover_interrupted

        def recover_while_locked(reason):
            self.assertTrue(self.lock.held)
            return original_recover(reason)

        with patch.object(self.jobs, "recover_interrupted", side_effect=recover_while_locked):
            executed = service.run()
        self.assertEqual(executed.job_id, pending.id)
        old = self.jobs.get(abandoned.id)
        self.assertEqual(old.job.status, "interrupted")
        self.assertEqual(old.attempts[0].id, running.id)
        self.assertEqual(old.attempts[0].status, "interrupted")
        self.assertEqual(len(source.calls), 2)

    def test_completed_job_cannot_be_replayed_as_another_attempt(self):
        service = self.service()
        job = service.enqueue()
        first = service.run(job.id)
        with self.assertRaises(ValidationError):
            service.run(job.id)
        self.assertEqual(self.jobs.get(job.id).attempts, (first,))

    def test_invalid_request_or_history_filters_do_not_change_jobs(self):
        source = FakeSource()
        service = self.service(source)
        for targets in (("missingbrand.com",), ("https://example.com",), ("abc.com",)):
            with self.subTest(targets=targets):
                with self.assertRaises(ValidationError):
                    service.enqueue(targets)
        for keywords in ({"limit": 0}, {"limit": 101}, {"status": "invented"}):
            with self.subTest(keywords=keywords):
                with self.assertRaises(ValidationError):
                    service.list(**keywords)
        with self.assertRaises(ValidationError):
            service.show("invalid\x1bid")
        self.assertEqual(self.jobs.list(), [])
        self.assertEqual(source.calls, [])

    def test_worker_without_pending_requests_does_not_contact_source(self):
        source = FakeSource()
        self.assertIsNone(self.service(source).run())
        self.assertEqual(source.calls, [])

    def test_source_history_uses_latest_attempt_not_latest_queued_request(self):
        failed_source = FakeSource({
            "%example%": SourceError("Kaynak kapalı."),
            "example%": SourceError("Kaynak kapalı."),
        })
        service = self.service(failed_source)
        job = service.enqueue()
        first = service.run(job.id)
        service.enqueue(["example.com"])
        saved_status = service.source_status()
        self.assertEqual(len(saved_status), 1)
        self.assertEqual(saved_status[0]["attempt_id"], first.id)
        self.assertEqual(saved_status[0]["source_status"], "failed")
        second = self.service().run(job.id)
        recovered_status = self.service().source_status()[0]
        self.assertEqual(recovered_status["attempt_id"], second.id)
        self.assertEqual(recovered_status["source_status"], "responded")
        self.assertTrue(recovered_status["finished_at"])

    def test_source_history_without_a_query_is_unknown_and_read_only(self):
        service = self.service()
        self.assertEqual(service.source_status(), [])
        job = service.enqueue()
        running = self.jobs.start(job.id)
        before = self.jobs.get(job.id)
        statuses = service.source_status()
        self.assertEqual(statuses[0]["attempt_id"], running.id)
        self.assertEqual(statuses[0]["source_status"], "unknown")
        self.assertEqual(statuses[0]["queries"], ())
        self.assertEqual(self.jobs.get(job.id), before)


if __name__ == "__main__":
    unittest.main()

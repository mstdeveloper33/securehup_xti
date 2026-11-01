"""Independent provider plans, persisted dispatch and shared evidence without HTTP."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.application.assets import AssetService
from xti.application.discovery import DiscoveryService, build_prefix_query_plan
from xti.application.findings import FindingService
from xti.application.jobs import JobService
from xti.domain.assets import ValidationError
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.domain.matching import DomainMatcher
from xti.ports.discovery import SourceError

from tests.test_discovery import FakeSource, batch, document
from tests.test_jobs import TrackingLock


COVERAGE_NOTE = "Anonim arama yalnız son 30 gün içindeki kayıtları kapsıyor."


class FakeUrlscanSource(FakeSource):
    def search_url(self, pattern):
        return "https://urlscan.io/api/v1/search/?" + urlencode({"q": f"page.domain:{pattern}"})


def urlscan_document(domain="example-support.net", identity="sample-scan"):
    return ImportDocument(
        f"https://urlscan.io/result/{identity}/",
        hashlib.sha256(f"urlscan:{identity}:{domain}".encode()).hexdigest(),
        (DomainInput(domain, domain, 1, "2026-10-28T10:00:00+00:00"),),
    )


def scoped_batch(*documents, warnings=()):
    return SourceBatch(tuple(documents), 0, len(documents), tuple(warnings), (COVERAGE_NOTE,))


class PrefixQueryPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = PublicSuffixResolver()

    def test_registered_brand_prefixes_normalize_and_deduplicate_across_roots(self):
        self.assertEqual(
            build_prefix_query_plan(
                ["EXAMPLE.COM.", "login.example.co.uk", "example.net", "mybrand.github.io"],
                self.resolver,
            ),
            ("example*", "mybrand*"),
        )

    def test_typo_search_is_bounded_deterministic_and_never_uses_leading_wildcards(self):
        plan = build_prefix_query_plan(["example.com"], self.resolver, typos=True)
        self.assertEqual(plan[0], "example*")
        self.assertIn("exampel*", plan)
        self.assertLessEqual(len(plan), 7)
        self.assertEqual(len(plan), len(set(plan)))
        self.assertEqual(plan, build_prefix_query_plan(["example.com"], self.resolver, typos=True))
        self.assertTrue(all(pattern.endswith("*") and pattern.count("*") == 1 for pattern in plan))
        self.assertTrue(all(not pattern.startswith("*") and "%" not in pattern for pattern in plan))

    def test_prefix_plan_rejects_unsupported_or_overbroad_targets(self):
        for targets in (
            [], ["abc.com"], ["co.uk"], ["https://example.com"], ["xn--exmple-cua.com"],
            [f"brand{number}.com" for number in range(6)],
        ):
            with self.subTest(targets=targets), self.assertRaises(ValidationError):
                build_prefix_query_plan(targets, self.resolver)


class MultiSourceServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "xti.db"
        self.assets = SQLiteAssetRepository(self.database)
        self.assets.initialize()
        AssetService(self.assets).add("example.com")
        self.findings = SQLiteFindingRepository(self.database)
        self.jobs = SQLiteJobRepository(self.database)
        self.matcher = DomainMatcher(PublicSuffixResolver())
        self.lock = TrackingLock()

    def service(self, crt=None, urlscan=None, *, urlscan_matcher=None):
        crt_discovery = DiscoveryService(
            self.assets, self.findings, self.matcher, crt or FakeSource(),
        )
        urlscan_discovery = DiscoveryService(
            self.assets, self.findings, urlscan_matcher or self.matcher,
            urlscan or FakeUrlscanSource(), query_planner=build_prefix_query_plan,
        )
        return JobService(
            self.jobs, crt_discovery, self.lock,
            discoveries={"crt.sh": crt_discovery, "urlscan": urlscan_discovery},
        )

    def test_oldest_mixed_queue_dispatches_saved_provider_after_claim(self):
        crt, urlscan = FakeSource(), FakeUrlscanSource()
        service = self.service(crt, urlscan)
        first = service.enqueue(provider="urlscan")
        second = service.enqueue(provider="crt.sh")
        self.assertEqual(crt.calls + urlscan.calls, [])
        original_search = urlscan.search

        def search_claimed_request(pattern):
            self.assertTrue(self.lock.held)
            self.assertEqual(self.jobs.get(first.id).job.status, "running")
            return original_search(pattern)

        urlscan.search = search_claimed_request
        reopened = self.service(crt, urlscan)
        self.assertEqual(reopened.run().job_id, first.id)
        self.assertEqual(urlscan.calls, ["example*"])
        self.assertEqual(crt.calls, [])
        self.assertEqual(reopened.run().job_id, second.id)
        self.assertEqual(crt.calls, ["%example%", "example%"])
        self.assertIsNone(reopened.run())
        self.assertEqual({item.job.provider for item in self.jobs.latest_by_provider()}, {"crt.sh", "urlscan"})

    def test_evidence_from_second_provider_keeps_finding_and_review_then_deduplicates(self):
        crt = FakeSource({"%example%": batch(document("example-support.net"))})
        urlscan = FakeUrlscanSource({"example*": scoped_batch(urlscan_document())})
        service = self.service(crt, urlscan)
        first = service.run(service.enqueue(provider="crt.sh").id)
        self.assertEqual(first.result.summary.findings_created, 1)
        finding = self.findings.list_findings()[0]
        FindingService(self.findings).review(finding.id, "dismissed", "Kontrollü örnek alan.")
        before = self.findings.get_finding(finding.id)
        second = service.run(service.enqueue(provider="urlscan").id)
        self.assertEqual(second.result.summary.observations_created, 1)
        self.assertEqual(second.result.summary.findings_created, 0)
        self.assertEqual(second.result.summary.findings_existing, 1)
        self.assertEqual(len(self.findings.list_findings()), 1)
        combined = self.findings.get_finding(finding.id)
        self.assertEqual(combined.reviews, before.reviews)
        self.assertEqual(combined.finding.status, "dismissed")
        self.assertEqual(len(combined.observations), 2)
        self.assertEqual(len({item.source_sha256 for item in combined.observations}), 2)
        self.assertEqual(
            {item.source_name for item in combined.observations},
            {document("example-support.net").source_name, urlscan_document().source_name},
        )
        self.assertIn(before.observations[0], combined.observations)
        for provider in ("crt.sh", "urlscan"):
            repeated = service.run(service.enqueue(provider=provider).id)
            self.assertEqual(repeated.result.summary.observations_created, 0)
            self.assertEqual(repeated.result.summary.findings_created, 0)
        self.assertEqual(self.findings.get_finding(finding.id), combined)
        self.assertEqual(self.assets.inspect()["observation_count"], 2)

    def test_provider_retry_preserves_failed_attempt_and_uses_saved_source(self):
        crt = FakeSource()
        failed_source = FakeUrlscanSource({"example*": SourceError("Kaynak yanıt vermedi.")})
        service = self.service(crt, failed_source)
        job = service.enqueue(provider="urlscan")
        failed = service.run(job.id)
        self.assertEqual(failed.status, "failed")
        recovered_source = FakeUrlscanSource({"example*": scoped_batch(urlscan_document())})
        recovered = self.service(crt, recovered_source).retry(job.id)
        self.assertEqual(recovered.status, "complete")
        self.assertEqual(recovered.number, 2)
        self.assertEqual(recovered_source.calls, ["example*"])
        self.assertEqual(crt.calls, [])
        saved = SQLiteJobRepository(self.database).get(job.id)
        self.assertEqual(saved.job.provider, "urlscan")
        self.assertEqual(saved.attempts, (failed, recovered))

    def test_date_scope_is_visible_and_persisted_without_falsely_failing_success(self):
        source = FakeUrlscanSource({"example*": scoped_batch(urlscan_document())})
        service = self.service(urlscan=source)
        job = service.enqueue(provider="urlscan")
        attempt = service.run(job.id)
        self.assertEqual(attempt.status, "complete")
        self.assertEqual(attempt.queries[0].status, "complete")
        self.assertEqual(attempt.queries[0].record_count, 1)
        self.assertEqual(attempt.queries[0].coverage_notes, (COVERAGE_NOTE,))
        reopened = SQLiteJobRepository(self.database).get(job.id)
        self.assertEqual(reopened.attempts, (attempt,))
        status = self.service().source_status()[0]
        self.assertEqual(status["provider"], "urlscan")
        self.assertEqual(status["source_status"], "responded")
        self.assertEqual(status["queries"][0].coverage_notes, (COVERAGE_NOTE,))

    def test_unsupported_provider_is_rejected_before_enqueue_or_http(self):
        crt, urlscan = FakeSource(), FakeUrlscanSource()
        service = self.service(crt, urlscan)
        with self.assertRaises(ValidationError):
            service.enqueue(provider="unsupported")
        self.assertEqual(self.jobs.list(), [])
        self.assertEqual(crt.calls + urlscan.calls, [])

    def test_unsupported_saved_provider_fails_attempt_before_http(self):
        crt, urlscan = FakeSource(), FakeUrlscanSource()
        job = self.jobs.create(("example.com",), False, "unsupported", self.matcher.rule_version)
        with self.assertRaises(ValidationError):
            self.service(crt, urlscan).run()
        self.assertEqual(crt.calls + urlscan.calls, [])
        saved = self.jobs.get(job.id)
        self.assertEqual(saved.job.provider, "unsupported")
        self.assertEqual(saved.job.status, "failed")
        self.assertEqual(saved.attempts[0].queries, ())
        self.assertTrue(saved.attempts[0].error)

    def test_rule_version_is_checked_against_saved_provider_not_default_provider(self):
        crt, urlscan = FakeSource(), FakeUrlscanSource()
        future_matcher = DomainMatcher(self.matcher.resolver, rule_version="future-rule")
        service = self.service(crt, urlscan, urlscan_matcher=future_matcher)
        job = service.enqueue(provider="urlscan")
        self.assertEqual(job.rule_version, "future-rule")
        attempt = service.run(job.id)
        self.assertEqual(attempt.status, "complete")
        self.assertEqual(crt.calls, [])
        self.assertEqual(urlscan.calls, ["example*"])
        changed_job = service.enqueue(provider="urlscan")
        urlscan.calls.clear()
        with self.assertRaises(ValidationError):
            self.service(crt, urlscan).run(changed_job.id)
        self.assertEqual(crt.calls + urlscan.calls, [])
        self.assertEqual(self.jobs.get(changed_job.id).job.status, "failed")


if __name__ == "__main__":
    unittest.main()

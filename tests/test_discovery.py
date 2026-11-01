"""Discovery behavior against disposable SQLite data and an in-memory source."""

from datetime import datetime
import hashlib
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.application.assets import AssetService
from xti.application.discovery import DiscoveryService, build_query_plan
from xti.application.findings import FindingService
from xti.domain.assets import ValidationError
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.domain.matching import DomainMatcher
from xti.ports.discovery import SourceError


def document(domain, certificate_id=1):
    identity = f"crt.sh:{certificate_id}:{domain}"
    return ImportDocument(
        f"https://crt.sh/?id={certificate_id}",
        hashlib.sha256(identity.encode()).hexdigest(),
        (DomainInput(domain, domain, 1, "2026-10-28T10:00:00+00:00"),),
    )


def batch(*documents, skipped_names=0, warnings=()):
    return SourceBatch(tuple(documents), skipped_names, len(documents), tuple(warnings))


class FakeSource:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def search_url(self, pattern):
        return "https://crt.sh/?" + urlencode({"q": pattern, "output": "json"})

    def search(self, pattern):
        self.calls.append(pattern)
        response = self.responses.get(pattern, batch())
        if isinstance(response, Exception):
            raise response
        return response


class QueryPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = PublicSuffixResolver()

    def test_searches_brand_across_suffixes_and_deduplicates_roots(self):
        plan = build_query_plan(
            ["EXAMPLE.COM.", "login.example.co.uk", "example.net"], self.resolver,
        )
        self.assertEqual(plan, ("%example%", "example%"))
        self.assertNotIn("%.example.com", plan)

    def test_uses_private_suffix_boundary_for_independent_hosted_sites(self):
        self.assertEqual(
            build_query_plan(["mybrand.github.io"], self.resolver),
            ("%mybrand%", "mybrand%"),
        )

    def test_rejects_invalid_or_too_broad_targets_before_network_work(self):
        for domains in (
            [], ["abc.com"], ["co.uk"], ["https://example.com"],
            ["xn--exmple-cua.com"], ["örnek.com"],
            [f"brand{number}.com" for number in range(6)],
        ):
            with self.subTest(domains=domains):
                with self.assertRaises(ValidationError):
                    build_query_plan(domains, self.resolver)

    def test_optional_typo_search_is_deterministic_bounded_and_adds_real_swaps(self):
        plain = build_query_plan(["example.com"], self.resolver)
        extended = build_query_plan(["example.com"], self.resolver, typos=True)
        self.assertEqual(extended[:len(plain)], plain)
        self.assertEqual(extended, build_query_plan(["example.com"], self.resolver, typos=True))
        self.assertEqual(len(extended), len(set(extended)))
        self.assertGreater(len(extended), len(plain))
        self.assertLessEqual(len(extended), len(plain) + 6)
        self.assertIn("exampel%", extended)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "xti.db"
        self.assets = SQLiteAssetRepository(self.database)
        self.assets.initialize()
        self.findings = SQLiteFindingRepository(self.database)
        self.asset_service = AssetService(self.assets)
        self.reviews = FindingService(self.findings)
        self.matcher = DomainMatcher(PublicSuffixResolver())

    def service(self, source):
        return DiscoveryService(self.assets, self.findings, self.matcher, source)

    def test_internet_source_results_reach_explainable_saved_findings(self):
        self.asset_service.add("example.com")
        source = FakeSource({"%example%": batch(
            document("example.com", 1),
            document("login.example.com", 2),
            document("example-support.net", 3),
            document("exampel.com", 4),
            document("example.com.attacker.net", 5),
            document("unrelated.org", 6),
        )})
        progress = []
        result = self.service(source).scan(progress=progress.append)
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.targets, ("example.com",))
        self.assertEqual(source.calls, ["%example%", "example%"])
        self.assertEqual(result.summary.observations_created, 6)
        self.assertEqual(result.summary.findings_created, 3)
        expected = {"example-support.net", "exampel.com", "example.com.attacker.net"}
        self.assertEqual(set(result.candidate_domains), expected)
        saved = self.findings.list_findings()
        self.assertEqual({item.domain for item in saved}, expected)
        for finding in saved:
            self.assertTrue(finding.reasons)
            details = self.findings.get_finding(finding.id)
            self.assertTrue(details.observations[0].source_name.startswith("https://crt.sh/?id="))
            self.assertEqual(details.observations[0].observed_at, "2026-10-28T10:00:00+00:00")
        self.assertTrue(progress)
        self.assertTrue(all(query.source_url.startswith("https://crt.sh/?") for query in result.queries))
        self.assertIsNotNone(datetime.fromisoformat(result.started_at).utcoffset())
        self.assertIsNotNone(datetime.fromisoformat(result.finished_at).utcoffset())

    def test_repeated_search_and_overlapping_queries_preserve_identity_and_review(self):
        self.asset_service.add("example.com")
        first = document("example-support.net", 1)
        second = document("example-support.net", 2)
        source = FakeSource({
            "%example%": batch(first, second), "example%": batch(second, first),
        })
        service = self.service(source)
        initial = service.scan()
        self.assertEqual(initial.summary.observations_created, 2)
        self.assertEqual(initial.summary.findings_created, 1)
        self.assertEqual(initial.summary.findings_existing, 0)
        self.assertEqual(initial.candidate_domains, ("example-support.net",))
        finding = self.findings.list_findings()[0]
        self.reviews.review(finding.id, "dismissed", "Kontrollü test alanı.")
        before = self.findings.get_finding(finding.id)
        repeated = service.scan()
        self.assertEqual(repeated.summary.observations_created, 0)
        self.assertEqual(repeated.summary.observations_existing, 2)
        self.assertEqual(repeated.summary.findings_created, 0)
        self.assertEqual(repeated.summary.findings_existing, 1)
        self.assertEqual(self.findings.get_finding(finding.id), before)

    def test_new_certificate_adds_evidence_without_overwriting_the_decision(self):
        self.asset_service.add("example.com")
        service = self.service(FakeSource({"%example%": batch(document("example-support.net", 1))}))
        service.scan()
        finding = self.findings.list_findings()[0]
        self.reviews.review(finding.id, "uncertain", "Ek kanıt bekleniyor.")
        source = FakeSource({"%example%": batch(document("example-support.net", 2))})
        result = self.service(source).scan()
        self.assertEqual(result.summary.findings_created, 0)
        self.assertEqual(result.summary.findings_existing, 1)
        details = self.findings.get_finding(finding.id)
        self.assertEqual(details.finding.status, "uncertain")
        self.assertEqual(len(details.observations), 2)
        self.assertEqual(len(details.reviews), 1)

    def test_selected_target_still_suppresses_every_registered_root(self):
        for domain in ("example.com", "example.net", "anotherbrand.com"):
            self.asset_service.add(domain)
        source = FakeSource({"%example%": batch(
            document("login.example.net", 1),
            document("example-support.net", 2),
            document("anotherbrand-support.net", 3),
        )})
        result = self.service(source).scan(["EXAMPLE.COM."])
        self.assertEqual(result.targets, ("example.com",))
        self.assertEqual(result.candidate_domains, ("example-support.net",))
        self.assertEqual({item.asset_value for item in self.findings.list_findings()}, {"example.com"})

    def test_missing_and_unregistered_targets_do_not_call_source_or_write(self):
        source = FakeSource()
        with self.assertRaises(ValidationError):
            self.service(source).scan()
        self.asset_service.add("example.com")
        with self.assertRaises(ValidationError):
            self.service(source).scan(["otherbrand.com"])
        self.assertEqual(source.calls, [])
        self.assertEqual(self.assets.inspect()["observation_count"], 0)

    def test_partial_source_failure_keeps_useful_results_and_reports_failure(self):
        self.asset_service.add("example.com")
        source = FakeSource({
            "%example%": SourceError("Kaynak zaman aşımına uğradı."),
            "example%": batch(document("example-support.net")),
        })
        result = self.service(source).scan()
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.summary.findings_created, 1)
        self.assertEqual(len(result.queries), 2)
        self.assertEqual(result.queries[0].status, "failed")
        self.assertIn("zaman aşımı", result.queries[0].error)
        self.assertIsNone(result.queries[1].error)

    def test_all_source_failures_are_distinct_from_a_successful_empty_search(self):
        self.asset_service.add("example.com")
        failed = FakeSource({
            "%example%": SourceError("Kaynak yanıt vermedi."),
            "example%": SourceError("Kaynak yanıt vermedi."),
        })
        failure = self.service(failed).scan()
        self.assertEqual(failure.status, "failed")
        self.assertEqual(failure.summary.total_records, 0)
        self.assertTrue(all(query.error for query in failure.queries))
        empty = self.service(FakeSource()).scan()
        self.assertEqual(empty.status, "complete")
        self.assertEqual(empty.summary.total_records, 0)
        self.assertEqual(empty.candidate_domains, ())
        self.assertTrue(all(query.error is None for query in empty.queries))
        self.assertEqual(self.assets.inspect()["observation_count"], 0)

    def test_source_cap_and_skipped_names_are_visible_as_incomplete_coverage(self):
        self.asset_service.add("example.com")
        for response in (
            batch(document("example-support.net"), warnings=("Kaynak sonuç sınırına ulaştı.",)),
            batch(document("example-support.net"), skipped_names=2),
        ):
            with self.subTest(response=response):
                result = self.service(FakeSource({"%example%": response})).scan()
                self.assertEqual(result.status, "partial")
                self.assertEqual(result.queries[0].skipped_names, response.skipped_names)
                self.assertEqual(result.queries[0].warnings, response.warnings)

    def test_scan_document_limit_is_checked_before_any_observation_is_saved(self):
        self.asset_service.add("example.com")
        too_many = batch(*(document("example-support.net", number) for number in range(10_001)))
        with self.assertRaises(ValidationError):
            self.service(FakeSource({"%example%": too_many})).scan()
        self.assertEqual(self.assets.inspect()["observation_count"], 0)
        self.assertEqual(self.findings.list_findings(), [])

    def test_conflicting_source_identity_is_rejected_before_saving_either_record(self):
        self.asset_service.add("example.com")
        original = document("example-support.net", 1)
        changed = ImportDocument(
            original.source_name, original.sha256,
            (DomainInput("example-login.net", "example-login.net", 1, None),),
        )
        source = FakeSource({"%example%": batch(original), "example%": batch(changed)})
        with self.assertRaises(ValidationError):
            self.service(source).scan()
        self.assertEqual(self.assets.inspect()["observation_count"], 0)
        self.assertEqual(self.findings.list_findings(), [])


if __name__ == "__main__":
    unittest.main()

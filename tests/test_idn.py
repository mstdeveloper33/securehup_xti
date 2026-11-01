"""Pinned Unicode/IDNA behavior; no test performs a network request."""

import hashlib
from pathlib import Path
import tempfile
import unittest

from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.unicode_security import unicode_security_profile
from xti.application.assets import AssetService
from xti.application.discovery import DiscoveryService, build_prefix_query_plan, build_query_plan
from xti.domain.assets import Asset, ValidationError
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.domain.idn import MAX_IDN_QUERY_VARIANTS, UNICODE_VERSION
from xti.domain.matching import DomainMatcher


def asset(value: str = "example.com") -> Asset:
    return Asset("watched", value, "2026-10-29T00:00:00+00:00")


class UnicodeProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.security = unicode_security_profile()

    def test_profile_is_pinned_and_u_label_round_trip_keeps_ascii_identity(self):
        self.assertEqual(self.security.version, UNICODE_VERSION)
        canonical = self.security.to_ascii("BÜCHER.example.")
        self.assertEqual(canonical, "xn--bcher-kva.example")
        self.assertEqual(self.security.to_unicode(canonical), "bücher.example")
        self.assertEqual(self.security.to_ascii(canonical), canonical)

    def test_invalid_fake_a_labels_controls_joiners_and_rtl_are_declined(self):
        values = (
            "xn--.example", "xn--abc-.example", "ab\u200dcd.example",
            "مثال.example", "bad\x1b.example",
        )
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.security.to_ascii(value)

    def test_uts39_skeleton_detects_cross_script_lookalike_not_arbitrary_idn(self):
        self.assertTrue(self.security.confusable("example", "еxample"))
        self.assertFalse(self.security.confusable("example", "bücher"))

    def test_search_variants_are_real_bounded_deterministic_a_labels(self):
        variants = self.security.search_variants("example")
        self.assertEqual(variants, self.security.search_variants("example"))
        self.assertEqual(len(variants), len(set(variants)))
        self.assertLessEqual(len(variants), MAX_IDN_QUERY_VARIANTS)
        self.assertTrue(variants)
        for variant in variants:
            self.assertTrue(variant.startswith("xn--"))
            self.assertFalse(self.security.to_unicode(variant + ".test").isascii())


class IdnBoundaryAndMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.security = unicode_security_profile()

    def setUp(self):
        self.resolver = PublicSuffixResolver(
            "// VERSION: fixture\ncom\nnet\n公司.cn\ncn\n",
            unicode_security=self.security,
        )
        self.matcher = DomainMatcher(
            self.resolver,
            unicode_security=self.security,
            rule_version="execution-v2",
            ascii_rule_version="ascii-v1",
            idn_rule_version="idn-v1",
        )

    def test_unicode_public_suffix_rule_is_converted_before_boundary_resolution(self):
        value = self.security.to_ascii("brand.公司.cn")
        parts = self.resolver.parts(value)
        self.assertEqual(parts.registrable_domain, value)
        self.assertEqual(parts.brand, "brand")
        self.assertEqual(parts.suffix, self.security.to_ascii("公司.cn"))

    def test_idn_candidate_gets_unicode_reason_and_separate_rule_identity(self):
        candidate = self.security.to_ascii("еxample.net")
        result = self.matcher.match(asset(), candidate)
        self.assertIsNotNone(result)
        self.assertEqual(result.domain, candidate)
        self.assertEqual(result.rule_version, "idn-v1")
        self.assertTrue(any("Unicode benzer-harf" in reason for reason in result.reasons))

    def test_idn_subdomain_is_detected_under_a_different_registration_root(self):
        candidate = self.security.to_ascii("еxample.com.attacker.net")
        result = self.matcher.match(asset(), candidate)
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_version, "idn-v1")
        self.assertTrue(any("alt etiketi" in reason for reason in result.reasons))

    def test_non_confusable_idn_is_not_a_candidate_and_ascii_identity_is_preserved(self):
        self.assertIsNone(self.matcher.match(asset(), self.security.to_ascii("bücher.net")))
        ascii_result = self.matcher.match(asset(), "example-support.net")
        self.assertEqual(ascii_result.rule_version, "ascii-v1")

    def test_matcher_without_profile_never_treats_punycode_as_plain_ascii(self):
        plain = DomainMatcher(PublicSuffixResolver("com\nnet\n"))
        with self.assertRaises(ValidationError):
            plain.match(asset(), self.security.to_ascii("еxample.net"))

    def test_query_plans_add_only_bounded_real_a_label_searches(self):
        crt = build_query_plan(
            ["example.com"], self.resolver, typos=True, unicode_security=self.security,
        )
        urlscan = build_prefix_query_plan(
            ["example.com"], self.resolver, typos=True, unicode_security=self.security,
        )
        variants = self.security.search_variants("example")
        self.assertEqual(crt[:2], ("%example%", "example%"))
        # ASCII adjacent swaps are also part of --typos, so assert bounded IDN
        # inclusion rather than coupling this test to that separate rule count.
        self.assertLessEqual(len(crt), 2 + 2 * len(variants) + 6)
        self.assertLessEqual(len(urlscan), 1 + len(variants) + 6)
        for variant in variants:
            self.assertIn(f"%{variant}%", crt)
            self.assertIn(f"{variant}%", crt)
            self.assertIn(f"{variant}*", urlscan)


class IdnPersistenceFlowTests(unittest.TestCase):
    def test_bounded_internet_plan_reaches_one_stable_review_candidate(self):
        security = unicode_security_profile()
        resolver = PublicSuffixResolver("com\nnet\n", unicode_security=security)
        matcher = DomainMatcher(
            resolver, unicode_security=security, rule_version="execution-v2",
            ascii_rule_version="ascii-v1", idn_rule_version="idn-v1",
        )
        candidate = security.to_ascii("еxample.net")
        digest = hashlib.sha256(b"idn-source-record").hexdigest()
        document = ImportDocument(
            "https://source.invalid/record/1", digest,
            (DomainInput(candidate, "еxample.net", 1, "2026-10-29T00:00:00+00:00"),),
        )

        class Source:
            def __init__(self):
                self.calls = []

            def search_url(self, pattern):
                return "https://source.invalid/search?q=" + pattern

            def search(self, pattern):
                self.calls.append(pattern)
                documents = (document,) if "xn--xample-2of" in pattern else ()
                return SourceBatch(documents, 0, len(documents))

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "xti.db"
            assets = SQLiteAssetRepository(database)
            assets.initialize()
            AssetService(assets).add("example.com")
            findings = SQLiteFindingRepository(database)
            source = Source()
            service = DiscoveryService(assets, findings, matcher, source)

            first = service.scan(typos=True)
            second = service.scan(typos=True)
            self.assertIn("%xn--xample-2of%", source.calls)
            self.assertEqual(first.summary.findings_created, 1)
            self.assertEqual(second.summary.findings_created, 0)
            self.assertEqual(second.summary.findings_existing, 1)
            saved = findings.list_findings()
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].domain, candidate)
            self.assertEqual(saved[0].rule_version, "idn-v1")
            self.assertTrue(any("Unicode benzer-harf" in item for item in saved[0].reasons))


if __name__ == "__main__":
    unittest.main()

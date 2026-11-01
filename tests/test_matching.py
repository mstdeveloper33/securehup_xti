"""Offline boundary and candidate-rule behavior on labelled examples."""

import json
from pathlib import Path
import unittest

from xti.adapters.public_suffix import PublicSuffixResolver
from xti.domain.assets import Asset, ValidationError
from xti.domain.matching import DomainMatcher, DomainParts, RULE_VERSION


_TEST_RULES = """
// VERSION: fixture-v1
// COMMIT: fixture-commit
com
net
org
uk
co.uk
tr
com.tr
io
github.io
jp
*.kawasaki.jp
!city.kawasaki.jp
ck
*.ck
!www.ck
"""


def asset(value: str) -> Asset:
    return Asset(id="watched-1", value=value, created_at="2026-10-28T00:00:00+00:00")


class PublicSuffixTests(unittest.TestCase):
    def setUp(self):
        self.resolver = PublicSuffixResolver(_TEST_RULES)

    def test_multi_label_suffix_uses_registration_boundary(self):
        self.assertEqual(
            self.resolver.parts("login.example.co.uk"),
            DomainParts("example.co.uk", "example", "co.uk", "login"),
        )
        self.assertEqual(self.resolver.parts("ornek.com.tr").brand, "ornek")

    def test_private_suffix_tenants_remain_separate(self):
        self.assertEqual(self.resolver.parts("alpha.github.io").registrable_domain,
                         "alpha.github.io")
        self.assertEqual(self.resolver.parts("beta.github.io").registrable_domain,
                         "beta.github.io")
        self.assertEqual(self.resolver.parts("github.io").registrable_domain, None)

    def test_wildcard_can_make_entire_domain_a_public_suffix(self):
        self.assertEqual(self.resolver.parts("foo.kawasaki.jp"),
                         DomainParts(None, None, "foo.kawasaki.jp", ""))
        self.assertEqual(self.resolver.parts("www.foo.kawasaki.jp"),
                         DomainParts("www.foo.kawasaki.jp", "www", "foo.kawasaki.jp", ""))
        self.assertEqual(self.resolver.parts("foo.ck").registrable_domain, None)

    def test_exception_overrides_wildcard(self):
        self.assertEqual(self.resolver.parts("www.city.kawasaki.jp"),
                         DomainParts("city.kawasaki.jp", "city", "kawasaki.jp", "www"))
        self.assertEqual(self.resolver.parts("x.www.ck"),
                         DomainParts("www.ck", "www", "ck", "x"))

    def test_unknown_suffix_uses_implicit_wildcard(self):
        self.assertEqual(self.resolver.parts("login.example.unlisted"),
                         DomainParts("example.unlisted", "example", "unlisted", "login"))

    def test_parser_metadata_is_tied_to_loaded_text(self):
        self.assertEqual(self.resolver.version, "fixture-v1")
        self.assertEqual(self.resolver.commit, "fixture-commit")
        self.assertEqual(len(self.resolver.sha256), 64)
        self.assertNotEqual(self.resolver.sha256, PublicSuffixResolver("com\n").sha256)

    def test_raw_unicode_is_rejected_but_ascii_registration_boundaries_accept_a_labels(self):
        with self.assertRaises(ValidationError):
            self.resolver.parts("örnek.com")
        self.assertEqual(self.resolver.parts("xn--rnek-4qa.com").suffix, "com")
        self.assertEqual(self.resolver.parts("example.xn--p1ai").brand, "example")

    def test_bundled_list_handles_public_private_and_exception_rules(self):
        resolver = PublicSuffixResolver()
        self.assertEqual(resolver.parts("login.example.co.uk").registrable_domain, "example.co.uk")
        self.assertEqual(resolver.parts("alpha.github.io").registrable_domain, "alpha.github.io")
        self.assertEqual(resolver.parts("www.city.kawasaki.jp").suffix, "kawasaki.jp")
        self.assertNotEqual(resolver.version, "unknown")


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.matcher = DomainMatcher(PublicSuffixResolver(_TEST_RULES))

    def test_labelled_candidate_examples(self):
        fixture = Path(__file__).parent / "fixtures" / "matching_cases.json"
        cases = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 20)
        for case in cases:
            with self.subTest(case=case["case"], asset=case["asset"], domain=case["domain"]):
                result = self.matcher.match(asset(case["asset"]), case["domain"])
                self.assertEqual(result is not None, case["candidate"])
                if result:
                    self.assertEqual(result.asset_id, "watched-1")
                    self.assertEqual(result.domain, case["domain"])
                    self.assertEqual(result.rule_version, RULE_VERSION)
                    self.assertTrue(result.reasons)
                    self.assertNotIn("doğrulanmış", " ".join(result.reasons))

    def test_complete_domain_embedding_has_specific_explanation(self):
        result = self.matcher.match(asset("example.com"), "login.example.com.attacker.net")
        self.assertIsNotNone(result)
        self.assertTrue(any("kayıt kökü farklı" in reason for reason in result.reasons))
        self.assertTrue(any("attacker.net" in reason for reason in result.reasons))

    def test_typo_and_swap_have_distinct_explanations(self):
        typo = self.matcher.match(asset("example.com"), "examp1e.net")
        swapped = self.matcher.match(asset("example.com"), "exampel.net")
        self.assertTrue(any("tek karakter farkı" in reason for reason in typo.reasons))
        self.assertTrue(any("iki karakterin yeri" in reason for reason in swapped.reasons))

    def test_inputs_are_canonicalized_without_network_checks(self):
        result = self.matcher.match(asset("EXAMPLE.COM."), " EXAMPLE-SUPPORT.NET. ")
        self.assertEqual(result.asset_value, "example.com")
        self.assertEqual(result.domain, "example-support.net")

    def test_punycode_asset_is_not_silently_compared_as_plain_text(self):
        with self.assertRaises(ValidationError):
            self.matcher.match(asset("xn--rnek-4qa.com"), "example.net")

    def test_an_asset_without_a_registrant_label_has_no_candidate(self):
        self.assertIsNone(self.matcher.match(asset("co.uk"), "example.co.uk"))

    def test_reference_specific_rule_version_is_saved_with_the_candidate(self):
        resolver = PublicSuffixResolver(_TEST_RULES)
        version = f"{RULE_VERSION}/psl:{resolver.sha256}"
        result = DomainMatcher(resolver, rule_version=version).match(
            asset("example.com"), "example-support.net"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_version, version)


if __name__ == "__main__":
    unittest.main()


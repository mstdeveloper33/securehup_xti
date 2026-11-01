"""Second-generation ASCII patterns preserve old identities and narrow scope."""

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_allowlist import SQLiteAllowlistRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.application.allowlist import AllowlistService
from xti.application.assets import AssetService
from xti.application.findings import DomainImportService
from xti.interfaces.cli import make_domain_matcher

from tests.test_discovery import document


class ExpandedMatchingTests(unittest.TestCase):
    def setUp(self):
        self.matcher = make_domain_matcher()

    def asset(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteAssetRepository(Path(directory) / "xti.db")
            repository.initialize()
            return AssetService(repository).add("example.com")[0]

    def test_new_patterns_have_new_identity_while_old_ascii_and_idn_stay_stable(self):
        asset = self.asset()
        standard = self.matcher.match(asset, "example-support.net")
        compact_shop = self.matcher.match(asset, "exampleshop.net")
        combined = self.matcher.match(asset, "exampel-login.net")
        idn = self.matcher.match(asset, "xn--xample-2of.net")
        self.assertIn("domain-rules-v3", self.matcher.rule_version)
        self.assertIn("domain-rules-v1", standard.rule_version)
        self.assertIn("domain-rules-v2", compact_shop.rule_version)
        self.assertIn("domain-rules-v2", combined.rule_version)
        self.assertIn("idn-confusables-v1", idn.rule_version)
        self.assertTrue(any("mağaza" in reason for reason in compact_shop.reasons))
        self.assertTrue(any("hizmet eki" in reason for reason in combined.reasons))

    def test_expansion_does_not_accept_unknown_suffix_longer_word_or_short_brand_shop(self):
        asset = self.asset()
        self.assertIsNone(self.matcher.match(asset, "exampel-garden.net"))
        self.assertIsNone(self.matcher.match(asset, "exampleshopping.net"))
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteAssetRepository(Path(directory) / "xti.db")
            repository.initialize()
            short = AssetService(repository).add("work.com")[0]
            self.assertIsNone(self.matcher.match(short, "workshop.net"))

    def test_existing_ascii_finding_is_reused_and_only_new_pattern_gets_v2_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "xti.db"
            assets = SQLiteAssetRepository(database)
            assets.initialize()
            AssetService(assets).add("example.com")
            findings = SQLiteFindingRepository(database)
            service = DomainImportService(assets, findings, self.matcher)

            first = service.import_document(document("example-support.net", 1))
            repeated = service.import_document(document("example-support.net", 2))
            expanded = service.import_document(document("exampel-login.net", 3))
            self.assertEqual(first.findings_created, 1)
            self.assertEqual(repeated.findings_existing, 1)
            self.assertEqual(expanded.findings_created, 1)
            saved = {item.domain: item for item in findings.list_findings()}
            self.assertIn("domain-rules-v1", saved["example-support.net"].rule_version)
            self.assertIn("domain-rules-v2", saved["exampel-login.net"].rule_version)
            self.assertEqual(assets.inspect()["notification_count"], 2)

    def test_exact_allowlist_also_suppresses_a_new_pattern_without_deleting_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "xti.db"
            assets = SQLiteAssetRepository(database)
            assets.initialize()
            AssetService(assets).add("example.com")
            allowlist = SQLiteAllowlistRepository(database)
            policy = AllowlistService(
                assets, allowlist, self.matcher,
                clock=lambda: datetime(2026, 10, 29, tzinfo=timezone.utc),
            )
            policy.add("example.com", "exampel-login.net", "Doğrulanmış test adresi.")
            findings = SQLiteFindingRepository(database)
            summary = DomainImportService(
                assets, findings, self.matcher, allowlist,
            ).import_document(document("exampel-login.net", 1))
            self.assertEqual(summary.findings_suppressed, 1)
            self.assertEqual(findings.list_findings(), [])
            self.assertEqual(assets.inspect()["observation_count"], 1)
            self.assertEqual(assets.inspect()["notification_count"], 0)


if __name__ == "__main__":
    unittest.main()

"""Exact-domain exceptions are narrow, reversible and evidence-preserving."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.public_suffix import PublicSuffixResolver
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_allowlist import SQLiteAllowlistRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.unicode_security import unicode_security_profile
from xti.application.allowlist import AllowlistService
from xti.application.assets import AssetService
from xti.application.discovery import DiscoveryService
from xti.application.findings import DomainImportService, FindingService
from xti.domain.assets import ValidationError
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument, MatchCandidate
from xti.domain.matching import DomainMatcher


TIMES = (
    datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc),
    datetime(2026, 10, 29, 10, 0, tzinfo=timezone.utc),
    datetime(2026, 10, 29, 11, 0, tzinfo=timezone.utc),
    datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc),
)


def document(domain="example-support.net", identity="one"):
    return ImportDocument(
        f"https://source.invalid/{identity}",
        hashlib.sha256(identity.encode()).hexdigest(),
        (DomainInput(domain, domain, 1, "2026-10-29T08:00:00+00:00"),),
    )


class RepeatingSource:
    def __init__(self, value):
        self.value = value

    def search_url(self, pattern):
        return "https://source.invalid/search?q=" + pattern

    def search(self, pattern):
        return SourceBatch((self.value,), 0, 1)


class AllowlistTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "xti.db"
        self.assets = SQLiteAssetRepository(self.database)
        self.assets.initialize()
        self.asset = AssetService(self.assets).add("example.com")[0]
        self.security = unicode_security_profile()
        self.matcher = DomainMatcher(
            PublicSuffixResolver("com\nnet\norg\n", unicode_security=self.security),
            unicode_security=self.security,
            rule_version="execution-v2",
            ascii_rule_version="ascii-v1",
            idn_rule_version="idn-v1",
        )
        self.repository = SQLiteAllowlistRepository(self.database)
        self.clock_values = iter(TIMES)
        self.service = AllowlistService(
            self.assets, self.repository, self.matcher, clock=lambda: next(self.clock_values),
        )

    def test_lifecycle_is_idempotent_reversible_and_append_only(self):
        entry, created = self.service.add(
            "EXAMPLE.COM.", "EXAMPLE-SUPPORT.NET.", "Bilinen hizmet sağlayıcı.",
        )
        self.assertTrue(created)
        self.assertTrue(entry.active)
        self.assertEqual(entry.domain, "example-support.net")
        self.assertEqual(entry.created_at, TIMES[0].isoformat())

        repeated, created = self.service.add(
            "example.com", "example-support.net", "Bu açıklama kaydedilmemeli.",
        )
        self.assertFalse(created)
        self.assertEqual(repeated, entry)
        self.assertEqual(len(self.service.show(entry.id).events), 1)

        revoked = self.service.revoke(entry.id, "Artık yeniden değerlendirilecek.")
        self.assertFalse(revoked.active)
        self.assertEqual(self.service.list(), ())
        self.assertEqual(self.service.list(active_only=False), (revoked,))

        reactivated, created = self.service.add(
            "example.com", "example-support.net", "İş ortaklığı doğrulandı.",
        )
        self.assertTrue(created)
        self.assertEqual(reactivated.id, entry.id)
        details = self.service.show(entry.id)
        self.assertEqual(
            tuple(event.action for event in details.events),
            ("added", "revoked", "reactivated"),
        )
        self.assertEqual(details.entry.created_at, entry.created_at)
        self.assertEqual(details.entry.updated_at, TIMES[3].isoformat())

    def test_scope_is_exact_and_unrelated_or_broad_exceptions_are_rejected(self):
        attempts = (
            ("missing.com", "example-support.net", "Kayıtlı değil."),
            ("example.com", "unrelated.org", "İlgisiz."),
            ("example.com", "example.com", "Kök adres."),
            ("example.com", "*.example.net", "Çok geniş."),
            ("example.com", "example-support.net", "  "),
            ("example.com", "example-support.net", "bad\x1btext"),
        )
        for asset, candidate, reason in attempts:
            with self.subTest(candidate=candidate, reason=reason):
                with self.assertRaises(ValidationError):
                    self.service.add(asset, candidate, reason)
        self.assertEqual(self.repository.list(active_only=False), ())
        with self.assertRaises(ValidationError):
            self.service.show("")
        with self.assertRaises(ValidationError):
            self.service.list(limit=0)

    def test_unicode_candidate_is_stored_as_one_canonical_ascii_identity(self):
        entry, created = self.service.add(
            "example.com", "еxample.net", "Doğrulanmış uluslararası alan adı.",
        )
        self.assertTrue(created)
        self.assertEqual(entry.domain, "xn--xample-2of.net")
        self.assertEqual(
            self.repository.active_pairs((self.asset.id, self.asset.id)),
            frozenset({(self.asset.id, "xn--xample-2of.net")}),
        )

    def test_active_exception_keeps_observation_but_prevents_finding_and_notification(self):
        self.service.add("example.com", "example-support.net", "Meşru test alanı.")
        findings = SQLiteFindingRepository(self.database)
        service = DiscoveryService(
            self.assets, findings, self.matcher, RepeatingSource(document()),
            allowlist=self.repository,
        )
        progress = []
        first = service.scan(progress=progress.append)
        second = service.scan()
        self.assertEqual(first.summary.observations_created, 1)
        self.assertEqual(first.summary.findings_suppressed, 1)
        self.assertEqual(first.candidate_domains, ())
        self.assertEqual(second.summary.observations_existing, 1)
        self.assertEqual(second.summary.findings_suppressed, 1)
        self.assertEqual(findings.list_findings(), [])
        self.assertTrue(any("istisnası uygulandı" in item for item in progress))
        info = self.assets.inspect()
        self.assertEqual(info["observation_count"], 1)
        self.assertEqual(info["notification_count"], 0)

    def test_revocation_reprocesses_preserved_observation_into_a_finding(self):
        entry, _ = self.service.add("example.com", "example-support.net", "Geçici istisna.")
        findings = SQLiteFindingRepository(self.database)
        source = RepeatingSource(document())
        discovery = DiscoveryService(
            self.assets, findings, self.matcher, source, allowlist=self.repository,
        )
        discovery.scan()
        self.service.revoke(entry.id, "İstisna geri alındı.")
        result = discovery.scan()
        self.assertEqual(result.summary.observations_existing, 1)
        self.assertEqual(result.summary.findings_created, 1)
        self.assertEqual(result.summary.findings_suppressed, 0)
        details = findings.get_finding(findings.list_findings()[0].id)
        self.assertEqual(len(details.observations), 1)
        self.assertEqual(self.assets.inspect()["notification_count"], 1)

    def test_existing_finding_review_and_evidence_are_never_deleted_by_exception(self):
        findings = SQLiteFindingRepository(self.database)
        source = RepeatingSource(document(identity="first"))
        discovery = DiscoveryService(
            self.assets, findings, self.matcher, source, allowlist=self.repository,
        )
        discovery.scan()
        saved = findings.list_findings()[0]
        FindingService(findings).review(saved.id, "dismissed", "Meşru olduğu doğrulandı.")
        before = findings.get_finding(saved.id)
        entry, _ = self.service.add("example.com", saved.domain, "Onaylı istisna.")

        source.value = document(identity="second")
        suppressed = discovery.scan()
        self.assertEqual(suppressed.summary.findings_suppressed, 1)
        during = findings.get_finding(saved.id)
        self.assertEqual(during, before)
        self.assertEqual(self.assets.inspect()["observation_count"], 2)

        self.service.revoke(entry.id, "Yeni kanıt tekrar ilişkilendirilecek.")
        linked = discovery.scan()
        self.assertEqual(linked.summary.findings_existing, 1)
        after = findings.get_finding(saved.id)
        self.assertEqual(after.finding.status, "dismissed")
        self.assertEqual(after.reviews, before.reviews)
        self.assertEqual(len(after.observations), 2)
        self.assertEqual(self.assets.inspect()["notification_count"], 1)

    def test_storage_enforces_policy_even_if_application_forgets_to_filter(self):
        self.service.add("example.com", "example-support.net", "Savunma katmanı testi.")
        candidate = self.matcher.match(self.asset, "example-support.net")
        self.assertIsNotNone(candidate)
        summary = SQLiteFindingRepository(self.database).save_import(document(), (candidate,))
        self.assertEqual(summary.findings_suppressed, 1)
        self.assertEqual(summary.findings_created, 0)
        self.assertEqual(self.assets.inspect()["observation_count"], 1)

    def test_offline_import_uses_the_same_policy(self):
        self.service.add("example.com", "example-support.net", "Meşru alan adı.")
        findings = SQLiteFindingRepository(self.database)
        summary = DomainImportService(
            self.assets, findings, self.matcher, self.repository,
        ).import_document(document())
        self.assertEqual(summary.findings_suppressed, 1)
        self.assertEqual(findings.list_findings(), [])

    def test_exception_is_scoped_to_one_watched_asset_not_the_whole_candidate(self):
        second_asset = AssetService(self.assets).add("example.net")[0]
        self.service.add("example.com", "example-support.org", "Yalnız bu varlık için meşru.")
        findings = SQLiteFindingRepository(self.database)
        summary = DomainImportService(
            self.assets, findings, self.matcher, self.repository,
        ).import_document(document("example-support.org"))
        self.assertEqual(summary.findings_suppressed, 1)
        self.assertEqual(summary.findings_created, 1)
        saved = findings.list_findings()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].asset_id, second_asset.id)
        self.assertEqual(saved[0].asset_value, "example.net")

    def test_missing_database_read_has_no_side_effect_and_corruption_fails_closed(self):
        missing = Path(self.temp.name) / "missing" / "xti.db"
        with self.assertRaises(StorageError):
            SQLiteAllowlistRepository(missing).list()
        self.assertFalse(missing.exists())

        entry, _ = self.service.add("example.com", "example-support.net", "Bozulma testi.")
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(
                "UPDATE allowlist_entries SET domain = 'EXAMPLE-SUPPORT.NET' WHERE id = ?",
                (entry.id,),
            )
        with self.assertRaisesRegex(StorageError, "bozuk"):
            self.repository.get(entry.id)


if __name__ == "__main__":
    unittest.main()

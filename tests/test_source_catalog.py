import unittest

from xti.application.sources import SourceCatalogService


class SourceCatalogTests(unittest.TestCase):
    def test_catalog_has_unique_stable_entries_and_explicit_credentials(self):
        items = SourceCatalogService().list()
        self.assertEqual(
            [item.identifier for item in items],
            [
                "crt.sh", "theharvester-archives", "urlscan", "google-public-dns",
                "explicit-https-head", "explicit-tcp-connect", "feodo-tracker",
                "certpl-warning-list", "hibp-public-breach-catalog", "threatcluster-ransomware-claims",
                "ransomlook-ransomware-posts",
                "mitre-attack-enterprise", "cisa-kev",
                "first-epss", "nist-nvd-cve", "osv-dev", "canonical-ubuntu-osv",
                "redhat-csaf-vex", "suse-csaf-vex", "news:cisa", "news:ncsc", "news:cert-fr",
                "mentions:tavily",
                "warninglist:cloudflare", "warninglist:rfc1918", "warninglist:rfc3849", "warninglist:rfc6761",
                "enrichment:ripestat", "enrichment:circl", "enrichment:urlscan",
            ],
        )
        self.assertEqual(len({item.identifier for item in items}), len(items))
        self.assertEqual([item.identifier for item in items if item.credential_required], ['mentions:tavily'])
        self.assertTrue(all(not item.paid_dependency for item in items))

    def test_only_explicit_active_check_claims_direct_target_contact(self):
        contacts = [item.identifier for item in SourceCatalogService().list()
                    if item.contacts_monitored_target]
        self.assertEqual(contacts, ["explicit-https-head", "explicit-tcp-connect"])

    def test_warninglists_are_reference_context_with_explicit_refresh_and_terms(self):
        entries = [item for item in SourceCatalogService().list() if item.identifier.startswith('warninglist:')]
        self.assertEqual(len(entries), 4)
        for entry in entries:
            self.assertEqual(entry.kind, 'reference_context')
            self.assertFalse(entry.credential_required or entry.paid_dependency or entry.contacts_monitored_target)
            self.assertIn('warninglists sync --list ' + entry.identifier.split(':')[1], entry.commands)
            self.assertIn('CC0-1.0', ' '.join(entry.limits))
            self.assertIn('gönderilmez', ' '.join(entry.limits))

    def test_every_entry_explains_scope_and_has_an_https_reference(self):
        for item in SourceCatalogService().list():
            with self.subTest(item.identifier):
                self.assertTrue(item.purpose)
                self.assertTrue(item.commands)
                self.assertTrue(item.limits)
                self.assertTrue(item.reference_url.startswith("https://"))

    def test_surface_monitor_is_visible_for_each_network_path_it_can_use(self):
        items = {item.identifier: item for item in SourceCatalogService().list()}
        self.assertIn("surface monitor", items["google-public-dns"].commands)
        self.assertIn("surface monitor", items["explicit-https-head"].commands)
        self.assertIn(
            "surface monitor --checks services",
            items["explicit-tcp-connect"].commands,
        )
        self.assertFalse(items["theharvester-archives"].contacts_monitored_target)
        self.assertIn(
            "surface discover KOK --source theharvester",
            items["theharvester-archives"].commands,
        )

    def test_canonical_source_exposes_verified_inventory_comparison(self):
        items = {item.identifier: item for item in SourceCatalogService().list()}
        canonical = items["canonical-ubuntu-osv"]
        self.assertIn(
            "vuln ubuntu-inventory-match UBUNTU_PAKET_KIMLIGI CVE-YIL-SAYI",
            canonical.commands,
        )
        self.assertIn(
            "vuln ubuntu-inventory-scan CVE-YIL-SAYI --domain ALAN_ADI",
            canonical.commands,
        )
        self.assertIn(
            "vuln ubuntu-evidence-add INCELEME_KIMLIGI UBUNTU_PAKET_KIMLIGI "
            "--summary ACIKLAMA",
            canonical.commands,
        )
        self.assertIn("vuln ubuntu-evidence-check KANIT_KIMLIGI", canonical.commands)
        self.assertIn("vuln ubuntu-evidence-plan --domain ALAN_ADI", canonical.commands)
        self.assertIn(
            "vuln ubuntu-evidence-scan --domain ALAN_ADI --limit 10",
            canonical.commands,
        )
        self.assertTrue(any("binary→source" in limit for limit in canonical.limits))
        self.assertTrue(any("Kalıcı destek kanıtı" in limit for limit in canonical.limits))

    def test_ransomware_source_exposes_explicit_refresh_all_watch_command(self):
        items = {item.identifier: item for item in SourceCatalogService().list()}
        ransomware = items["threatcluster-ransomware-claims"]
        self.assertIn("ransomware watch-refresh-all", ransomware.commands)
        self.assertIn(
            "ransomware watch-monitor --cycles 3 --interval 3600 --duration 86400",
            ransomware.commands,
        )
        self.assertIn("ransomware watch-monitor-list", ransomware.commands)
        self.assertIn(
            "ransomware watch-monitor-show OTURUM_KIMLIGI", ransomware.commands,
        )
        self.assertIn(
            "ransomware watch-timeline IZLEME_KIMLIGI", ransomware.commands,
        )
        self.assertIn(
            "ransomware watch-identity-candidates IZLEME_KIMLIGI",
            ransomware.commands,
        )
        self.assertIn(
            "ransomware watch-identity-review IZLEME_KIMLIGI ADAY_KIMLIGI",
            ransomware.commands,
        )
        self.assertIn(
            "ransomware watch-identity-review-show ADAY_KIMLIGI",
            ransomware.commands,
        )
        self.assertIn("ransomware source-compare", ransomware.commands)
        self.assertIn(
            "ransomware source-review KARSILASTIRMA_KIMLIGI",
            ransomware.commands,
        )
        self.assertIn(
            "ransomware source-review-show KARSILASTIRMA_KIMLIGI",
            ransomware.commands,
        )
        self.assertIn(
            "ransomware source-compare",
            items["ransomlook-ransomware-posts"].commands,
        )
        self.assertIn(
            "ransomware source-review KARSILASTIRMA_KIMLIGI",
            items["ransomlook-ransomware-posts"].commands,
        )
        self.assertTrue(any(
            "silinmeyen olay geçmişidir" in limit
            for limit in ransomware.limits
        ))
        self.assertIn("watch-refresh-all", ransomware.access)
        self.assertIn("watch-monitor", ransomware.access)
        self.assertTrue(any(
            "terminal açıkken" in limit and "zamanlayıcı" in limit
            for limit in ransomware.limits
        ))


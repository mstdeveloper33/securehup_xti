"""Explicit grouping reuses real records and never starts collection."""

import unittest

from tests import test_collection_watch_cli as fixtures


class OrganizationCLITests(unittest.TestCase):
    setUp = fixtures.CollectionWatchCLITests.setUp
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files
    add_social = fixtures.CollectionWatchCLITests.add_social
    add_tc = fixtures.CollectionWatchCLITests.add_tc
    add_rl = fixtures.CollectionWatchCLITests.add_rl

    def add_org(self, name="Örnek kuruluş"):
        return self.result("organizations", "add", name)["organization"]

    def link(self, organization_id, kind, value):
        return self.result("organizations", "link", organization_id, "--kind", kind, "--value", value)

    def assert_no_collection(self):
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])
        self.assertEqual(self.maigret.calls, [])
        self.assertEqual((self.threatcluster.calls, self.ransomlook.calls), (0, 0))

    def test_group_domain_and_selected_watch_families_without_copying_or_collecting(self):
        social, tc, rl = self.add_social(), self.add_tc(), self.add_rl()
        org = self.add_org()
        for kind, value in (("domain", "example.com"), ("username-watch", social.id), ("ransomware-watch", tc.id), ("ransomlook-watch", rl.id)):
            self.link(org["id"], kind, value)
        before = self.files()
        details = self.result("organizations", "show", org["id"])
        self.assertEqual(details["total_link_count"], 4)
        self.assertEqual({item["link"]["target"]["value"] for item in details["links"]}, {"example.com", social.id, tc.id, rl.id})
        self.assertTrue(all(item["target"]["active"] for item in details["links"]))
        self.result("organizations", "list")
        self.assertEqual(self.files(), before)
        self.assert_no_collection()

    def test_same_target_can_belong_to_two_groups_and_repeat_is_idempotent(self):
        first, second = self.add_org(), self.add_org("İkinci kuruluş")
        a = self.link(first["id"], "domain", "example.com")
        again = self.link(first["id"], "domain", "EXAMPLE.COM.")
        b = self.link(second["id"], "domain", "example.com")
        self.assertEqual(again["action"], "unchanged")
        self.assertEqual(a["link"]["id"], again["link"]["id"])
        self.assertNotEqual(a["link"]["id"], b["link"]["id"])
        self.assert_no_collection()

    def test_unknown_target_is_rejected_without_database_mutation(self):
        org = self.add_org()
        before = self.files()
        code, _, _ = self.invoke("organizations", "link", org["id"], "--kind", "domain", "--value", "unregistered.example")
        self.assertNotEqual(code, 0)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.result("organizations", "show", org["id"])["total_link_count"], 0)

    def test_revoke_keeps_links_and_allows_explicit_unlink_and_reactivation(self):
        org = self.add_org()
        linked = self.link(org["id"], "domain", "example.com")["link"]
        self.result("organizations", "revoke", org["id"], "--reason", "İzleme grubu kapatıldı.")
        details = self.result("organizations", "show", org["id"])
        self.assertFalse(details["organization"]["active"])
        self.assertTrue(details["links"][0]["link"]["active"])
        self.assertEqual(self.result("organizations", "list")["total_count"], 0)
        self.assertEqual(self.result("organizations", "list", "--all")["total_count"], 1)
        self.result("organizations", "unlink", org["id"], linked["id"], "--reason", "Bağlantı gerekmiyor.")
        self.result("organizations", "reactivate", org["id"], "--reason", "Grup yeniden kullanılacak.")
        details = self.result("organizations", "show", org["id"])
        self.assertTrue(details["organization"]["active"])
        self.assertFalse(details["links"][0]["link"]["active"])
        self.assert_no_collection()

    def test_target_revocation_is_visible_without_erasing_explicit_link(self):
        social, org = self.add_social(), self.add_org()
        linked = self.link(org["id"], "username-watch", social.id)["link"]
        self.social.revoke(social.id, reason="Sosyal izleme durduruldu.")
        before = self.files()
        details = self.result("organizations", "show", org["id"])
        self.assertTrue(details["links"][0]["link"]["active"])
        self.assertFalse(details["links"][0]["target"]["active"])
        self.result("organizations", "link-show", org["id"], linked["id"])
        self.assertEqual(self.files(), before)
        self.assert_no_collection()

    def test_rename_preserves_identity_and_history_and_refuses_name_collision(self):
        a, b = self.add_org(), self.add_org("İkinci kuruluş")
        changed = self.result("organizations", "rename", a["id"], "Yeni ad", "--reason", "Ad düzeltildi.")
        self.assertEqual(changed["organization"]["id"], a["id"])
        self.assertEqual(changed["organization"]["revision"], 2)
        before = self.files()
        code, _, _ = self.invoke("organizations", "rename", a["id"], b["display_name"], "--reason", "Aynı ad deneniyor.")
        self.assertNotEqual(code, 0)
        self.assertEqual(self.files(), before)
        details = self.result("organizations", "show", a["id"])
        self.assertEqual(details["total_event_count"], 2)


if __name__ == "__main__":
    unittest.main()

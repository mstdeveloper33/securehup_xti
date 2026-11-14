"""Saved recipes exercise real storage and collection with offline source fixtures."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.collection import DEFAULT_COLLECTION_TASKS
from xti.domain.collection_profiles import CollectionProfileDefinition
from xti.ports.discovery import SourceError
from tests import test_collection_watch_cli as fixtures


class CollectionProfileCLITests(unittest.TestCase):
    setUp = fixtures.CollectionWatchCLITests.setUp
    invoke = fixtures.CollectionWatchCLITests.invoke
    result = fixtures.CollectionWatchCLITests.result
    files = fixtures.CollectionWatchCLITests.files
    add_social = fixtures.CollectionWatchCLITests.add_social
    add_tc = fixtures.CollectionWatchCLITests.add_tc
    add_rl = fixtures.CollectionWatchCLITests.add_rl

    def save(self, *options):
        return self.result("profiles", "save", "Gunluk", "example.com", *options)

    def assert_no_collection(self):
        self.assertEqual(self.crt.calls, [])
        self.assertEqual(self.urlscan.calls, [])
        self.assertEqual(self.threatcluster.calls, 0)
        self.assertEqual(self.ransomlook.calls, 0)

    def test_save_freezes_defaults_and_repeated_save_is_idempotent(self):
        first = self.save()
        self.assertEqual(first["action"], "added")
        self.assertEqual(first["profile"]["revision"], 1)
        definition = first["profile"]["definition"]
        self.assertEqual(definition["task_ids"], list(DEFAULT_COLLECTION_TASKS))
        self.assertEqual((definition["stale_after_hours"], definition["finding_limit"]), (24, 10))
        again = self.save()
        self.assertEqual(again["action"], "unchanged")
        details = self.result("profiles", "show", "gunluk")
        self.assertEqual(details["event_count"], 1)
        self.assertEqual(details["events"][0]["definition"], definition)
        self.assert_no_collection()

    def test_saved_full_selection_runs_real_collect_and_preserves_revision(self):
        social, tc, rl = self.add_social(), self.add_tc(), self.add_rl()
        saved = self.save(
            "--task", "scan-crtsh", "--username-watch", social.id,
            "--ransomware-watch", tc.id, "--ransomlook-watch", rl.id,
            "--stale-after-hours", "72", "--finding-limit", "7", "--watch-item-limit", "2",
        )
        before = self.files()
        plan = self.result("collect", "--profile", "gunluk", "--plan")
        self.assertEqual(self.files(), before)
        self.assertEqual(len(plan["tasks"]), 4)
        self.assertEqual(plan["watch_item_limit"], 2)
        self.assert_no_collection()
        self.maigret.responses.append({"GitHub": fixtures.github()})
        run = self.result("collect", "--profile", "gunluk")
        self.assertEqual(run["status"], "complete")
        self.assertEqual(len(run["steps"]), 4)
        self.assertEqual((self.threatcluster.calls, self.ransomlook.calls), (1, 1))
        self.assertEqual(self.urlscan.calls, [])
        self.assertEqual(self.result("profiles", "show", "gunluk")["profile"], saved["profile"])

    def test_show_list_and_plan_are_read_only_and_do_not_acquire_lock(self):
        self.save()
        before = self.files()
        with patch.object(LocalExecutionLock, "acquire", side_effect=AssertionError("Read acquired lock")):
            records = self.result("profiles", "list")
            self.assertEqual(len(records["profiles"]), 1)
            self.result("profiles", "show", "Gunluk")
            self.result("collect", "--profile", "Gunluk", "--plan")
        self.assertEqual(self.files(), before)
        self.assert_no_collection()

    def test_save_replaces_full_definition_and_retains_old_snapshot(self):
        first = self.save("--task", "scan-crtsh", "--finding-limit", "20")
        second = self.save("--task", "discover-crtsh")
        self.assertEqual(second["action"], "updated")
        self.assertEqual(second["profile"]["revision"], 2)
        self.assertEqual(second["profile"]["definition"]["finding_limit"], 10)
        history = self.result("profiles", "show", "gunluk")
        definitions = {event["revision"]: event["definition"] for event in history["events"]}
        self.assertEqual(definitions[1], first["profile"]["definition"])
        self.assertEqual(definitions[2], second["profile"]["definition"])
        self.assert_no_collection()

    def test_revoke_prevents_work_and_save_reactivates_same_identity(self):
        saved = self.save()
        revoked = self.result("profiles", "revoke", "gunluk", "--reason", "Geçici olarak kapatıldı.")
        self.assertFalse(revoked["profile"]["active"])
        before = self.files()
        for arguments in (("collect", "--profile", "gunluk"), ("collect", "--profile", "gunluk", "--plan")):
            code, _, error = self.invoke(*arguments)
            self.assertNotEqual(code, 0)
            self.assertIn("geri", error.lower())
        self.assertEqual(self.files(), before)
        self.assertEqual(self.result("profiles", "list")["profiles"], [])
        self.assertEqual(len(self.result("profiles", "list", "--all")["profiles"]), 1)
        active = self.save()
        self.assertEqual(active["action"], "reactivated")
        self.assertEqual(active["profile"]["id"], saved["profile"]["id"])
        self.assertEqual(active["profile"]["revision"], 3)
        self.assert_no_collection()

    def test_revoked_watch_stays_readable_but_blocks_save_and_run(self):
        social = self.add_social()
        self.save("--username-watch", social.id)
        self.social.revoke(social.id, reason="İzleme kapatıldı.")
        before = self.files()
        self.result("profiles", "show", "gunluk")
        for args in (
            ("collect", "--profile", "gunluk"),
            ("collect", "--profile", "gunluk", "--plan"),
            ("profiles", "save", "gunluk", "example.com", "--username-watch", social.id),
        ):
            code, _, _ = self.invoke(*args)
            self.assertNotEqual(code, 0)
        self.assertEqual(self.files(), before)
        self.assert_no_collection()

    def test_profile_cannot_be_combined_with_domain_or_explicit_overrides(self):
        self.save()
        before = self.files()
        for options in (
            ("example.com",), ("--task", "scan-crtsh"), ("--finding-limit", "10"),
            ("--stale-after-hours", "24"), ("--watch-item-limit", "100"), ("--typos",),
        ):
            code, _, _ = self.invoke("collect", "--profile", "gunluk", *options)
            self.assertNotEqual(code, 0)
        self.assertNotEqual(self.invoke("collect")[0], 0)
        self.assertEqual(self.files(), before)
        self.assert_no_collection()

    def test_changed_profile_between_preflight_and_lock_does_not_collect(self):
        self.save()
        repository = SQLiteCollectionProfileRepository(self.database)
        old = repository.get("gunluk")
        original = LocalExecutionLock.acquire

        @contextmanager
        def changed(lock):
            with original(lock):
                repository.save(
                    old.display_name, replace(old.definition, task_ids=("discover-crtsh",)),
                    recorded_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
                )
                yield

        with patch.object(LocalExecutionLock, "acquire", changed):
            code, _, error = self.invoke("collect", "--profile", "gunluk")
        self.assertNotEqual(code, 0)
        self.assertIn("profil", error.lower())
        self.assertEqual(repository.get("gunluk").revision, 2)
        self.assert_no_collection()

    def test_source_failure_remains_partial_and_does_not_change_profile(self):
        saved = self.save()
        self.crt.responses["%example%"] = SourceError("Kaynak erişilemiyor.")
        self.crt.responses["example%"] = SourceError("Kaynak erişilemiyor.")
        result = self.result("collect", "--profile", "gunluk", expected_code=3)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(self.result("profiles", "show", "gunluk")["profile"], saved["profile"])

    def test_list_reports_overflow_and_supports_maximum_page(self):
        repository = SQLiteCollectionProfileRepository(self.database)
        for name in ("Birinci", "İkinci"):
            repository.save(name, CollectionProfileDefinition("example.com"), recorded_at=datetime.now(timezone.utc).isoformat())
        result = self.result("profiles", "list", "--limit", "1")
        self.assertEqual(len(result["profiles"]), 1)
        self.assertTrue(result["has_more"])
        result = self.result("profiles", "list", "--limit", "500")
        self.assertEqual(len(result["profiles"]), 2)
        self.assertFalse(result["has_more"])


if __name__ == "__main__":
    unittest.main()

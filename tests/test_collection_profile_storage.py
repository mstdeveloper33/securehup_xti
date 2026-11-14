"""Saved collection definitions survive lifecycle changes without lost evidence."""

from contextlib import closing
from dataclasses import replace
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.domain.assets import ValidationError
from xti.domain.collection_profiles import (
    CollectionProfileDefinition,
    canonical_definition_json,
    definition_sha256,
    normalize_profile_definition,
    normalize_profile_name,
    parse_definition_json,
    profile_name_key,
)


NOW = "2026-11-14T08:00:00+00:00"
LATER = "2026-11-14T09:00:00+00:00"
WATCH_A = "11111111-1111-4111-8111-111111111111"
WATCH_B = "22222222-2222-4222-8222-222222222222"


class CollectionProfileDefinitionTests(unittest.TestCase):
    def test_definition_roundtrip_and_canonical_task_and_watch_order(self):
        raw = CollectionProfileDefinition(
            " EXAMPLE.COM. ", task_ids=("ioc-certpl", "scan-crtsh"),
            username_watch_ids=(WATCH_B, WATCH_A), typos=True,
        )
        definition = normalize_profile_definition(raw)
        self.assertEqual(definition.asset_value, "example.com")
        self.assertEqual(definition.task_ids, ("scan-crtsh", "ioc-certpl"))
        self.assertEqual(definition.username_watch_ids, (WATCH_A, WATCH_B))
        encoded = canonical_definition_json(raw)
        self.assertEqual(parse_definition_json(encoded), definition)
        self.assertEqual(json.loads(encoded)["version"], 1)
        self.assertEqual(definition_sha256(raw), definition_sha256(definition))
        self.assertNotEqual(definition_sha256(raw), definition_sha256(replace(raw, typos=False)))
        self.assertEqual((definition.stale_after_hours, definition.finding_limit), (24, 10))
        self.assertEqual(profile_name_key("  EXAMPLE   Profile  "), "example profile")

    def test_invalid_definitions_are_rejected_before_persistence(self):
        valid = CollectionProfileDefinition("example.com")
        for values in (
            {"task_ids": ()}, {"task_ids": ("scan-crtsh", "scan-crtsh")},
            {"task_ids": ("active-port-scan",)}, {"typos": 1},
            {"task_ids": ("ioc-certpl",), "typos": True},
            {"finding_limit": True}, {"finding_limit": 51},
            {"watch_item_limit": 501}, {"stale_after_hours": 0},
            {"username_watch_ids": (WATCH_A, WATCH_A)},
            {"ransomlook_watch_ids": ("not-a-uuid",)},
            {"ransomware_watch_ids": (WATCH_A.replace("1", "A"),)},
            {"asset_value": "https://example.com"},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                normalize_profile_definition(replace(valid, **values))
        ids = tuple(f"{number:08x}-1111-4111-8111-111111111111" for number in range(51))
        with self.assertRaises(ValidationError):
            normalize_profile_definition(replace(valid, username_watch_ids=ids[:26], ransomlook_watch_ids=ids[26:]))
        for name in ("x", "line\nbreak", "escape\x1b[31m", "rtl\u202eoverride"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                normalize_profile_name(name)

    def test_stored_json_cannot_silently_change_version_or_canonical_content(self):
        encoded = canonical_definition_json(CollectionProfileDefinition("example.com"))
        payload = json.loads(encoded)
        for changed in (
            encoded + " ", encoded.replace('"example.com"', '"EXAMPLE.COM"'),
            encoded.replace('"version":1', '"version":true'),
            encoded.replace('"version":1', '"version":2'),
            encoded.replace('"version":1', '"version":1,"version":1'),
            encoded.replace('"version":1', '"version":1,"unknown":0'),
            "[" * 2000, json.dumps({key: value for key, value in payload.items() if key != "typos"}),
        ):
            with self.subTest(encoded=changed[:80]), self.assertRaises(ValidationError):
                parse_definition_json(changed)


class CollectionProfileStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.repo = SQLiteCollectionProfileRepository(self.path)
        self.definition = CollectionProfileDefinition("example.com", username_watch_ids=(WATCH_A,))

    def save(self):
        return self.repo.save("Example Profile", self.definition, recorded_at=NOW)

    def test_lifecycle_is_idempotent_and_history_preserves_full_definitions(self):
        added = self.save()
        unchanged = self.save()
        updated = self.repo.save("Example Profile", replace(self.definition, typos=True), recorded_at=LATER)
        revoked = self.repo.revoke("EXAMPLE PROFILE", reason="Artık kullanılmıyor.", recorded_at=LATER)
        noop = self.repo.revoke("Example Profile", reason="Yeniden geri çekme.", recorded_at=LATER)
        self.assertEqual(self.repo.list(), ())
        self.assertFalse(self.repo.get("example profile").active)
        self.assertEqual(len(self.repo.list(active_only=False)), 1)
        reactivated = self.repo.save("Example Profile", self.definition, recorded_at=LATER)
        self.assertEqual(
            [value.action for value in (added, unchanged, updated, revoked, noop, reactivated)],
            ["added", "unchanged", "updated", "revoked", "unchanged", "reactivated"],
        )
        self.assertEqual({value.profile.id for value in (added, updated, revoked, reactivated)}, {added.profile.id})
        details = self.repo.details("EXAMPLE PROFILE")
        self.assertEqual(details.profile.revision, 4)
        self.assertEqual(details.event_count, 4)
        self.assertEqual([event.revision for event in details.events], [4, 3, 2, 1])
        self.assertEqual(details.events[-1].definition, self.definition)
        self.assertTrue(details.events[1].definition.typos)
        self.assertEqual(self.repo.details("example profile", event_limit=1).event_count, 4)
        self.assertEqual(len(self.repo.details("example profile", event_limit=1).events), 1)

    def test_identity_is_canonical_and_reads_do_not_require_watch_or_asset_to_exist(self):
        added = self.save()
        changed = self.repo.save("EXAMPLE PROFILE", self.definition, recorded_at=LATER)
        self.assertEqual(changed.profile.id, added.profile.id)
        self.assertEqual(changed.action, "updated")
        self.assertEqual(self.repo.get("  example   profile ").definition.username_watch_ids, (WATCH_A,))
        self.assertEqual(len(self.repo.list()), 1)
        before = self.path.read_bytes()
        self.repo.details("example profile")
        self.repo.list()
        self.assertEqual(before, self.path.read_bytes())

    def test_repository_accepts_one_extra_list_row_for_public_overflow_reporting(self):
        added = self.save()
        self.assertEqual(self.repo.list(limit=501), (added.profile,))
        with self.assertRaises(ValidationError):
            self.repo.list(limit=502)
        with self.assertRaises(ValidationError):
            self.repo.details("example profile", event_limit=501)

    def test_write_failure_rolls_back_current_row_and_event_together(self):
        self.save()
        before = self.repo.details("example profile")
        with patch.object(self.repo, "_append_event", side_effect=sqlite3.OperationalError("disk failure")):
            with self.assertRaises(StorageError):
                self.repo.save("Example Profile", replace(self.definition, typos=True), recorded_at=LATER)
        self.assertEqual(self.repo.details("example profile"), before)

    def test_invalid_or_regressing_mutations_do_not_write(self):
        self.save()
        before = self.path.read_bytes()
        for operation in (
            lambda: self.repo.save("Example Profile", self.definition, recorded_at="2026-11-13T08:00:00+00:00"),
            lambda: self.repo.revoke("Example Profile", reason="ok", recorded_at=LATER),
            lambda: self.repo.save("Example Profile", replace(self.definition, finding_limit=True), recorded_at=NOW),
            lambda: self.repo.save("Example Profile", self.definition, recorded_at="2026-11-14T08:00:00"),
            lambda: self.repo.list(limit=True),
            lambda: self.repo.list(active_only=1),
            lambda: self.repo.get("unknown profile"),
        ):
            with self.assertRaises(ValidationError):
                operation()
        self.assertEqual(before, self.path.read_bytes())

    def test_corrupt_current_or_history_records_stop_reads_and_writes(self):
        mutations = (
            "UPDATE collection_profiles SET definition_sha256='bad'",
            "UPDATE collection_profiles SET name_key='different name'",
            "UPDATE collection_profiles SET active=0",
            "UPDATE collection_profiles SET revision=2",
            "UPDATE collection_profile_events SET definition_sha256='bad'",
            "UPDATE collection_profile_events SET action='reactivated'",
            "UPDATE collection_profile_events SET revision=2",
            "UPDATE collection_profile_events SET recorded_at='2026-11-14T10:00:00+00:00'",
            "DELETE FROM collection_profile_events",
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=mutation):
                path = Path(self.temp.name) / f"corrupt-{index}.db"
                SQLiteAssetRepository(path).initialize()
                repo = SQLiteCollectionProfileRepository(path)
                repo.save("Example Profile", self.definition, recorded_at=NOW)
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute(mutation)
                before = path.read_bytes()
                for operation in (
                    lambda: repo.get("Example Profile"),
                    lambda: repo.list(),
                    lambda: repo.details("Example Profile"),
                    lambda: repo.save("Example Profile", self.definition, recorded_at=LATER),
                ):
                    with self.assertRaises(StorageError):
                        operation()
                self.assertEqual(before, path.read_bytes())

    def test_backup_restore_preserves_profile_history_and_inspection_counts(self):
        self.save()
        self.repo.revoke("example profile", reason="Yerel test tamamlandı.", recorded_at=LATER)
        before = self.repo.details("example profile")
        backup = Path(self.temp.name) / "snapshot.db"
        restored = Path(self.temp.name) / "restored.db"
        self.storage.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteCollectionProfileRepository(restored).details("example profile"), before)
        report = SQLiteAssetRepository(restored).inspect()
        self.assertEqual(report["collection_profile_count"], 1)
        self.assertEqual(report["active_collection_profile_count"], 0)
        self.assertEqual(report["collection_profile_event_count"], 2)
        with self.assertRaises(StorageError):
            self.storage.backup(backup)
        with self.assertRaises(StorageError):
            SQLiteAssetRepository.restore(backup, restored)

    def test_missing_database_read_creates_nothing(self):
        path = Path(self.temp.name) / "missing" / "xti.db"
        with self.assertRaises(StorageError):
            SQLiteCollectionProfileRepository(path).list()
        self.assertFalse(path.parent.exists())


if __name__ == "__main__":
    unittest.main()

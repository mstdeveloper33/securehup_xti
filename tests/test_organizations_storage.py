"""Persistent explicit groupings retain source identity and complete history."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_brand_username_watches import SQLiteBrandUsernameWatchRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.organizations import OrganizationService
from xti.domain.assets import ValidationError
from xti.domain.organizations import normalize_organization_target, organization_link_effective


NOW = "2026-11-14T12:00:00+00:00"
LATER = "2026-11-14T13:00:00+00:00"
LAST = "2026-11-14T14:00:00+00:00"
REASON = "Kullanıcının açık seçimi."


class OrganizationStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.storage.add("example.com")
        self.repository = SQLiteOrganizationRepository(self.path)

    def add(self, name="Example", when=NOW):
        return self.repository.add(name_key=name.casefold(), display_name=name, reason=REASON, recorded_at=when)

    def link(self, organization, kind="domain", value="example.com", reason=REASON, when=NOW):
        return self.repository.link(organization.id, normalize_organization_target(kind, value), reason=reason, recorded_at=when)

    def watch_targets(self):
        social = SQLiteBrandUsernameWatchRepository(self.path)
        tc = SQLiteRansomwareWatchRepository(self.path)
        rl = SQLiteRansomLookWatchRepository(self.path)
        sw = social.upsert(name_key="social", display_name="Social", username="example", platforms=("GitHub",), source_key="maigret", recorded_at=NOW).watch
        tw = tc.upsert(name_key="threatcluster", display_name="ThreatCluster", kind="organization", query="Example", query_key="example", match_mode="exact", recorded_at=NOW).watch
        rw = rl.upsert(name_key="ransomlook", display_name="RansomLook", query="Example", query_key="example", match_mode="exact", recorded_at=NOW).watch
        return (("username-watch", sw, social), ("ransomware-watch", tw, tc), ("ransomlook-watch", rw, rl))

    def test_organization_lifecycle_preserves_id_and_noops_have_no_event(self):
        original = self.add().organization
        self.assertEqual(self.add().action, "unchanged")
        renamed = self.repository.rename(original.id, name_key="renamed", display_name="Renamed", reason=REASON, recorded_at=LATER)
        self.assertEqual((renamed.action, renamed.organization.id), ("renamed", original.id))
        self.repository.revoke(original.id, reason=REASON, recorded_at=LAST)
        self.assertEqual(self.repository.revoke(original.id, reason=REASON, recorded_at=LAST).action, "unchanged")
        with self.assertRaises(ValidationError):
            self.add("Renamed", when=LAST)
        self.repository.rename(original.id, name_key="inactive renamed", display_name="Inactive Renamed", reason=REASON, recorded_at=LAST)
        self.assertFalse(self.repository.show(original.id).organization.active)
        self.repository.reactivate(original.id, reason=REASON, recorded_at=LAST)
        self.assertEqual(self.repository.reactivate(original.id, reason=REASON, recorded_at=LAST).action, "unchanged")
        details = self.repository.show(original.id)
        self.assertEqual(details.organization.revision, 5)
        self.assertEqual([event.action for event in details.events], ["reactivated", "renamed", "revoked", "renamed", "added"])

    def test_name_collision_and_regressing_time_preserve_all_rows(self):
        first = self.add().organization
        second = self.add("Another").organization
        self.repository.revoke(second.id, reason=REASON, recorded_at=LATER)
        before = self.path.read_bytes()
        for operation in (
            lambda: self.repository.rename(first.id, name_key="another", display_name="Another", reason=REASON, recorded_at=LAST),
            lambda: self.repository.revoke(first.id, reason=REASON, recorded_at="2026-11-14T11:00:00+00:00"),
        ):
            with self.assertRaises(ValidationError): operation()
        self.assertEqual(self.path.read_bytes(), before)

    def test_target_can_belong_to_two_organizations_without_copying_any_source(self):
        targets = self.watch_targets()
        first, second = self.add().organization, self.add("Another").organization
        for organization in (first, second):
            self.link(organization)
            for kind, watch, _repository in targets:
                result = self.link(organization, kind, watch.id)
                self.assertEqual(self.link(organization, kind, watch.id).action, "unchanged")
                self.assertEqual(result.link.target.value, watch.id)
        self.assertEqual(self.repository.show(first.id).total_link_count, 4)
        with closing(sqlite3.connect(self.path)) as connection:
            for table in ("assets", "brand_username_watches", "ransomware_watches", "ransomlook_watches"):
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 1)

    def test_link_reason_lifecycle_and_org_shutdown_do_not_modify_source(self):
        organization = self.add().organization
        linked = self.link(organization).link
        updated = self.link(organization, reason="Bağlantı açıklaması güncellendi.", when=LATER)
        self.assertEqual((updated.action, updated.link.id), ("updated", linked.id))
        self.repository.revoke(organization.id, reason=REASON, recorded_at=LATER)
        details = self.repository.show(organization.id)
        self.assertTrue(details.links[0].link.active)
        self.assertFalse(organization_link_effective(details.organization, details.links[0]))
        with self.assertRaises(ValidationError): self.link(organization, when=LAST)
        self.repository.unlink(organization.id, linked.id, reason=REASON, recorded_at=LATER)
        self.assertEqual(self.repository.unlink(organization.id, linked.id, reason=REASON, recorded_at=LATER).action, "unchanged")
        self.repository.reactivate(organization.id, reason=REASON, recorded_at=LAST)
        self.assertFalse(self.repository.show_link(organization.id, linked.id).view.link.active)
        restored = self.link(organization, when=LAST)
        self.assertEqual((restored.action, restored.link.id), ("reactivated", linked.id))
        history = self.repository.show_link(organization.id, linked.id)
        self.assertEqual([event.action for event in history.events], ["reactivated", "revoked", "updated", "linked"])

    def test_revoked_targets_remain_readable_and_block_new_links(self):
        organization = self.add().organization
        for kind, watch, repository in self.watch_targets():
            link = self.link(organization, kind, watch.id).link
            repository.revoke(watch.id, reason="Kaynak izlemesi kapatıldı.", recorded_at=LATER)
            details = self.repository.show_link(organization.id, link.id)
            self.assertTrue(details.view.link.active)
            self.assertFalse(details.view.target.active)
            with self.assertRaises(ValidationError): self.link(organization, kind, watch.id, when=LAST)
            self.repository.unlink(organization.id, link.id, reason=REASON, recorded_at=LAST)
        self.assertEqual(self.repository.show(organization.id, active_links_only=True).total_link_count, 0)

    def test_unknown_wrong_type_and_cross_organization_ids_never_write(self):
        organization, other = self.add().organization, self.add("Another").organization
        link = self.link(organization).link
        _, watch, _ = self.watch_targets()[0]
        before = self.path.read_bytes()
        for operation in (
            lambda: self.link(organization, value="unknown.example"),
            lambda: self.link(organization, "ransomware-watch", watch.id),
            lambda: self.repository.unlink(other.id, link.id, reason=REASON, recorded_at=LATER),
            lambda: self.repository.show_link(other.id, link.id),
        ):
            with self.assertRaises(ValidationError): operation()
        self.assertEqual(self.path.read_bytes(), before)

    def test_target_is_rechecked_after_shared_lock_acquisition(self):
        organization = self.add().organization
        kind, watch, source = self.watch_targets()[0]
        from contextlib import contextmanager
        @contextmanager
        def retire_at_lock():
            source.revoke(watch.id, reason="Eşzamanlı hedef kapatma.", recorded_at=LATER)
            yield
        lock = LocalExecutionLock(self.path)
        service = OrganizationService(self.repository, lock, clock=lambda: datetime(2026, 11, 14, 14, tzinfo=timezone.utc))
        with patch.object(lock, "acquire", retire_at_lock):
            with self.assertRaises(ValidationError):
                service.link(organization.id, kind=kind, value=watch.id, reason=REASON)
        self.assertEqual(self.repository.show(organization.id).total_link_count, 0)

    def test_read_uses_one_snapshot_while_source_is_concurrently_revoked(self):
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        organization = self.add().organization
        kind, watch, source = self.watch_targets()[0]
        link = self.link(organization, kind, watch.id).link
        resolve = SQLiteOrganizationRepository._resolve_target
        changed = False

        def revoke_before_target_read(connection, reference, state):
            nonlocal changed
            if not changed:
                changed = True
                source.revoke(watch.id, reason="Eşzamanlı kaynak değişikliği.", recorded_at=LATER)
            return resolve(connection, reference, state)

        with patch.object(SQLiteOrganizationRepository, "_resolve_target", side_effect=revoke_before_target_read):
            earlier = self.repository.show_link(organization.id, link.id)
        later = self.repository.show_link(organization.id, link.id)
        self.assertTrue(earlier.view.target.active)
        self.assertFalse(later.view.target.active)
        self.assertEqual(earlier.events, later.events)
        self.assertEqual(earlier.view.link, later.view.link)

    def test_target_reactivation_and_definition_changes_keep_explicit_link_history(self):
        organization = self.add().organization
        kind, watch, source = self.watch_targets()[0]
        link = self.link(organization, kind, watch.id).link
        before = self.repository.show_link(organization.id, link.id)
        source.revoke(watch.id, reason="İzleme geçici kapatıldı.", recorded_at=LATER)
        restored = source.upsert(name_key="social", display_name="SOCIAL", username="newexample",
            platforms=("GitHub",), source_key="maigret", recorded_at=LAST).watch
        after = self.repository.show_link(organization.id, link.id)
        self.assertEqual(restored.id, watch.id)
        self.assertEqual(after.view.target.display_name, "SOCIAL")
        self.assertTrue(organization_link_effective(organization, after.view))
        self.assertEqual((after.view.link, after.events), (before.view.link, before.events))

    def test_event_insert_failure_rolls_back_current_record_and_link(self):
        organization = self.add().organization
        before = self.path.read_bytes()
        for method, operation in (
            ("_append_event", lambda: self.repository.rename(organization.id, name_key="changed", display_name="Changed", reason=REASON, recorded_at=LATER)),
            ("_append_link_event", lambda: self.link(organization)),
        ):
            with patch.object(self.repository, method, side_effect=sqlite3.OperationalError("controlled write failure")):
                with self.assertRaises(StorageError): operation()
            self.assertEqual(self.path.read_bytes(), before)

    def test_reads_are_network_free_byte_preserving_and_paginated(self):
        organization = self.add().organization
        for index in range(4):
            self.storage.add(f"test{index}.example")
            self.link(organization, value=f"test{index}.example")
        self.add("Another")
        before = self.path.read_bytes()
        with patch("socket.create_connection", side_effect=AssertionError("network")), patch("subprocess.run", side_effect=AssertionError("process")):
            page = self.repository.list(offset=1, limit=1)
            details = self.repository.show(organization.id, link_offset=2, link_limit=2, event_limit=1)
        self.assertEqual((page.total_count, len(page.organizations)), (2, 1))
        self.assertEqual((details.total_link_count, len(details.links)), (4, 2))
        self.assertEqual([item.link.target.value for item in details.links], ["test2.example", "test3.example"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_corruption_blocks_reads_and_writes_without_repair(self):
        mutations = (
            "UPDATE organizations SET active=0", "UPDATE organizations SET revision=2",
            "UPDATE organization_events SET action='reactivated'", "DELETE FROM organization_events",
            "UPDATE organization_links SET target_value='other.example'", "UPDATE organization_links SET active=0",
            "UPDATE organization_link_events SET action='updated'", "UPDATE organization_link_events SET reason='Different reason'",
            "DELETE FROM organization_link_events", "DELETE FROM assets",
        )
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=mutation):
                path = Path(self.temp.name) / f"broken{index}.db"
                storage = SQLiteAssetRepository(path); storage.initialize(); storage.add("example.com")
                repository = SQLiteOrganizationRepository(path)
                organization = repository.add(name_key="example", display_name="Example", reason=REASON, recorded_at=NOW).organization
                repository.link(organization.id, normalize_organization_target("domain", "example.com"), reason=REASON, recorded_at=NOW)
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute(mutation)
                before = path.read_bytes()
                for operation in (lambda: repository.list(), lambda: repository.show(organization.id),
                                  lambda: repository.revoke(organization.id, reason=REASON, recorded_at=LATER)):
                    with self.assertRaises(StorageError): operation()
                self.assertEqual(path.read_bytes(), before)

    def test_backup_restore_keeps_complete_link_and_source_history(self):
        organization = self.add().organization
        linked = self.link(organization).link
        self.repository.unlink(organization.id, linked.id, reason=REASON, recorded_at=LATER)
        before = self.repository.show(organization.id)
        history = self.repository.show_link(organization.id, linked.id)
        backup, restored = Path(self.temp.name) / "backup.db", Path(self.temp.name) / "restored.db"
        self.storage.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        repository = SQLiteOrganizationRepository(restored)
        self.assertEqual(repository.show(organization.id), before)
        self.assertEqual(repository.show_link(organization.id, linked.id), history)
        self.assertEqual(SQLiteAssetRepository(restored).inspect()["organization_link_count"], 1)
        with self.assertRaises(StorageError): self.storage.backup(backup)
        with self.assertRaises(StorageError): SQLiteAssetRepository.restore(backup, restored)

    def test_missing_database_read_never_creates_storage(self):
        missing = Path(self.temp.name) / "missing" / "xti.db"
        with self.assertRaises(StorageError): SQLiteOrganizationRepository(missing).list()
        self.assertFalse(missing.parent.exists())


if __name__ == "__main__":
    unittest.main()

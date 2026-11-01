"""Atomic local notices for real DNS, mail and service evidence changes."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_mail import SQLiteSurfaceMailRepository
from xti.adapters.sqlite_services import SQLiteSurfaceServiceScanRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.surface import SurfaceService
from tests.test_mail import result as mail_result
from tests.test_services import ADDRESS, scan_result
from tests.test_surface import result as surface_result


START = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
READ_AT = "2026-10-29T13:00:00+00:00"


class SurfaceChangeNotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.asset, _ = self.storage.add("example.com")
        self.ticks = iter(START + timedelta(minutes=index) for index in range(100))
        clock = lambda: next(self.ticks)
        self.surface = SQLiteSurfaceRepository(self.path, clock=clock)
        SurfaceService(self.storage, self.surface, clock=clock).approve(
            "example.com", "Kendi alan adım",
        )
        self.mail = SQLiteSurfaceMailRepository(self.path, clock=clock)
        self.services = SQLiteSurfaceServiceScanRepository(self.path, clock=clock)
        self.inbox = SQLiteInboxRepository(self.path)

    def counts(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "surface_checks", "surface_mail_checks",
                    "surface_service_checks", "surface_change_notifications",
                )
            )

    def create_three_changes(self):
        self.surface.append_check(self.asset.id, surface_result())
        self.surface.append_check(
            self.asset.id, surface_result(addresses=("93.184.216.35",)),
        )
        self.mail.append_check(self.asset.id, mail_result())
        self.mail.append_check(
            self.asset.id, mail_result(dmarc=("v=DMARC1; p=quarantine",)),
        )
        self.services.append_check(
            self.asset.id, "Yönettiğim sunucu", scan_result(opened=(22, 443)),
        )
        self.services.append_check(
            self.asset.id, "Yönettiğim sunucu", scan_result(opened=(443,)),
        )

    def test_only_real_changes_create_linked_unread_notices(self):
        self.surface.append_check(self.asset.id, surface_result())
        self.surface.append_check(self.asset.id, surface_result())
        self.mail.append_check(self.asset.id, mail_result())
        self.mail.append_check(self.asset.id, mail_result())
        self.services.append_check(
            self.asset.id, "Yönettiğim sunucu", scan_result(opened=(22, 443)),
        )
        self.services.append_check(
            self.asset.id, "Yönettiğim sunucu", scan_result(opened=(22, 443)),
        )
        self.assertEqual(self.inbox.list("all").total_count, 0)

        self.surface.append_check(
            self.asset.id, surface_result(addresses=("93.184.216.35",)),
        )
        self.mail.append_check(
            self.asset.id, mail_result(dmarc=("v=DMARC1; p=quarantine",)),
        )
        self.services.append_check(
            self.asset.id, "Yönettiğim sunucu", scan_result(opened=(443,)),
        )
        page = self.inbox.list("all")
        self.assertEqual((page.total_count, page.unread_count), (3, 3))
        self.assertEqual(
            [item.change_evidence.evidence_type for item in page.items],
            ["service", "mail", "surface"],
        )
        service, mail, surface = [item.change_evidence for item in page.items]
        self.assertEqual(service.changed_fields, ("ports",))
        self.assertEqual(
            [(item.port, item.before, item.after) for item in service.port_changes],
            [(22, "open", "closed")],
        )
        self.assertEqual(mail.changed_fields, ("dmarc",))
        self.assertEqual(surface.added_addresses, ("93.184.216.35",))
        self.assertEqual(surface.removed_addresses, ("93.184.216.34",))
        details = self.inbox.get(page.items[0].notification.id)
        self.assertEqual(details.change_evidence, service)
        self.assertIsNone(details.details)
        self.assertIsNone(details.candidate_details)

    def test_read_state_backup_and_restore_preserve_change_evidence(self):
        self.create_three_changes()
        original = self.inbox.list("all")
        identifiers = tuple(item.notification.id for item in original.items)
        marked = self.inbox.mark(identifiers, True, READ_AT)
        self.assertEqual(marked.changed_count, 3)
        self.assertEqual(self.inbox.list().items, ())
        expected = self.inbox.list("all")
        backup = self.path.parent / "snapshot.db"
        self.storage.backup(backup)
        restored = self.path.parent / "restored.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteInboxRepository(restored).list("all"), expected)

    def test_notification_failure_rolls_back_each_changed_check(self):
        cases = (
            (
                "xti.adapters.sqlite_surface.notify_surface_change",
                lambda: self.surface.append_check(
                    self.asset.id, surface_result(addresses=("93.184.216.35",)),
                ),
            ),
            (
                "xti.adapters.sqlite_mail.notify_surface_change",
                lambda: self.mail.append_check(
                    self.asset.id, mail_result(dmarc=("v=DMARC1; p=quarantine",)),
                ),
            ),
            (
                "xti.adapters.sqlite_services.notify_surface_change",
                lambda: self.services.append_check(
                    self.asset.id, "Yönettiğim sunucu", scan_result(opened=(443,)),
                ),
            ),
        )
        self.surface.append_check(self.asset.id, surface_result())
        self.mail.append_check(self.asset.id, mail_result())
        self.services.append_check(
            self.asset.id, "Yönettiğim sunucu", scan_result(opened=(22, 443)),
        )
        before = self.counts()
        for target, action in cases:
            with self.subTest(target=target):
                with patch(target, side_effect=sqlite3.OperationalError("disk full")):
                    with self.assertRaises(StorageError):
                        action()
                self.assertEqual(self.counts(), before)

    def test_corrupt_or_misdirected_notice_fails_closed_without_mutation(self):
        self.surface.append_check(self.asset.id, surface_result())
        changed = self.surface.append_check(
            self.asset.id, surface_result(addresses=("93.184.216.35",)),
        )
        baseline_mail = self.mail.append_check(self.asset.id, mail_result())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "UPDATE surface_change_notifications SET surface_check_id = NULL, "
                "mail_check_id = ? WHERE surface_check_id = ?",
                (baseline_mail.id, changed.id),
            )
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.inbox.list("all")
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

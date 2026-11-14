"""Historical, organization-scoped HIBP evidence in the shared local inbox."""

from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import timedelta
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.hibp_public_notices import parse_hibp_public_notices_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_organizations import SQLiteOrganizationRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.sqlite_public_notice_watches import SQLitePublicNoticeWatchRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.adapters.sqlite_status import SQLiteStatusRepository
from xti.adapters.sqlite_webhooks import SQLiteWebhookRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.application.organizations import OrganizationService
from xti.application.public_notice_watches import PublicNoticeWatchService
from xti.application.ransomlook_watches import RansomLookWatchService
from xti.application.webhooks import WebhookService
from xti.domain.assets import ValidationError
from xti.domain.findings import DomainInput, ImportDocument, MatchCandidate
from xti.domain.public_notices import HIBP_ATTRIBUTION, HIBP_LICENSE
from xti.interfaces.cli import main
from xti.interfaces.inbox import detail_lines, page_lines
from tests.test_public_notices import NOW, item
from tests.test_ransomlook_ransomware import post
from tests.test_ransomlook_watches import NOW as RANSOMLOOK_NOW, snapshot as ransomlook_snapshot
from tests.test_webhooks import FakeSender


class PublicNoticeNotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.asset, _ = self.assets.add("example.com")
        self.clock = NOW
        lock = LocalExecutionLock(self.path)
        self.organizations = OrganizationService(SQLiteOrganizationRepository(self.path), lock, clock=lambda: self.tick())
        self.catalog = SQLitePublicNoticeRepository(self.path)
        self.watches = SQLitePublicNoticeWatchRepository(self.path)
        self.service = PublicNoticeWatchService(self.watches, lock, clock=lambda: self.tick())
        self.inbox = SQLiteInboxRepository(self.path)
        self.organization = self.organizations.add("Example group", reason="Explicit test grouping.").organization
        self.link = self.organizations.link(self.organization.id, kind="domain", value=self.asset.value,
                                            reason="Explicit domain choice.").link

    def tick(self):
        self.clock += timedelta(minutes=1)
        return self.clock

    def apply(self, *records):
        now = self.tick()
        feed = parse_hibp_public_notices_response(json.dumps(records).encode(), fetched_at=now)
        return self.catalog.apply(feed, started_at=now.isoformat(),
                                  finished_at=(now + timedelta(seconds=1)).isoformat(), item_limit=20)

    def enable(self, organization=None):
        return self.service.configure((organization or self.organization).id, enabled=True,
                                      reason="Explicit public catalog watch.").watch

    def latest(self, organization=None):
        details = self.service.show((organization or self.organization).id)
        return self.service.run_show(details.runs[0].id, item_limit=100)

    def changed(self):
        self.enable()
        self.apply(item())
        baseline = self.latest()
        self.apply(item(PwnCount=54321, ModifiedDate="2025-03-01T00:00:00Z"), item("NewEvent"))
        return baseline, self.latest()

    def finding(self):
        domain = "example-support.net"
        SQLiteFindingRepository(self.path).save_import(
            ImportDocument("fixture:notice", "notice:fixture", (DomainInput(domain, domain, 1, None),)),
            (MatchCandidate(self.asset.id, self.asset.value, domain, "rules-v1", ("Test match",)),),
        )
        return next(row.notification for row in self.inbox.list("all", 100).items
                    if row.notification.finding_id is not None)

    def test_baseline_repeat_removal_and_source_failure_do_not_notify(self):
        self.enable()
        self.apply(item())
        self.assertIsNone(self.latest().notification_id)
        self.apply(item())
        self.assertIsNone(self.latest().notification_id)
        self.apply(item("Other", "other.example"))
        removed = self.latest()
        self.assertEqual(removed.run.removed_count, 1)
        self.assertIsNone(removed.notification_id)
        now = self.tick().isoformat()
        self.catalog.record_failure(started_at=now, finished_at=now, error="Source unavailable.")
        self.assertEqual(self.inbox.list("all").total_count, 0)

    def test_exact_historical_evidence_and_source_classifications_survive_new_catalogs(self):
        baseline, changed = self.changed()
        details = self.inbox.get(changed.notification_id)
        notice, evidence = details.notification, details.public_notice_change
        self.assertEqual(notice.event_type, "public_notice_watch_changed")
        self.assertEqual(notice.public_notice_watch_run_id, changed.run.id)
        self.assertEqual((evidence.watch_id, evidence.organization_id), (changed.watch.id, self.organization.id))
        self.assertEqual((evidence.source_run_id, evidence.previous_source_run_id),
                         (changed.run.source_run_id, baseline.run.source_run_id))
        self.assertEqual((evidence.added_count, evidence.updated_count, evidence.baseline_count), (1, 1, 0))
        updated = next(value for value in evidence.items if value.action == "updated")
        self.assertEqual((updated.before.pwn_count, updated.after.pwn_count), (12345, 54321))
        self.assertTrue(updated.after.is_verified)
        self.assertEqual((evidence.attribution, evidence.license), (HIBP_ATTRIBUTION, HIBP_LICENSE))
        self.apply(item("Unrelated", "other.example"))
        self.assertEqual(self.inbox.get(notice.id), details)

    def test_sequence_paging_readonly_views_and_idempotent_mixed_mark(self):
        finding = self.finding()
        _, changed = self.changed()
        page = self.inbox.list("all", limit=1)
        self.assertEqual(page.items[0].notification.id, changed.notification_id)
        self.assertGreater(page.items[0].notification.sequence, finding.sequence)
        older = self.inbox.list("all", limit=1, before=page.next_before)
        self.assertEqual(older.items[0].notification.id, finding.id)
        before = self.path.read_bytes()
        with patch.object(SQLiteAssetRepository, "initialize", side_effect=AssertionError("No initialization")), \
             patch("socket.create_connection", side_effect=AssertionError("No network")):
            self.inbox.list(); self.inbox.get(changed.notification_id)
        self.assertEqual(self.path.read_bytes(), before)
        early = (NOW - timedelta(days=1)).isoformat()
        marked = self.inbox.mark((changed.notification_id, finding.id), True, early)
        self.assertEqual(marked.changed_count, 2)
        self.assertEqual(self.inbox.list().unread_count, 0)
        again = self.inbox.mark((changed.notification_id,), True, self.tick().isoformat())
        self.assertEqual(again.changed_count, 0)
        self.assertEqual(again.notifications[0].read_at, early)
        self.assertEqual(self.inbox.mark((changed.notification_id,), False, early).changed_count, 1)
        self.assertEqual(self.inbox.list("read").matching_count, 1)

    def test_invalid_mixed_batch_and_partial_write_failure_roll_back_every_read_state(self):
        finding = self.finding(); _, changed = self.changed()
        identifiers = (finding.id, changed.notification_id)
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.inbox.mark((*identifiers, "missing"), True, NOW.isoformat())
        self.assertEqual(self.path.read_bytes(), before)
        def partial(connection, ids, read, now):
            connection.execute("UPDATE notifications SET read_at=? WHERE id=?", (now, finding.id))
            raise sqlite3.OperationalError("Controlled write failure")
        with patch.object(self.inbox, "_mark_rows", side_effect=partial), self.assertRaises(StorageError):
            self.inbox.mark(identifiers, True, NOW.isoformat())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.inbox.list().unread_count, 2)

    def test_corrupt_watch_run_or_scope_and_sequence_collision_fail_closed(self):
        finding = self.finding(); baseline, changed = self.changed()
        other = self.organizations.add("Other group", reason="Separate grouping.").organization
        self.organizations.link(other.id, kind="domain", value=self.asset.value,
                                reason="Explicit comparison grouping.")
        other_watch = self.enable(other)
        mutations = (("run_id", baseline.run.id), ("watch_id", other_watch.id),
                     ("organization_id", other.id), ("sequence", finding.sequence))
        for column, value in mutations:
            with self.subTest(column=column):
                path = self.root / f"corrupt-{column}.db"
                self.assets.backup(path)
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute(f"UPDATE public_notice_watch_notifications SET {column}=?", (value,))
                corrupted = SQLiteInboxRepository(path)
                before = path.read_bytes()
                for operation in (lambda: corrupted.list(), lambda: corrupted.get(changed.notification_id),
                                  lambda: corrupted.mark((changed.notification_id,), True, NOW.isoformat())):
                    with self.assertRaises(StorageError):
                        operation()
                self.assertEqual(path.read_bytes(), before)

    def test_corrupt_historical_scope_or_source_blocks_views_and_mark(self):
        _, changed = self.changed()
        mutations = (
            ("scope", "UPDATE public_notice_watch_runs SET scope_sha256=? WHERE id=?", changed.run.id),
            ("source", "UPDATE public_notice_changes SET state_sha256=? WHERE run_id=?", changed.run.source_run_id),
        )
        for name, statement, identifier in mutations:
            with self.subTest(name=name):
                path = self.root / f"corrupt-{name}.db"
                self.assets.backup(path)
                with closing(sqlite3.connect(path)) as connection, connection:
                    connection.execute(statement, ("0" * 64, identifier))
                corrupted = SQLiteInboxRepository(path)
                before = path.read_bytes()
                for operation in (lambda: corrupted.list(), lambda: corrupted.get(changed.notification_id),
                                  lambda: corrupted.mark((changed.notification_id,), True, NOW.isoformat())):
                    with self.assertRaises(StorageError):
                        operation()
                self.assertEqual(path.read_bytes(), before)

    def test_rename_unlink_and_disabled_watch_preserve_historical_scope_and_read_time(self):
        _, changed = self.changed()
        self.inbox.mark((changed.notification_id,), True, self.tick().isoformat())
        before = self.inbox.get(changed.notification_id)
        self.organizations.rename(self.organization.id, "Renamed group", reason="Label changed.")
        self.organizations.unlink(self.organization.id, self.link.id, reason="Current scope changed.")
        self.service.configure(self.organization.id, enabled=False, reason="Explicitly disabled.")
        after = self.inbox.get(changed.notification_id)
        self.assertEqual(after.notification, before.notification)
        self.assertEqual(after.public_notice_change.scope, before.public_notice_change.scope)
        self.assertEqual(after.public_notice_change.items, before.public_notice_change.items)
        self.assertEqual(after.public_notice_change.source_run_id, before.public_notice_change.source_run_id)

    def test_bounded_change_evidence_preserves_totals_and_real_followup_page(self):
        self.enable(); self.apply(item())
        other_asset, _ = self.assets.add("new.example")
        self.organizations.link(self.organization.id, kind="domain", value=other_asset.value,
                                reason="Additional explicit domain begins with a baseline.")
        self.apply(item(), item("NewScope", other_asset.value),
                   *(item(f"Event{index:02}") for index in range(23)))
        changed = self.latest()
        detail = self.inbox.get(changed.notification_id)
        evidence = detail.public_notice_change
        self.assertEqual(evidence.added_count, 23)
        self.assertEqual(evidence.baseline_count, 1)
        self.assertEqual(changed.run.unchanged_count, 1)
        self.assertEqual(evidence.total_item_count, 25)
        self.assertEqual(len(evidence.items), 20)
        self.assertTrue(evidence.has_more)
        following = self.service.run_show(changed.run.id, item_limit=20, offset=20)
        self.assertEqual(evidence.total_item_count, following.total_item_count)
        self.assertEqual(len(evidence.items) + len(following.items), evidence.total_item_count)
        self.assertFalse({(row.notice_id, row.action) for row in evidence.items}
                         & {(row.notice_id, row.action) for row in following.items})
        self.assertIn(f"notices watch-run-show {changed.run.id} --offset 20", "\n".join(detail_lines(detail)))

    def test_multiple_notices_use_one_batch_evidence_audit_per_view_or_mark(self):
        other = self.organizations.add("Other group", reason="Separate explicit grouping.").organization
        self.organizations.link(other.id, kind="domain", value=self.asset.value, reason="Explicit same domain.")
        self.enable(); self.enable(other)
        self.apply(item()); self.apply(item(), item("NewEvent"))
        helper = SQLitePublicNoticeWatchRepository.notification_evidences
        with patch.object(SQLitePublicNoticeWatchRepository, "notification_evidences", wraps=helper) as audit:
            page = self.inbox.list("all")
        self.assertEqual(audit.call_count, 1)
        self.assertEqual(len(page.items), 2)
        self.assertEqual({row.public_notice_change.organization_id for row in page.items},
                         {self.organization.id, other.id})
        identifiers = tuple(row.notification.id for row in page.items)
        with patch.object(SQLitePublicNoticeWatchRepository, "notification_evidences", wraps=helper) as audit:
            self.inbox.mark(identifiers, True, NOW.isoformat())
        self.assertEqual(audit.call_count, 1)

    def test_backup_restore_preserves_exact_evidence_and_inspection_counts(self):
        _, changed = self.changed()
        self.inbox.mark((changed.notification_id,), True, self.tick().isoformat())
        expected = self.inbox.get(changed.notification_id)
        backup, restored = self.root / "backup.db", self.root / "restored.db"
        self.assets.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteInboxRepository(restored).get(changed.notification_id), expected)
        counts = SQLiteAssetRepository(restored).inspect()
        self.assertEqual((counts["notification_count"], counts["unread_notification_count"]), (1, 0))

    def test_status_counts_include_finding_ransomlook_and_public_notice_read_states(self):
        finding = self.finding(); self.changed()
        claims = SQLiteRansomLookClaimRepository(self.path)
        watches = SQLiteRansomLookWatchRepository(self.path)
        def apply_claims(records, minute):
            now = RANSOMLOOK_NOW + timedelta(minutes=minute)
            claims.apply(ransomlook_snapshot(records, minute=minute), started_at=now.isoformat(),
                         finished_at=(now + timedelta(seconds=1)).isoformat(), item_limit=20)
        apply_claims([post("Example Holding")], 1)
        service = RansomLookWatchService(watches, claims,
            clock=lambda: RANSOMLOOK_NOW + timedelta(minutes=2))
        watch = service.add("Example", "Example", kind="organization", match_mode="contains").watch
        service.run(watch.id)
        apply_claims([post("Example Holding"), post("Example Labs")], 3)
        service = RansomLookWatchService(watches, claims,
            clock=lambda: RANSOMLOOK_NOW + timedelta(minutes=4))
        self.assertIsNotNone(service.run(watch.id).notification_id)
        self.inbox.mark((finding.id,), True, self.tick().isoformat())
        inbox = self.inbox.list("all")
        status = SQLiteStatusRepository(self.path).snapshot(("crt.sh",), None, 10)
        self.assertEqual((inbox.total_count, inbox.unread_count), (3, 2))
        self.assertEqual((status.notification_count, status.unread_notification_count), (3, 2))

    def test_terminal_json_and_explicit_webhook_preserve_attribution_and_before_after(self):
        _, changed = self.changed()
        details = self.inbox.get(changed.notification_id)
        rendered = "\n".join(detail_lines(details) + page_lines(self.inbox.list(), status="unread", next_command=None))
        for expected in (HIBP_ATTRIBUTION, HIBP_LICENSE, "12345", "54321", "Example", "NewEvent"):
            self.assertIn(expected, rendered)
        unsafe = replace(details, public_notice_change=replace(details.public_notice_change,
                         organization_name="name\x1b[31m"))
        self.assertNotIn("\x1b", "\n".join(detail_lines(unsafe)))
        stdout, stderr = StringIO(), StringIO()
        before = self.path.read_bytes()
        with redirect_stdout(stdout), redirect_stderr(stderr), \
             patch("socket.create_connection", side_effect=AssertionError("No network")):
            code = main(["--data-dir", str(self.root), "--json", "inbox", "show", changed.notification_id])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        self.assertEqual(self.path.read_bytes(), before)
        data = json.loads(stdout.getvalue())["data"]["public_notice_change"]
        self.assertEqual((data["attribution"], data["license"]), (HIBP_ATTRIBUTION, HIBP_LICENSE))
        sender = FakeSender(); repository = SQLiteWebhookRepository(self.path)
        service = WebhookService(repository, self.inbox, sender, clock=lambda: self.tick())
        destination = service.add_destination("Local", "https://hooks.example.test/xti", b"s" * 32).destination
        queued, created = service.queue(destination.id, changed.notification_id)
        self.assertTrue(created)
        payload = json.loads(repository.delivery_target(queued.id).payload)
        self.assertEqual(payload["data"]["public_notice_change"], data)
        self.assertEqual(sender.calls, [])


if __name__ == "__main__":
    unittest.main()

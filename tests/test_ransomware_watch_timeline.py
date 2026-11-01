"""Offline ransomware watch timelines deduplicate repeated source snapshots."""

from contextlib import closing, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.ransomware_watch_timeline import RansomwareWatchTimelineService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.domain.assets import ValidationError
from xti.domain.ransomware_claims import ransomware_claim_state_sha256
from xti.interfaces.cli import main
from tests.test_threatcluster_ransomware import claim, content


NOW = datetime(2026, 10, 30, 23, tzinfo=timezone.utc)


def feed(records, *, minute):
    return parse_threatcluster_ransomware_response(
        content(records), fetched_at=NOW + timedelta(minutes=minute),
    )


class RansomwareWatchTimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.claims = SQLiteRansomwareClaimRepository(self.path)
        self.watch_repository = SQLiteRansomwareWatchRepository(self.path)
        self.watches = RansomwareWatchService(
            self.watch_repository, self.claims, clock=lambda: NOW,
        )
        self.timeline = RansomwareWatchTimelineService(
            self.watch_repository, self.claims,
        )

    def apply(self, records, *, minute):
        return self.claims.apply(
            feed(records, minute=minute),
            started_at=(NOW + timedelta(minutes=minute, seconds=1)).isoformat(),
            finished_at=(NOW + timedelta(minutes=minute, seconds=2)).isoformat(),
            item_limit=100,
        )

    def organization_watch(self):
        return self.watches.add(
            "Alpha kuruluş", "Alpha Ltd", kind="organization",
        ).watch

    def test_repeat_update_removal_and_reappearance_have_distinct_meanings(self):
        watch = self.organization_watch()
        original = claim("Alpha Ltd", website="alpha.example")
        changed = claim("Alpha Ltd", website="alpha.example", sector="Finance")
        self.apply([original], minute=1)
        self.apply([original], minute=2)
        self.claims.record_failure(
            started_at=(NOW + timedelta(minutes=3)).isoformat(),
            finished_at=(NOW + timedelta(minutes=3, seconds=1)).isoformat(),
            error="Kaynak bağlantısı tamamlanamadı; sonuç üretilmedi.",
        )
        self.apply([changed], minute=4)
        self.apply([], minute=5)
        self.apply([changed], minute=6)

        report = self.timeline.show(watch.id)
        self.assertEqual(
            [event.action for event in report.events],
            ["first_seen", "updated", "removed", "reappeared"],
        )
        self.assertEqual(
            (report.complete_source_run_count, report.failed_source_run_count,
             report.distinct_claim_count, report.active_claim_count,
             report.repeat_observation_count, report.reappearance_count),
            (5, 1, 1, 1, 1, 1),
        )
        self.assertEqual(len({event.claim.id for event in report.events}), 1)

    def test_domain_relation_can_start_and_end_without_a_new_claim_identity(self):
        watch = self.watches.add(
            "Alpha domain", "alpha.example", kind="domain",
        ).watch
        self.apply([claim("Alpha Ltd", website="other.example")], minute=1)
        self.apply([
            claim("Alpha Ltd", website="portal.alpha.example"),
        ], minute=2)
        self.apply([claim("Alpha Ltd", website="other.example")], minute=3)
        self.apply([], minute=4)

        report = self.timeline.show(watch.id)
        self.assertEqual([event.action for event in report.events],
                         ["match_started", "match_ended"])
        self.assertEqual((report.distinct_claim_count, report.active_claim_count), (1, 0))
        self.assertEqual(
            report.events[0].claim.id, report.events[1].claim.id,
        )

    def test_limit_changes_display_only_and_cli_is_offline_read_only(self):
        watch = self.organization_watch()
        value = claim("Alpha Ltd")
        self.apply([value], minute=1)
        self.apply([claim("Alpha Ltd", sector="Finance")], minute=2)
        self.apply([], minute=3)
        self.apply([value], minute=4)
        before = self.path.read_bytes()

        report = self.timeline.show(watch.id, event_limit=2)
        self.assertEqual((report.total_event_count, len(report.events)), (4, 2))
        self.assertEqual([event.action for event in report.events],
                         ["removed", "reappeared"])

        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-dir", self.temp.name, "--json", "ransomware",
                "watch-timeline", watch.id, "--event-limit", "2",
            ])
        payload = json.loads(output.getvalue())
        self.assertEqual((code, payload["data"]["total_event_count"]), (0, 4))
        self.assertEqual(self.path.read_bytes(), before)

        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-dir", self.temp.name, "ransomware",
                "watch-timeline", watch.id,
            ])
        self.assertEqual(code, 0)
        self.assertIn("Değişmeden tekrar gözlem", output.getvalue())
        self.assertIn("doğrulanmış ihlal değil", output.getvalue())
        self.assertEqual(self.path.read_bytes(), before)

    def test_empty_history_revoked_watch_and_invalid_limit_are_safe(self):
        watch = self.organization_watch()
        self.watches.revoke(watch.id, reason="İzleme kapsamı kapatıldı")
        before = self.path.read_bytes()
        report = self.timeline.show(watch.id)
        self.assertEqual(
            (report.watch.active, report.total_event_count,
             report.complete_source_run_count), (False, 0, 0),
        )
        with self.assertRaises(ValidationError):
            self.timeline.show(watch.id, event_limit=0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_changed_removal_evidence_fails_closed(self):
        watch = self.organization_watch()
        self.apply([claim("Alpha Ltd")], minute=1)
        self.apply([], minute=2)
        history = self.claims.history()
        removed = next(item for item in history.items if item.action == "removed")
        changed = replace(removed.claim, sector="Changed")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ransomware_claim_run_items SET sector=?, state_sha256=? "
                "WHERE id=?",
                (changed.sector, ransomware_claim_state_sha256(changed), removed.id),
            )
        with self.assertRaisesRegex(StorageError, "çıkarma kanıtı"):
            self.timeline.show(watch.id)


if __name__ == "__main__":
    unittest.main()

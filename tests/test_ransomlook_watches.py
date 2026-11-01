"""Durable organization-only watches over source-isolated RansomLook history."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomlook_watches import SQLiteRansomLookWatchRepository
from xti.application.ransomlook_watches import RansomLookWatchService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from tests.test_ransomlook_ransomware import content, post


NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)


def snapshot(records, *, minute):
    return parse_ransomlook_ransomware_response(
        content(records), fetched_at=NOW + timedelta(minutes=minute),
    )


class RansomLookWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.claims = SQLiteRansomLookClaimRepository(self.path)
        self.watches = SQLiteRansomLookWatchRepository(self.path)

    def apply(self, records, *, minute):
        started = NOW + timedelta(minutes=minute, seconds=1)
        return self.claims.apply(
            snapshot(records, minute=minute),
            started_at=started.isoformat(),
            finished_at=(started + timedelta(seconds=1)).isoformat(),
            item_limit=100,
        )

    def service(self, *, minute):
        return RansomLookWatchService(
            self.watches, self.claims,
            clock=lambda: NOW + timedelta(minutes=minute, seconds=3),
        )

    def test_first_run_is_silent_then_only_new_match_needs_attention(self):
        self.apply([
            post("Example Holding"),
            post(
                "Other Company", group="other-group",
                discovered="2026-10-29T18:00:00Z",
            ),
        ], minute=1)
        watch = self.service(minute=2).add(
            "Example kuruluşu", "Example", kind="organization",
            match_mode="contains",
        ).watch
        baseline = self.service(minute=3).run(watch.id)
        self.assertTrue(baseline.is_baseline)
        self.assertEqual(
            (baseline.run.total_count, baseline.run.added_count, baseline.attention_count),
            (1, 1, 0),
        )

        self.apply([
            post("Example Holding"),
            post(
                "Example Labs", group="second-group",
                discovered="2026-10-28T18:00:00Z",
            ),
        ], minute=4)
        changed = self.service(minute=5).run(watch.id)
        self.assertEqual(
            (
                changed.run.total_count, changed.run.added_count,
                changed.run.unchanged_count, changed.run.removed_count,
                changed.attention_count,
            ),
            (2, 1, 1, 0, 1),
        )
        self.assertEqual(
            {item.action for item in changed.items}, {"added", "unchanged"},
        )

        self.apply([], minute=6)
        removed = self.service(minute=7).run(watch.id)
        self.assertEqual(
            (removed.run.total_count, removed.run.removed_count, removed.attention_count),
            (0, 2, 0),
        )

    def test_domain_is_rejected_and_definition_change_resets_baseline(self):
        self.apply([post("Example Holding")], minute=1)
        service = self.service(minute=2)
        with self.assertRaisesRegex(ValidationError, "domain bilgisi sağlamaz"):
            service.add(
                "Domain denemesi", "example.com", kind="domain",
            )
        self.assertEqual(self.watches.list(active_only=False, limit=10), ())

        watch = service.add(
            "Kuruluş", "Example Holding", kind="organization",
        ).watch
        self.assertTrue(self.service(minute=3).run(watch.id).is_baseline)
        updated = self.service(minute=4).add(
            "Kuruluş", "Example", kind="organization", match_mode="contains",
        )
        second = self.service(minute=5).run(updated.watch.id)
        self.assertTrue(second.is_baseline)
        self.assertEqual(second.attention_count, 0)

        revoked = self.service(minute=6).revoke(
            watch.id, reason="Artık izlenmeyecek",
        )
        self.assertFalse(revoked.watch.active)
        with self.assertRaisesRegex(ValidationError, "Geri çekilmiş"):
            self.service(minute=7).run(watch.id)

    def test_backup_restore_counts_and_corruption_fail_closed(self):
        self.apply([post("Example Holding")], minute=1)
        watch = self.service(minute=2).add(
            "Example", "Example Holding", kind="organization",
        ).watch
        report = self.service(minute=3).run(watch.id)
        inspection = SQLiteAssetRepository(self.path).inspect()
        self.assertEqual(
            (
                inspection["ransomlook_watch_count"],
                inspection["active_ransomlook_watch_count"],
                inspection["ransomlook_watch_run_count"],
                inspection["ransomware_watch_count"],
            ),
            (1, 1, 1, 0),
        )
        backup = self.path.parent / "backup.db"
        SQLiteAssetRepository(self.path).backup(backup)
        restored = self.path.parent / "restored.db"
        SQLiteAssetRepository.restore(backup, restored)
        restored_report = SQLiteRansomLookWatchRepository(restored).run_details(
            report.run.id, item_limit=100,
        )
        self.assertEqual(restored_report, report)

        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ransomlook_watch_run_items SET state_sha256=?",
                ("0" * 64,),
            )
        with self.assertRaisesRegex(StorageError, "izleme sonucu"):
            self.watches.list(active_only=True, limit=10)

    def test_cli_routes_basic_watch_commands_to_ransomlook_only(self):
        self.apply([post("Example Holding")], minute=1)
        prefix = ["--data-dir", self.temp.name, "--json", "ransomware"]
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([
                *prefix, "watch-add", "Example kuruluşu", "Example Holding",
                "--kind", "organization", "--source", "ransomlook",
            ])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        watch = json.loads(stdout.getvalue())["data"]["watch"]
        self.assertEqual(watch["query"], "Example Holding")

        stdout = StringIO()
        with redirect_stdout(stdout), redirect_stderr(StringIO()):
            self.assertEqual(main([
                *prefix, "watch-run", watch["id"], "--source", "ransomlook",
            ]), 0)
        report = json.loads(stdout.getvalue())["data"]
        self.assertTrue(report["is_baseline"])
        self.assertEqual(report["attention_count"], 0)

        stdout = StringIO()
        with redirect_stdout(stdout), redirect_stderr(StringIO()):
            self.assertEqual(main([
                *prefix, "watch-list", "--source", "ransomlook",
            ]), 0)
        self.assertEqual(len(json.loads(stdout.getvalue())["data"]["records"]), 1)
        self.assertEqual(
            SQLiteAssetRepository(self.path).inspect()["ransomware_watch_count"], 0,
        )


if __name__ == "__main__":
    unittest.main()


"""Durable RansomLook history stays separate and preserves complete differences."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.application.ransomlook_ransomware import RansomLookClaimHistoryService
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError
from tests.test_ransomlook_ransomware import content, post


NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)


def snapshot(records, *, fetched_at=NOW):
    return parse_ransomlook_ransomware_response(
        content(records), fetched_at=fetched_at,
    )


class RansomLookHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteRansomLookClaimRepository(self.path)

    def apply(self, feed, *, minute):
        started = NOW + timedelta(minutes=minute)
        return self.repository.apply(
            feed,
            started_at=started.isoformat(),
            finished_at=(started + timedelta(seconds=1)).isoformat(),
            item_limit=100,
        )

    def test_baseline_then_added_removed_and_unchanged_are_distinct(self):
        first = snapshot([
            post("Alpha Ltd"),
            post(
                "Beta Ltd", group="second-group",
                discovered="2026-10-29T18:00:00Z",
            ),
        ])
        baseline = self.apply(first, minute=1)
        self.assertTrue(baseline.is_baseline)
        self.assertEqual(
            (baseline.run.added_count, baseline.run.unchanged_count), (2, 0),
        )

        second = snapshot([
            post("Alpha Ltd"),
            post(
                "Gamma Ltd", group="third-group",
                discovered="2026-10-28T18:00:00Z",
            ),
        ])
        changed = self.apply(second, minute=2)
        self.assertEqual(
            (
                changed.run.added_count, changed.run.updated_count,
                changed.run.unchanged_count, changed.run.removed_count,
            ),
            (1, 0, 1, 1),
        )
        self.assertEqual({item.action for item in changed.items}, {"added", "removed"})

        same = self.apply(second, minute=3)
        self.assertEqual(
            (same.run.added_count, same.run.unchanged_count, same.run.removed_count),
            (0, 2, 0),
        )
        self.assertEqual((same.items, same.total_item_count), ((), 0))
        rebuilt = self.repository.latest_snapshot()
        self.assertEqual(
            [claim.victim for claim in rebuilt.claims], ["Alpha Ltd", "Gamma Ltd"],
        )
        inspection = SQLiteAssetRepository(self.path).inspect()
        self.assertEqual(
            (
                inspection["ransomlook_claim_run_count"],
                inspection["ransomlook_claim_item_count"],
                inspection["ransomware_claim_run_count"],
            ),
            (3, 4, 0),
        )

    def test_failure_is_audited_without_erasing_last_success(self):
        baseline = self.apply(snapshot([post()]), minute=1)

        class FailingSource:
            def fetch(self):
                raise SourceError("RansomLook bağlantısı tamamlanamadı; sonuç üretilmedi.")

        times = iter((NOW + timedelta(minutes=2), NOW + timedelta(minutes=2, seconds=1)))
        report = RansomLookClaimHistoryService(
            self.repository, FailingSource(), clock=lambda: next(times),
        ).refresh()
        self.assertEqual(report.run.status, "failed")
        status = self.repository.status(run_limit=10)
        self.assertEqual(status.latest_run.id, report.run.id)
        self.assertEqual(status.latest_complete_run.id, baseline.run.id)
        self.assertEqual(self.repository.latest_snapshot().run.id, baseline.run.id)

    def test_corruption_fails_closed_and_backup_restore_preserves_history(self):
        self.apply(snapshot([post()]), minute=1)
        backup = self.path.parent / "backup.db"
        SQLiteAssetRepository(self.path).backup(backup)
        restored = self.path.parent / "restored.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(
            SQLiteRansomLookClaimRepository(restored).latest_snapshot(),
            self.repository.latest_snapshot(),
        )
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ransomlook_claim_run_items SET state_sha256 = ?", ("0" * 64,),
            )
        with self.assertRaisesRegex(StorageError, "öğe geçmişi"):
            self.repository.status(run_limit=10)

    def test_cli_refresh_and_status_are_source_isolated(self):
        feed = snapshot([post()])
        stdout, stderr = StringIO(), StringIO()
        with (
            patch(
                "xti.interfaces.cli.RansomLookRansomwareSource.fetch", return_value=feed,
            ),
            patch(
                "xti.interfaces.cli.ThreatClusterRansomwareSource.fetch",
                side_effect=AssertionError("ThreatCluster must not be called"),
            ),
            patch(
                "xti.interfaces.cli.RansomLookClaimHistoryService._now",
                side_effect=(
                    (NOW + timedelta(minutes=1)).isoformat(),
                    (NOW + timedelta(minutes=1, seconds=1)).isoformat(),
                ),
            ),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main([
                "--data-dir", str(self.path.parent), "--json", "ransomware",
                "refresh", "--source", "ransomlook", "--limit", "10",
            ])
        payload = json.loads(stdout.getvalue())
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        self.assertTrue(payload["data"]["is_baseline"])
        self.assertEqual(payload["data"]["run"]["source_name"], feed.source_name)

        stdout = StringIO()
        with (
            patch(
                "xti.interfaces.cli.RansomLookRansomwareSource.fetch",
                side_effect=AssertionError("status must stay offline"),
            ),
            redirect_stdout(stdout), redirect_stderr(StringIO()),
        ):
            code = main([
                "--data-dir", str(self.path.parent), "--json", "ransomware",
                "status", "--source", "ransomlook",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(stdout.getvalue())["data"]["latest_run"]["status"], "complete",
        )


if __name__ == "__main__":
    unittest.main()

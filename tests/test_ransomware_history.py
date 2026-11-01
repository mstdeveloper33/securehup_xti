"""Durable, bounded ransomware-claim snapshot history."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.ransomware_claims import RansomwareClaimHistoryService
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError
from tests.test_threatcluster_ransomware import claim, content


NOW = datetime(2026, 10, 30, 17, tzinfo=timezone.utc)


def snapshot(records, *, fetched_at=NOW):
    return parse_threatcluster_ransomware_response(
        content(records), fetched_at=fetched_at,
    )


class RansomwareHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteRansomwareClaimRepository(self.path)

    def apply(self, feed, *, minute):
        started = NOW + timedelta(minutes=minute)
        finished = started + timedelta(seconds=1)
        return self.repository.apply(
            feed, started_at=started.isoformat(), finished_at=finished.isoformat(),
            item_limit=100,
        )

    def test_baseline_then_added_updated_removed_and_unchanged_are_distinct(self):
        first = snapshot([
            claim("Alpha Ltd", website="alpha.example"),
            claim(
                "Beta Ltd", group="second-group", website="beta.example",
                discovered="2026-10-29T12:00:00Z",
            ),
        ])
        baseline = self.apply(first, minute=1)
        self.assertTrue(baseline.is_baseline)
        self.assertEqual(
            (baseline.run.added_count, baseline.run.updated_count,
             baseline.run.unchanged_count, baseline.run.removed_count),
            (2, 0, 0, 0),
        )

        second = snapshot([
            claim("Alpha Ltd", website="alpha.example", sector="Finance"),
            claim(
                "Gamma Ltd", group="third-group", website="gamma.example",
                discovered="2026-10-28T12:00:00Z",
            ),
        ])
        changed = self.apply(second, minute=2)
        self.assertFalse(changed.is_baseline)
        self.assertEqual(
            (changed.run.added_count, changed.run.updated_count,
             changed.run.unchanged_count, changed.run.removed_count),
            (1, 1, 0, 1),
        )
        self.assertEqual({item.action for item in changed.items}, {"added", "updated", "removed"})

        same = self.apply(second, minute=3)
        self.assertEqual(
            (same.run.added_count, same.run.updated_count,
             same.run.unchanged_count, same.run.removed_count),
            (0, 0, 2, 0),
        )
        self.assertEqual((same.items, same.total_item_count), ((), 0))
        inspection = SQLiteAssetRepository(self.path).inspect()
        self.assertEqual(
            (inspection["ransomware_claim_run_count"],
             inspection["ransomware_claim_item_count"]),
            (3, 5),
        )
        status = self.repository.status(run_limit=2)
        self.assertEqual(status.latest_complete_run.id, same.run.id)
        self.assertEqual([run.sequence for run in status.recent_runs], [3, 2])

    def test_source_failure_is_audited_without_erasing_last_success(self):
        baseline = self.apply(snapshot([claim()]), minute=1)

        class FailingSource:
            def fetch(self):
                raise SourceError("ThreatCluster bağlantısı tamamlanamadı; sonuç üretilmedi.")

        times = iter((NOW + timedelta(minutes=2), NOW + timedelta(minutes=2, seconds=1)))
        report = RansomwareClaimHistoryService(
            self.repository, FailingSource(), clock=lambda: next(times),
        ).refresh()
        self.assertEqual(report.run.status, "failed")
        status = self.repository.status(run_limit=10)
        self.assertEqual(status.latest_run.id, report.run.id)
        self.assertEqual(status.latest_complete_run.id, baseline.run.id)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM ransomware_claim_run_items").fetchone()[0],
                1,
            )

    def test_history_never_persists_raw_leak_site_url_and_corruption_fails_closed(self):
        self.apply(snapshot([claim(post_url="http://hiddenexample.onion/post/secret")]), minute=1)
        with closing(sqlite3.connect(self.path)) as connection:
            values = " ".join(
                str(value) for row in connection.execute(
                    "SELECT * FROM ransomware_claim_run_items"
                ).fetchall() for value in row if value is not None
            )
            self.assertNotIn("onion", values)
            connection.execute(
                "UPDATE ransomware_claim_run_items SET state_sha256 = ?",
                ("0" * 64,),
            )
            connection.commit()
        with self.assertRaisesRegex(StorageError, "öğe geçmişi"):
            self.repository.status(run_limit=10)

    def test_cli_refresh_and_offline_status_use_initialized_database(self):
        feed = snapshot([claim()])
        stdout, stderr = StringIO(), StringIO()
        with (
            patch("xti.interfaces.cli.ThreatClusterRansomwareSource.fetch", return_value=feed),
            patch(
                "xti.interfaces.cli.RansomwareClaimHistoryService._now",
                side_effect=((NOW + timedelta(minutes=1)).isoformat(),
                             (NOW + timedelta(minutes=1, seconds=1)).isoformat()),
            ),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main([
                "--data-dir", str(self.path.parent), "--json",
                "ransomware", "refresh", "--limit", "10",
            ])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        result = json.loads(stdout.getvalue())
        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["is_baseline"])

        stdout = StringIO()
        with (
            patch(
                "xti.interfaces.cli.ThreatClusterRansomwareSource.fetch",
                side_effect=AssertionError("status must stay offline"),
            ),
            redirect_stdout(stdout), redirect_stderr(StringIO()),
        ):
            code = main([
                "--data-dir", str(self.path.parent), "--json",
                "ransomware", "status",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["data"]["latest_run"]["status"], "complete")


if __name__ == "__main__":
    unittest.main()

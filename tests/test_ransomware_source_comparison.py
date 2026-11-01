"""Explainable read-only comparisons across stored ransomware sources."""

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
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.ransomware_source_comparison import (
    RansomwareSourceComparisonService,
)
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from tests.test_ransomlook_ransomware import content as ransomlook_content, post
from tests.test_threatcluster_ransomware import claim, content as threatcluster_content


NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)


class RansomwareSourceComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.threatcluster = SQLiteRansomwareClaimRepository(self.path)
        self.ransomlook = SQLiteRansomLookClaimRepository(self.path)

    def apply_threatcluster(self, records, *, minute=1):
        feed = parse_threatcluster_ransomware_response(
            threatcluster_content(records), fetched_at=NOW,
        )
        started = NOW + timedelta(minutes=minute)
        return self.threatcluster.apply(
            feed, started_at=started.isoformat(),
            finished_at=(started + timedelta(seconds=1)).isoformat(), item_limit=100,
        )

    def apply_ransomlook(self, records, *, minute=2):
        feed = parse_ransomlook_ransomware_response(
            ransomlook_content(records), fetched_at=NOW,
        )
        started = NOW + timedelta(minutes=minute)
        return self.ransomlook.apply(
            feed, started_at=started.isoformat(),
            finished_at=(started + timedelta(seconds=1)).isoformat(), item_limit=100,
        )

    def populate(self):
        self.apply_threatcluster([
            claim(
                "Alpha AŞ", group="LockGroup",
                discovered="2026-10-30T12:00:00Z",
            ),
            claim(
                "Beta Ltd", group="Shared Group",
                discovered="2026-10-30T13:00:00Z",
            ),
            claim(
                "Gamma Ltd", group="Old Group",
                discovered="2026-10-30T14:00:00Z",
            ),
            claim(
                "Name Only", group="First Group",
                discovered="2026-10-30T15:00:00Z",
            ),
            claim(
                "Different Victim", group="Batch Group",
                discovered="2026-10-30T16:00:00Z",
            ),
        ])
        self.apply_ransomlook([
            post(
                "alpha aş", group="lockgroup",
                discovered="2026-10-30T12:00:00Z",
            ),
            post(
                "Beta Ltd", group="Shared Group",
                discovered="2026-10-30T13:30:00Z",
            ),
            post(
                "Gamma Ltd", group="New Group",
                discovered="2026-10-30T14:00:00Z",
            ),
            post(
                "Name Only", group="Second Group",
                discovered="2026-10-30T15:30:00Z",
            ),
            post(
                "Another Victim", group="Batch Group",
                discovered="2026-10-30T16:00:00Z",
            ),
        ])

    def service(self):
        return RansomwareSourceComparisonService(self.threatcluster, self.ransomlook)

    def test_only_strong_explainable_shared_evidence_is_reported(self):
        self.populate()
        report = self.service().compare(limit=100)
        self.assertEqual(report.total_comparison_count, 3)
        self.assertEqual(
            [item.basis for item in report.comparisons],
            [
                "organization_group_time",
                "organization_group",
                "organization_time",
            ],
        )
        self.assertEqual(
            [item.threatcluster_claim.victim for item in report.comparisons],
            ["Alpha AŞ", "Beta Ltd", "Gamma Ltd"],
        )
        self.assertEqual(
            report.comparisons[0].common_evidence,
            ("organization", "group", "discovered_at"),
        )
        self.assertEqual(
            report.comparisons[1].different_evidence, ("discovered_at",),
        )
        self.assertEqual(report.comparisons[2].different_evidence, ("group",))
        self.assertNotIn(
            "Name Only",
            {item.threatcluster_claim.victim for item in report.comparisons},
        )

    def test_limit_is_display_only_and_comparison_does_not_write(self):
        self.populate()
        before = self.path.read_bytes()
        report = self.service().compare(limit=1)
        after = self.path.read_bytes()
        self.assertEqual(before, after)
        self.assertEqual(
            (report.total_comparison_count, report.displayed_count, report.has_more),
            (3, 1, True),
        )
        first_id = report.comparisons[0].id
        self.assertEqual(self.service().compare(limit=1).comparisons[0].id, first_id)

    def test_cli_is_offline_json_and_keeps_both_source_records(self):
        self.populate()
        stdout, stderr = StringIO(), StringIO()
        with (
            patch(
                "xti.interfaces.cli.ThreatClusterRansomwareSource.fetch",
                side_effect=AssertionError("comparison must stay offline"),
            ),
            patch(
                "xti.interfaces.cli.RansomLookRansomwareSource.fetch",
                side_effect=AssertionError("comparison must stay offline"),
            ),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main([
                "--data-dir", self.temp.name, "--json", "ransomware",
                "source-compare", "--limit", "2",
            ])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        data = json.loads(stdout.getvalue())["data"]
        self.assertEqual(
            (data["total_comparison_count"], data["displayed_count"], data["has_more"]),
            (3, 2, True),
        )
        self.assertIn("threatcluster_claim", data["comparisons"][0])
        self.assertIn("ransomlook_claim", data["comparisons"][0])

        stdout = StringIO()
        with redirect_stdout(stdout), redirect_stderr(StringIO()):
            self.assertEqual(main([
                "--data-dir", self.temp.name, "ransomware", "source-compare",
                "--limit", "1",
            ]), 0)
        human = stdout.getvalue()
        self.assertIn("Neden gösterildi: Kuruluş + grup + keşif zamanı aynı", human)
        self.assertIn("ThreatCluster:", human)
        self.assertIn("RansomLook:", human)
        self.assertIn("kayıtları birleştirmez", human)

    def test_invalid_limit_and_corrupt_source_fail_closed(self):
        class NeverRead:
            def latest_snapshot(self):
                raise AssertionError("invalid input must fail before storage")

        with self.assertRaisesRegex(ValidationError, "1–500"):
            RansomwareSourceComparisonService(NeverRead(), NeverRead()).compare(limit=0)

        self.populate()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ransomlook_claim_run_items SET state_sha256=?", ("0" * 64,),
            )
        before = self.path.read_bytes()
        with self.assertRaisesRegex(StorageError, "RansomLook öğe geçmişi"):
            self.service().compare()
        self.assertEqual(self.path.read_bytes(), before)

    def test_both_successful_local_snapshots_are_required(self):
        with self.assertRaisesRegex(ValidationError, "ransomware refresh"):
            self.service().compare()
        self.apply_threatcluster([claim()])
        with self.assertRaisesRegex(
            ValidationError, "refresh --source ransomlook",
        ):
            self.service().compare()


if __name__ == "__main__":
    unittest.main()

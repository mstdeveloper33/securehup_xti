"""One explicit refresh safely runs every active ransomware claim watch."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.ransomware_claims import RansomwareClaimHistoryService
from xti.application.ransomware_watch_refresh import RansomwareWatchRefreshService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError
from tests.test_threatcluster_ransomware import claim, content


NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)


def feed(records, *, minute=0):
    return parse_threatcluster_ransomware_response(
        content(records), fetched_at=NOW + timedelta(minutes=minute),
    )


class MutableSource:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


class RansomwareWatchRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.claims = SQLiteRansomwareClaimRepository(self.path)
        self.watch_repository = SQLiteRansomwareWatchRepository(self.path)
        self.clock_value = NOW
        self.watches = RansomwareWatchService(
            self.watch_repository, self.claims, clock=lambda: self.clock_value,
        )

    def service(self, source):
        history = RansomwareClaimHistoryService(
            self.claims, source, clock=lambda: self.clock_value,
        )
        return RansomwareWatchRefreshService(
            history, self.watches, clock=lambda: self.clock_value,
        )

    def test_success_refreshes_once_and_runs_active_watches_in_stable_order(self):
        zeta = self.watches.add(
            "Zeta kuruluş", "Beta Ltd", kind="organization",
        ).watch
        alpha = self.watches.add(
            "Alpha domain", "alpha.example", kind="domain",
        ).watch
        revoked = self.watches.add(
            "Revoked", "revoked.example", kind="domain",
        ).watch
        self.watches.revoke(revoked.id, reason="Bu izleme artık kapsam dışı.")
        source = MutableSource(feed([
            claim("Alpha Ltd", website="portal.alpha.example"),
            claim(
                "Beta Ltd", group="second", website="beta.example",
                discovered="2026-10-29T12:00:00Z",
            ),
        ]))

        report = self.service(source).run(max_watches=10, watch_item_limit=10)

        self.assertEqual(source.calls, 1)
        self.assertEqual((report.planned_watch_count, report.completed_watch_count), (2, 2))
        self.assertEqual([item.display_name for item in report.items],
                         ["Alpha domain", "Zeta kuruluş"])
        self.assertTrue(all(item.is_baseline for item in report.items))
        self.assertEqual((report.baseline_watch_count, report.notification_count), (2, 0))
        self.assertEqual({item.source_run_id for item in report.items}, {report.refresh.run.id})
        self.assertEqual(self.watches.show(alpha.id).total_run_count, 1)
        self.assertEqual(self.watches.show(zeta.id).total_run_count, 1)
        self.assertEqual(self.watches.show(revoked.id).total_run_count, 0)

    def test_no_active_watch_still_refreshes_source_without_invented_work(self):
        source = MutableSource(feed([claim("Alpha Ltd")]))
        report = self.service(source).run()
        self.assertEqual(source.calls, 1)
        self.assertEqual(report.refresh.run.status, "complete")
        self.assertEqual(
            (report.planned_watch_count, report.completed_watch_count, report.items),
            (0, 0, ()),
        )

    def test_second_refresh_notifies_only_watch_with_new_or_changed_match(self):
        alpha = self.watches.add(
            "Alpha", "Alpha Ltd", kind="organization",
        ).watch
        beta = self.watches.add(
            "Beta", "Beta Ltd", kind="organization",
        ).watch
        source = MutableSource(feed([
            claim("Alpha Ltd", website="alpha.example"),
            claim(
                "Beta Ltd", group="second", website="beta.example",
                discovered="2026-10-29T12:00:00Z",
            ),
        ]))
        first = self.service(source).run()
        self.assertEqual(first.notification_count, 0)

        self.clock_value += timedelta(minutes=1)
        source.value = feed([
            claim("Alpha Ltd", website="alpha.example", sector="Finance"),
            claim(
                "Beta Ltd", group="second", website="beta.example",
                discovered="2026-10-29T12:00:00Z",
            ),
        ], minute=1)
        second = self.service(source).run()

        self.assertEqual(second.notification_count, 1)
        by_id = {item.watch_id: item for item in second.items}
        self.assertIsNotNone(by_id[alpha.id].notification_id)
        self.assertEqual(by_id[alpha.id].updated_count, 1)
        self.assertIsNone(by_id[beta.id].notification_id)
        self.assertEqual(by_id[beta.id].unchanged_count, 1)

    def test_source_failure_never_runs_watches_on_previous_successful_snapshot(self):
        source = MutableSource(feed([claim("Alpha Ltd")]))
        watch = self.watches.add(
            "Alpha", "Alpha Ltd", kind="organization",
        ).watch
        successful = self.service(source).run()
        before = self.watches.show(watch.id).total_run_count

        self.clock_value += timedelta(minutes=1)
        source.value = SourceError("ThreatCluster bağlantısı tamamlanamadı; sonuç üretilmedi.")
        failed = self.service(source).run()

        self.assertEqual(failed.refresh.run.status, "failed")
        self.assertEqual((failed.planned_watch_count, failed.completed_watch_count), (1, 0))
        self.assertEqual(failed.baseline_watch_count, 0)
        self.assertEqual(self.watches.show(watch.id).total_run_count, before)
        status = self.claims.status(run_limit=10)
        self.assertEqual(status.latest_run.id, failed.refresh.run.id)
        self.assertEqual(status.latest_complete_run.id, successful.refresh.run.id)

    def test_overflow_and_invalid_limits_stop_before_source_or_write(self):
        self.watches.add("Alpha", "Alpha Ltd", kind="organization")
        self.watches.add("Beta", "Beta Ltd", kind="organization")
        source = MutableSource(feed([]))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValidationError, "tamamı toplu sınıra sığmıyor"):
            self.service(source).run(max_watches=1)
        self.assertEqual((source.calls, self.path.read_bytes()), (0, before))
        for values in ((0, 100, 100), (501, 100, 100), (1, 0, 100), (1, 100, 501)):
            with self.assertRaises(ValidationError):
                RansomwareWatchRefreshService.validate_limits(*values)

    def test_expected_source_identity_is_checked_before_watch_write(self):
        watch = self.watches.add(
            "Alpha", "Alpha Ltd", kind="organization",
        ).watch
        source = MutableSource(feed([claim("Alpha Ltd")]))
        history = RansomwareClaimHistoryService(
            self.claims, source, clock=lambda: self.clock_value,
        )
        refresh = history.refresh()
        self.assertEqual(refresh.run.status, "complete")

        with self.assertRaisesRegex(ValidationError, "beklenen yenilemeyle eşleşmiyor"):
            self.watches.run(
                watch.id, expected_source_run_id=str(uuid4()),
            )
        self.assertEqual(self.watches.show(watch.id).total_run_count, 0)

    def test_later_watch_failure_keeps_source_and_completed_watch_run(self):
        first = self.watches.add("Alpha", "Alpha Ltd", kind="organization").watch
        second = self.watches.add("Beta", "Beta Ltd", kind="organization").watch
        third = self.watches.add("Gamma", "Gamma Ltd", kind="organization").watch
        source = MutableSource(feed([claim("Alpha Ltd")]))
        service = self.service(source)
        original_run = self.watches.run
        calls = 0

        def fail_second(
            watch_id, *, item_limit=100, expected_source_run_id=None,
        ):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise StorageError("İkinci izleme için kontrollü kayıt hatası.")
            return original_run(
                watch_id, item_limit=item_limit,
                expected_source_run_id=expected_source_run_id,
            )

        self.watches.run = fail_second
        with self.assertRaises(StorageError):
            service.run()
        self.assertEqual(self.claims.status(run_limit=1).latest_run.status, "complete")
        self.assertEqual(self.watches.show(first.id).total_run_count, 1)
        self.assertEqual(self.watches.show(second.id).total_run_count, 0)
        self.assertEqual(self.watches.show(third.id).total_run_count, 0)

    def test_cli_returns_one_bounded_json_report(self):
        self.clock_value = datetime.now(timezone.utc)
        watch = self.watches.add(
            "Alpha", "Alpha Ltd", kind="organization",
        ).watch
        cli_feed = parse_threatcluster_ransomware_response(
            content(
                [claim("Alpha Ltd")],
                generated_at=(self.clock_value - timedelta(minutes=30)).isoformat(),
            ),
            fetched_at=self.clock_value,
        )
        stdout, stderr = StringIO(), StringIO()
        with (
            patch(
                "xti.interfaces.cli.ThreatClusterRansomwareSource.fetch",
                return_value=cli_feed,
            ),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main([
                "--data-dir", str(self.data), "--json", "ransomware",
                "watch-refresh-all", "--watch-limit", "5",
                "--source-item-limit", "10", "--watch-item-limit", "10",
            ])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        result = json.loads(stdout.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["completed_watch_count"], 1)
        self.assertEqual(result["data"]["items"][0]["watch_id"], watch.id)

    def test_cli_source_failure_returns_three_and_no_watch_run(self):
        self.clock_value = datetime.now(timezone.utc)
        watch = self.watches.add(
            "Alpha", "Alpha Ltd", kind="organization",
        ).watch
        stdout, stderr = StringIO(), StringIO()
        with (
            patch(
                "xti.interfaces.cli.ThreatClusterRansomwareSource.fetch",
                side_effect=SourceError(
                    "ThreatCluster bağlantısı tamamlanamadı; sonuç üretilmedi."
                ),
            ),
            redirect_stdout(stdout), redirect_stderr(stderr),
        ):
            code = main([
                "--data-dir", str(self.data), "--json", "ransomware",
                "watch-refresh-all",
            ])
        self.assertEqual((code, stderr.getvalue()), (3, ""))
        result = json.loads(stdout.getvalue())
        self.assertFalse(result["ok"])
        self.assertEqual(result["data"]["completed_watch_count"], 0)
        self.assertEqual(self.watches.show(watch.id).total_run_count, 0)


if __name__ == "__main__":
    unittest.main()

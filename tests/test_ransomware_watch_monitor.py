"""Foreground ransomware monitoring remains bounded and interruption-safe."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.ransomware_claims import RansomwareClaimHistoryService
from xti.application.ransomware_watch_monitor import RansomwareWatchMonitorService
from xti.application.ransomware_watch_refresh import RansomwareWatchRefreshService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError
from tests.test_threatcluster_ransomware import claim, content


NOW = datetime(2026, 10, 30, 21, tzinfo=timezone.utc)


def feed(records, *, second=0):
    return parse_threatcluster_ransomware_response(
        content(records), fetched_at=NOW + timedelta(seconds=second),
    )


class SequenceSource:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def fetch(self):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class Timer:
    def __init__(self, *, interrupt=False):
        self.value = 0.0
        self.interrupt = interrupt
        self.sleeps = []

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        if self.interrupt:
            raise KeyboardInterrupt
        self.sleeps.append(seconds)
        self.value += seconds


class RansomwareWatchMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.claims = SQLiteRansomwareClaimRepository(self.path)
        self.watch_repository = SQLiteRansomwareWatchRepository(self.path)
        self.timer = Timer()
        self.watches = RansomwareWatchService(
            self.watch_repository, self.claims, clock=self.wall_clock,
        )

    def wall_clock(self):
        return NOW + timedelta(seconds=self.timer.value)

    def monitor(self, source, *, timer=None):
        timer = timer or self.timer

        def clock():
            return NOW + timedelta(seconds=timer.value)

        history = RansomwareClaimHistoryService(
            self.claims, source, clock=clock,
        )
        combined = RansomwareWatchRefreshService(
            history,
            RansomwareWatchService(
                self.watch_repository, self.claims, clock=clock,
            ),
            clock=clock,
        )
        return RansomwareWatchMonitorService(
            combined, clock=clock,
            monotonic=timer.monotonic, sleeper=timer.sleep,
        )

    def add_watch(self):
        return self.watches.add(
            "Alpha kuruluş", "Alpha Ltd", kind="organization",
        ).watch

    def test_two_cycles_keep_source_and_watch_runs_then_notify_change(self):
        watch = self.add_watch()
        source = SequenceSource([
            feed([claim("Alpha Ltd", website="alpha.example")]),
            feed([
                claim("Alpha Ltd", website="alpha.example", sector="Finance"),
            ], second=300),
        ])
        report = self.monitor(source).run(
            max_cycles=2, interval_seconds=300, max_duration_seconds=600,
        )

        self.assertEqual((report.completed_cycles, report.stop_reason), (2, "cycles"))
        self.assertEqual((report.successful_cycles, report.failed_cycles), (2, 0))
        self.assertEqual((report.completed_watch_runs, report.notification_count), (2, 1))
        self.assertEqual((report.baseline_watch_runs,
                          [cycle.baseline_watch_count for cycle in report.cycles]),
                         (1, [1, 0]))
        self.assertEqual(source.calls, 2)
        self.assertEqual(sum(self.timer.sleeps), 300)
        self.assertEqual(self.watches.show(watch.id).total_run_count, 2)
        self.assertEqual(len(self.claims.status(run_limit=10).recent_runs), 2)

    def test_failed_source_cycle_is_preserved_and_later_cycle_can_succeed(self):
        watch = self.add_watch()
        source = SequenceSource([
            SourceError("ThreatCluster bağlantısı tamamlanamadı; sonuç üretilmedi."),
            feed([claim("Alpha Ltd")], second=300),
        ])
        report = self.monitor(source).run(
            max_cycles=2, interval_seconds=300, max_duration_seconds=600,
        )

        self.assertEqual((report.successful_cycles, report.failed_cycles), (1, 1))
        self.assertEqual([cycle.source_status for cycle in report.cycles],
                         ["failed", "complete"])
        self.assertEqual([cycle.completed_watch_count for cycle in report.cycles], [0, 1])
        self.assertEqual(self.watches.show(watch.id).total_run_count, 1)
        self.assertEqual([run.status for run in self.claims.status(run_limit=10).recent_runs],
                         ["complete", "failed"])

    def test_duration_stops_new_cycle_and_keeps_completed_evidence(self):
        watch = self.add_watch()
        source = SequenceSource([feed([claim("Alpha Ltd")])])
        report = self.monitor(source).run(
            max_cycles=3, interval_seconds=300, max_duration_seconds=5,
        )
        self.assertEqual((report.completed_cycles, report.stop_reason), (1, "duration"))
        self.assertEqual(source.calls, 1)
        self.assertEqual(sum(self.timer.sleeps), 5)
        self.assertEqual(self.watches.show(watch.id).total_run_count, 1)

    def test_ctrl_c_during_wait_preserves_first_cycle_and_propagates(self):
        watch = self.add_watch()
        timer = Timer(interrupt=True)
        source = SequenceSource([feed([claim("Alpha Ltd")])])
        with self.assertRaises(KeyboardInterrupt):
            self.monitor(source, timer=timer).run(
                max_cycles=2, interval_seconds=300, max_duration_seconds=600,
            )
        self.assertEqual(source.calls, 1)
        self.assertEqual(self.watches.show(watch.id).total_run_count, 1)
        self.assertEqual(len(self.claims.status(run_limit=10).recent_runs), 1)

    def test_invalid_limits_and_overflow_stop_before_source_access(self):
        for values in ((0, 300, 10), (1, 299, 10), (1, 300, 0)):
            with self.assertRaises(ValidationError):
                RansomwareWatchMonitorService.validate_limits(*values)
        self.add_watch()
        self.watches.add("Beta kuruluş", "Beta Ltd", kind="organization")
        source = SequenceSource([feed([])])
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValidationError, "tamamı toplu sınıra sığmıyor"):
            self.monitor(source).run(max_watches=1)
        self.assertEqual((source.calls, self.path.read_bytes()), (0, before))

    def test_bad_monotonic_clock_stops_before_source_access(self):
        self.add_watch()
        source = SequenceSource([feed([])])
        monitor = self.monitor(source)
        monitor.monotonic = lambda: float("nan")
        with self.assertRaisesRegex(ValidationError, "ölçen saat geçersiz"):
            monitor.run(max_cycles=1)
        self.assertEqual(source.calls, 0)

    def test_cli_one_cycle_returns_bounded_json_report(self):
        actual = datetime.now(timezone.utc)
        self.watches.clock = lambda: actual
        watch = self.add_watch()
        cli_feed = parse_threatcluster_ransomware_response(
            content(
                [claim("Alpha Ltd")],
                generated_at=(actual - timedelta(minutes=30)).isoformat(),
            ),
            fetched_at=actual,
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
                "--data-dir", str(self.data), "--json", "ransomware", "watch-monitor",
                "--cycles", "1", "--interval", "300", "--duration", "10",
                "--watch-limit", "5", "--source-item-limit", "10",
                "--watch-item-limit", "10",
            ])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        result = json.loads(stdout.getvalue())
        self.assertTrue(result["ok"])
        self.assertEqual((result["data"]["completed_cycles"],
                          result["data"]["completed_watch_runs"]), (1, 1))
        self.assertEqual(self.watches.show(watch.id).total_run_count, 1)

    def test_cli_failed_source_cycle_returns_three_without_watch_run(self):
        actual = datetime.now(timezone.utc)
        self.watches.clock = lambda: actual
        watch = self.add_watch()
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
                "--data-dir", str(self.data), "--json", "ransomware", "watch-monitor",
                "--cycles", "1", "--interval", "300", "--duration", "10",
            ])
        self.assertEqual((code, stderr.getvalue()), (3, ""))
        result = json.loads(stdout.getvalue())
        self.assertFalse(result["ok"])
        self.assertEqual((result["data"]["failed_cycles"],
                          result["data"]["completed_watch_runs"]), (1, 0))
        self.assertEqual(self.watches.show(watch.id).total_run_count, 0)


if __name__ == "__main__":
    unittest.main()

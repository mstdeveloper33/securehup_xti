"""Foreground social username monitoring is bounded and interruption-safe."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.maigret_username import INTEGRATION_PROFILE
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_brand_username_watches import (
    SQLiteBrandUsernameWatchRepository,
)
from xti.application.brand_username_watch_monitor import (
    BrandUsernameWatchMonitorService,
)
from xti.application.brand_username_watches import BrandUsernameWatchService
from xti.domain.assets import ValidationError
from xti.domain.brand_username import BrandProfileMatch, BrandUsernamePreview
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 31, 18, tzinfo=timezone.utc)


def github(username, *, alternate=False):
    host = "www.github.com" if alternate else "github.com"
    return f"https://{host}/{username}"


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


class FakeSource:
    source_name = "Maigret"
    source_version = "0.6.6"
    integration_profile = INTEGRATION_PROFILE

    def __init__(self, outcomes, *, clock):
        self.outcomes = list(outcomes)
        self.clock = clock
        self.calls = 0

    def preview(self, username, *, platforms, request_timeout):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        matches = tuple(
            BrandProfileMatch(platform, profile_url, "found_unverified")
            for platform, profile_url in outcome.items()
        )
        return BrandUsernamePreview(
            username=username,
            source=self.source_name,
            source_version=self.source_version,
            integration_profile=self.integration_profile,
            checked_at=self.clock().isoformat(),
            requested_platforms=platforms,
            matches=matches,
            unreported_platforms=tuple(
                platform for platform in platforms if platform not in outcome
            ),
            notes=("Sahiplik kanıtı değildir.",),
        )


class BrandUsernameWatchMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteBrandUsernameWatchRepository(self.path)
        self.timer = Timer()

    def wall_clock(self):
        return NOW + timedelta(seconds=self.timer.value)

    def service(self, source):
        return BrandUsernameWatchService(
            self.repository,
            source,
            clock=self.wall_clock,
        )

    def monitor(self, source, *, timer=None):
        timer = timer or self.timer

        def clock():
            return NOW + timedelta(seconds=timer.value)

        service = BrandUsernameWatchService(
            self.repository,
            source,
            clock=clock,
        )
        return service, BrandUsernameWatchMonitorService(
            service,
            clock=clock,
            monotonic=timer.monotonic,
            sleeper=timer.sleep,
        )

    def add_watch(self, source):
        return self.service(source).add(
            "Example watch",
            "example",
            platforms=("GitHub",),
        ).watch

    def test_two_cycles_persist_runs_and_report_second_profile_change(self):
        source = FakeSource(
            [
                {"GitHub": github("example")},
                {"GitHub": github("example", alternate=True)},
            ],
            clock=self.wall_clock,
        )
        watch = self.add_watch(source)
        service, monitor = self.monitor(source)

        report = monitor.run(
            watch.id,
            max_cycles=2,
            interval_seconds=300,
            max_duration_seconds=600,
            request_timeout=5,
        )

        self.assertEqual((report.completed_cycles, report.stop_reason), (2, "cycles"))
        self.assertEqual((report.successful_cycles, report.failed_cycles), (2, 0))
        self.assertEqual((report.changed_count, report.attention_count), (1, 1))
        self.assertEqual(source.calls, 2)
        self.assertEqual(sum(self.timer.sleeps), 300)
        self.assertEqual(service.show(watch.id).total_run_count, 2)

    def test_failed_source_cycle_is_preserved_and_next_cycle_can_succeed(self):
        source = FakeSource(
            [
                SourceError("Maigret geçici olarak yanıt vermedi."),
                {"GitHub": github("example")},
            ],
            clock=self.wall_clock,
        )
        watch = self.add_watch(source)
        service, monitor = self.monitor(source)

        report = monitor.run(
            watch.id,
            max_cycles=2,
            interval_seconds=300,
            max_duration_seconds=600,
        )

        self.assertEqual((report.successful_cycles, report.failed_cycles), (1, 1))
        self.assertEqual(
            [cycle.status for cycle in report.cycles],
            ["failed", "complete"],
        )
        self.assertEqual(service.show(watch.id).total_run_count, 2)

    def test_duration_stops_new_cycle_and_keeps_completed_run(self):
        source = FakeSource(
            [{"GitHub": github("example")}],
            clock=self.wall_clock,
        )
        watch = self.add_watch(source)
        service, monitor = self.monitor(source)

        report = monitor.run(
            watch.id,
            max_cycles=3,
            interval_seconds=300,
            max_duration_seconds=5,
        )

        self.assertEqual((report.completed_cycles, report.stop_reason), (1, "duration"))
        self.assertEqual(source.calls, 1)
        self.assertEqual(sum(self.timer.sleeps), 5)
        self.assertEqual(service.show(watch.id).total_run_count, 1)

    def test_ctrl_c_during_wait_preserves_first_run_and_propagates(self):
        timer = Timer(interrupt=True)

        def clock():
            return NOW + timedelta(seconds=timer.value)

        source = FakeSource(
            [{"GitHub": github("example")}],
            clock=clock,
        )
        watch = BrandUsernameWatchService(
            self.repository,
            source,
            clock=clock,
        ).add("Example watch", "example", platforms=("GitHub",)).watch
        service, monitor = self.monitor(source, timer=timer)

        with self.assertRaises(KeyboardInterrupt):
            monitor.run(
                watch.id,
                max_cycles=2,
                interval_seconds=300,
                max_duration_seconds=600,
            )

        self.assertEqual(source.calls, 1)
        self.assertEqual(service.show(watch.id).total_run_count, 1)

    def test_invalid_limits_inactive_watch_and_bad_clock_stop_before_source(self):
        source = FakeSource([], clock=self.wall_clock)
        for values in (
            (0, 300, 10, 10),
            (1, 299, 10, 10),
            (1, 300, 0, 10),
            (1, 300, 10, 4),
        ):
            with self.assertRaises(ValidationError):
                BrandUsernameWatchMonitorService.validate_limits(*values)

        watch = self.add_watch(source)
        service = self.service(source)
        service.revoke(watch.id, reason="Bu izleme artık gerekli değil.")
        with self.assertRaisesRegex(ValidationError, "Geri çekilmiş"):
            BrandUsernameWatchMonitorService(service).run(
                watch.id,
                max_cycles=1,
                interval_seconds=300,
                max_duration_seconds=10,
            )
        self.assertEqual(source.calls, 0)

        active_source = FakeSource([], clock=self.wall_clock)
        active = self.service(active_source).add(
            "Active watch", "active", platforms=("GitHub",),
        ).watch
        bad_clock = BrandUsernameWatchMonitorService(
            self.service(active_source),
            monotonic=lambda: float("nan"),
        )
        with self.assertRaisesRegex(ValidationError, "ölçen saat geçersiz"):
            bad_clock.run(active.id, max_cycles=1)
        self.assertEqual(active_source.calls, 0)

    def call_cli(self, *arguments):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_one_cycle_returns_bounded_json_report(self):
        actual = datetime.now(timezone.utc)
        source = FakeSource([], clock=lambda: actual)
        service = BrandUsernameWatchService(
            self.repository,
            source,
            clock=lambda: actual,
        )
        watch = service.add(
            "Example watch", "example", platforms=("GitHub",),
        ).watch

        preview = BrandUsernamePreview(
            "example",
            "Maigret",
            "0.6.6",
            INTEGRATION_PROFILE,
            actual.isoformat(),
            ("GitHub",),
            (BrandProfileMatch("GitHub", github("example"), "found_unverified"),),
            (),
            ("Sahiplik kanıtı değildir.",),
        )
        with patch(
            "xti.interfaces.cli.MaigretUsernameSource.preview",
            return_value=preview,
        ):
            code, output, error = self.call_cli(
                "brand",
                "watch-monitor",
                watch.id,
                "--cycles",
                "1",
                "--interval",
                "300",
                "--duration",
                "10",
                "--timeout",
                "5",
            )

        self.assertEqual((code, error), (0, ""))
        payload = json.loads(output)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            (
                payload["data"]["completed_cycles"],
                len(payload["data"]["cycles"]),
            ),
            (1, 1),
        )
        self.assertEqual(service.show(watch.id).total_run_count, 1)

    def test_cli_source_failure_returns_three_with_failed_run(self):
        actual = datetime.now(timezone.utc)
        source = FakeSource([], clock=lambda: actual)
        service = BrandUsernameWatchService(
            self.repository,
            source,
            clock=lambda: actual,
        )
        watch = service.add(
            "Example watch", "example", platforms=("GitHub",),
        ).watch

        with patch(
            "xti.interfaces.cli.MaigretUsernameSource.preview",
            side_effect=SourceError("Maigret geçici olarak yanıt vermedi."),
        ):
            code, output, error = self.call_cli(
                "brand",
                "watch-monitor",
                watch.id,
                "--cycles",
                "1",
                "--interval",
                "300",
                "--duration",
                "10",
            )

        self.assertEqual((code, error), (3, ""))
        payload = json.loads(output)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["data"]["failed_cycles"], 1)
        self.assertEqual(service.show(watch.id).total_run_count, 1)


if __name__ == "__main__":
    unittest.main()

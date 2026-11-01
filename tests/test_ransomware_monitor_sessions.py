"""Durable ransomware monitor sessions preserve bounded foreground evidence."""

from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_monitor_sessions import (
    SQLiteRansomwareMonitorSessionRepository,
)
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.ransomware_claims import RansomwareClaimHistoryService
from xti.application.ransomware_monitor_sessions import RansomwareMonitorSessionService
from xti.application.ransomware_watch_monitor import RansomwareWatchMonitorService
from xti.application.ransomware_watch_refresh import RansomwareWatchRefreshService
from xti.application.ransomware_watches import RansomwareWatchService
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError
from tests.test_threatcluster_ransomware import claim, content


NOW = datetime(2026, 10, 30, 22, tzinfo=timezone.utc)


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
    def __init__(self, *, failure=None):
        self.value = 0.0
        self.failure = failure

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        if self.failure is not None:
            raise self.failure
        self.value += seconds


class RansomwareMonitorSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.claims = SQLiteRansomwareClaimRepository(self.path)
        self.watch_repository = SQLiteRansomwareWatchRepository(self.path)
        self.sessions = SQLiteRansomwareMonitorSessionRepository(self.path)

    def service(self, source, timer):
        clock = lambda: NOW + timedelta(seconds=timer.value)
        watch_service = RansomwareWatchService(
            self.watch_repository, self.claims, clock=clock,
        )
        history = RansomwareClaimHistoryService(self.claims, source, clock=clock)
        refresh = RansomwareWatchRefreshService(history, watch_service, clock=clock)
        monitor = RansomwareWatchMonitorService(
            refresh, clock=clock, monotonic=timer.monotonic, sleeper=timer.sleep,
        )
        return RansomwareMonitorSessionService(self.sessions, monitor, clock=clock)

    def add_watch(self):
        return RansomwareWatchService(
            self.watch_repository, self.claims, clock=lambda: NOW,
        ).add("Alpha kuruluş", "Alpha Ltd", kind="organization").watch

    def test_two_cycles_are_complete_and_each_cycle_is_auditable(self):
        watch = self.add_watch()
        timer = Timer()
        report = self.service(SequenceSource([
            feed([claim("Alpha Ltd")]),
            feed([claim("Alpha Ltd", sector="Finance")], second=300),
        ]), timer).run(
            max_cycles=2, interval_seconds=300, max_duration_seconds=600,
        )

        self.assertIsNotNone(report.session_id)
        # A later manual run may reuse the newest source snapshot, but must not
        # retroactively change the completed monitor cycle.
        RansomwareWatchService(
            self.watch_repository, self.claims,
            clock=lambda: NOW + timedelta(seconds=400),
        ).run(watch.id)
        details = self.sessions.details(report.session_id, cycle_limit=100)
        self.assertEqual((details.session.status, details.session.stop_reason),
                         ("complete", "cycles"))
        self.assertEqual((details.session.completed_cycles,
                          details.session.completed_watch_runs,
                          details.session.baseline_watch_runs,
                          details.session.notification_count), (2, 2, 1, 1))
        self.assertEqual(
            RansomwareWatchService(
                self.watch_repository, self.claims,
            ).show(watch.id).total_run_count,
            3,
        )
        self.assertEqual([item.cycle for item in details.cycles], [1, 2])
        self.assertEqual(
            [item.source_run_id for item in details.cycles],
            [item.source_run_id for item in report.cycles],
        )

    def test_failed_source_cycle_finishes_as_partial_and_keeps_next_success(self):
        self.add_watch()
        timer = Timer()
        report = self.service(SequenceSource([
            SourceError("Kaynak bağlantısı tamamlanamadı; sonuç üretilmedi."),
            feed([claim("Alpha Ltd")], second=300),
        ]), timer).run(
            max_cycles=2, interval_seconds=300, max_duration_seconds=600,
        )
        details = self.sessions.details(report.session_id, cycle_limit=100)
        self.assertEqual((details.session.status, details.session.failed_cycles),
                         ("partial", 1))
        self.assertEqual([item.source_status for item in details.cycles],
                         ["failed", "complete"])

    def test_ctrl_c_and_runtime_failure_get_distinct_durable_states(self):
        self.add_watch()
        interrupted_timer = Timer(failure=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.service(
                SequenceSource([feed([claim("Alpha Ltd")])]), interrupted_timer,
            ).run(max_cycles=2, interval_seconds=300, max_duration_seconds=600)
        interrupted = self.sessions.list(limit=10)[0]
        self.assertEqual((interrupted.status, interrupted.stop_reason,
                          interrupted.completed_cycles), ("interrupted", "interrupted", 1))

        failed_timer = Timer(failure=RuntimeError("internal detail"))
        with self.assertRaisesRegex(RuntimeError, "internal detail"):
            self.service(
                SequenceSource([feed([claim("Alpha Ltd")])]), failed_timer,
            ).run(max_cycles=2, interval_seconds=300, max_duration_seconds=600)
        failed = self.sessions.list(limit=10)[0]
        self.assertEqual((failed.status, failed.stop_reason, failed.completed_cycles),
                         ("failed", "error", 1))
        self.assertNotIn("internal detail", failed.error)

    def test_unfinished_process_is_never_misreported_as_complete(self):
        session = self.sessions.start(
            started_at=NOW.isoformat(), planned_cycles=3, interval_seconds=300,
            max_duration_seconds=600, max_watches=50, source_item_limit=100,
            watch_item_limit=100,
        )
        restored = self.sessions.details(session.id, cycle_limit=10).session
        self.assertEqual((restored.status, restored.finished_at,
                          restored.completed_cycles), ("running", None, 0))
        self.assertEqual(
            SQLiteAssetRepository(self.path).inspect()[
                "running_ransomware_monitor_session_count"
            ], 1,
        )

    def test_semantically_corrupt_session_fails_closed(self):
        self.add_watch()
        report = self.service(
            SequenceSource([feed([claim("Alpha Ltd")])]), Timer(),
        ).run(max_cycles=1, interval_seconds=300, max_duration_seconds=10)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE ransomware_monitor_sessions SET status='partial' WHERE id=?",
                (report.session_id,),
            )
        with self.assertRaisesRegex(StorageError, "kısmi durumu"):
            self.sessions.details(report.session_id, cycle_limit=10)

    def test_cli_lists_and_shows_sessions_without_network(self):
        self.add_watch()
        report = self.service(
            SequenceSource([feed([claim("Alpha Ltd")])]), Timer(),
        ).run(max_cycles=1, interval_seconds=300, max_duration_seconds=10)
        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-dir", str(self.data), "--json", "ransomware",
                "watch-monitor-list", "--limit", "10",
            ])
        payload = json.loads(output.getvalue())
        self.assertEqual((code, payload["data"]["sessions"][0]["id"]),
                         (0, report.session_id))

        output = StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-dir", str(self.data), "ransomware", "watch-monitor-show",
                report.session_id,
            ])
        self.assertEqual(code, 0)
        self.assertIn("doğrulanmış ihlal değildir", output.getvalue())


if __name__ == "__main__":
    unittest.main()

"""Foreground CTI watch scheduling is bounded, visible and interruption-safe."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_cti_saved_searches import SQLiteCtiSavedSearchRepository
from xti.application.cti_knowledge import CtiKnowledgeService
from xti.application.cti_saved_search_monitor import CtiSavedSearchMonitorService
from xti.application.cti_saved_searches import CtiSavedSearchService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


class CtiSavedSearchMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name) / "data"
        self.path = self.data / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.elapsed = 0.0
        self.saved = CtiSavedSearchService(
            SQLiteCtiSavedSearchRepository(self.path), clock=self.wall_clock,
        )
        self.knowledge = CtiKnowledgeService(
            SQLiteCtiKnowledgeRepository(self.path), clock=self.wall_clock,
        )

    def wall_clock(self):
        return NOW + timedelta(seconds=self.elapsed)

    def tick(self):
        return self.elapsed

    def entity(self, name, source):
        return self.knowledge.add_entity(
            "malware", name, aliases=(), source_name=source,
            source_reference=f"local:{source}", confidence=70,
            description="Ön plan CTI izleme kabul testi kaynak kaydı.",
        )

    def test_two_cycles_persist_full_runs_and_second_change_notification(self):
        watch = self.saved.add("Example watch", "Example", kind="entity")
        self.entity("Example One", "one")
        inserted = False

        def sleep(seconds):
            nonlocal inserted
            self.elapsed += seconds
            if not inserted:
                inserted = True
                self.entity("Example Two", "two")

        report = CtiSavedSearchMonitorService(
            self.saved, clock=self.wall_clock, monotonic=self.tick, sleeper=sleep,
        ).run(
            watch.saved_search.id, max_cycles=2, interval_seconds=300,
            max_duration_seconds=600,
        )
        self.assertEqual((report.completed_cycles, report.stop_reason), (2, "cycles"))
        self.assertEqual((report.added_count, report.notification_count), (2, 1))
        self.assertIsNone(report.cycles[0].notification_id)
        self.assertIsNotNone(report.cycles[1].notification_id)
        self.assertEqual(self.saved.show(watch.saved_search.id).total_run_count, 2)

    def test_duration_stops_new_cycle_and_keeps_completed_work(self):
        watch = self.saved.add("Example watch", "Example")
        self.entity("Example One", "one")

        def sleep(seconds):
            self.elapsed += seconds

        report = CtiSavedSearchMonitorService(
            self.saved, clock=self.wall_clock, monotonic=self.tick, sleeper=sleep,
        ).run(
            watch.saved_search.id, max_cycles=3, interval_seconds=300,
            max_duration_seconds=5,
        )
        self.assertEqual((report.completed_cycles, report.stop_reason), (1, "duration"))
        self.assertEqual(self.saved.show(watch.saved_search.id).total_run_count, 1)

    def test_interrupt_during_wait_preserves_first_cycle_and_propagates(self):
        watch = self.saved.add("Example watch", "Example")
        self.entity("Example One", "one")

        def interrupted_sleep(_seconds):
            raise KeyboardInterrupt

        service = CtiSavedSearchMonitorService(
            self.saved, clock=self.wall_clock, monotonic=self.tick,
            sleeper=interrupted_sleep,
        )
        with self.assertRaises(KeyboardInterrupt):
            service.run(
                watch.saved_search.id, max_cycles=2, interval_seconds=300,
                max_duration_seconds=600,
            )
        self.assertEqual(self.saved.show(watch.saved_search.id).total_run_count, 1)

    def test_invalid_limits_inactive_watch_and_bad_clock_fail_safely(self):
        watch = self.saved.add("Example watch", "Example")
        before = self.path.read_bytes()
        for values in ((0, 300, 10), (1, 299, 10), (1, 300, 0)):
            with self.assertRaises(ValidationError):
                CtiSavedSearchMonitorService.validate_limits(*values)
        self.assertEqual(self.path.read_bytes(), before)
        self.saved.revoke(watch.saved_search.id, reason="Bu izleme artık gerekli değil.")
        with self.assertRaisesRegex(ValidationError, "Geri çekilmiş"):
            CtiSavedSearchMonitorService(
                self.saved, clock=self.wall_clock, monotonic=self.tick,
            ).run(
                watch.saved_search.id, max_cycles=1, interval_seconds=300,
                max_duration_seconds=10,
            )

    def call_cli(self, *arguments):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--data-dir", str(self.data), "--json", *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_cli_one_cycle_is_bounded_and_reports_persisted_run(self):
        watch = self.saved.add("Example watch", "Example")
        self.entity("Example One", "one")
        code, output, error = self.call_cli(
            "cti", "watch-monitor", watch.saved_search.id,
            "--cycles", "1", "--interval", "300", "--duration", "10",
        )
        self.assertEqual((code, error), (0, ""))
        data = json.loads(output)["data"]
        self.assertEqual((data["completed_cycles"], len(data["cycles"])), (1, 1))
        self.assertEqual(self.saved.show(watch.saved_search.id).total_run_count, 1)


if __name__ == "__main__":
    unittest.main()

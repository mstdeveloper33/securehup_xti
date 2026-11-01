"""Monitoring ownership, atomic grouping, recovery and compact immutable evidence."""

from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.sqlite_monitoring import SQLiteMonitorRepository
from xti.domain.assets import ValidationError
from xti.domain.discovery import QueryResult, ScanResult
from xti.domain.findings import ImportSummary
from xti.domain.monitoring import MonitorSpec


NOW = "2026-10-29T10:00:00+00:00"
LATER = "2026-10-29T10:10:00+00:00"


class MonitorStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.assets.add("example.com")
        self.jobs = SQLiteJobRepository(self.path)
        self.repo = SQLiteMonitorRepository(self.path)
        self.spec = MonitorSpec(("example.com",), ("crt.sh", "urlscan"), False, "rules-v1", 3, 300, 3600)

    def run_record(self, **changes):
        return self.repo.create(replace(self.spec, **changes), NOW)

    def complete(self, job, run, *, status="complete", count=2):
        with patch("xti.adapters.sqlite_jobs._now", return_value=NOW):
            attempt = self.jobs.start(job.id, monitor_id=run.id)
            query = QueryResult("%example%", "https://crt.sh/", status, count, 0,
                                "Controlled query error" if status == "failed" else None, ())
            result = ScanResult(job.targets, NOW, NOW, status, (query,),
                                ImportSummary(count, count, 0, count, 0), ("example-support.net",))
            return self.jobs.finish(attempt.id, status, result=result)

    def counts(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return tuple(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                         for name in ("monitor_runs", "monitor_jobs", "scan_jobs", "scan_attempts"))

    def test_create_and_compact_first_attempt_survive_reopen(self):
        run = self.run_record()
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        attempt = self.complete(job, run)
        details = SQLiteMonitorRepository(self.path).get(run.id)
        self.assertEqual(details.run, run)
        self.assertEqual(len(details.entries), 1)
        saved = details.entries[0].attempt
        self.assertEqual((saved.id, saved.number, saved.status, saved.query_count), (attempt.id, 1, "complete", 1))
        self.assertEqual(saved.summary.findings_created, 2)
        self.assertFalse(hasattr(saved, "queries"))
        self.assertFalse(hasattr(saved, "candidate_domains"))

    def test_only_one_running_session_and_targets_must_be_registered(self):
        with self.assertRaises(ValidationError):
            self.run_record(targets=("missing.com",))
        self.assertEqual(self.counts(), (0, 0, 0, 0))
        self.run_record()
        with self.assertRaises(ValidationError):
            self.run_record()
        self.assertEqual(self.counts(), (1, 0, 0, 0))

    def test_enqueue_and_link_failure_roll_back_together(self):
        run = self.run_record()
        with patch.object(SQLiteJobRepository, "_get_job", side_effect=StorageError("disk failure")):
            with self.assertRaises(StorageError):
                self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        self.assertEqual(self.counts(), (1, 0, 0, 0))
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        self.assertEqual(self.jobs.get(job.id).job.id, job.id)

    def test_duplicate_and_out_of_order_enqueue_leave_no_orphan_jobs(self):
        run = self.run_record()
        for cycle, provider in ((1, "urlscan"), (2, "crt.sh"), (4, "crt.sh")):
            with self.assertRaises(ValidationError):
                self.repo.enqueue(run.id, cycle, provider, NOW)
        self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        with self.assertRaises(ValidationError):
            self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        self.assertEqual(self.counts(), (1, 1, 1, 0))

    def test_generic_worker_skips_monitor_jobs_but_runs_ordinary_queue(self):
        run = self.run_record()
        monitored = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        self.assertIsNone(self.jobs.start())
        ordinary = self.jobs.create(("example.com",), False, "crt.sh", "rules-v1")
        attempt = self.jobs.start()
        self.assertEqual(attempt.job_id, ordinary.id)
        self.assertEqual(self.jobs.get(monitored.id).job.status, "queued")

    def test_explicit_monitored_work_requires_matching_live_owner(self):
        run = self.run_record()
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        before = self.path.read_bytes()
        for owner in (None, "wrong-session"):
            with self.assertRaises(ValidationError):
                self.jobs.start(job.id, monitor_id=owner)
        self.assertEqual(self.path.read_bytes(), before)
        attempt = self.jobs.start(job.id, monitor_id=run.id)
        self.jobs.finish(attempt.id, "failed", error="controlled")
        for owner in (None, run.id):
            with self.assertRaises(ValidationError):
                self.jobs.start(job.id, monitor_id=owner)
        self.repo.finish(run.id, "completed", "duration", LATER, 10.0)
        with self.assertRaises(ValidationError):
            self.jobs.start(job.id, monitor_id=run.id)

    def test_monitor_owner_cannot_claim_an_ordinary_job(self):
        run = self.run_record()
        ordinary = self.jobs.create(("example.com",), False, "crt.sh", "rules-v1")
        with self.assertRaises(ValidationError):
            self.jobs.start(ordinary.id, monitor_id=run.id)
        with self.assertRaises(ValidationError):
            self.jobs.start(monitor_id=run.id)
        self.assertEqual(self.jobs.get(ordinary.id).job.status, "queued")

    def test_recovery_keeps_saved_queries_and_retires_unstarted_work(self):
        run = self.run_record()
        first = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        attempt = self.jobs.start(first.id, monitor_id=run.id)
        query = QueryResult("%example%", "https://crt.sh/", "complete", 2, 0, None, ())
        self.jobs.progress(attempt.id, "Saved query", query)
        second = self.repo.enqueue(run.id, 1, "urlscan", NOW)
        ordinary = self.jobs.create(("example.com",), False, "urlscan", "rules-v1")
        self.assertEqual(self.repo.recover(LATER), 1)
        details = self.repo.get(run.id)
        self.assertEqual((details.run.status, details.run.stop_reason, details.run.elapsed_seconds),
                         ("interrupted", "recovered", None))
        self.assertEqual(details.entries[0].attempt.status, "interrupted")
        self.assertEqual(details.entries[0].attempt.query_count, 1)
        self.assertIsNone(details.entries[0].attempt.summary)
        self.assertEqual(self.jobs.get(first.id).attempts[0].queries, (query,))
        self.assertEqual(self.jobs.get(second.id).job.status, "interrupted")
        self.assertEqual(self.jobs.get(second.id).attempts, ())
        self.assertEqual(self.jobs.get(ordinary.id).job.status, "queued")
        before = self.path.read_bytes()
        self.assertEqual(self.repo.recover(LATER), 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_reading_running_session_never_recovers_or_changes_files(self):
        run = self.run_record()
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        self.jobs.start(job.id, monitor_id=run.id)
        before = self.path.read_bytes()
        files = tuple(self.path.parent.iterdir())
        self.assertEqual(self.repo.list(), (run,))
        self.assertEqual(self.repo.get(run.id).entries[0].attempt.status, "running")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(tuple(self.path.parent.iterdir()), files)

    def test_completion_refuses_unfinished_jobs_and_cancel_closes_them(self):
        run = self.run_record()
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.repo.finish(run.id, "completed", "cycles", LATER, 5)
        self.assertEqual(self.path.read_bytes(), before)
        finished = self.repo.finish(run.id, "interrupted", "cancelled", LATER, 5)
        self.assertEqual(finished.elapsed_seconds, 5.0)
        self.assertEqual(self.jobs.get(job.id).job.status, "interrupted")
        self.assertEqual(self.jobs.get(job.id).attempts, ())
        with self.assertRaises(ValidationError):
            self.repo.finish(run.id, "failed", "error", LATER, 6)
        with self.assertRaises(ValidationError):
            self.repo.enqueue(run.id, 1, "urlscan", LATER)

    def test_recovery_failure_rolls_back_both_attempt_and_session(self):
        run = self.run_record()
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        self.jobs.start(job.id, monitor_id=run.id)
        before = self.path.read_bytes()
        original = self.repo._retire_pending

        def fail_after_retirement(connection, run_id, now):
            original(connection, run_id, now)
            raise StorageError("simulated storage failure")

        with patch.object(self.repo, "_retire_pending", side_effect=fail_after_retirement):
            with self.assertRaises(StorageError):
                self.repo.recover(LATER)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.repo.get(run.id).run.status, "running")
        self.assertEqual(self.jobs.get(job.id).attempts[0].status, "running")

    def test_backup_restore_retains_summary_and_first_attempt_attribution(self):
        run = self.run_record()
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        self.complete(job, run)
        self.repo.finish(run.id, "completed", "duration", LATER, 42.25)
        before = self.repo.get(run.id)
        backup = self.root / "backup.db"
        self.assets.backup(backup)
        restored = self.root / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteMonitorRepository(restored).get(run.id), before)
        self.assertEqual(SQLiteMonitorRepository(restored).list(), (before.run,))

    def test_later_manually_recorded_attempt_cannot_change_attributed_result(self):
        run = self.run_record()
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        self.complete(job, run)
        self.repo.finish(run.id, "completed", "duration", LATER, 10)
        first = self.repo.get(run.id).entries[0].attempt
        # Later attempts are blocked by the public adapter. This fixture proves
        # that the read contract remains pinned if a future migration adds one.
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE scan_jobs SET status = 'failed', attempt_count = 2 WHERE id = ?", (job.id,))
            connection.execute(
                "INSERT INTO scan_attempts VALUES ('later-attempt', ?, 2, 'failed', ?, ?, NULL, 'Later error', '[]', NULL)",
                (job.id, LATER, LATER),
            )
        self.assertEqual(self.repo.get(run.id).entries[0].attempt, first)

    def test_corrupt_scope_or_missing_attempt_is_rejected(self):
        run = self.run_record()
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        self.complete(job, run)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE scan_jobs SET provider = 'urlscan' WHERE id = ?", (job.id,))
        with self.assertRaises(StorageError):
            self.repo.get(run.id)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE scan_jobs SET provider = 'crt.sh' WHERE id = ?", (job.id,))
            connection.execute("DELETE FROM scan_attempts WHERE job_id = ?", (job.id,))
        with self.assertRaises(StorageError):
            self.repo.get(run.id)

    def test_time_rollback_does_not_discard_measured_elapsed_duration(self):
        run = self.run_record()
        earlier = "2026-10-29T09:00:00+00:00"
        closed = self.repo.finish(run.id, "completed", "duration", earlier, 1.5)
        self.assertEqual(closed.finished_at, earlier)
        self.assertEqual(closed.elapsed_seconds, 1.5)

    def test_invalid_inputs_never_write_or_create_storage(self):
        before = self.path.read_bytes()
        for changes in ({"max_cycles": 0}, {"interval_seconds": 1}, {"max_duration_seconds": 604801},
                        {"targets": ("EXAMPLE.COM",)}, {"providers": ("crt.sh", "crt.sh")}, {"typos": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.run_record(**changes)
        self.assertEqual(self.path.read_bytes(), before)
        missing = self.root / "missing" / "xti.db"
        repo = SQLiteMonitorRepository(missing)
        with self.assertRaises(StorageError):
            repo.list()
        with self.assertRaises(StorageError):
            repo.get("missing")
        self.assertFalse(missing.parent.exists())
        for bad in (0, 101, True):
            with self.assertRaises(ValidationError):
                repo.list(bad)

    def test_invalid_finish_and_timestamp_do_not_change_running_session(self):
        run = self.run_record()
        before = self.path.read_bytes()
        for status, reason, elapsed in (("completed", "error", 1), ("failed", "cycles", 1),
                                        ("interrupted", "cancelled", -1), ("failed", "error", float("inf"))):
            with self.assertRaises(ValidationError):
                self.repo.finish(run.id, status, reason, LATER, elapsed)
        with self.assertRaises(ValidationError):
            self.repo.finish(run.id, "failed", "error", "2026-10-29T10:00:00", 1)
        self.assertEqual(self.path.read_bytes(), before)

    def test_duration_finish_retires_queued_job_but_cannot_close_running_request(self):
        run = self.run_record()
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        closed = self.repo.finish(run.id, "completed", "duration", LATER, 3)
        self.assertEqual((closed.status, closed.stop_reason), ("completed", "duration"))
        entry = self.repo.get(run.id).entries[0]
        self.assertIsNone(entry.attempt)
        self.assertEqual(entry.job.status, "interrupted")
        self.assertIsNone(self.jobs.start())
        another = self.run_record()
        next_job = self.repo.enqueue(another.id, 1, "crt.sh", NOW)
        self.jobs.start(next_job.id, monitor_id=another.id)
        with self.assertRaises(ValidationError):
            self.repo.finish(another.id, "completed", "duration", LATER, 4)
        self.assertEqual(self.repo.get(another.id).run.status, "running")

    def test_get_uses_one_snapshot_when_another_writer_adds_a_link(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        run = self.run_record()
        self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        original = self.repo._entry
        written = []

        def concurrent_entry(connection, saved_run, cycle, provider, job_id):
            if not written:
                written.append(self.repo.enqueue(run.id, 1, "urlscan", NOW))
            return original(connection, saved_run, cycle, provider, job_id)

        with patch.object(self.repo, "_entry", side_effect=concurrent_entry):
            shown = self.repo.get(run.id)
        self.assertEqual(len(shown.entries), 1)
        self.assertEqual(len(self.repo.get(run.id).entries), 2)

    def test_cycle_limit_finish_requires_all_planned_terminal_first_attempts(self):
        run = self.run_record(max_cycles=1)
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        self.complete(job, run)
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.repo.finish(run.id, "completed", "cycles", LATER, 10)
        self.assertEqual(self.path.read_bytes(), before)
        second = self.repo.enqueue(run.id, 1, "urlscan", NOW)
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.repo.finish(run.id, "completed", "cycles", LATER, 10)
        self.assertEqual(self.path.read_bytes(), before)
        self.complete(second, run)
        closed = self.repo.finish(run.id, "completed", "cycles", LATER, 10)
        self.assertEqual(closed.stop_reason, "cycles")
        self.assertEqual(len(self.repo.get(run.id).entries), 2)

    def test_closed_cycle_read_rejects_a_missing_trailing_job_link(self):
        run = self.run_record(max_cycles=1)
        for provider in run.spec.providers:
            self.complete(self.repo.enqueue(run.id, 1, provider, NOW), run)
        self.repo.finish(run.id, "completed", "cycles", LATER, 10)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DELETE FROM monitor_jobs WHERE run_id = ? AND provider = 'urlscan'", (run.id,))
        with self.assertRaises(StorageError):
            self.repo.get(run.id)

    def test_completed_duration_read_rejects_unretired_or_running_work(self):
        run = self.run_record()
        job = self.repo.enqueue(run.id, 1, "crt.sh", NOW)
        self.repo.finish(run.id, "completed", "duration", LATER, 1)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE scan_jobs SET status = 'queued' WHERE id = ?", (job.id,))
        with self.assertRaises(StorageError):
            self.repo.get(run.id)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE scan_jobs SET status = 'running', attempt_count = 1 WHERE id = ?", (job.id,))
            connection.execute(
                "INSERT INTO scan_attempts VALUES ('corrupt-running', ?, 1, 'running', ?, NULL, NULL, NULL, '[]', NULL)",
                (job.id, NOW),
            )
        with self.assertRaises(StorageError):
            self.repo.get(run.id)


if __name__ == "__main__":
    unittest.main()

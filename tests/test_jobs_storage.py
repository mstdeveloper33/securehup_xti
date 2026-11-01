"""Durable attempts, exclusive claims and history preservation without networking."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.domain.assets import ValidationError
from xti.domain.discovery import QueryResult, ScanResult
from xti.domain.findings import ImportSummary
from xti.ports.jobs import WorkerBusyError


class JobStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.repo = SQLiteJobRepository(self.path)

    def job(self, provider="crt.sh"):
        return self.repo.create(("example.com",), False, provider, "rules-v1")

    def result(self, attempt, *, status="complete", queries=()):
        return ScanResult(
            ("example.com",), attempt.started_at, datetime.now(timezone.utc).isoformat(),
            status, tuple(queries), ImportSummary(0, 0, 0, 0, 0), (),
        )

    def test_job_and_result_survive_new_repository_instance(self):
        job = self.job()
        attempt = self.repo.start(job.id)
        query = QueryResult("%example%", "https://crt.sh/?q=example", "complete", 0, 0, None, ())
        self.repo.progress(attempt.id, "Kaynak yanıtı alındı.", query)
        result = self.result(attempt, queries=(query,))
        finished = self.repo.finish(attempt.id, "complete", result=result)
        reopened = SQLiteJobRepository(self.path)
        details = reopened.get(job.id)
        self.assertEqual(details.job.status, "complete")
        self.assertEqual(details.job.targets, job.targets)
        self.assertEqual(details.job.rule_version, "rules-v1")
        self.assertEqual(details.attempts, (finished,))
        self.assertEqual(finished.result, result)
        self.assertEqual(finished.queries, (query,))
        self.assertIsNotNone(finished.finished_at)

    def test_read_only_list_and_show_do_not_recover_running_work(self):
        job = self.job()
        self.repo.start(job.id)
        before = self.path.read_bytes()
        self.assertEqual(self.repo.get(job.id).job.status, "running")
        self.assertEqual(self.repo.list()[0].status, "running")
        self.assertEqual(self.path.read_bytes(), before)

    def test_recovery_preserves_partial_queries_and_retry_appends_attempt(self):
        job = self.job()
        first = self.repo.start(job.id)
        query = QueryResult("%example%", "https://crt.sh/?q=example", "failed", 0, 0, "Kesinti.", ())
        self.repo.progress(first.id, "Sonraki sorgu bekleniyor.", query)
        self.assertEqual(self.repo.recover_interrupted("Önceki süreç kapandı."), 1)
        self.assertEqual(self.repo.recover_interrupted("Tekrar kontrol."), 0)
        interrupted = self.repo.get(job.id).attempts[0]
        self.assertEqual(interrupted.status, "interrupted")
        self.assertEqual(interrupted.queries, (query,))
        self.assertIsNone(interrupted.result)
        second = self.repo.start(job.id)
        self.repo.finish(second.id, "complete", result=self.result(second))
        details = self.repo.get(job.id)
        self.assertEqual([item.number for item in details.attempts], [1, 2])
        self.assertEqual(details.attempts[0], interrupted)
        self.assertEqual(details.job.attempt_count, 2)

    def test_late_progress_and_finish_cannot_overwrite_old_attempt(self):
        job = self.job()
        first = self.repo.start(job.id)
        self.repo.recover_interrupted("Kesildi.")
        second = self.repo.start(job.id)
        before = self.repo.get(job.id)
        with self.assertRaises(ValidationError):
            self.repo.progress(first.id, "Eski çalışan geri döndü.")
        with self.assertRaises(ValidationError):
            self.repo.finish(first.id, "failed", error="Eski hata.")
        self.assertEqual(self.repo.get(job.id), before)
        self.repo.finish(second.id, "failed", error="Yeni hata.")

    def test_concurrent_claims_allow_one_running_attempt_only(self):
        jobs = [self.job(), self.job()]
        barrier = threading.Barrier(2)

        def claim(job):
            barrier.wait(timeout=5)
            try:
                return SQLiteJobRepository(self.path).start(job.id)
            except WorkerBusyError:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            attempts = list(executor.map(claim, jobs))
        self.assertEqual(sum(item is not None for item in attempts), 1)
        self.assertEqual(len(self.repo.list(status="running")), 1)
        self.assertEqual(len(self.repo.list(status="queued")), 1)

    def test_queue_order_and_explicit_retry_states(self):
        first = self.job()
        second = self.job()
        attempt = self.repo.start()
        self.assertEqual(attempt.job_id, first.id)
        self.repo.finish(attempt.id, "failed", error="Kaynak kapalı.")
        next_attempt = self.repo.start()
        self.assertEqual(next_attempt.job_id, second.id)
        self.repo.finish(next_attempt.id, "complete", result=self.result(next_attempt))
        self.assertIsNone(self.repo.start())
        with self.assertRaises(ValidationError):
            self.repo.start(second.id)
        retry = self.repo.start(first.id)
        self.assertEqual(retry.number, 2)

    def test_clock_rollback_does_not_change_queue_or_recent_job_order(self):
        with patch("xti.adapters.sqlite_jobs._now", return_value="2026-10-28T12:00:00+00:00"):
            first = self.job()
        with patch("xti.adapters.sqlite_jobs._now", return_value="2026-10-28T11:00:00+00:00"):
            second = self.job()
        self.assertEqual([job.id for job in self.repo.list()], [second.id, first.id])
        first_attempt = self.repo.start()
        self.assertEqual(first_attempt.job_id, first.id)
        self.repo.finish(first_attempt.id, "failed", error="İlk iş tamamlandı.")
        second_attempt = self.repo.start()
        self.assertEqual(second_attempt.job_id, second.id)

    def test_result_mismatch_rolls_back_without_finishing_job(self):
        job = self.job()
        attempt = self.repo.start(job.id)
        query = QueryResult("example%", "https://crt.sh/", "complete", 0, 0, None, ())
        self.repo.progress(attempt.id, "Tamamlanan sorgu.", query)
        before = self.repo.get(job.id)
        for invalid in (
            self.result(attempt),
            replace(self.result(attempt, queries=(query,)), targets=("different.com",)),
        ):
            with self.subTest(result=invalid):
                with self.assertRaises(ValidationError):
                    self.repo.finish(attempt.id, "complete", result=invalid)
                self.assertEqual(self.repo.get(job.id), before)

    def test_corrupt_json_is_storage_error_not_raw_decoder_failure(self):
        job = self.job()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE scan_jobs SET targets = ? WHERE id = ?", ('{"bad":', job.id))
        with self.assertRaises(StorageError):
            self.repo.get(job.id)
        with self.assertRaises(StorageError):
            self.repo.list()

    def test_backup_restore_keeps_all_attempts_and_results(self):
        job = self.job()
        attempt = self.repo.start(job.id)
        self.repo.finish(attempt.id, "failed", error="Kaynak hatası.")
        retry = self.repo.start(job.id)
        self.repo.finish(retry.id, "complete", result=self.result(retry))
        before = self.repo.get(job.id)
        backup = Path(self.temp.name) / "backup.db"
        restored = Path(self.temp.name) / "restored" / "xti.db"
        self.assets.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteJobRepository(restored).get(job.id), before)

    def test_latest_provider_uses_attempt_order_not_wall_clock_or_queued_jobs(self):
        self.assertEqual(self.repo.latest_by_provider(), [])
        later = "2026-10-28T12:00:00+00:00"
        earlier = "2026-10-28T11:00:00+00:00"
        with patch("xti.adapters.sqlite_jobs._now", return_value=later):
            first = self.job()
            first_attempt = self.repo.start(first.id)
            self.repo.finish(first_attempt.id, "failed", error="Önceki hata.")
        with patch("xti.adapters.sqlite_jobs._now", return_value=earlier):
            second = self.job()
            second_attempt = self.repo.start(second.id)
            self.repo.finish(second_attempt.id, "complete", result=self.result(second_attempt))
        self.job("never-attempted")
        self.job()
        health = self.repo.latest_by_provider()
        self.assertEqual(len(health), 1)
        self.assertEqual(health[0].job.id, second.id)
        retry = self.repo.start(first.id)
        self.repo.finish(retry.id, "failed", error="En yeni hata.")
        self.assertEqual(self.repo.latest_by_provider()[0].job.id, first.id)


if __name__ == "__main__":
    unittest.main()

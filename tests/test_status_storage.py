"""Consistent monitoring history, bounded selected results and no read side effects."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.adapters.sqlite_status import SQLiteStatusRepository
from xti.domain.assets import ValidationError
from xti.domain.discovery import QueryResult, ScanResult
from xti.domain.findings import DomainInput, ImportDocument, ImportSummary, MatchCandidate


NOW = "2026-10-29T08:00:00+00:00"
EARLIER = "2026-10-28T08:00:00+00:00"
PROVIDERS = ("crt.sh", "urlscan")


class StatusStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.asset, _ = self.assets.add("example.com")
        self.jobs = SQLiteJobRepository(self.path)
        self.repo = SQLiteStatusRepository(self.path)

    def snapshot(self, *, domain=None, limit=20):
        return self.repo.snapshot(PROVIDERS, domain, limit)

    def history(self, domain="example.com", provider="crt.sh"):
        snapshot = self.snapshot()
        asset = next(item for item in snapshot.assets if item.asset.value == domain)
        return next(item for item in asset.sources if item.provider == provider)

    def job(self, targets=("example.com",), provider="crt.sh", *, typos=False):
        return self.jobs.create(targets, typos, provider, "rules-v1")

    def finish(self, job, status="complete", *, now=NOW, error=None, query_error=None):
        with patch("xti.adapters.sqlite_jobs._now", return_value=now):
            attempt = self.jobs.start(job.id)
            queries = (QueryResult(
                "%example%", "https://crt.sh/", status, 0, 0, query_error, (),
            ),)
            result = ScanResult(
                job.targets, now, now, status, queries, ImportSummary(0, 0, 0, 0, 0), (),
            )
            return self.jobs.finish(attempt.id, status, result=result, error=error)

    def create_finding(self):
        domain = "example-support.net"
        SQLiteFindingRepository(self.path).save_import(
            ImportDocument("fixture", "status-fixture", (DomainInput(domain, domain, 1, None),)),
            (MatchCandidate(self.asset.id, self.asset.value, domain, "rules-v1", ("Test",)),),
        )

    def test_empty_history_has_all_count_keys_and_explicit_unseen_sources(self):
        snapshot = self.snapshot()
        self.assertEqual(snapshot.asset_count, 1)
        self.assertEqual(snapshot.observation_count, 0)
        self.assertEqual(snapshot.finding_counts, {"new": 0, "suspicious": 0, "dismissed": 0, "uncertain": 0})
        self.assertEqual(set(snapshot.job_counts), {"queued", "running", "complete", "partial", "failed", "interrupted"})
        self.assertTrue(all(count == 0 for count in snapshot.job_counts.values()))
        self.assertEqual([item.provider for item in snapshot.assets[0].sources], list(PROVIDERS))
        self.assertTrue(all(item.latest_attempt is None and item.last_complete is None
                            for item in snapshot.assets[0].sources))

    def test_latest_failure_preserves_previous_complete_and_new_asset_is_unseen(self):
        good = self.finish(self.job())
        bad = self.finish(self.job(), "failed", query_error="Kaynak yanıt vermedi.")
        self.assets.add("another.com")
        history = self.history()
        self.assertEqual(history.latest_attempt.id, bad.id)
        self.assertEqual(history.last_complete.id, good.id)
        self.assertEqual(history.latest_attempt.failed_query_count, 1)
        self.assertEqual(history.latest_attempt.error, "Kaynak yanıt vermedi.")
        self.assertIsNone(self.history("another.com").last_complete)
        self.assertIsNone(self.history(provider="urlscan").latest_attempt)

    def test_retry_of_older_job_is_latest_even_with_earlier_clock(self):
        old_job = self.job(typos=True)
        self.finish(old_job, "failed")
        self.finish(self.job(), now=NOW)
        retried = self.finish(old_job, now=EARLIER)
        history = self.history()
        self.assertEqual(history.latest_attempt.id, retried.id)
        self.assertEqual(history.last_complete.id, retried.id)
        self.assertEqual(history.latest_attempt.number, 2)
        self.assertTrue(history.latest_attempt.typos)
        self.assertEqual(history.last_complete.finished_at, EARLIER)

    def test_old_complete_is_found_beyond_a_hundred_recent_failures(self):
        good = self.finish(self.job())
        bad = None
        for _ in range(105):
            bad = self.finish(self.job(), "failed")
        with patch.object(SQLiteJobRepository, "_get_attempt", wraps=SQLiteJobRepository._get_attempt) as read:
            history = self.history()
        self.assertEqual(history.last_complete.id, good.id)
        self.assertEqual(history.latest_attempt.id, bad.id)
        # Only the chosen latest and complete records need large JSON parsing.
        self.assertEqual(read.call_count, 2)

    def test_multi_target_partial_never_invents_individual_success(self):
        self.assets.add("another.com")
        job = self.job(("example.com", "another.com"))
        partial = self.finish(job, "partial")
        for domain in job.targets:
            history = self.history(domain)
            self.assertEqual(history.latest_attempt.id, partial.id)
            self.assertIsNone(history.last_complete)
            self.assertEqual(history.latest_attempt.partial_query_count, 1)
        good = self.finish(job)
        self.assertEqual(self.history("another.com").last_complete.id, good.id)
        self.assertEqual(self.history().last_complete.id, good.id)

    def test_filter_limits_assets_but_keeps_global_counts_and_queued_per_target(self):
        self.assets.add("another.com")
        self.assets.add("zebra.com")
        self.job(("example.com", "another.com"))
        self.job(provider="urlscan")
        self.job(("zebra.com",))
        self.create_finding()
        limited = self.snapshot(limit=1)
        self.assertEqual(limited.asset_count, 3)
        self.assertEqual([item.asset.value for item in limited.assets], ["another.com"])
        filtered = self.snapshot(domain="EXAMPLE.COM.")
        self.assertEqual([item.asset.value for item in filtered.assets], ["example.com"])
        self.assertEqual(filtered.job_counts["queued"], 3)
        self.assertEqual([item.queued_count for item in filtered.assets[0].sources], [1, 1])
        self.assertEqual(filtered.finding_counts["new"], 1)
        self.assertEqual((filtered.observation_count, filtered.notification_count, filtered.unread_notification_count), (1, 1, 1))

    def test_read_does_not_recover_running_job_or_mark_notice_read_or_create_lock(self):
        self.create_finding()
        job = self.job()
        attempt = self.jobs.start(job.id)
        before = self.path.read_bytes()
        snapshot = self.snapshot()
        self.assertEqual(snapshot.job_counts["running"], 1)
        self.assertEqual(snapshot.assets[0].sources[0].latest_attempt.id, attempt.id)
        self.assertEqual(snapshot.unread_notification_count, 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.path.with_name("xti.db.worker.lock").exists())
        self.assertEqual(self.jobs.get(job.id).job.status, "running")

    def test_notice_read_state_and_review_counts_are_separate(self):
        self.create_finding()
        inbox = SQLiteInboxRepository(self.path)
        item = inbox.list().items[0]
        SQLiteFindingRepository(self.path).review_finding(item.finding.id, "dismissed", "İncelendi.")
        self.assertEqual(self.snapshot().unread_notification_count, 1)
        inbox.mark((item.notification.id,), True, NOW)
        snapshot = self.snapshot()
        self.assertEqual(snapshot.finding_counts["dismissed"], 1)
        self.assertEqual(snapshot.unread_notification_count, 0)

    def test_cooldown_is_in_same_snapshot_and_keeps_expired_rows(self):
        wait = SQLiteCooldownRepository(self.path).extend("crt.sh", NOW, EARLIER, "rate_limit")
        self.assertEqual(self.snapshot().cooldowns, (wait,))

    def test_concurrent_commit_cannot_mix_global_counts_and_history(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        good = self.finish(self.job())
        original = SQLiteStatusRepository._histories

        def write_then_read(connection, assets, providers):
            self.assets.add("concurrent.com")
            self.finish(self.job(), "failed", error="Sonraki snapshot.")
            SQLiteCooldownRepository(self.path).extend("crt.sh", NOW, EARLIER, "rate_limit")
            return original(connection, assets, providers)

        with patch.object(SQLiteStatusRepository, "_histories", side_effect=write_then_read):
            snapshot = self.snapshot()
        self.assertEqual(snapshot.asset_count, 1)
        self.assertEqual(snapshot.job_counts["failed"], 0)
        self.assertEqual(snapshot.assets[0].sources[0].latest_attempt.id, good.id)
        self.assertEqual(snapshot.cooldowns, ())
        current = self.snapshot()
        self.assertEqual(current.asset_count, 2)
        self.assertEqual(current.job_counts["failed"], 1)
        self.assertEqual(len(current.cooldowns), 1)

    def test_selected_result_target_mismatch_is_rejected_without_mutation(self):
        attempt = self.finish(self.job())
        with closing(sqlite3.connect(self.path)) as connection:
            result = json.loads(connection.execute("SELECT result FROM scan_attempts WHERE id = ?", (attempt.id,)).fetchone()[0])
            result["targets"] = ["another.com"]
            connection.execute("UPDATE scan_attempts SET result = ? WHERE id = ?", (json.dumps(result), attempt.id))
            connection.commit()
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.snapshot()
        self.assertEqual(self.path.read_bytes(), before)

    def test_inflated_attempt_count_cannot_promote_old_complete_to_current(self):
        job = self.job()
        self.finish(job)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE scan_jobs SET attempt_count = 2 WHERE id = ?", (job.id,))
            connection.commit()
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.snapshot()
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_latest_attempt_is_rejected_instead_of_falling_back(self):
        job = self.job()
        self.finish(job, "failed")
        latest = self.finish(job)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("DELETE FROM scan_attempts WHERE id = ?", (latest.id,))
            connection.commit()
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.snapshot()
        self.assertEqual(self.path.read_bytes(), before)

    def test_attempt_number_gap_is_rejected_even_when_row_count_matches(self):
        job = self.job()
        first = self.finish(job, "failed")
        self.finish(job)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE scan_attempts SET number = 3 WHERE id = ?", (first.id,))
            connection.commit()
        with self.assertRaises(StorageError):
            self.snapshot()

    def test_complete_without_query_records_cannot_claim_completed_coverage(self):
        attempt = self.finish(self.job())
        with closing(sqlite3.connect(self.path)) as connection:
            result = json.loads(connection.execute(
                "SELECT result FROM scan_attempts WHERE id = ?", (attempt.id,),
            ).fetchone()[0])
            result["queries"] = []
            connection.execute(
                "UPDATE scan_attempts SET queries = '[]', result = ? WHERE id = ?",
                (json.dumps(result), attempt.id),
            )
            connection.commit()
        before = self.path.read_bytes()
        with self.assertRaises(StorageError):
            self.snapshot()
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_selected_json_fails_but_unselected_result_is_not_loaded(self):
        self.assets.add("another.com")
        good = self.finish(self.job())
        bad = self.finish(self.job(("another.com",)))
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE scan_attempts SET result = 'not json' WHERE id = ?", (bad.id,))
            connection.commit()
        self.assertEqual(self.snapshot(domain="example.com").assets[0].sources[0].last_complete.id, good.id)
        with self.assertRaises(StorageError):
            self.snapshot(domain="another.com")

    def test_missing_database_and_unknown_domain_are_read_only_errors(self):
        missing = self.path.parent / "missing" / "xti.db"
        with self.assertRaises(StorageError):
            SQLiteStatusRepository(missing).snapshot(PROVIDERS, None, 20)
        self.assertFalse(missing.parent.exists())
        before = self.path.read_bytes()
        with self.assertRaises(ValidationError):
            self.snapshot(domain="missing.com")
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_selection_is_rejected_before_database_access(self):
        missing = self.path.parent / "missing" / "xti.db"
        repo = SQLiteStatusRepository(missing)
        for providers, domain, limit in (
            (PROVIDERS, None, 0), (PROVIDERS, None, 101), (PROVIDERS, None, True),
            ((), None, 20), (("crt.sh", "crt.sh"), None, 20),
            (("\x1b",), None, 20), (PROVIDERS, "https://example.com", 20),
        ):
            with self.subTest(providers=providers, domain=domain, limit=limit):
                with self.assertRaises(ValidationError):
                    repo.snapshot(providers, domain, limit)
        self.assertFalse(missing.parent.exists())

    def test_backup_restore_preserves_status_history_and_counts(self):
        self.create_finding()
        self.finish(self.job())
        self.job(provider="urlscan")
        expected = self.snapshot()
        backup = self.path.parent / "snapshot.db"
        self.assets.backup(backup)
        restored = self.path.parent / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteStatusRepository(restored).snapshot(PROVIDERS, None, 20), expected)


if __name__ == "__main__":
    unittest.main()

"""Real SQLite reads preserve source provenance, recovery state and one snapshot."""

from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.hibp_public_notices import parse_hibp_public_notices_response
from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_event_candidates import SQLiteEventCandidateRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository, read_public_notice_snapshot
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_source_reviews import SQLiteRansomwareSourceReviewRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.application.ransomware_source_comparison import RansomwareSourceComparisonService
from xti.application.ransomware_source_reviews import RansomwareSourceReviewService
from xti.domain.event_candidates import EVENT_SOURCE_KEYS
from xti.domain.ransomlook_ransomware import ransomlook_claim_state_sha256
from xti.domain.ransomware_claims import ransomware_claim_state_sha256
from tests.test_public_notices import item as notice_item
from tests.test_ransomlook_ransomware import content as ransomlook_content, post
from tests.test_threatcluster_ransomware import claim, content as threatcluster_content


NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)
DISCOVERED = "2026-10-30T16:00:00Z"


class EventCandidateStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "xti.db"
        SQLiteAssetRepository(self.path).initialize()
        self.repository = SQLiteEventCandidateRepository(self.path)
        self.threatcluster = SQLiteRansomwareClaimRepository(self.path)
        self.ransomlook = SQLiteRansomLookClaimRepository(self.path)
        self.notices = SQLitePublicNoticeRepository(self.path)
        self.review_repository = SQLiteRansomwareSourceReviewRepository(self.path)
        self.review_time = NOW + timedelta(hours=1)
        self.comparisons = RansomwareSourceComparisonService(self.threatcluster, self.ransomlook)
        self.reviews = RansomwareSourceReviewService(
            self.review_repository, self.comparisons, clock=lambda: self.review_time,
        )

    def apply_tc(self, names=("Example Holding",), *, minute=1, website="example.com"):
        feed = parse_threatcluster_ransomware_response(
            threatcluster_content([
                {**claim(name, group="example-group", discovered=DISCOVERED), "website": website}
                for name in names
            ]), fetched_at=NOW,
        )
        return self._apply(self.threatcluster, feed, minute)

    def apply_rl(self, names=("Example Holding",), *, minute=2):
        feed = parse_ransomlook_ransomware_response(
            ransomlook_content([
                post(name, group="example-group", discovered=DISCOVERED) for name in names
            ]), fetched_at=NOW,
        )
        return self._apply(self.ransomlook, feed, minute)

    def apply_notices(self, names=("Example",), *, minute=3):
        records = [notice_item(name) for name in names]
        feed = parse_hibp_public_notices_response(json.dumps(records).encode(), fetched_at=NOW)
        return self._apply(self.notices, feed, minute)

    @staticmethod
    def _apply(repository, feed, minute):
        at = NOW + timedelta(minutes=minute)
        return repository.apply(feed, started_at=at.isoformat(),
                                finished_at=(at + timedelta(seconds=1)).isoformat(), item_limit=100)

    def populate(self):
        return self.apply_tc(), self.apply_rl(), self.apply_notices()

    def database_dump(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return tuple(connection.iterdump())

    def corrupt(self, query, parameters=()):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(query, parameters)
            connection.commit()

    def audit_reviews(self, *, compact=False):
        with SQLiteAssetRepository(self.path)._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return self.review_repository._audit(connection, compact=compact)

    def test_missing_database_is_not_created_and_empty_sources_are_explicit(self):
        missing = Path(self.temp.name) / "missing" / "new.db"
        with patch.object(SQLiteAssetRepository, "initialize", side_effect=AssertionError("No initialization")):
            with self.assertRaises(StorageError):
                SQLiteEventCandidateRepository(missing).read()
            snapshot = self.repository.read()
        self.assertFalse(missing.parent.exists())
        self.assertEqual(tuple(source.source_key for source in snapshot.sources), EVENT_SOURCE_KEYS)
        self.assertEqual(snapshot.legacy_reviews, ())
        for source in snapshot.sources:
            self.assertIsNone(source.latest_run)
            self.assertIsNone(source.successful_run)
            self.assertEqual(source.records, ())

    def test_source_namespace_keeps_identical_ids_separate_and_read_never_mutates(self):
        self.populate()
        before_bytes, before_dump = self.path.read_bytes(), self.database_dump()
        statements, connections = [], []
        original = self.repository._storage._connection

        @contextmanager
        def traced(*, readonly=False, **options):
            connections.append(readonly)
            with original(readonly=readonly, **options) as connection:
                connection.set_trace_callback(statements.append)
                yield connection

        with (
            patch.object(self.repository._storage, "_connection", traced),
            patch.object(SQLiteAssetRepository, "initialize", side_effect=AssertionError("No initialization")),
            patch("socket.create_connection", side_effect=AssertionError("No network")),
        ):
            snapshot = self.repository.read()
        tc, rl, hibp = snapshot.sources
        self.assertEqual(tc.records[0].id, rl.records[0].id)
        self.assertEqual((tc.source_key, rl.source_key, hibp.source_key), EVENT_SOURCE_KEYS)
        self.assertEqual(hibp.records[0].id, "Example")
        self.assertEqual(sum(len(source.records) for source in snapshot.sources), 3)
        self.assertEqual(connections, [True])
        self.assertEqual(sum(statement == "BEGIN" for statement in statements), 1)
        self.assertFalse(any(statement.lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP")) for statement in statements))
        self.assertEqual(self.database_dump(), before_dump)
        self.assertEqual(self.path.read_bytes(), before_bytes)

    def test_failed_attempt_retains_success_and_failed_only_has_no_records(self):
        successful = self.populate()
        repositories = (self.threatcluster, self.ransomlook, self.notices)
        failures = []
        for repository in repositories:
            failures.append(repository.record_failure(
                started_at=(NOW + timedelta(minutes=10)).isoformat(),
                finished_at=(NOW + timedelta(minutes=10, seconds=1)).isoformat(),
                error="Kaynak yanıtı alınamadı.",
            ))
        snapshot = self.repository.read()
        for source, success, failure in zip(snapshot.sources, successful, failures):
            self.assertEqual(source.latest_run, failure)
            self.assertEqual(source.successful_run, success.run)
            self.assertEqual(len(source.records), 1)
        other = Path(self.temp.name) / "failed-only.db"
        SQLiteAssetRepository(other).initialize()
        for kind in (SQLiteRansomwareClaimRepository, SQLiteRansomLookClaimRepository, SQLitePublicNoticeRepository):
            kind(other).record_failure(started_at=NOW.isoformat(), finished_at=NOW.isoformat(),
                                       error="Kaynak yanıtı alınamadı.")
        for source in SQLiteEventCandidateRepository(other).read().sources:
            self.assertEqual(source.latest_run.status, "failed")
            self.assertIsNone(source.successful_run)
            self.assertEqual(source.records, ())

    def test_removed_records_stay_out_and_unchanged_records_use_latest_success(self):
        self.apply_tc(("Keep", "Removed"))
        self.apply_rl(("Keep", "Removed"))
        self.apply_notices(("Keep", "Removed"))
        runs = (self.apply_tc(("Keep",), minute=4), self.apply_rl(("Keep",), minute=5),
                self.apply_notices(("Keep",), minute=6))
        for source, result in zip(self.repository.read().sources, runs):
            self.assertEqual(source.successful_run.id, result.run.id)
            self.assertEqual(len(source.records), 1)
            self.assertEqual(getattr(source.records[0], "victim", source.records[0].id), "Keep")
            self.assertEqual(result.run.unchanged_count, 1)
            self.assertEqual(result.run.removed_count, 1)

    def test_frozen_review_evidence_stays_old_while_current_source_can_change(self):
        self.populate()
        comparison = self.comparisons.compare().comparisons[0]
        decision = self.reviews.decide(comparison.id, decision="different",
                                      reason="Ayrı olaylar olarak değerlendirildi.")
        frozen = decision.details.evidence.comparison
        self.apply_tc(minute=5, website="changed.example")
        self.review_time += timedelta(minutes=1)
        self.reviews.decide(comparison.id, decision="uncertain", reason="Ek inceleme gerekiyor.")
        before = self.database_dump()
        snapshot = self.repository.read()
        self.assertEqual(len(snapshot.legacy_reviews), 1)
        review = snapshot.legacy_reviews[0]
        self.assertEqual(review.state.comparison_id, comparison.id)
        self.assertEqual((review.state.decision, review.state.event_count), ("uncertain", 2))
        self.assertEqual(review.threatcluster_state_sha256, ransomware_claim_state_sha256(frozen.threatcluster_claim))
        self.assertEqual(review.ransomlook_state_sha256, ransomlook_claim_state_sha256(frozen.ransomlook_claim))
        self.assertNotEqual(review.threatcluster_state_sha256,
                            ransomware_claim_state_sha256(snapshot.sources[0].records[0]))
        self.assertEqual(self.database_dump(), before)

    def test_source_changes_committed_between_readers_do_not_leak_into_snapshot(self):
        original_runs = self.populate()
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        written = []

        def interleave(connection):
            notices = read_public_notice_snapshot(connection)
            # These are real commits on other connections while the reader's
            # HIBP SELECT has already established its WAL snapshot.
            written.extend((self.apply_tc(("Replacement",), minute=10),
                            self.apply_rl(("Replacement",), minute=11),
                            self.apply_notices(("Replacement",), minute=12)))
            return notices

        with patch("xti.adapters.sqlite_event_candidates.read_public_notice_snapshot", side_effect=interleave):
            old = self.repository.read()
        self.assertEqual([source.successful_run.id for source in old.sources],
                         [result.run.id for result in original_runs])
        self.assertEqual(old.sources[0].records[0].victim, "Example Holding")
        self.assertEqual(old.sources[1].records[0].victim, "Example Holding")
        self.assertEqual(old.sources[2].records[0].id, "Example")
        current = self.repository.read()
        self.assertEqual([source.successful_run.id for source in current.sources],
                         [result.run.id for result in written])
        self.assertTrue(all(getattr(source.records[0], "victim", source.records[0].id) == "Replacement"
                            for source in current.sources))

    def test_bad_source_hash_or_historical_count_fails_closed(self):
        self.populate()
        for table in ("ransomware_claim_run_items", "ransomlook_claim_run_items", "public_notice_changes"):
            with self.subTest(table=table):
                with closing(sqlite3.connect(self.path)) as connection:
                    rows = connection.execute(f"SELECT rowid,state_sha256 FROM {table}").fetchall()
                self.corrupt(f"UPDATE {table} SET state_sha256=?", ("0" * 64,))
                with self.assertRaises(StorageError):
                    self.repository.read()
                for rowid, digest in rows:
                    self.corrupt(f"UPDATE {table} SET state_sha256=? WHERE rowid=?", (digest, rowid))
        self.corrupt("UPDATE ransomware_claim_runs SET claim_count=claim_count+1")
        with self.assertRaises(StorageError):
            self.repository.read()

    def test_corrupt_frozen_review_rejects_whole_report(self):
        self.populate()
        comparison = self.comparisons.compare().comparisons[0]
        self.reviews.decide(comparison.id, decision="possible_same", reason="Kaynak alanları aynı.")
        self.corrupt("UPDATE ransomware_source_review_events SET evidence_sha256=?", ("0" * 64,))
        with self.assertRaises(StorageError):
            self.repository.read()

    def test_total_record_limit_rejects_instead_of_truncating(self):
        self.populate()
        with patch("xti.adapters.sqlite_event_candidates.MAX_EVENT_RECORDS", 2):
            with self.assertRaisesRegex(StorageError, "kayıt sınırını"):
                self.repository.read()

    def test_compact_audit_retains_only_latest_snapshots_without_review_history(self):
        names = ("Example Holding", "Second Holding", "Third Holding")
        for index in range(20):
            self.apply_tc(names, minute=index * 2 + 1)
            self.apply_rl(names, minute=index * 2 + 2)
        before = self.database_dump()
        compact, full = self.audit_reviews(compact=True), self.audit_reviews()
        for index in (0, 1, 4, 5, 6):
            self.assertEqual(compact[index], full[index])
        for run_index, snapshot_index in ((0, 2), (1, 3)):
            latest = full[run_index][-1].id
            self.assertEqual(set(compact[snapshot_index]), {latest})
            self.assertEqual(compact[snapshot_index][latest], full[snapshot_index][latest])
            self.assertEqual(sum(map(len, compact[snapshot_index].values())), 3)
            self.assertEqual(sum(map(len, full[snapshot_index].values())), 60)
        self.assertEqual(self.database_dump(), before)

    def test_compact_audit_keeps_frozen_claim_only_and_latest_complete_catalog(self):
        names = ("Example Holding", "Second Holding", "Third Holding")
        first_tc, first_rl = self.apply_tc(names), self.apply_rl(names)
        comparison = next(value for value in self.comparisons.compare().comparisons
                          if value.threatcluster_claim.victim == "Example Holding")
        saved = self.reviews.decide(comparison.id, decision="uncertain", reason="Ek kanıt gerekli.")
        middle_tc, middle_rl = self.apply_tc(names, minute=3), self.apply_rl(names, minute=4)
        latest_tc = self.apply_tc(names, minute=5, website="changed.example")
        latest_rl = self.apply_rl(names, minute=6)
        compact, full = self.audit_reviews(compact=True), self.audit_reviews()
        for index in (0, 1, 4, 5, 6):
            self.assertEqual(compact[index], full[index])
        for snapshot_index, first, middle, latest, claim_id in (
            (2, first_tc, middle_tc, latest_tc, comparison.threatcluster_claim.id),
            (3, first_rl, middle_rl, latest_rl, comparison.ransomlook_claim.id),
        ):
            retained = compact[snapshot_index]
            self.assertEqual(set(retained), {first.run.id, latest.run.id})
            self.assertEqual(set(retained[first.run.id]), {claim_id})
            self.assertEqual(retained[first.run.id][claim_id], full[snapshot_index][first.run.id][claim_id])
            self.assertEqual(len(retained[latest.run.id]), 3)
            self.assertIn(middle.run.id, full[snapshot_index])
        self.assertEqual(compact[4][comparison.id], replace(
            saved.details.evidence,
            comparison=replace(saved.details.evidence.comparison, current_review=None),
        ))
        self.assertEqual(self.reviews.show(comparison.id), saved.details)

    def test_compact_audit_still_rejects_corrupt_unselected_historical_evidence(self):
        first = self.apply_tc(("Keep", "Removed"))
        self.apply_rl(("Keep",))
        self.apply_tc(("Keep",), minute=3)
        current = self.apply_tc(("Keep",), minute=4)
        before = self.audit_reviews(compact=True)
        self.assertEqual(set(before[2]), {current.run.id})
        removed = next(item for item in first.items if item.claim.victim == "Removed")
        self.corrupt("UPDATE ransomware_claim_run_items SET state_sha256=? WHERE id=?",
                     ("0" * 64, removed.id))
        with self.assertRaises(StorageError):
            self.repository.read()

    def test_selected_snapshot_replay_checks_unselected_run_count(self):
        first = self.apply_tc(("Keep", "Removed"))
        latest = self.apply_tc(("Keep",), minute=3)
        with SQLiteAssetRepository(self.path)._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            runs, items = self.threatcluster._audit(connection)
        runs = tuple(replace(run, claim_count=run.claim_count + 1)
                     if run.id == first.run.id else run for run in runs)
        with self.assertRaisesRegex(StorageError, "snapshot"):
            self.review_repository._snapshots(runs, items, {latest.run.id: None})

    def test_compact_review_reference_validation_and_cap_precede_snapshot_copies(self):
        self.populate()
        comparison = self.comparisons.compare().comparisons[0]
        self.reviews.decide(comparison.id, decision="uncertain", reason="Ek kanıt gerekli.")
        with (
            patch("xti.adapters.sqlite_ransomware_source_reviews._MAX_EVENTS", 0),
            patch.object(SQLiteRansomwareSourceReviewRepository, "_snapshots",
                         side_effect=AssertionError("No snapshots over cap")),
        ):
            with self.assertRaisesRegex(StorageError, "güvenli sınırı"):
                self.audit_reviews(compact=True)
        for field in ("threatcluster_run_id", "ransomlook_run_id",
                      "threatcluster_claim_id", "ransomlook_claim_id"):
            with self.subTest(field=field):
                with closing(sqlite3.connect(self.path)) as connection:
                    original = connection.execute(f"SELECT {field} FROM ransomware_source_review_events").fetchone()[0]
                self.corrupt(f"UPDATE ransomware_source_review_events SET {field}=?", ("invalid",))
                with patch.object(SQLiteRansomwareSourceReviewRepository, "_snapshots",
                                  side_effect=AssertionError("No snapshots with malformed selection")):
                    with self.assertRaisesRegex(StorageError, "karar geçmişi bozuk"):
                        self.audit_reviews(compact=True)
                self.corrupt(f"UPDATE ransomware_source_review_events SET {field}=?", (original,))


if __name__ == "__main__":
    unittest.main()

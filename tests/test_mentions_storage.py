"""Frozen metered-search evidence, stable source identities and corruption detection."""

from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_mentions import SQLiteMentionRepository, read_mentions_catalog
from xti.domain.assets import ValidationError
from xti.domain.mentions import (
    MentionHit, MentionRequest, MentionResponse, MentionTarget, build_query, company_target,
    match_hit, request_key, run_from_json, run_json, validate_request, validate_response,
)


def request(*, name="Example Company", domains=("example.com",), topic="general", max_results=5):
    return MentionRequest(company_target(name, domains), topic, max_results)


def hit(*, url="https://publisher.example/article", title="Example Company news", summary="About example.com.", score=0.7):
    return MentionHit(url, title, summary, "2026-11-15", score)


class MentionStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "data" / "xti.db"
        self.storage = SQLiteAssetRepository(self.path)
        self.storage.initialize()
        self.repo = SQLiteMentionRepository(self.path)
        self.clock = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)

    def tick(self):
        self.clock += timedelta(seconds=1)
        return self.clock.isoformat()

    def apply(self, *hits, scope=None, credits=1):
        scope = scope or request()
        response = MentionResponse(build_query(scope.target), "provider-request", tuple(hits), credits)
        at = self.tick()
        return self.repo.apply(scope, response, started_at=at, finished_at=at)

    def failure(self, *, scope=None):
        at = self.tick()
        return self.repo.record_failure(scope or request(), started_at=at, finished_at=at, error="Source unavailable")

    def rows(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute("SELECT rowid,* FROM mentions_runs ORDER BY sequence").fetchall()

    def test_repeated_results_retain_first_seen_and_do_not_duplicate_or_count_rank_changes(self):
        first = self.apply(hit())
        second = self.apply(hit(score=0.9))
        catalog = self.repo.catalog()
        self.assertEqual(len(catalog.records), 1)
        record = catalog.records[0]
        self.assertEqual((second.added_count, second.updated_count, second.unchanged_count), (0, 0, 1))
        self.assertEqual(record.first_run_id, first.id)
        self.assertEqual(record.last_seen_run_id, second.id)
        self.assertEqual(record.last_change_run_id, first.id)
        self.assertEqual(record.hit.score, 0.9)
        self.assertEqual(self.repo.run_show(first.id).response.hits[0].score, 0.7)

    def test_updated_content_retains_frozen_runs_after_subsequent_changes(self):
        first = self.apply(hit())
        changed = self.apply(hit(title="Example Company correction"))
        self.apply(hit(title="Example Company later update"))
        self.assertEqual((changed.added_count, changed.updated_count), (0, 1))
        self.assertEqual(self.repo.run_show(first.id), first)
        self.assertEqual(self.repo.run_show(changed.id), changed)

    def test_empty_success_and_failed_query_are_distinct_and_preserve_evidence(self):
        first = self.apply(hit())
        failed = self.failure()
        empty = self.apply()
        catalog = self.repo.catalog()
        self.assertEqual(len(catalog.records), 1)
        self.assertEqual(catalog.records[0].last_seen_run_id, first.id)
        self.assertEqual(failed.status, "failed")
        self.assertIsNone(failed.response)
        self.assertEqual(empty.status, "complete")
        self.assertEqual(empty.response.hits, ())
        self.assertEqual(self.repo.run_show(failed.id), failed)

    def test_removed_results_remain_available_without_false_resolution(self):
        original = hit()
        second = hit(url="https://publisher.example/second")
        self.apply(original, second)
        run = self.apply(second)
        self.assertEqual((run.result_count, run.unchanged_count), (1, 1))
        self.assertEqual(len(self.repo.catalog().records), 2)

    def test_company_topic_and_limit_scope_changes_do_not_reuse_old_baseline(self):
        scopes = (request(), request(topic="news"), request(max_results=10), request(name="Another Company"))
        for scope in scopes:
            run = self.apply(hit(), scope=scope)
            self.assertEqual(run.added_count, 1)
        catalog = self.repo.catalog()
        self.assertEqual(len({record.id for record in catalog.records}), 4)
        self.assertEqual(len({record.request_key for record in catalog.records}), 4)

    def test_same_name_organization_and_supplier_keep_explicit_identity(self):
        identifier = "11111111-1111-4111-8111-111111111111"
        for kind in ("organization", "supplier"):
            target = MentionTarget(kind, identifier, "Example Company", ("example.com",))
            self.apply(hit(), scope=MentionRequest(target, "general", 5))
        self.assertEqual({record.request.target.kind for record in self.repo.catalog().records}, {"organization", "supplier"})

    def test_duplicate_link_or_wrong_query_rejects_atomically(self):
        self.apply(hit())
        before = self.rows()
        scope = request()
        responses = (
            MentionResponse("wrong query", None, (hit(),), 1),
            MentionResponse(build_query(scope.target), None, (hit(), hit(title="conflicting")), 1),
        )
        for response in responses:
            at = self.tick()
            with self.assertRaises(ValidationError):
                self.repo.apply(scope, response, started_at=at, finished_at=at)
            self.assertEqual(self.rows(), before)

    def test_provider_metadata_does_not_leak_into_substantive_content_identity(self):
        first = self.apply(hit(), credits=None)
        second = self.apply(hit(), credits=1)
        self.assertEqual(second.unchanged_count, 1)
        self.assertIsNone(self.repo.run_show(first.id).response.credits)

    def test_tampered_payload_metadata_or_chain_is_rejected_without_mutation(self):
        for column, value in (("payload_json", "{}"), ("request_key", "a" * 64), ("chain_sha256", "b" * 64)):
            with self.subTest(column=column):
                self.path.unlink(missing_ok=True)
                self.storage.initialize()
                self.apply(hit())
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    connection.execute(f"UPDATE mentions_runs SET {column}=?", (value,))
                before = self.path.read_bytes()
                with self.assertRaises(StorageError):
                    self.repo.catalog()
                with self.assertRaises(StorageError):
                    self.failure()
                self.assertEqual(self.path.read_bytes(), before)

    def test_missing_middle_run_is_detected(self):
        self.apply(hit())
        middle = self.apply(hit())
        self.apply(hit())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("DELETE FROM mentions_runs WHERE id=?", (middle.id,))
        with self.assertRaises(StorageError):
            self.repo.catalog()

    def test_deleted_last_or_all_runs_are_detected_by_allocated_sequence(self):
        for delete_all in (False, True):
            with self.subTest(delete_all=delete_all):
                self.path.unlink(missing_ok=True)
                self.storage.initialize()
                self.apply(hit())
                final = self.apply(hit(title="Updated Example Company"))
                with closing(sqlite3.connect(self.path)) as connection, connection:
                    if delete_all:
                        connection.execute("DELETE FROM mentions_runs")
                    else:
                        connection.execute("DELETE FROM mentions_runs WHERE id=?", (final.id,))
                before = self.path.read_bytes()
                with self.assertRaises(StorageError):
                    self.repo.catalog()
                with self.assertRaises(StorageError):
                    self.failure()
                self.assertEqual(self.path.read_bytes(), before)

    def test_count_capacity_rejects_new_write_but_keeps_reads_and_existing_rows(self):
        self.apply(hit())
        before = self.rows()
        with patch("xti.adapters.sqlite_mentions.MAX_MENTION_RUNS", 1):
            with self.assertRaises(StorageError):
                self.repo.validate()
            with self.assertRaises(StorageError):
                self.failure()
            self.assertEqual(len(self.repo.catalog().runs), 1)
        self.assertEqual(self.rows(), before)

    def test_record_capacity_and_time_failure_roll_back(self):
        self.apply(hit())
        before = self.rows()
        with patch("xti.adapters.sqlite_mentions.MAX_MENTION_RECORDS", 1):
            with self.assertRaises(StorageError):
                self.repo.validate(max_results=1)
            with self.assertRaises(ValidationError):
                self.apply(hit(url="https://publisher.example/second"))
        old = "2026-01-01T00:00:00+00:00"
        with self.assertRaises(ValidationError):
            self.repo.record_failure(request(), error="Source unavailable", started_at=old, finished_at=old)
        self.assertEqual(self.rows(), before)

    def test_read_only_catalog_does_not_modify_files_or_create_missing_database(self):
        self.apply(hit())
        before = self.path.read_bytes()
        with patch("socket.socket.connect", side_effect=AssertionError("No network")):
            self.repo.catalog()
            self.repo.run_show(self.repo.catalog().runs[0].id)
            self.assertEqual(self.path.read_bytes(), before)
            missing = self.path.parent / "missing.db"
            with self.assertRaises(StorageError):
                SQLiteMentionRepository(missing).catalog()
            self.assertFalse(missing.exists())

    def test_canonical_snapshot_round_trip_rejects_unknown_fields_and_duplicate_keys(self):
        run = self.apply(hit())
        payload = run_json(run)
        self.assertEqual(run_from_json(payload), run)
        for invalid in (payload.replace('"policy":', '"extra":1,"policy":', 1),
                        payload.replace('"policy":', '"policy":"wrong","policy":', 1)):
            with self.assertRaises(ValidationError):
                run_from_json(invalid)

    def test_match_evidence_does_not_accept_spoofed_domain_suffix_or_embedded_company_name(self):
        target = company_target("Acme", ("example.com",))
        spoof = hit(url="https://publisher.example/page", title="AcmeOther", summary="badexample.com example.com.evil.test")
        self.assertEqual(match_hit(target, spoof), ((), ()))
        valid = replace(spoof, title="Acme news", summary="See sub.example.com and example.com.")
        self.assertEqual(match_hit(target, valid), (("Acme", "example.com"), ("title", "summary")))

    def test_nonfinite_score_control_text_and_bad_search_limit_rejected(self):
        scope = request()
        for invalid in (replace(hit(), score=float("nan")), replace(hit(), title="bad\x1b[31m"),
                        replace(hit(), url="https://user:secret@example.com/page")):
            with self.assertRaises(ValidationError):
                validate_response(MentionResponse(build_query(scope.target), None, (invalid,), 1), scope)
        for count in (0, 21, True):
            with self.assertRaises(ValidationError):
                validate_request(replace(scope, max_results=count))

    def test_queries_quote_terms_and_query_identity_includes_target_snapshot(self):
        target = company_target('Example "OR" Other', ("example.com",))
        self.assertEqual(build_query(target), '"Example OR Other" OR "example.com"')
        original = request()
        self.assertNotEqual(request_key(original), request_key(replace(original, topic="news")))
        with self.assertRaises(ValidationError):
            build_query(company_target('""'))


if __name__ == "__main__":
    unittest.main()

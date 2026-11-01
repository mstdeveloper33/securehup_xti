"""Read unchanged 0.4 query blobs and append generic multi-source history safely."""

from contextlib import closing
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_jobs import SQLiteJobRepository
from xti.domain.discovery import QueryResult, ScanResult
from xti.domain.findings import ImportSummary


class SourceHistoryCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "xti.db"
        self.assets = SQLiteAssetRepository(self.path)
        self.assets.initialize()
        self.repo = SQLiteJobRepository(self.path)
        self.job_id = "00000000-0000-4000-8000-000000000001"
        self.attempt_id = "00000000-0000-4000-8000-000000000002"
        self.started = "2026-10-28T12:00:00+00:00"
        self.finished = "2026-10-28T12:00:10+00:00"
        self.legacy_query = {
            "pattern": "%example%", "source_url": "https://crt.sh/?q=%25example%25&output=json",
            "status": "partial", "certificate_count": 1, "skipped_names": 1,
            "error": None, "warnings": [],
        }
        self.legacy_result = {
            "targets": ["example.com"], "started_at": self.started,
            "finished_at": self.finished, "status": "partial",
            "queries": [self.legacy_query],
            "summary": {"total_records": 1, "observations_created": 1,
                        "observations_existing": 0, "findings_created": 0, "findings_existing": 0},
            "candidate_domains": [],
        }
        # Insert the exact old JSON shape rather than generating it with new models.
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO scan_jobs (id, targets, typos, provider, rule_version, status, "
                "created_at, updated_at, attempt_count) VALUES (?, ?, 0, 'crt.sh', 'rules-v1', "
                "'partial', ?, ?, 1)",
                (self.job_id, '["example.com"]', self.started, self.finished),
            )
            connection.execute(
                "INSERT INTO scan_attempts (id, job_id, number, status, started_at, finished_at, "
                "progress, error, queries, result) VALUES (?, ?, 1, 'partial', ?, ?, ?, NULL, ?, ?)",
                (self.attempt_id, self.job_id, self.started, self.finished, "Eski kaynak yanıtı.",
                 json.dumps([self.legacy_query]), json.dumps(self.legacy_result)),
            )

    def raw_history(self, attempt_id=None):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute(
                "SELECT queries, result FROM scan_attempts WHERE id = ?",
                (attempt_id or self.attempt_id,),
            ).fetchone()

    def replace_query(self, value):
        report = deepcopy(self.legacy_result)
        report["queries"] = [value]
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "UPDATE scan_attempts SET queries = ?, result = ? WHERE id = ?",
                (json.dumps([value]), json.dumps(report), self.attempt_id),
            )

    def test_legacy_count_is_read_generically_without_rewriting_database(self):
        before = self.path.read_bytes()
        raw = self.raw_history()
        details = self.repo.get(self.job_id)
        self.assertEqual(self.repo.list()[0], details.job)
        self.assertEqual(self.repo.latest_by_provider(), [details])
        attempt = details.attempts[0]
        self.assertEqual(attempt.queries[0].record_count, 1)
        self.assertEqual(attempt.queries[0].coverage_notes, ())
        self.assertEqual(attempt.result.queries, attempt.queries)
        self.assertEqual(self.raw_history(), raw)
        self.assertEqual(self.path.read_bytes(), before)

    def test_retry_keeps_legacy_blob_and_appends_new_count_and_scope_format(self):
        old_raw = self.raw_history()
        old_attempt = self.repo.get(self.job_id).attempts[0]
        second = self.repo.start(self.job_id)
        query = QueryResult(
            "example%", "https://crt.sh/?q=example%25&output=json", "complete", 3, 0, None, (),
            ("Bu kaynak geçmiş sertifika kayıtlarını içerir.",),
        )
        self.repo.progress(second.id, "Yeni sorgu tamamlandı.", query)
        report = ScanResult(
            ("example.com",), second.started_at, self.finished, "complete", (query,),
            ImportSummary(3, 1, 2, 0, 0), (),
        )
        self.repo.finish(second.id, "complete", result=report)
        reopened = SQLiteJobRepository(self.path)
        details = reopened.get(self.job_id)
        self.assertEqual(details.attempts[0], old_attempt)
        self.assertEqual(details.attempts[1].result, report)
        self.assertEqual(self.raw_history(), old_raw)
        new_queries, new_result = self.raw_history(second.id)
        for value in (json.loads(new_queries)[0], json.loads(new_result)["queries"][0]):
            self.assertEqual(value["record_count"], 3)
            self.assertNotIn("certificate_count", value)
            self.assertEqual(value["coverage_notes"], list(query.coverage_notes))
        backup = Path(self.temp.name) / "mixed-history.db"
        restored = Path(self.temp.name) / "restored" / "xti.db"
        self.assets.backup(backup)
        SQLiteAssetRepository.restore(backup, restored)
        self.assertEqual(SQLiteJobRepository(restored).get(self.job_id), details)

    def test_generic_shape_without_optional_scope_notes_is_supported(self):
        query = deepcopy(self.legacy_query)
        query["record_count"] = query.pop("certificate_count")
        self.replace_query(query)
        before = self.path.read_bytes()
        result = self.repo.get(self.job_id).attempts[0]
        self.assertEqual(result.queries[0].record_count, 1)
        self.assertEqual(result.queries[0].coverage_notes, ())
        self.assertEqual(self.path.read_bytes(), before)

    def test_ambiguous_unknown_or_invalid_count_shapes_are_rejected(self):
        malformed = []
        for bad_count in (True, -1, "1", None, [], {}):
            for key in ("certificate_count", "record_count"):
                value = deepcopy(self.legacy_query)
                value.pop("certificate_count")
                value[key] = bad_count
                malformed.append(value)
        malformed.extend([
            {**self.legacy_query, "record_count": 1},
            {**self.legacy_query, "coverage_notes": []},
            {**self.legacy_query, "unexpected": "data"},
            {key: value for key, value in self.legacy_query.items() if key != "certificate_count"},
        ])
        for query in malformed:
            with self.subTest(query=query):
                self.replace_query(query)
                before = self.path.read_bytes()
                with self.assertRaises(StorageError):
                    self.repo.get(self.job_id)
                self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_scope_notes_are_rejected_and_valid_notes_are_preserved(self):
        query = asdict(QueryResult(
            "example%", "https://crt.sh/?q=example%25&output=json", "partial", 1, 1, None, (),
        ))
        for notes in (None, "not a list", [42], [True], ["x" * 4097]):
            with self.subTest(notes=notes):
                self.replace_query({**query, "coverage_notes": notes})
                with self.assertRaises(StorageError):
                    self.repo.get(self.job_id)
        notes = ["Sonuçlar kaynak kapsamıyla sınırlıdır."]
        self.replace_query({**query, "coverage_notes": notes})
        attempt = self.repo.get(self.job_id).attempts[0]
        self.assertEqual(attempt.queries[0].coverage_notes, tuple(notes))
        self.assertEqual(attempt.result.queries, attempt.queries)


if __name__ == "__main__":
    unittest.main()

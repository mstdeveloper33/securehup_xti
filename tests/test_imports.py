"""Bounded local-file import validates every record before persisting anything."""

from datetime import datetime, timezone
import json
import unittest

from xti.adapters.domain_file import read_domain_file
from xti.adapters.sqlite import StorageError
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.domain.findings import MatchCandidate
from tests.test_findings_cli import CLIHarness


class ImportValidationTests(CLIHarness, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.initialize("example.com")

    def test_text_comments_and_blank_lines_preserve_physical_source_line(self):
        source = self.write_source("\n# A saved domain list\n   \nexample-support.net\n\n")
        summary = self.import_source(source)
        self.assertEqual(summary["total_records"], 1)
        self.assertEqual(summary["observations_created"], 1)
        details = self.details(self.findings()[0]["id"])
        self.assertEqual(details["observations"][0]["source_line"], 4)

    def test_jsonl_accepts_timezone_aware_observation_time(self):
        timestamp = "2026-10-28T10:30:00+03:00"
        source = self.write_source(
            json.dumps({"domain": "EXAMPLE-SUPPORT.NET.", "observed_at": timestamp}) + "\n"
            + json.dumps({"domain": "exampel.com", "observed_at": "2026-10-28T07:30:00Z"}) + "\n",
            "observations.jsonl",
        )
        summary = self.import_source(source)
        self.assertEqual(summary["total_records"], 2)
        self.assertEqual(summary["observations_created"], 2)
        self.assertEqual(summary["findings_created"], 2)
        expected = datetime(2026, 10, 28, 7, 30, tzinfo=timezone.utc)
        for finding in self.findings():
            observation = self.details(finding["id"])["observations"][0]
            actual = datetime.fromisoformat(observation["observed_at"].replace("Z", "+00:00"))
            self.assertEqual(actual, expected)

    def test_import_without_watched_asset_is_rejected_without_writes(self):
        empty_data = self.root / "empty"
        self.success_json(self.run_cli("init", data_dir=empty_data))
        source = self.write_source("example-support.net\n")
        database = empty_data / "xti.db"
        before = database.read_bytes()
        self.error_json(self.run_cli("import", "domains", str(source), data_dir=empty_data), 2)
        self.assertEqual(database.read_bytes(), before)
        self.assertEqual(self.findings(data_dir=empty_data), [])

    def test_bad_later_domain_rolls_back_the_entire_import(self):
        self.import_source(self.write_source("exampel.com\n", "existing.txt"))
        before = self.database_dump()
        for invalid in ("https://example.com", "example.net:443", "bad\x1b[31m.com", "örnek.com"):
            with self.subTest(invalid=invalid):
                source = self.write_source("example-support.net\n" + invalid + "\n")
                self.error_json(self.run_cli("import", "domains", str(source)), 2)
                self.assertEqual(self.database_dump(), before)

    def test_storage_failure_after_partial_import_rolls_back_observations_and_findings(self):
        self.import_source(self.write_source("exampel.com\n", "existing.txt"))
        asset = self.success_json(self.run_cli("assets", "list"))["assets"][0]
        document = read_domain_file(self.write_source("example-support.net\nexample-login.net\n"))
        candidates = [
            MatchCandidate(
                asset["id"], asset["value"], "example-support.net", "test-rules-v1", ("Test eşleşmesi.",),
            ),
            MatchCandidate(
                "00000000-0000-4000-8000-000000000000", "missing.example",
                "example-login.net", "test-rules-v1", ("Test eşleşmesi.",),
            ),
        ]
        before = self.database_dump()
        with self.assertRaises(StorageError):
            SQLiteFindingRepository(self.data / "xti.db").save_import(document, candidates)
        self.assertEqual(self.database_dump(), before)

    def test_malformed_json_records_fail_atomically(self):
        valid = json.dumps({"domain": "example-support.net"}) + "\n"
        invalid_records = [
            "{",
            "[]",
            '"example-support.net"',
            "null",
            json.dumps({"observed_at": "2026-10-28T07:30:00Z"}),
            json.dumps({"domain": 12}),
            json.dumps({"domain": "exampel.com", "unexpected": True}),
            json.dumps({"domain": "exampel.com", "observed_at": "not-a-date"}),
            json.dumps({"domain": "exampel.com", "observed_at": "2026-10-28T07:30:00"}),
            json.dumps({"domain": "exampel.com", "observed_at": "2026-02-30T07:30:00Z"}),
            json.dumps({"domain": "exampel.com", "observed_at": "0001-01-01T00:00:00+01:00"}),
            json.dumps({"domain": "exampel.com", "observed_at": "9999-12-31T23:59:59-01:00"}),
            json.dumps({"domain": "exampel.com", "observed_at": 12}),
        ]
        before = self.database_dump()
        for invalid in invalid_records:
            with self.subTest(invalid=invalid):
                source = self.write_source(valid + invalid + "\n", "bad.jsonl")
                self.error_json(self.run_cli("import", "domains", str(source)), 2)
                self.assertEqual(self.database_dump(), before)

    def test_oversized_file_and_too_many_records_are_rejected_before_writes(self):
        before = self.database_dump()
        source = self.root / "large.txt"
        source.write_bytes(b"#" + b"x" * (2 * 1024 * 1024))
        self.error_json(self.run_cli("import", "domains", str(source)), 2)
        self.assertEqual(self.database_dump(), before)
        source.write_text("example-support.net\n" * 5001, encoding="utf-8")
        self.error_json(self.run_cli("import", "domains", str(source)), 2)
        self.assertEqual(self.database_dump(), before)

    def test_invalid_encoding_and_unsupported_format_do_not_modify_database(self):
        before = self.database_dump()
        invalid = self.root / "invalid.txt"
        invalid.write_bytes(b"example-support.net\n\xff\xfe\n")
        self.error_json(self.run_cli("import", "domains", str(invalid)), 2)
        unsupported = self.write_source("example-support.net\n", "domains.csv")
        self.error_json(self.run_cli("import", "domains", str(unsupported)), 2)
        self.assertEqual(self.database_dump(), before)

    def test_missing_file_reports_filesystem_error_without_mutation(self):
        before = self.database_dump()
        source = self.root / "missing.txt"
        self.error_json(self.run_cli("import", "domains", str(source)), 1)
        self.assertFalse(source.exists())
        self.assertEqual(self.database_dump(), before)


if __name__ == "__main__":
    unittest.main()

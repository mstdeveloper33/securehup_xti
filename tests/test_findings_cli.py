"""Exercise offline finding evidence and review history across CLI processes."""

from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite_findings import SQLiteFindingRepository


class CLIHarness:
    """Shared public-command helpers; every test uses disposable storage."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.project = Path(__file__).resolve().parents[1]

    def run_cli(self, *arguments, data_dir=None, as_json=True):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(self.project / "src")
        command = [sys.executable, "-m", "xti", "--data-dir", str(data_dir or self.data)]
        if as_json:
            command.append("--json")
        return subprocess.run(
            [*command, *arguments],
            text=True, capture_output=True, check=False, timeout=20,
            env=environment, cwd=self.project,
        )

    def success_json(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        self.assertIs(payload["ok"], True)
        return payload["data"]

    def error_json(self, result, expected_code):
        self.assertEqual(result.returncode, expected_code, result.stderr)
        self.assertEqual(result.stdout, "")
        payload = json.loads(result.stderr)
        self.assertIs(payload["ok"], False)
        self.assertTrue(payload["error"]["code"])
        self.assertTrue(payload["error"]["message"])
        return payload["error"]

    def initialize(self, *domains):
        self.success_json(self.run_cli("init"))
        for domain in domains:
            self.success_json(self.run_cli("assets", "add", domain))

    def write_source(self, text, name="domains.txt"):
        source = self.root / name
        source.write_text(text, encoding="utf-8")
        return source

    def import_source(self, source):
        return self.success_json(self.run_cli("import", "domains", str(source)))

    def findings(self, *arguments, data_dir=None):
        return self.success_json(
            self.run_cli("findings", "list", *arguments, data_dir=data_dir)
        )["findings"]

    def details(self, finding_id, data_dir=None):
        return self.success_json(
            self.run_cli("findings", "show", finding_id, data_dir=data_dir)
        )

    def database_dump(self):
        with closing(sqlite3.connect(self.data / "xti.db")) as connection:
            return tuple(connection.iterdump())


class FindingsCLITests(CLIHarness, unittest.TestCase):
    def test_import_explains_candidates_and_excludes_unrelated_or_watched_domains(self):
        self.initialize("example.com")
        source = self.write_source(
            "example-support.net\nexampel.com\nexample.com.attacker.net\n"
            "unrelated.org\nexample.com\nlogin.example.com\n"
        )
        summary = self.import_source(source)
        self.assertEqual(summary["total_records"], 6)
        self.assertEqual(summary["observations_created"], 6)
        self.assertEqual(summary["observations_existing"], 0)
        self.assertEqual(summary["findings_created"], 3)
        self.assertEqual(summary["findings_existing"], 0)
        findings = self.findings()
        self.assertEqual(
            {finding["domain"] for finding in findings},
            {"example-support.net", "exampel.com", "example.com.attacker.net"},
        )
        for finding in findings:
            with self.subTest(domain=finding["domain"]):
                self.assertEqual(finding["status"], "new")
                self.assertEqual(finding["asset_value"], "example.com")
                self.assertTrue(finding["rule_version"])
                self.assertTrue(finding["reasons"])
                self.assertTrue(all(isinstance(reason, str) and reason for reason in finding["reasons"]))
                details = self.details(finding["id"])
                self.assertEqual(details["finding"], finding)
                self.assertEqual(len(details["observations"]), 1)
                self.assertEqual(details["reviews"], [])

    def test_repeat_and_renamed_source_preserve_observation_and_finding_identity(self):
        self.initialize("example.com")
        source = self.write_source("# Saved input\n  EXAMPLE-SUPPORT.NET.  \n")
        self.import_source(source)
        finding = self.findings()[0]
        first_details = self.details(finding["id"])
        observation = first_details["observations"][0]
        self.assertEqual(observation["domain"], "example-support.net")
        self.assertEqual(observation["source_line"], 2)
        self.assertEqual(len(observation["source_sha256"]), 64)
        self.assertIsNone(observation["observed_at"])
        self.assertTrue(observation["ingested_at"])

        for current_source in (source, source.with_name("renamed.txt")):
            with self.subTest(source=current_source.name):
                if current_source != source:
                    source.rename(current_source)
                repeated = self.import_source(current_source)
                self.assertEqual(repeated["total_records"], 1)
                self.assertEqual(repeated["observations_created"], 0)
                self.assertEqual(repeated["observations_existing"], 1)
                self.assertEqual(repeated["findings_created"], 0)
                self.assertEqual(repeated["findings_existing"], 1)
                self.assertEqual(self.details(finding["id"]), first_details)

    def test_new_evidence_does_not_reset_a_reviewed_finding(self):
        self.initialize("example.com")
        self.import_source(self.write_source("example-support.net\n"))
        finding_id = self.findings()[0]["id"]
        reason = "Kendi test alanım; inceleme tamamlandı."
        reviewed = self.success_json(self.run_cli(
            "findings", "review", finding_id,
            "--decision", "dismissed", "--reason", reason,
        ))["finding"]
        source = self.write_source(
            json.dumps({"domain": "example-support.net", "observed_at": "2026-10-28T10:30:00+03:00"}) + "\n",
            "second-source.jsonl",
        )
        summary = self.import_source(source)
        self.assertEqual(summary["observations_created"], 1)
        self.assertEqual(summary["findings_created"], 0)
        self.assertEqual(summary["findings_existing"], 1)
        details = self.details(finding_id)
        self.assertEqual(details["finding"]["status"], "dismissed")
        self.assertEqual(details["finding"]["created_at"], reviewed["created_at"])
        self.assertEqual(len(details["observations"]), 2)
        self.assertEqual(len({item["source_sha256"] for item in details["observations"]}), 2)
        self.assertEqual(len(details["reviews"]), 1)
        self.assertEqual(details["reviews"][0]["reason"], reason)

    def test_reimport_after_adding_watch_can_match_existing_observation(self):
        self.initialize("unrelated.org")
        source = self.write_source("exampel.com\n")
        first = self.import_source(source)
        self.assertEqual(first["observations_created"], 1)
        self.assertEqual(first["findings_created"], 0)
        self.success_json(self.run_cli("assets", "add", "example.com"))
        repeated = self.import_source(source)
        self.assertEqual(repeated["observations_created"], 0)
        self.assertEqual(repeated["observations_existing"], 1)
        self.assertEqual(repeated["findings_created"], 1)
        details = self.details(self.findings()[0]["id"])
        self.assertEqual(details["finding"]["asset_value"], "example.com")
        self.assertEqual(len(details["observations"]), 1)

    def test_all_watched_roots_are_excluded_from_candidates(self):
        self.initialize("example.com", "example.net")
        summary = self.import_source(self.write_source("login.example.net\nexample.com\n"))
        self.assertEqual(summary["observations_created"], 2)
        self.assertEqual(summary["findings_created"], 0)
        self.assertEqual(self.findings(), [])

    def test_review_history_filters_and_backup_restore_preserve_complete_details(self):
        self.initialize("example.com")
        self.import_source(self.write_source("example-support.net\n"))
        finding_id = self.findings()[0]["id"]
        decisions = [
            ("suspicious", "Benzer ad; daha ayrıntılı inceleyeceğim."),
            ("uncertain", "Karar için ek bilgi gerekli."),
        ]
        for decision, reason in decisions:
            reviewed = self.success_json(self.run_cli(
                "findings", "review", finding_id,
                "--decision", decision, "--reason", reason,
            ))
            self.assertEqual(reviewed["finding"]["status"], decision)
        details = self.details(finding_id)
        self.assertEqual(
            [(item["decision"], item["reason"]) for item in details["reviews"]], decisions,
        )
        self.assertEqual(len({item["id"] for item in details["reviews"]}), 2)
        self.assertEqual(self.findings("--status", "uncertain"), [details["finding"]])
        self.assertEqual(self.findings("--status", "new"), [])
        self.assertEqual(self.findings("--status", "suspicious"), [])

        backup = self.root / "with-findings.db"
        self.success_json(self.run_cli("backup", "--output", str(backup)))
        restored_data = self.root / "restored"
        self.success_json(self.run_cli("restore", str(backup), data_dir=restored_data))
        self.assertEqual(self.details(finding_id, data_dir=restored_data), details)
        self.assertEqual(self.findings(data_dir=restored_data), [details["finding"]])
        self.assertEqual(self.details(finding_id), details)

    def test_invalid_review_or_missing_finding_leaves_existing_records_unchanged(self):
        self.initialize("example.com")
        self.import_source(self.write_source("example-support.net\n"))
        finding_id = self.findings()[0]["id"]
        missing_id = "00000000-0000-4000-8000-000000000000"
        attempts = [
            ("findings", "show", missing_id),
            ("findings", "show", "not-an-id"),
            ("findings", "list", "--status", "unknown"),
            ("findings", "review", missing_id, "--decision", "dismissed", "--reason", "Bilinen sonuç."),
            ("findings", "review", finding_id, "--decision", "confirmed", "--reason", "Bir neden."),
            ("findings", "review", finding_id, "--decision", "new", "--reason", "Bir neden."),
            ("findings", "review", finding_id, "--decision", "dismissed"),
            ("findings", "review", finding_id, "--decision", "dismissed", "--reason", "  "),
            ("findings", "review", finding_id, "--decision", "dismissed", "--reason", "bad\x1b[31mtext"),
        ]
        before = self.database_dump()
        for arguments in attempts:
            with self.subTest(arguments=arguments):
                self.error_json(self.run_cli(*arguments), 2)
                self.assertEqual(self.database_dump(), before)

    def test_review_history_preserves_append_order_when_clock_repeats_or_moves_back(self):
        self.initialize("example.com")
        self.import_source(self.write_source("example-support.net\n"))
        finding_id = self.findings()[0]["id"]
        repository = SQLiteFindingRepository(self.data / "xti.db")
        times = [
            datetime(2026, 10, 28, 12, tzinfo=timezone.utc),
            datetime(2026, 10, 28, 11, tzinfo=timezone.utc),
            datetime(2026, 10, 28, 11, tzinfo=timezone.utc),
        ]
        decisions = ["suspicious", "dismissed", "uncertain"]
        with patch("xti.adapters.sqlite_findings.datetime") as clock:
            clock.now.side_effect = times
            for number, decision in enumerate(decisions):
                repository.review_finding(finding_id, decision, f"İnceleme adımı {number + 1}.")
        details = self.details(finding_id)
        self.assertEqual([item["decision"] for item in details["reviews"]], decisions)
        self.assertEqual([item["created_at"] for item in details["reviews"]], [value.isoformat() for value in times])
        self.assertEqual(details["finding"]["status"], "uncertain")

    def test_terminal_detail_escapes_untrusted_source_name(self):
        self.initialize("example.com")
        source = self.write_source("example-support.net\n", "source\x1b[31m.txt")
        self.import_source(source)
        finding_id = self.findings()[0]["id"]
        result = self.run_cli("findings", "show", finding_id, as_json=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("\x1b", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

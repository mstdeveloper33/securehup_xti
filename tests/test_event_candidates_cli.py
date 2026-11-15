"""Real stored three-source candidates through terminal, JSON and subprocess CLI."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.ransomlook_ransomware import parse_ransomlook_ransomware_response
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_public_notices import SQLitePublicNoticeRepository
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.threatcluster_ransomware import parse_threatcluster_ransomware_response
from xti.domain.public_notices import PublicNoticeFeed
from xti.interfaces.cli import build_parser, main
from xti.interfaces.event_candidates import event_candidate_lines, make_event_candidate_service
from tests.test_public_notices import feed, item
from tests.test_ransomlook_ransomware import content as rl_content, post
from tests.test_threatcluster_ransomware import content as tc_content, claim


PROJECT = Path(__file__).resolve().parents[1]


class EventCandidateCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="xti-event-candidates-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.database = self.data / "xti.db"
        SQLiteAssetRepository(self.database).initialize()
        self.tc = SQLiteRansomwareClaimRepository(self.database)
        self.rl = SQLiteRansomLookClaimRepository(self.database)
        self.hibp = SQLitePublicNoticeRepository(self.database)
        self.now = datetime.now(timezone.utc) - timedelta(hours=2)
        self.discovered = (self.now - timedelta(hours=3)).isoformat()

    def files(self):
        return {str(path.relative_to(self.data)): path.read_bytes()
                for path in self.data.rglob("*") if path.is_file()}

    def invoke(self, *arguments, as_json=True, data=None):
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--data-dir", str(data or self.data), *(["--json"] if as_json else []), *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def result(self, *arguments):
        code, output, error = self.invoke(*arguments)
        self.assertEqual((code, error), (0, ""), output)
        result = json.loads(output)
        self.assertTrue(result["ok"])
        return result["data"]

    def seed(self, *, country="TR"):
        at = self.now.isoformat()
        records = [claim(name, group=group, discovered=self.discovered, website=domain, country=country)
                   for name, group, domain in (("Alpha Holding", "alpha-group", "alpha.example"),
                                               ("Beta Holding", "beta-group", "beta.example"))]
        tc_feed = parse_threatcluster_ransomware_response(
            tc_content(records, generated_at=at), fetched_at=self.now)
        self.tc.apply(tc_feed, started_at=at, finished_at=at, item_limit=100)
        rl_feed = parse_ransomlook_ransomware_response(
            rl_content([post(name, group=group, discovered=self.discovered)
                        for name, group in (("Alpha Holding", "alpha-group"), ("Beta Holding", "beta-group"))]),
            fetched_at=self.now)
        self.rl.apply(rl_feed, started_at=at, finished_at=at, item_limit=100)
        notices = feed(item("AlphaNotice", "alpha.example"), item("BetaNotice", "beta.example")).notices
        self.hibp.apply(PublicNoticeFeed(at, "a" * 64, notices), started_at=at, finished_at=at)

    def read_guard(self):
        stack = ExitStack()
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection",
                       "socket.getaddrinfo", "subprocess.run", "subprocess.Popen",
                       "xti.adapters.worker_lock.LocalExecutionLock.acquire"):
            stack.enter_context(patch(target, side_effect=AssertionError("Candidate read attempted a side effect.")))
        stack.enter_context(patch.object(SQLiteAssetRepository, "initialize",
                                         side_effect=AssertionError("Candidate read initialized storage.")))
        for target in ("ThreatClusterRansomwareSource", "RansomLookRansomwareSource", "HibpPublicNoticeSource"):
            stack.enter_context(patch("xti.interfaces.cli." + target,
                                     side_effect=AssertionError("Candidate read constructed a collector.")))
        return stack

    def test_json_and_terminal_keep_both_candidate_kinds_and_all_source_evidence_without_writes(self):
        self.seed()
        before = self.files()
        with self.read_guard():
            data = self.result("events", "candidates")
            code, text, error = self.invoke("events", "candidates", as_json=False)
        self.assertEqual((code, error), (0, ""))
        self.assertEqual((data["total_candidate_count"], data["possible_same_event_count"],
                          data["organization_context_count"]), (4, 2, 2))
        self.assertEqual({row["source_key"] for row in data["coverage"]}, {"threatcluster", "ransomlook", "hibp"})
        self.assertTrue(all(row["status"] == "available" for row in data["coverage"]))
        for candidate in data["candidates"]:
            self.assertIn(candidate["id"], text)
            self.assertIn(candidate["evidence_sha256"], text)
            self.assertTrue(candidate["reasons"])
            self.assertTrue(candidate["cautions"])
            for evidence in (candidate["left"], candidate["right"]):
                for value in (evidence["record_id"], evidence["source_run_id"], evidence["state_sha256"], evidence["source_url"]):
                    self.assertIn(value, text)
                self.assertTrue(evidence["dates"])
                self.assertTrue(evidence["record"])
        for value in ("Aynı olay olabilir", "Ortak kuruluş/domain bağlamı", "Neden gösterildi", "Tarihler ve anlamları"):
            self.assertIn(value, text)
        self.assertEqual(self.files(), before)

    def test_domain_pagination_retains_filters_and_distinguishes_page_past_end(self):
        self.seed()
        before = self.files()
        pages = [self.result("events", "candidates", "--domain", "alpha.example", "--limit", "1",
                             "--offset", str(offset), "--stale-hours", "1") for offset in range(3)]
        self.assertEqual([page["total_candidate_count"] for page in pages], [2, 2, 2])
        self.assertEqual([page["has_more"] for page in pages], [True, False, False])
        self.assertNotEqual(pages[0]["candidates"][0]["id"], pages[1]["candidates"][0]["id"])
        self.assertEqual(pages[2]["candidates"], [])
        self.assertNotIn("beta.example", json.dumps(pages))
        _, text, _ = self.invoke("events", "candidates", "--domain", "alpha.example", "--limit", "1",
                                "--stale-hours", "1", as_json=False)
        navigation = next(line.removeprefix("Sonraki sayfa: ") for line in text.splitlines() if line.startswith("Sonraki sayfa: "))
        arguments = shlex.split(navigation)[1:]
        parsed = build_parser().parse_args(arguments)
        self.assertEqual((parsed.domain, parsed.limit, parsed.offset, parsed.stale_hours), ("alpha.example", 1, 1, 1))
        _, text, _ = self.invoke("events", "candidates", "--offset", "100", as_json=False)
        self.assertIn("başlangıç değeri toplam aday sayısının dışında", text)
        self.assertEqual(self.files(), before)

    def test_missing_failed_and_old_successful_sources_remain_explicit(self):
        empty = self.result("events", "candidates")
        self.assertEqual(empty["total_candidate_count"], 0)
        self.assertTrue(all(row["status"] == "not_collected" for row in empty["coverage"]))
        at = self.now.isoformat()
        self.tc.record_failure(started_at=at, finished_at=at, error="Kontrollü kaynak kesintisi.")
        unavailable = self.result("events", "candidates")
        self.assertEqual(unavailable["coverage"][0]["status"], "unavailable")
        self.seed()
        failed_at = (self.now + timedelta(minutes=1)).isoformat()
        self.tc.record_failure(started_at=failed_at, finished_at=failed_at, error="Kontrollü son deneme hatası.")
        before = self.files()
        data = self.result("events", "candidates", "--stale-hours", "1")
        tc = next(row for row in data["coverage"] if row["source_key"] == "threatcluster")
        self.assertEqual((tc["status"], tc["freshness"]), ("last_attempt_failed", "stale"))
        self.assertNotEqual(tc["latest_run_id"], tc["latest_success_run_id"])
        self.assertEqual(data["total_candidate_count"], 4)
        self.assertEqual(self.files(), before)

    def test_missing_storage_and_invalid_options_never_initialize_or_write(self):
        missing = self.root / "missing"
        with self.read_guard():
            code, output, error = self.invoke("events", "candidates", data=missing)
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertEqual(json.loads(error)["error"]["code"], "storage_error")
        self.assertFalse(missing.exists())
        before = self.files()
        for options in (("--limit", "0"), ("--offset", "-1"), ("--stale-hours", "0"), ("--domain", "invalid/host")):
            with self.subTest(options=options), self.read_guard():
                code, _, error = self.invoke("events", "candidates", *options)
                self.assertEqual(code, 2)
                self.assertEqual(json.loads(error)["error"]["code"], "validation_error")
        self.assertEqual(self.files(), before)

    def test_previous_human_decision_is_shown_as_historical_when_source_evidence_changes(self):
        self.seed()
        comparison = self.result("ransomware", "source-compare")["comparisons"][0]
        self.result("ransomware", "source-review", comparison["id"], "--decision", "different", "--reason", "İnsan değerlendirmesi.")
        original = self.result("events", "candidates")
        candidate = next(row for row in original["candidates"] if row["legacy_comparison_id"] == comparison["id"])
        self.assertTrue(candidate["legacy_review"]["evidence_matches"])
        self.now += timedelta(minutes=1)
        self.seed(country="US")
        before = self.files()
        updated = self.result("events", "candidates")
        current = next(row for row in updated["candidates"] if row["id"] == candidate["id"])
        self.assertFalse(current["legacy_review"]["evidence_matches"])
        self.assertEqual(current["legacy_review"]["decision"], "different")
        _, text, _ = self.invoke("events", "candidates", as_json=False)
        self.assertIn("Önceki kaynak karşılaştırması kararı", text)
        self.assertIn("Karar eski kanıta bağlı", text)
        self.assertIn("ransomware source-review-show " + comparison["id"], text)
        self.assertNotIn("--decision", text)
        self.assertEqual(self.files(), before)

    def test_renderer_escapes_external_control_characters(self):
        self.seed()
        report = make_event_candidate_service(self.database).candidates()
        candidate = report.candidates[0]
        hostile = "Alpha\x1b[2J\nFORGED"
        record = replace(candidate.left.record, victim=hostile)
        evidence = replace(candidate.left, title=hostile, record=record, source_url="https://example.test/\x1b[31m")
        candidate = replace(candidate, left=evidence, reasons=(hostile,), cautions=(hostile,))
        report = replace(report, candidates=(candidate,), notes=(hostile,))
        text = "\n".join(event_candidate_lines(report))
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\nFORGED", text)
        self.assertIn("\\u001b", text)
        self.assertIn("\\u000a", text)

    def test_real_cli_subprocess_returns_candidates_and_keeps_database_bytes(self):
        self.seed()
        before = self.files()
        injection = self.root / "offline"
        injection.mkdir()
        (injection / "sitecustomize.py").write_text(
            "import socket\n"
            "def deny(*a, **k): raise AssertionError('Event candidate subprocess must stay offline')\n"
            "socket.create_connection=deny\nsocket.socket.connect=deny\nsocket.getaddrinfo=deny\n")
        environment = dict(os.environ, XTI_PYTHON=sys.executable,
                           PYTHONPATH=os.pathsep.join((str(injection), str(PROJECT / "src"))),
                           PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.run([str(PROJECT / "xti"), "--data-dir", str(self.data), "--json",
                                  "events", "candidates", "--domain", "alpha.example"],
                                 env=environment, cwd=PROJECT, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual((process.returncode, process.stderr), (0, ""), process.stdout)
        self.assertEqual(json.loads(process.stdout)["data"]["total_candidate_count"], 2)
        self.assertEqual(self.files(), before)


if __name__ == "__main__":
    unittest.main()

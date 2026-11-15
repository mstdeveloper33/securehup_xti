"""Real CLI flows with isolated storage and a deterministic provider boundary."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import json
import os
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.mentions import MentionHit, MentionResponse, build_query
from xti.interfaces.cli import build_parser, main
from xti.ports.discovery import SourceError


KEY = "tvly-test-private-key-never-persisted"


class MentionCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "records with spaces"
        self.storage = SQLiteAssetRepository(self.data / "xti.db")
        self.storage.initialize()
        self.calls, self.error = [], None
        self.hits = (
            MentionHit("https://publisher.example/one", "Example Company update", "example.com açıklaması", None, 0.8),
            MentionHit("https://publisher.example/two", "Other company", "Arama kaynağının adayı", None, 0.6),
        )
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"TAVILY_API_KEY": KEY, "XDG_CONFIG_HOME": str(self.root / "config")}).start()
        patch("socket.socket.connect", side_effect=AssertionError("No real network")).start()
        patch("socket.getaddrinfo", side_effect=AssertionError("No real DNS")).start()
        patch("xti.adapters.tavily_search.TavilySearchSource.fetch", side_effect=self.fetch).start()

    def fetch(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return MentionResponse(build_query(request.target), "provider-request", self.hits, 1)

    def invoke(self, *arguments, data=None, as_json=True):
        out, err = StringIO(), StringIO()
        prefix = ["--data-dir", str(data or self.data)]
        if as_json:
            prefix.append("--json")
        with redirect_stdout(out), redirect_stderr(err):
            code = main([*prefix, *arguments])
        self.assertNotIn(KEY, out.getvalue() + err.getvalue())
        return code, out.getvalue(), err.getvalue()

    def result(self, *arguments, **kwargs):
        code, out, err = self.invoke(*arguments, **kwargs)
        self.assertEqual((code, err), (0, ""), out + err)
        return json.loads(out)["data"]

    def search(self, **kwargs):
        return self.result("mentions", "search", "--name", "Example Company", "--domain", "example.com", **kwargs)

    def test_plan_needs_no_database_key_or_network_and_reads_never_initialize(self):
        missing = self.root / "missing"
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
            plan = self.result("mentions", "plan", "--name", "Example Company", "--domain", "example.com", data=missing)
            self.assertEqual((plan["requests"], plan["expected_credits"], plan["search_depth"]), (1, 1, "basic"))
            self.assertEqual(plan["query"], '"Example Company" OR "example.com"')
            for action in ("list", "status"):
                code, _, err = self.invoke("mentions", action, data=missing)
                self.assertEqual(code, 1, err)
        self.assertFalse(missing.exists())
        self.assertEqual(self.calls, [])

    def test_search_and_offline_views_preserve_full_details_and_page_links(self):
        report = self.search()
        self.assertEqual((report["run"]["added_count"], len(report["results"]), len(self.calls)), (2, 2, 1))
        self.assertEqual(report["results"][0]["matched_terms"], ["Example Company", "example.com"])
        self.assertEqual(report["results"][1]["matched_terms"], [])
        before = self.storage.path.read_bytes()
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
            page = self.result("mentions", "list", "--limit", "1")
            self.assertEqual((page["total_count"], len(page["records"]), page["has_more"]), (2, 1, True))
            detail = self.result("mentions", "show", page["records"][0]["id"])
            self.assertEqual(detail["request"]["target"]["name"], "Example Company")
            original = self.result("mentions", "run-show", report["run"]["id"])
            self.assertEqual(original, report)
            code, text, err = self.invoke("mentions", "list", "--limit", "1", as_json=False)
            self.assertEqual((code, err), (0, ""))
            command = next(line.split(": ", 1)[1] for line in text.splitlines() if line.startswith("Sonraki sayfa:"))
            parsed = build_parser().parse_args(shlex.split(command)[1:])
            self.assertEqual((parsed.data_dir, parsed.offset, parsed.limit), (str(self.data), 1, 1))
            empty_page = self.result("mentions", "list", "--offset", "999")
            self.assertEqual((empty_page["total_count"], empty_page["records"]), (2, []))
        self.assertEqual(self.storage.path.read_bytes(), before)
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn(KEY.encode(), before)

    def test_repeat_update_and_failed_search_keep_immutable_evidence(self):
        first = self.search()
        self.hits = (replace(self.hits[0], score=0.99), self.hits[1])
        repeated = self.search()
        self.assertEqual(repeated["run"]["unchanged_count"], 2)
        self.hits = (replace(self.hits[0], title="Example Company corrected report"),)
        updated = self.search()
        self.assertEqual(updated["results"][0]["action"], "updated")
        self.assertEqual(updated["results"][0]["before"]["title"], "Example Company update")
        self.error = SourceError("Tavily istek sınırına ulaştı; otomatik tekrar yapılmadı.")
        code, out, err = self.invoke("mentions", "search", "--name", "Example Company", "--domain", "example.com")
        self.assertEqual((code, err), (3, ""))
        self.assertFalse(json.loads(out)["ok"])
        self.assertEqual(self.result("mentions", "list")["total_count"], 2)
        self.assertEqual(self.result("mentions", "run-show", first["run"]["id"]), first)
        status = self.result("mentions", "status")
        self.assertEqual((status["reported_credits"], status["unknown_usage_runs"]), (3, 1))

    def test_successful_empty_run_is_not_failure_and_does_not_delete(self):
        self.search()
        self.hits = ()
        empty = self.search()
        self.assertEqual((empty["run"]["status"], empty["results"]), ("complete", []))
        self.assertEqual(self.result("mentions", "list")["total_count"], 2)

    def test_registered_targets_and_renaming_preserve_historical_scope(self):
        org = self.result("organizations", "add", "Example Company", "--reason", "İçerik izleme kapsamım")["organization"]
        self.result("assets", "add", "example.com")
        self.result("organizations", "link", org["id"], "--kind", "domain", "--value", "example.com", "--reason", "Firma domaini")
        plan = self.result("mentions", "plan", "--organization", org["id"])
        self.assertEqual(plan["request"]["target"]["domains"], ["example.com"])
        first = self.result("mentions", "search", "--organization", org["id"])
        self.result("organizations", "rename", org["id"], "New Company Name", "--reason", "Adı değişti")
        self.assertEqual(self.result("mentions", "run-show", first["run"]["id"])["run"]["request"]["target"]["name"], "Example Company")
        supplier = self.result("suppliers", "add", "Example Supplier", "--domain", "vendor.example", "--relationship", "cloud", "--criticality", "high", "--reason", "Bulut tedarikçim")["supplier"]
        self.result("mentions", "search", "--supplier", supplier["id"], "--topic", "news")
        self.assertEqual(self.calls[-1].target.domains, ("vendor.example",))
        page = self.result("mentions", "list", "--supplier", supplier["id"])
        self.assertEqual(page["total_count"], 2)
        self.assertTrue(all(item["request"]["target"]["id"] == supplier["id"] for item in page["records"]))
        self.result("suppliers", "revoke", supplier["id"], "--reason", "Artık kullanmıyorum")
        before = len(self.calls)
        code, _, err = self.invoke("mentions", "search", "--supplier", supplier["id"])
        self.assertEqual(code, 2, err)
        self.assertEqual(len(self.calls), before)
        self.assertEqual(self.result("mentions", "list", "--supplier", supplier["id"])["total_count"], 2)

    def test_missing_key_busy_lock_invalid_input_stop_before_request(self):
        before = self.storage.path.read_bytes()
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
            code, _, err = self.invoke("mentions", "search", "--name", "Example Company")
            self.assertEqual(code, 2, err)
        with LocalExecutionLock(self.storage.path).acquire():
            code, _, err = self.invoke("mentions", "search", "--name", "Example Company")
            self.assertEqual(code, 4, err)
        for arguments in (("search", "--name", "Example Company", "--max-results", "21"),
                          ("search", "--supplier", "not-a-uuid"), ("list", "--limit", "0"),
                          ("run-show", "bad-id"), ("show", "bad-id")):
            code, _, err = self.invoke("mentions", *arguments)
            self.assertEqual(code, 2, err)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.storage.path.read_bytes(), before)

    def test_private_configuration_no_database_key_output_or_network(self):
        missing = self.root / "missing"
        with patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", return_value=KEY):
            result = self.result("mentions", "configure", data=missing)
        saved = Path(result["key_file"])
        self.assertEqual(saved, self.root / "config" / "xti" / "tavily.key")
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.assertFalse(missing.exists())
        self.assertEqual(self.calls, [])
        with patch("sys.stdin.isatty", return_value=False):
            code, _, err = self.invoke("mentions", "configure")
            self.assertEqual(code, 2, err)


if __name__ == "__main__":
    unittest.main()

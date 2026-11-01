"""Persistent source waits and explicit, reviewable maintenance through the CLI."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.urlscan import UrlscanSource
from xti.adapters.worker_lock import LocalExecutionLock
from xti.domain.findings import DomainInput, ImportDocument, MatchCandidate
from xti.interfaces.cli import main
from tests.test_discovery import FakeSource
from tests.test_urlscan import Response, body


class OperationsCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "local records with spaces"
        self.database = self.data / "xti.db"

    def invoke(self, *arguments, as_json=True, data_dir=None):
        argv = ["--data-dir", str(data_dir or self.data)]
        if as_json:
            argv.append("--json")
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([*argv, *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def success(self, *arguments, **kwargs):
        code, stdout, stderr = self.invoke(*arguments, **kwargs)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, "")
        data = json.loads(stdout)
        self.assertTrue(data["ok"])
        return data["data"]

    def seed(self):
        repository = SQLiteAssetRepository(self.database)
        repository.initialize()
        asset, _ = repository.add("example.com")
        findings = SQLiteFindingRepository(self.database)
        findings.save_import(ImportDocument("fixture", "test-operations-fixture", (
            DomainInput("example-support.net", "example-support.net", 1, None),
            DomainInput("unrelated.net", "unrelated.net", 2, None),
        )), (MatchCandidate(asset.id, asset.value, "example-support.net", "test-rule", ("Test fixture",)),))
        finding = findings.list_findings()[0]
        findings.review_finding(finding.id, "dismissed", "Normal test kaydı.")
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE observations SET ingested_at = '2020-01-01T00:00:00+00:00'")
        return finding.id

    def test_preview_is_read_only_and_reports_protected_evidence_and_exact_apply_command(self):
        self.seed()
        before = self.database.read_bytes()
        preview = self.success("storage", "cleanup")
        plan = preview["plan"]
        self.assertEqual(plan["eligible_count"], 1)
        self.assertEqual(plan["selected_count"], 1)
        self.assertEqual(plan["protected_count"], 1)
        self.assertEqual(len(plan["token"]), 64)
        self.assertIn("--apply " + plan["token"], preview["apply_command"])
        self.assertIn("local records with spaces", preview["apply_command"])
        self.assertEqual(self.database.read_bytes(), before)
        self.assertFalse((self.data / "xti.db.worker.lock").exists())
        self.assertFalse((self.data / "backups").exists())
        self.assertEqual(self.success("storage", "history")["runs"], [])
        usage = self.success("storage", "status")
        self.assertEqual(usage["observation_count"], 2)
        self.assertEqual(usage["linked_observation_count"], 1)
        self.assertGreater(usage["database_bytes"], 0)
        self.assertEqual(self.database.read_bytes(), before)

    def test_explicit_cleanup_backs_up_and_restore_recovers_unlinked_observation(self):
        finding_id = self.seed()
        before = self.success("findings", "show", finding_id)
        token = self.success("storage", "cleanup")["plan"]["token"]
        result = self.success("storage", "cleanup", "--apply", token)
        self.assertEqual(result["deleted_count"], 1)
        self.assertTrue(Path(result["backup"]).is_file())
        self.assertEqual(self.success("findings", "show", finding_id), before)
        self.assertEqual(self.success("storage", "status")["observation_count"], 1)
        history = self.success("storage", "history")["runs"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["token"], token)
        self.assertEqual(history[0]["backup"], result["backup"])
        restored = self.root / "restored"
        self.success("restore", result["backup"], data_dir=restored)
        self.assertEqual(self.success("storage", "status", data_dir=restored)["observation_count"], 2)
        self.assertEqual(self.success("findings", "show", finding_id, data_dir=restored), before)
        self.assertEqual(self.success("storage", "history", data_dir=restored)["runs"], [])

    def test_stale_preview_is_rejected_without_a_backup_or_deletion(self):
        self.seed()
        token = self.success("storage", "cleanup")["plan"]["token"]
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE observations SET raw_domain = 'CHANGED.NET' WHERE domain = 'unrelated.net'")
        before = self.database.read_bytes()
        code, stdout, stderr = self.invoke("storage", "cleanup", "--apply", token)
        self.assertEqual(code, 2, stderr)
        self.assertEqual(stdout, "")
        self.assertEqual(self.database.read_bytes(), before)
        self.assertFalse((self.data / "backups").exists())

    def test_running_scan_prevents_cleanup_and_retains_all_records(self):
        self.seed()
        token = self.success("storage", "cleanup")["plan"]["token"]
        with LocalExecutionLock(self.database).acquire():
            code, stdout, stderr = self.invoke("storage", "cleanup", "--apply", token)
        self.assertEqual(code, 4, stderr)
        self.assertEqual(stdout, "")
        self.assertEqual(self.success("storage", "status")["observation_count"], 2)
        self.assertFalse((self.data / "backups").exists())

    def test_invalid_options_and_missing_storage_do_not_create_files(self):
        for arguments in [
            ("storage", "cleanup", "--older-than-days", "6"),
            ("storage", "cleanup", "--limit", "10001"),
            ("storage", "cleanup", "--apply", "invalid"),
            ("storage", "history", "--limit", "0"),
        ]:
            with self.subTest(arguments=arguments):
                code, stdout, stderr = self.invoke(*arguments)
                self.assertEqual(code, 2, stderr)
                self.assertEqual(stdout, "")
                self.assertFalse(self.data.exists())
        for arguments in [("storage", "status"), ("storage", "cleanup"), ("storage", "history")]:
            with self.subTest(arguments=arguments):
                code, stdout, stderr = self.invoke(*arguments)
                self.assertEqual(code, 1, stderr)
                self.assertEqual(stdout, "")
                self.assertFalse(self.data.exists())

    def test_empty_apply_makes_no_backup_and_has_no_cleanup_history(self):
        self.success("init")
        token = self.success("storage", "cleanup")["plan"]["token"]
        before = self.database.read_bytes()
        result = self.success("storage", "cleanup", "--apply", token)
        self.assertEqual(result["deleted_count"], 0)
        self.assertIsNone(result["backup"])
        self.assertIsNone(result["run"])
        self.assertEqual(self.database.read_bytes(), before)
        self.assertFalse((self.data / "backups").exists())

    def test_sources_exposes_persisted_wait_without_network_or_mutation(self):
        self.success("init")
        now = datetime.now(timezone.utc)
        SQLiteCooldownRepository(self.database).extend(
            "urlscan", (now + timedelta(hours=1)).isoformat(), now.isoformat(), "rate_limit",
        )
        before = self.database.read_bytes()
        with patch("xti.interfaces.cli.UrlscanSource") as factory:
            status = self.success("sources")
        factory.return_value.search.assert_not_called()
        self.assertEqual(status["sources"], [])
        self.assertEqual(len(status["cooldowns"]), 1)
        self.assertEqual(status["cooldowns"][0]["provider"], "urlscan")
        self.assertTrue(status["cooldowns"][0]["active"])
        self.assertGreater(status["cooldowns"][0]["remaining_seconds"], 3500)
        self.assertEqual(self.database.read_bytes(), before)
        code, stdout, stderr = self.invoke("sources", as_json=False)
        self.assertEqual(code, 0, stderr)
        self.assertIn("saniye kaldı", stdout)

    def test_new_cli_run_honors_wait_and_other_source_still_runs(self):
        blocked = Mock(side_effect=HTTPError("https://urlscan.io", 429, "quota", {"Retry-After": "3600"}, None))
        with patch("xti.interfaces.cli.UrlscanSource", side_effect=lambda **kw: UrlscanSource(opener=blocked, **kw)):
            code, stdout, stderr = self.invoke("scan", "example.com", "--source", "urlscan")
        self.assertEqual(code, 3, stderr)
        self.assertEqual(blocked.call_count, 1)
        self.assertEqual(json.loads(stdout)["data"]["status"], "failed")
        fresh_opener = Mock(return_value=Response(body()))
        crt = FakeSource({})
        with (
            patch("xti.interfaces.cli.UrlscanSource", side_effect=lambda **kw: UrlscanSource(opener=fresh_opener, **kw)),
            patch("xti.interfaces.cli.CrtShSource", return_value=crt),
        ):
            code, stdout, stderr = self.invoke("scan", "example.com")
        self.assertEqual(code, 3, stderr)
        data = json.loads(stdout)["data"]
        self.assertEqual([item["status"] for item in data["results"]], ["complete", "failed"])
        fresh_opener.assert_not_called()
        self.assertEqual(crt.calls, ["%example%", "example%"])
        self.assertIn("bekleme", data["results"][1]["queries"][0]["error"])
        self.assertTrue(self.success("sources")["cooldowns"][0]["active"])

    def test_scan_does_not_automatically_remove_old_unlinked_records(self):
        self.seed()
        with patch("xti.interfaces.cli.CrtShSource", return_value=FakeSource({})):
            self.success("scan", "example.com", "--source", "crt.sh")
        self.assertEqual(self.success("storage", "status")["observation_count"], 2)


if __name__ == "__main__":
    unittest.main()

"""Operator-facing privacy acceptance using real CLI/engine subprocesses.

All secrets are synthetic. No webhook is sent and no source is contacted.
Backups intentionally retain configuration secrets and must remain private.
"""

import base64
from contextlib import closing
from io import StringIO
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_webhooks import SQLiteWebhookRepository
from xti.adapters.webhook_https import SafeHttpsWebhookSender
from xti.interfaces.engine import run_engine


PROJECT = Path(__file__).resolve().parents[1]
SENTINEL = "fixture-private-key-0123456789-DO-NOT-PUBLISH"
URL_TOKEN = "fixture-private-url-token-987654321"


class StabilizationPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.data = self.root / "private-data"
        self.database = self.data / "xti.db"
        storage = SQLiteAssetRepository(self.database)
        storage.initialize()
        storage.add("example.com")
        self.key = self.root / "private.key"
        self.key.write_text(SENTINEL + "\n")
        self.key.chmod(0o600)
        self.environment = dict(os.environ, XTI_DATA_DIR=str(self.data), XTI_PYTHON=sys.executable)
        self.environment.pop("XTI_AUTO_MIGRATE", None)
        result = self.invoke("webhook", "target-add", "Private fixture receiver",
                             "https://hooks.example.test/xti?token=" + URL_TOKEN,
                             "--secret-file", str(self.key))
        self.destination = json.loads(result.stdout)["data"]["destination"]["id"]

    def invoke(self, *args, payload=None, human=False, expected=0, timeout=20):
        command = [str(PROJECT / "xti"), "--data-dir", str(self.data)]
        if not human and (not args or args[0] != "engine"):
            command.append("--json")
        process = subprocess.run(command + list(args), input=payload, text=True,
                                 capture_output=True, env=self.environment, timeout=timeout)
        self.assertEqual(process.returncode, expected, process.stdout + process.stderr)
        self.assert_private_output(process.stdout + process.stderr)
        return process

    def assert_private_output(self, output):
        for private in (SENTINEL, URL_TOKEN, base64.b64encode(SENTINEL.encode()).decode()):
            self.assertNotIn(private, output)

    def test_existing_configuration_is_hidden_in_terminal_json_engine_and_html(self):
        organization = json.loads(self.invoke("organizations", "add", "Example organization").stdout)["data"]["organization"]
        self.invoke("organizations", "link", organization["id"], "--kind", "domain", "--value", "example.com")
        for human in (False, True):
            for args in (("webhook", "target-list"), ("webhook", "target-show", self.destination),
                         ("webhook", "delivery-list"), ("doctor",)):
                with self.subTest(args=args, human=human):
                    self.invoke(*args, human=human)
        request = {"contract_version": 1, "request_id": "privacy:1", "operation": "search",
                   "parameters": {"query": "example"}}
        response = json.loads(self.invoke("engine", payload=json.dumps(request)).stdout)
        self.assertEqual(response["status"], "complete")
        self.assertGreater(response["data"]["total_match_count"], 0)
        output = self.root / "organization.html"
        self.invoke("organizations", "export", organization["id"], "--output", str(output))
        self.assert_private_output(output.read_text())
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)

    def test_backup_and_restore_preserve_sensitive_configuration_in_private_files(self):
        before = self.database.read_bytes()
        backup = self.root / "backup.db"
        self.invoke("backup", "--output", str(backup))
        restored = self.root / "restored" / "xti.db"
        SQLiteAssetRepository.restore(backup, restored)
        for path in (self.database, backup, restored, self.key):
            with self.subTest(path=path.name):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        with closing(sqlite3.connect(restored)) as connection:
            row = connection.execute("SELECT secret_b64, url FROM webhook_destinations WHERE id=?",
                                     (self.destination,)).fetchone()
        self.assertEqual(base64.b64decode(row[0]), SENTINEL.encode())
        self.assertIn(URL_TOKEN, row[1])
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(SQLiteWebhookRepository(restored).get_destination(self.destination).id,
                         self.destination)

    def test_engine_rejects_scope_and_command_injection_without_creating_target(self):
        original = self.database.read_bytes()
        outside = self.root / "should-not-exist"
        for name, value in (("data_dir", str(outside)), ("tenant_id", "different-owner"),
                            ("command", "touch " + str(outside))):
            request = {"contract_version": 1, "request_id": "privacy:scope", "operation": "search",
                       "parameters": {"query": "example", name: value}}
            response = json.loads(self.invoke("engine", payload=json.dumps(request), expected=2).stdout)
            self.assertEqual(response["error"]["code"], "invalid_parameters")
            self.assertFalse(outside.exists())
        self.assertEqual(self.database.read_bytes(), original)

    def test_exception_details_are_hidden_from_engine_and_transport_errors(self):
        request = json.dumps({"contract_version": 1, "request_id": "privacy:error", "operation": "search",
                              "parameters": {"query": "example"}})
        for error in (RuntimeError(SENTINEL), OSError(URL_TOKEN), StorageError(SENTINEL)):
            output = StringIO()
            with patch("xti.interfaces.engine.make_engine_service", side_effect=error):
                code = run_engine(self.database, stream=StringIO(request), output=output)
            self.assertEqual(code, 1)
            self.assert_private_output(output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["status"], "error")
        with patch("xti.adapters.webhook_https._resolve_public", side_effect=OSError(SENTINEL)):
            result = SafeHttpsWebhookSender().send(
                "https://hooks.example.test/?token=" + URL_TOKEN, b"{}", {}, timeout=2)
        self.assertEqual(result.outcome, "retryable")
        self.assert_private_output(str(result))

    def test_secret_reader_rejects_special_files_without_waiting_or_mutating_data(self):
        original = self.database.read_bytes()
        alias = self.root / "key-alias"
        alias.symlink_to(self.key)
        pipe = self.root / "key-pipe"
        os.mkfifo(pipe, 0o600)
        for path in (alias, pipe, self.root):
            with self.subTest(path=path.name):
                self.invoke("webhook", "target-add", "Rejected receiver", "https://other.example.test/hook",
                            "--secret-file", str(path), expected=2, timeout=5)
        self.assertEqual(self.database.read_bytes(), original)
        self.assertTrue(alias.is_symlink())
        self.assertTrue(stat.S_ISFIFO(pipe.lstat().st_mode))


if __name__ == "__main__":
    unittest.main()

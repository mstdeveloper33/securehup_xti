"""Explicit, signed and auditable webhook delivery without a background sender."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_findings import SQLiteFindingRepository
from xti.adapters.sqlite_inbox import SQLiteInboxRepository
from xti.adapters.sqlite_webhooks import SQLiteWebhookRepository
from xti.adapters.webhook_https import SafeHttpsWebhookSender
from xti.adapters.webhook_secret_file import generate_webhook_secret, read_webhook_secret
from xti.application.webhooks import WebhookService
from xti.domain.assets import ValidationError
from xti.domain.findings import DomainInput, ImportDocument, MatchCandidate
from xti.domain.webhooks import WebhookSendResult
from xti.interfaces.cli import main


NOW = datetime(2026, 10, 30, 21, tzinfo=timezone.utc)
SECRET = b"s" * 32


class FakeSender:
    def __init__(self, *results):
        self.results = list(results) or [WebhookSendResult("delivered", 204, None)]
        self.calls = []

    def send(self, url, body, headers, *, timeout):
        self.calls.append((url, body, dict(headers), timeout))
        return self.results.pop(0)


class WebhookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.database = self.data / "xti.db"
        self.storage = SQLiteAssetRepository(self.database)
        self.storage.initialize()
        asset, _ = self.storage.add("example.com")
        findings = SQLiteFindingRepository(self.database)
        document = ImportDocument("fixture:webhook", "webhook:example-login.net", (
            DomainInput("example-login.net", "example-login.net", 1, None),
        ))
        findings.save_import(document, (
            MatchCandidate(
                asset.id, asset.value, "example-login.net", "rules-v1", ("Test eşleşmesi",),
            ),
        ))
        self.notice = SQLiteInboxRepository(self.database).list("all", 10).items[0].notification
        self.clock_value = NOW
        self.sender = FakeSender()
        self.repository = SQLiteWebhookRepository(self.database)
        self.service = WebhookService(
            self.repository, SQLiteInboxRepository(self.database), self.sender,
            clock=lambda: self.clock_value,
        )
        self.destination = self.service.add_destination(
            "Local SIEM", "https://hooks.example.test/xti?token=private", SECRET,
        ).destination

    def advance(self):
        self.clock_value += timedelta(minutes=1)

    def test_destination_never_exposes_url_or_secret_and_lifecycle_is_audited(self):
        shown = self.service.show_destination(self.destination.id)
        serialized = json.dumps(shown.__dict__ if hasattr(shown, "__dict__") else {
            field: getattr(shown, field) for field in shown.__slots__
        })
        self.assertNotIn("token=private", serialized)
        self.assertNotIn(SECRET.decode(), serialized)
        self.assertIn("hooks.example.test", shown.endpoint)

        self.advance()
        rotated = self.service.rotate_secret(self.destination.id, b"n" * 32)
        self.advance()
        revoked = self.service.revoke_destination(self.destination.id)
        self.assertEqual(rotated.action, "secret_rotated")
        self.assertEqual(revoked.action, "revoked")
        self.assertFalse(revoked.destination.active)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(
                [row[0] for row in connection.execute(
                    "SELECT action FROM webhook_destination_events ORDER BY sequence"
                )],
                ["added", "secret_rotated", "revoked"],
            )

    def test_queue_is_deduplicated_and_delivery_signature_covers_exact_body(self):
        queued, created = self.service.queue(self.destination.id, self.notice.id)
        repeated, repeated_created = self.service.queue(self.destination.id, self.notice.id)
        self.assertTrue(created)
        self.assertFalse(repeated_created)
        self.assertEqual(repeated, queued)

        self.advance()
        result = self.service.deliver(queued.id)
        self.assertEqual((result.delivery.status, result.attempt.number), ("delivered", 1))
        url, body, headers, timeout = self.sender.calls[0]
        self.assertEqual(url, "https://hooks.example.test/xti?token=private")
        self.assertEqual(timeout, 10.0)
        self.assertEqual(json.loads(body)["id"], queued.id)
        expected = hmac.new(
            SECRET, headers["X-XTI-Timestamp"].encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(headers["X-XTI-Signature-256"], "sha256=" + expected)
        self.assertEqual(headers["X-XTI-Delivery"], queued.id)
        with self.assertRaisesRegex(ValidationError, "daha önce"):
            self.service.deliver(queued.id)

    def test_failed_attempt_is_durable_and_retry_uses_identical_payload(self):
        self.sender.results = [
            WebhookSendResult("retryable", 503, "Hedef geçici olarak kullanılamıyor."),
            WebhookSendResult("delivered", 200, None),
        ]
        queued, _ = self.service.queue(self.destination.id, self.notice.id)
        first = self.service.deliver(queued.id)
        self.assertEqual(first.delivery.status, "retryable")
        self.advance()
        second = self.service.deliver(queued.id)
        self.assertEqual((second.delivery.status, second.delivery.attempt_count), ("delivered", 2))
        self.assertEqual(self.sender.calls[0][1], self.sender.calls[1][1])
        details = self.service.show_delivery(queued.id)
        self.assertEqual([item.outcome for item in details.attempts], ["retryable", "delivered"])

    def test_corrupt_payload_or_attempt_history_fails_closed_without_repair(self):
        queued, _ = self.service.queue(self.destination.id, self.notice.id)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(
                "UPDATE webhook_deliveries SET payload_json=? WHERE id=?",
                ("{}", queued.id),
            )
        corrupt = self.database.read_bytes()
        with self.assertRaisesRegex(StorageError, "olay gövdesi bozuk"):
            self.service.deliver(queued.id)
        self.assertEqual(self.database.read_bytes(), corrupt)

    def test_secret_file_is_private_bounded_and_never_overwritten(self):
        target = self.root / "secrets" / "webhook.key"
        artifact = generate_webhook_secret(target)
        self.assertEqual((artifact.character_count, target.stat().st_mode & 0o777), (64, 0o600))
        self.assertEqual(len(read_webhook_secret(target)), 64)
        before = target.read_bytes()
        with self.assertRaisesRegex(ValidationError, "zaten var"):
            generate_webhook_secret(target)
        self.assertEqual(target.read_bytes(), before)
        target.chmod(0o644)
        with self.assertRaisesRegex(ValidationError, "chmod 600"):
            read_webhook_secret(target)

    def test_private_dns_target_is_rejected_before_any_connection(self):
        sender = SafeHttpsWebhookSender()
        with patch("xti.adapters.webhook_https.socket.getaddrinfo", return_value=[
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ]), patch("xti.adapters.webhook_https.socket.create_connection") as connect:
            result = sender.send(
                "https://receiver.example.test/hook", b"{}",
                {"Content-Type": "application/json"}, timeout=10.0,
            )
        self.assertEqual(result.outcome, "failed")
        self.assertIn("genel internet", result.error)
        connect.assert_not_called()

    def test_redirect_is_recorded_as_failure_and_never_followed(self):
        class Response:
            status = 302

            @staticmethod
            def getheaders():
                return [("Location", "https://elsewhere.example/hook")]

            @staticmethod
            def read(_limit):
                return b""

        class Connection:
            def __init__(self, *args, **kwargs):
                self.requests = []

            def request(self, *args, **kwargs):
                self.requests.append((args, kwargs))

            @staticmethod
            def getresponse():
                return Response()

            @staticmethod
            def close():
                return None

        connection = Connection()
        with patch(
            "xti.adapters.webhook_https._resolve_public", return_value=("1.1.1.1",),
        ), patch(
            "xti.adapters.webhook_https._PinnedHTTPSConnection", return_value=connection,
        ):
            result = SafeHttpsWebhookSender().send(
                "https://receiver.example/hook?event=xti", b"{}",
                {"Content-Type": "application/json"}, timeout=10.0,
            )
        self.assertEqual((result.outcome, result.http_status), ("failed", 302))
        self.assertEqual(len(connection.requests), 1)
        self.assertEqual(connection.requests[0][0][:2], ("POST", "/hook?event=xti"))

    def test_cli_config_queue_and_views_do_not_leak_secret_or_full_url(self):
        # Use a second clean database so CLI setup is tested independently.
        cli_data = self.root / "cli-data"
        setup_output, setup_error = StringIO(), StringIO()
        with redirect_stdout(setup_output), redirect_stderr(setup_error):
            self.assertEqual(main(["--data-dir", str(cli_data), "init"]), 0)
        self.assertEqual(setup_error.getvalue(), "")
        assets = SQLiteAssetRepository(cli_data / "xti.db")
        asset, _ = assets.add("cli.example")
        findings = SQLiteFindingRepository(cli_data / "xti.db")
        findings.save_import(
            ImportDocument("fixture:cli", "cli:cli-login.example", (
                DomainInput("cli-login.example", "cli-login.example", 1, None),
            )),
            (MatchCandidate(asset.id, asset.value, "cli-login.example", "rules-v1", ("Test",)),),
        )
        notification = SQLiteInboxRepository(cli_data / "xti.db").list("all").items[0].notification
        secret_file = self.root / "cli.key"
        secret_file.write_bytes(b"z" * 32 + b"\n")
        secret_file.chmod(0o600)

        def invoke(*args):
            output, error = StringIO(), StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                code = main(["--data-dir", str(cli_data), "--json", *args])
            return code, output.getvalue(), error.getvalue()

        code, output, error = invoke(
            "webhook", "target-add", "CLI target",
            "https://cli.example.test/hook?secret=hidden",
            "--secret-file", str(secret_file),
        )
        self.assertEqual((code, error), (0, ""))
        self.assertNotIn("secret=hidden", output)
        self.assertNotIn("z" * 32, output)
        destination_id = json.loads(output)["data"]["destination"]["id"]
        code, output, error = invoke(
            "webhook", "queue", destination_id, notification.id,
        )
        self.assertEqual((code, error), (0, ""))
        delivery_id = json.loads(output)["data"]["delivery"]["id"]
        code, output, error = invoke("webhook", "delivery-show", delivery_id)
        self.assertEqual((code, error), (0, ""))
        self.assertNotIn("secret=hidden", output)
        self.assertEqual(json.loads(output)["data"]["delivery"]["status"], "queued")


if __name__ == "__main__":
    unittest.main()


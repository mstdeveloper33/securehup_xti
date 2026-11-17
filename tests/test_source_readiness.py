"""Readiness explains independent setup, outcome and freshness states."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from io import StringIO
import json
import unittest
from unittest.mock import Mock, patch

from xti.application.source_readiness import SourceReadinessService
from xti.domain.assets import ValidationError
from xti.domain.source_readiness import SourceReadinessEvidence, SourceReadinessSnapshot
from xti.interfaces.cli import main
from xti.interfaces.source_readiness import report_lines


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def evidence(**changes):
    row = SourceReadinessEvidence(
        identifier="ioc:feodo", label="Feodo", scope="Genel IOC listesi",
        installation="builtin", latest_status="complete",
        last_attempt_at="2026-11-13T11:00:00+00:00",
        last_success_at="2026-11-13T11:00:00+00:00", error=None,
        next_command="./xti ioc sync --source feodo", notes=(), record_count=0,
    )
    return replace(row, **changes)


class SourceReadinessTests(unittest.TestCase):
    def test_terminal_distinguishes_partial_empty_failure_and_retained_stale_success(self):
        service, _ = self.service([
            evidence(identifier="empty", record_count=0),
            evidence(identifier="partial", latest_status="partial", last_success_at=None,
                     record_count=2, error="Bir sorgu zaman aşımına uğradı."),
            evidence(identifier="partial-empty", latest_status="partial", last_success_at=None, record_count=0),
            evidence(identifier="failed", latest_status="failed", last_success_at=None, record_count=0),
            evidence(identifier="old", latest_status="failed", last_success_at="2026-11-10T12:00:00+00:00"),
            evidence(identifier="never", latest_status="never", last_success_at=None, last_attempt_at=None),
        ])
        report = service.show()
        for details in (False, True):
            output = "\n".join(report_lines(report, details=details))
            for text in ("Tamamlandı; sonuç sayısı 0", "Kısmi kanıt var", "bu denemede kayıt alınamadı",
                         "Son deneme başarısız; tam başarılı çalışma yok", "korunan önceki sonuç eski",
                         "Henüz çalışma kaydı yok", "Bir sorgu zaman aşımına uğradı."):
                self.assertIn(text, output)
        self.assertEqual(report.sources[1].freshness, "never")
        self.assertEqual(report.sources[1].evidence.latest_status, "partial")

    def service(self, rows, storage="ready"):
        repo = Mock()
        repo.snapshot.return_value = SourceReadinessSnapshot(storage, tuple(rows))
        return SourceReadinessService(repo, clock=lambda: NOW), repo

    def test_failed_attempt_preserves_success_age_and_other_source_empty_success(self):
        service, _ = self.service([
            evidence(),
            evidence(identifier="ioc:certpl", latest_status="failed", error="Timeout"),
        ])
        result = service.show()
        empty, failed = result.sources
        self.assertEqual(empty.evidence.record_count, 0)
        self.assertFalse(empty.needs_attention)
        self.assertEqual(failed.freshness, "current")
        self.assertTrue(failed.needs_attention)
        self.assertEqual(failed.evidence.error, "Timeout")
        self.assertEqual(result.attention_count, 1)

    def test_installation_history_and_cooldown_are_independent(self):
        service, _ = self.service([
            evidence(installation="missing"),
            evidence(identifier="scan:crt.sh", cooldown_until="2026-11-13T12:03:00+00:00"),
            evidence(identifier="cti:attack", latest_status="unknown", last_attempt_at=None),
        ])
        result = service.show()
        self.assertTrue(result.sources[0].needs_attention)
        self.assertTrue(result.sources[1].cooldown_active)
        self.assertEqual(result.sources[1].cooldown_seconds, 180)
        self.assertEqual(result.sources[2].evidence.latest_status, "unknown")
        self.assertEqual(result.sources[2].freshness, "current")

    def test_stale_boundary_never_and_future_time(self):
        service, _ = self.service([
            evidence(last_success_at="2026-11-12T12:00:00+00:00"),
            evidence(identifier="social:maigret", latest_status="never", last_attempt_at=None, last_success_at=None),
            evidence(identifier="scan:crt.sh", last_attempt_at="2026-11-14T12:00:00+00:00"),
        ])
        self.assertEqual(
            [r.freshness for r in service.show().sources], ["stale", "never", "clock_error"],
        )

    def test_invalid_input_rejected_before_read_and_domain_is_normalized(self):
        service, repo = self.service([])
        for value in (0, True, 8761):
            with self.assertRaises(ValidationError):
                service.show(stale_after_hours=value)
        with self.assertRaises(ValidationError):
            service.show(domain="https://example.com/")
        repo.snapshot.assert_not_called()
        service.show(domain="EXAMPLE.COM")
        repo.snapshot.assert_called_once_with(domain="example.com")

    def test_missing_storage_does_not_claim_ready_and_terminal_escapes_external_text(self):
        service, _ = self.service([evidence(error="source\x1b[31m\nerror")], "not_initialized")
        result = service.show()
        self.assertEqual(result.sources[0].next_command, "./setup")
        self.assertTrue(result.sources[0].needs_attention)
        rendered = "\n".join(report_lines(result))
        self.assertNotIn("\x1b", rendered)
        self.assertIn("veritabanı henüz hazırlanmadı", rendered)

    def test_cli_status_json_has_scope_and_separate_states(self):
        _, repo = self.service([evidence()])
        stdout, stderr = StringIO(), StringIO()
        with patch("xti.interfaces.cli.SQLiteSourceReadinessRepository", return_value=repo), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--json", "sources", "status", "--domain", "example.com"])
        self.assertEqual((code, stderr.getvalue()), (0, ""))
        data = json.loads(stdout.getvalue())["data"]
        self.assertEqual(data["domain"], "example.com")
        row = data["sources"][0]
        self.assertEqual(row["evidence"]["latest_status"], "complete")
        self.assertIn("freshness", row)
        repo.snapshot.assert_called_once_with(domain="example.com")

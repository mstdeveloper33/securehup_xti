"""Pinned, P0-only theHarvester archive adapter contracts."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from xti.adapters.theharvester_archive import (
    INTEGRATION_PROFILE,
    REVIEWED_UPSTREAM_COMMIT,
    SOURCES,
    TheHarvesterArchiveSource,
    parse_theharvester_jsonl,
)
from xti.ports.discovery import SourceError


def report(*, statuses=("completed", "completed"), outside=False):
    findings = [
        {"sources": ["commoncrawl"], "type": "hostname", "value": "api.example.com"},
        {
            "sources": ["commoncrawl", "waybackarchive"],
            "type": "hostname",
            "value": "outside.test" if outside else "dev.example.com",
        },
    ]
    counts = {"commoncrawl": 2, "waybackarchive": 1}
    executions = []
    for source, status in zip(SOURCES, statuses):
        executions.append({
            "duration_ms": 12.5,
            "error_type": None if status == "completed" else "TimeoutError",
            "result_count": counts[source] if status != "failed" else 0,
            "source": source,
            "status": status,
            "stop_reason": None if status == "completed" else "runtime-limit",
        })
    if statuses == ("failed", "failed"):
        findings = []
    evidence_status = (
        "failed" if statuses == ("failed", "failed")
        else "partial" if statuses != ("completed", "completed")
        else "complete"
    )
    summary = {
        "action_executions": [], "artifacts": [],
        "completed_at": "2026-10-31T10:01:00Z",
        "counts": {"hostname": len(findings)} if findings else {},
        "evidence_status": evidence_status, "result_count": len(findings),
        "run_id": "123e4567-e89b-12d3-a456-426614174000",
        "source_executions": executions,
        "started_at": "2026-10-31T10:00:00Z",
        "target": "example.com", "type": "summary",
    }
    return [summary, *findings]


def payload(records) -> bytes:
    return b"".join(
        json.dumps(item, ensure_ascii=True, sort_keys=True).encode() + b"\n"
        for item in records
    )


class TheHarvesterArchiveTests(unittest.TestCase):
    def test_complete_report_keeps_source_provenance_and_minimal_hostnames(self):
        batch = parse_theharvester_jsonl(
            payload(report()), domain="example.com", limit=250,
        )
        self.assertEqual(batch.record_count, 2)
        self.assertEqual(batch.warnings, ())
        self.assertEqual(len(batch.documents), 3)
        self.assertEqual(
            [(item.records[0].domain, item.source_name.split(":")[1].split("@")[0])
             for item in batch.documents],
            [
                ("api.example.com", "commoncrawl"),
                ("dev.example.com", "commoncrawl"),
                ("dev.example.com", "waybackarchive"),
            ],
        )
        self.assertTrue(all(
            item.records[0].observed_at == "2026-10-31T10:01:00+00:00"
            for item in batch.documents
        ))
        self.assertIn(INTEGRATION_PROFILE.split("-")[1], batch.coverage_notes[0])

    def test_partial_is_visible_and_two_failed_sources_are_not_empty_success(self):
        records = report(statuses=("partial", "completed"))
        batch = parse_theharvester_jsonl(
            payload(records), domain="example.com", limit=250,
        )
        self.assertEqual(len(batch.warnings), 1)
        self.assertIn("commoncrawl", batch.warnings[0])

        with self.assertRaisesRegex(SourceError, "iki arşiv"):
            parse_theharvester_jsonl(
                payload(report(statuses=("failed", "failed"))),
                domain="example.com", limit=250,
            )

    def test_schema_drift_active_evidence_and_out_of_scope_hostname_fail_closed(self):
        cases = []
        changed = report()
        changed[0]["unexpected"] = True
        cases.append(changed)
        active = report()
        active[0]["action_executions"] = [{"action": "dns-resolve"}]
        cases.append(active)
        cases.append(report(outside=True))
        duplicate = report()
        duplicate.append(deepcopy(duplicate[1]))
        duplicate[0]["result_count"] = 3
        duplicate[0]["counts"]["hostname"] = 3
        duplicate[0]["source_executions"][0]["result_count"] = 3
        cases.append(duplicate)
        wrong_source = report()
        wrong_source[1]["sources"] = ["crtsh"]
        cases.append(wrong_source)
        malformed_source = report()
        malformed_source[1]["sources"] = [{"not": "text"}]
        cases.append(malformed_source)
        for records in cases:
            with self.subTest(case=records), self.assertRaises(SourceError):
                parse_theharvester_jsonl(
                    payload(records), domain="example.com", limit=250,
                )

    def test_failed_sources_preserve_their_separate_validated_reasons(self):
        records = report(statuses=("failed", "failed"))
        executions = records[0]["source_executions"]
        executions[0]["stop_reason"] = "invalid-catalog"
        executions[0]["error_type"] = "RuntimeError: private diagnostic detail"
        executions[1]["stop_reason"] = "runtime-limit"
        with self.assertRaises(SourceError) as raised:
            parse_theharvester_jsonl(
                payload(records), domain="example.com", limit=250,
            )
        message = str(raised.exception)
        self.assertIn("commoncrawl: failed, neden: invalid-catalog", message)
        self.assertIn("waybackarchive: failed, neden: runtime-limit", message)
        self.assertNotIn("private diagnostic detail", message)

        executions[0]["stop_reason"] = None
        executions[1]["stop_reason"] = "request-error"
        with self.assertRaises(SourceError) as raised:
            parse_theharvester_jsonl(
                payload(records), domain="example.com", limit=250,
            )
        self.assertIn("commoncrawl: failed, neden: bildirilmedi", str(raised.exception))
        self.assertIn("waybackarchive: failed, neden: request-error", str(raised.exception))

    def test_failed_source_reasons_reject_control_characters_and_remain_bounded(self):
        for reason in ("invalid\ncatalog", "\x1b[31merror", "\u202ereversed", "x" * 201):
            with self.subTest(reason=reason):
                records = report(statuses=("failed", "failed"))
                records[0]["source_executions"][0]["stop_reason"] = reason
                with self.assertRaisesRegex(SourceError, "beklenmeyen kanıt metni"):
                    parse_theharvester_jsonl(
                        payload(records), domain="example.com", limit=250,
                    )

        records = report(statuses=("failed", "failed"))
        for execution in records[0]["source_executions"]:
            execution["stop_reason"] = "x" * 200
        with self.assertRaises(SourceError) as raised:
            parse_theharvester_jsonl(
                payload(records), domain="example.com", limit=250,
            )
        self.assertLess(len(str(raised.exception)), 600)

    def test_adapter_uses_fixed_command_temporary_home_and_pinned_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "checkout"
            executable = checkout / ".venv" / "bin" / "theHarvester"
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o700)
            executable.with_name("python").symlink_to(sys.executable)
            (checkout / ".git").mkdir()
            (checkout / ".git" / "HEAD").write_text(
                REVIEWED_UPSTREAM_COMMIT + "\n", encoding="ascii",
            )
            seen = {}

            def runner(command, **kwargs):
                seen.update(command=command, kwargs=kwargs)
                output = Path(command[command.index("--report") + 1])
                output.write_bytes(payload(report()))
                return subprocess.CompletedProcess(command, 0, "safe stdout", "")

            source = TheHarvesterArchiveSource(
                runner=runner, executable_locator=lambda: executable,
                checkout_locator=lambda: checkout,
            )
            batch = source.search("%.example.com")
            self.assertEqual(batch.record_count, 2)
            command = seen["command"]
            self.assertEqual(command[0], str(executable.with_name("python")))
            self.assertEqual(Path(command[1]).name, "theharvester_archive_worker.py")
            self.assertEqual(command[2:7], [
                "--domain", "example.com", "--limit", "250", "--report",
            ])
            self.assertEqual(seen["kwargs"]["timeout"], 270)
            environment = seen["kwargs"]["env"]
            self.assertEqual(environment["HOME"], seen["kwargs"]["cwd"])
            self.assertNotIn("HTTP_PROXY", environment)
            self.assertEqual(environment["PYTHONNOUSERSITE"], "1")
            self.assertEqual(Path(environment["PYTHONPATH"]).name, "src")
            self.assertFalse(Path(environment["HOME"]).exists())

    def test_both_rate_limited_sources_are_not_partial_success(self):
        records = report(statuses=("failed", "failed"))
        for item in records[0]["source_executions"]:
            item["status"] = "rate-limited"
            item["stop_reason"] = "http-429"
        with self.assertRaisesRegex(SourceError, "rate-limited.*http-429"):
            parse_theharvester_jsonl(payload(records), domain="example.com", limit=250)

    def test_incomplete_python_installation_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            (checkout / ".git").mkdir()
            (checkout / ".git/HEAD").write_text(REVIEWED_UPSTREAM_COMMIT + "\n")
            executable = checkout / ".venv/bin/theHarvester"
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/bin/sh\n")
            executable.chmod(0o700)
            calls = []
            source = TheHarvesterArchiveSource(
                executable_locator=lambda: executable, checkout_locator=lambda: checkout,
                runner=lambda *args, **kwargs: calls.append(args),
            )
            with self.assertRaisesRegex(SourceError, "Python ortamı eksik"):
                source.search("%.example.com")
            self.assertEqual(calls, [])

    def test_missing_or_changed_checkout_never_runs(self):
        called = []
        source = TheHarvesterArchiveSource(
            runner=lambda *args, **kwargs: called.append(args),
            executable_locator=lambda: None, checkout_locator=lambda: None,
        )
        with self.assertRaisesRegex(SourceError, "setup-harvester"):
            source.search("%.example.com")
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()

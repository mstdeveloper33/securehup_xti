"""Strict CERT Polska Warning List source and isolated snapshot lifecycle."""

from contextlib import closing, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from xti.adapters.certpl_warning import (
    CertPlWarningSource,
    MAX_RESPONSE_BYTES,
    parse_certpl_warning_response,
)
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_cti_feeds import SQLiteCtiFeedRepository
from xti.adapters.sqlite_cti_indicators import SQLiteCtiIndicatorRepository
from xti.application.cti_indicators import CtiIndicatorService
from xti.domain.assets import ValidationError
from xti.domain.cti_feeds import (
    CERTPL_CONFIDENCE,
    CERTPL_POLICY,
    CERTPL_SOURCE,
    CERTPL_URL,
)
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def content(*domains: str, version: str = "202610301100") -> bytes:
    lines = [
        "! Title: CERT.PL's Warning List",
        f"! Version: {version}",
        "! Expires: 1 hours",
        "! Homepage: https://cert.pl/lista-ostrzezen/",
        *domains,
    ]
    return ("\n".join(lines) + "\n").encode()


class Response:
    def __init__(self, body, *, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = {
            "Content-Type": "text/plain; charset=utf-8",
            "Content-Encoding": "identity",
            "Content-Length": str(len(body)),
            **(headers or {}),
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def read(self, limit=-1):
        return self.body if limit < 0 else self.body[:limit]


class CertPlWarningTests(unittest.TestCase):
    def test_parser_accepts_only_complete_recent_canonical_domain_snapshot(self):
        snapshot = parse_certpl_warning_response(
            content("login-example.test", "xn--e1awd7f.com", "a.example.test"),
            fetched_at=NOW,
        )
        self.assertEqual(
            (snapshot.source_name, snapshot.source_url),
            (CERTPL_SOURCE, CERTPL_URL),
        )
        self.assertEqual(snapshot.source_record_count, 3)
        self.assertEqual(
            [item.value for item in snapshot.indicators],
            ["a.example.test", "login-example.test", "xn--e1awd7f.com"],
        )
        item = snapshot.indicators[0]
        self.assertEqual((item.indicator_type, item.confidence), ("domain", CERTPL_CONFIDENCE))
        self.assertEqual(item.source_reference, CERTPL_URL)
        self.assertEqual(item.valid_from, "2026-10-30T11:00:00+00:00")
        self.assertEqual(len(item.state_sha256), 64)
        without_final_newline = parse_certpl_warning_response(
            content("example.test")[:-1], fetched_at=NOW,
        )
        self.assertEqual(without_final_newline.source_record_count, 1)

    def test_bad_header_time_lines_duplicates_and_size_fail_whole_snapshot(self):
        fixtures = (
            content("example.test").replace(b"Warning List", b"Unexpected List", 1),
            content("example.test", version="202610270000"),
            content("example.test", version="202610301400"),
            content("Example.test"),
            content("example.test", "example.test"),
            content("not a domain"),
            content("! unexpected-comment"),
            content("example.test").replace(b"\n", b"\r\n"),
            b"x" * (MAX_RESPONSE_BYTES + 1),
        )
        for body in fixtures:
            with self.subTest(size=len(body)), self.assertRaises(SourceError):
                parse_certpl_warning_response(body, fetched_at=NOW)

    def test_transport_is_fixed_bounded_plain_text_and_does_not_leak_remote_error(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(content("example.test"))

        snapshot = CertPlWarningSource(opener=opener, clock=lambda: NOW).fetch()
        self.assertEqual(len(snapshot.indicators), 1)
        request, timeout = calls[0]
        self.assertEqual((request.full_url, timeout), (CERTPL_URL, 30))
        self.assertEqual(request.get_header("Accept"), "text/plain")
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        bad_responses = (
            Response(content("example.test"), status=500),
            Response(content("example.test"), headers={"Content-Type": "text/html"}),
            Response(content("example.test"), headers={"Content-Encoding": "gzip"}),
            Response(
                content("example.test"),
                headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)},
            ),
        )
        for response in bad_responses:
            with self.subTest(headers=response.headers), self.assertRaises(SourceError):
                CertPlWarningSource(
                    opener=lambda *args, value=response, **kwargs: value,
                    clock=lambda: NOW,
                ).fetch()
        with self.assertRaisesRegex(SourceError, "önceki IOC'ler korundu"):
            CertPlWarningSource(
                opener=lambda *args, **kwargs: (_ for _ in ()).throw(
                    URLError("private remote detail"),
                ),
                clock=lambda: NOW,
            ).fetch()

    def test_repository_keeps_source_isolation_and_snapshot_membership_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "data" / "xti.db"
            storage = SQLiteAssetRepository(path)
            storage.initialize()
            indicators = SQLiteCtiIndicatorRepository(path)
            CtiIndicatorService(indicators, clock=lambda: NOW).add(
                "domain", "shared.example", source_name="manual",
                source_reference="local:case", confidence=40,
                description="Independent manual source.",
            )
            with self.assertRaisesRegex(ValidationError, "otomatik besleme"):
                CtiIndicatorService(indicators, clock=lambda: NOW).add(
                    "domain", "forged.example", source_name=CERTPL_SOURCE,
                    source_reference=CERTPL_URL, confidence=50,
                    description="Managed source must not be added manually.",
                )
            repository = SQLiteCtiFeedRepository(path, CERTPL_POLICY)
            first = repository.apply(
                parse_certpl_warning_response(
                    content("old.example", "shared.example"), fetched_at=NOW,
                ),
                started_at=NOW.isoformat(), finished_at=NOW.isoformat(),
            )
            second_time = datetime(2026, 10, 30, 13, tzinfo=timezone.utc)
            second = repository.apply(
                parse_certpl_warning_response(
                    content("new.example", "shared.example", version="202610301230"),
                    fetched_at=second_time,
                ),
                started_at=second_time.isoformat(),
                finished_at=second_time.isoformat(),
            )

            self.assertEqual((first.added_count, first.indicator_count), (2, 2))
            self.assertEqual(
                (second.added_count, second.unchanged_count, second.revoked_count),
                (1, 1, 1),
            )
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM cti_feed_run_items WHERE run_id = ?",
                        (second.id,),
                    ).fetchone()[0],
                    2,
                )
            status = repository.status(run_limit=5)
            self.assertEqual(status.source_name, CERTPL_SOURCE)
            self.assertEqual(status.active_assertion_count, 2)
            details = CtiIndicatorService(
                indicators, clock=lambda: second_time,
            ).lookup("domain", "shared.example")
            self.assertEqual(
                {item.source_name for item in details.assertions},
                {"manual", CERTPL_SOURCE},
            )
            # The separate Feodo source remains empty and readable.
            self.assertEqual(
                SQLiteCtiFeedRepository(path).status(run_limit=5).recent_runs, (),
            )

    def test_cli_refreshes_certpl_and_exact_domain_match_appears_in_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "data"

            def call(*arguments):
                output, error = StringIO(), StringIO()
                with redirect_stdout(output), redirect_stderr(error):
                    code = main(["--data-dir", str(data), "--json", *arguments])
                return code, output.getvalue(), error.getvalue()

            self.assertEqual(call("init")[0], 0)
            self.assertEqual(call("assets", "add", "example.com")[0], 0)
            snapshot = parse_certpl_warning_response(
                content("example.com"), fetched_at=NOW,
            )
            with patch(
                "xti.interfaces.cli.CertPlWarningSource.fetch", return_value=snapshot,
            ):
                code, output, error = call(
                    "analyze", "example.com", "--refresh-ioc", "certpl",
                )
            self.assertEqual((code, error), (0, ""))
            result = json.loads(output)
            self.assertTrue(result["ok"])
            self.assertEqual(result["data"]["refresh_source"], "certpl")
            matches = result["data"]["report"]["ioc_matches"]
            self.assertEqual([(item["indicator_type"], item["value"]) for item in matches], [
                ("domain", "example.com"),
            ])
            status = json.loads(call(
                "ioc", "status", "--source", "certpl",
            )[1])["data"]
            self.assertEqual(status["source_name"], CERTPL_SOURCE)


if __name__ == "__main__":
    unittest.main()

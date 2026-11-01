"""Bounded public ransomware claim preview without Tor or persistence."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from xti.adapters.threatcluster_ransomware import (
    EXPECTED_FEED,
    EXPECTED_LICENSE,
    MAX_RESPONSE_BYTES,
    SOURCE_URL,
    ThreatClusterRansomwareSource,
    parse_threatcluster_ransomware_response,
)
from xti.application.ransomware_claims import RansomwareClaimService
from xti.domain.assets import ValidationError
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


NOW = datetime(2026, 10, 30, 17, tzinfo=timezone.utc)


def claim(
    victim="Example Holding", *, group="example-group", country="TR",
    sector="Technology", discovered="2026-10-30T12:00:00+00:00",
    status="listed", website="example.com",
    post_url="http://examplehiddenservice.onion:8080/post/1",
    **extra,
):
    return {
        "group": group, "victim": victim, "country": country, "sector": sector,
        "discovered": discovered, "post_url": post_url, "status": status,
        "website": website, **extra,
    }


def payload(records=None, **updates):
    records = [claim()] if records is None else records
    value = {
        "feed": EXPECTED_FEED,
        "generated_at": "2026-10-30T16:30:00Z",
        "window_days": 30,
        "count": len(records),
        "note": "Claims published by extortion groups; a listing is not confirmation.",
        "license": EXPECTED_LICENSE,
        "victims": records,
    }
    value.update(updates)
    return value


def content(records=None, **updates):
    return json.dumps(
        payload(records, **updates), ensure_ascii=False, separators=(",", ":"),
    ).encode()


class Response:
    def __init__(self, body, *, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = {
            "Content-Type": "application/json; charset=utf-8",
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


class ThreatClusterRansomwareTests(unittest.TestCase):
    def test_parser_keeps_claim_metadata_but_discards_raw_leak_site_url(self):
        snapshot = parse_threatcluster_ransomware_response(
            content([
                claim(),
                claim(
                    "Old Example", group="second-group", country=None, sector=None,
                    discovered="2026-10-29T10:00:00Z", status="delisted",
                    website=None, post_url=None,
                    delisted_at="2026-10-30T10:00:00+00:00", first_party=True,
                    last_seen_at="2026-10-30T09:00:00+00:00",
                ),
            ]),
            fetched_at=NOW,
        )
        self.assertEqual((snapshot.window_days, snapshot.source_record_count), (30, 2))
        self.assertEqual(len(snapshot.content_sha256), 64)
        first, second = snapshot.claims
        self.assertEqual((first.victim, first.website, first.status), (
            "Example Holding", "example.com", "listed",
        ))
        self.assertTrue(first.source_post_available)
        self.assertEqual((second.status, second.first_party), ("delisted", True))
        self.assertNotIn("onion", repr(snapshot))
        self.assertNotIn("post_url", snapshot.claims[0].__dataclass_fields__)

    def test_parser_rejects_schema_drift_bad_counts_times_duplicates_and_oversize(self):
        base = payload()
        fixtures = []
        changed = deepcopy(base)
        changed["unexpected"] = True
        fixtures.append(changed)
        changed = deepcopy(base)
        changed["count"] = 2
        fixtures.append(changed)
        changed = deepcopy(base)
        changed["license"] = "unknown"
        fixtures.append(changed)
        changed = deepcopy(base)
        changed["generated_at"] = "2026-10-27T00:00:00Z"
        fixtures.append(changed)
        changed = deepcopy(base)
        changed["victims"][0]["status"] = ["listed"]
        fixtures.append(changed)
        changed = deepcopy(base)
        changed["victims"][0]["country"] = "tur"
        fixtures.append(changed)
        changed = deepcopy(base)
        changed["victims"][0]["unexpected"] = "field"
        fixtures.append(changed)
        fixtures.append(payload([claim(), claim()]))
        fixtures.append(payload([claim(discovered="2026-10-31T00:00:00Z")]))
        fixtures.append(payload([claim(delisted_at="2026-10-30T15:00:00Z")]))
        for value in fixtures:
            with self.subTest(keys=value.keys()), self.assertRaises(SourceError):
                parse_threatcluster_ransomware_response(
                    json.dumps(value, ensure_ascii=False).encode(), fetched_at=NOW,
                )
        with self.assertRaises(SourceError):
            parse_threatcluster_ransomware_response(
                b"x" * (MAX_RESPONSE_BYTES + 1), fetched_at=NOW,
            )
        with self.assertRaises(SourceError):
            parse_threatcluster_ransomware_response(
                b'{"feed":"x","feed":"y"}', fetched_at=NOW,
            )

    def test_transport_is_fixed_bounded_json_and_hides_remote_error_detail(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(content())

        result = ThreatClusterRansomwareSource(opener=opener, clock=lambda: NOW).fetch()
        self.assertEqual(result.source_record_count, 1)
        request, timeout = calls[0]
        self.assertEqual((request.full_url, timeout), (SOURCE_URL, 30))
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        bad_responses = (
            Response(content(), status=500),
            Response(content(), headers={"Content-Type": "text/html"}),
            Response(content(), headers={"Content-Encoding": "gzip"}),
            Response(content(), headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)}),
        )
        for response in bad_responses:
            with self.subTest(headers=response.headers), self.assertRaises(SourceError):
                ThreatClusterRansomwareSource(
                    opener=lambda *args, value=response, **kwargs: value,
                    clock=lambda: NOW,
                ).fetch()
        with self.assertRaisesRegex(SourceError, "sonuç üretilmedi") as raised:
            ThreatClusterRansomwareSource(
                opener=lambda *args, **kwargs: (_ for _ in ()).throw(
                    URLError("private remote detail"),
                ),
                clock=lambda: NOW,
            ).fetch()
        self.assertNotIn("private remote detail", str(raised.exception))

    def test_service_filters_locally_ranks_exact_values_and_validates_limits(self):
        snapshot = parse_threatcluster_ransomware_response(
            content([
                claim("Newest Other", website="other.example"),
                claim(
                    "Example Holding", website="example.com",
                    discovered="2026-10-29T12:00:00Z",
                ),
                claim(
                    "Example Old", group="other-group", website="old.example",
                    discovered="2026-10-28T12:00:00Z", status="delisted",
                    delisted_at="2026-10-29T12:00:00Z",
                ),
            ]),
            fetched_at=NOW,
        )

        class Source:
            def fetch(self):
                return snapshot

        service = RansomwareClaimService(Source())
        exact = service.recent("example.com", limit=10)
        self.assertEqual([item.victim for item in exact.claims], ["Example Holding"])
        filtered = service.recent("example", status="delisted", limit=10)
        self.assertEqual([item.victim for item in filtered.claims], ["Example Old"])
        limited = service.recent("example", limit=1)
        self.assertEqual((limited.matched_count, limited.displayed_count, limited.has_more), (
            3, 1, True,
        ))
        for bad_limit in (0, 101, True):
            with self.subTest(limit=bad_limit), self.assertRaises(ValidationError):
                service.recent(limit=bad_limit)

    def test_cli_preview_needs_no_database_and_never_emits_onion_url(self):
        snapshot = parse_threatcluster_ransomware_response(content(), fetched_at=NOW)
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "not-created"

            def invoke(*arguments, as_json=True):
                stdout, stderr = StringIO(), StringIO()
                values = ["--data-dir", str(data)]
                if as_json:
                    values.append("--json")
                with (
                    patch(
                        "xti.interfaces.cli.ThreatClusterRansomwareSource.fetch",
                        return_value=snapshot,
                    ),
                    redirect_stdout(stdout), redirect_stderr(stderr),
                ):
                    code = main([*values, "ransomware", "recent", *arguments])
                return code, stdout.getvalue(), stderr.getvalue()

            code, stdout, stderr = invoke("example.com", "--limit", "10")
            self.assertEqual((code, stderr), (0, ""))
            report = json.loads(stdout)
            self.assertTrue(report["ok"])
            self.assertEqual(report["data"]["matched_count"], 1)
            self.assertNotIn("post_url", stdout)
            self.assertNotIn(".onion", stdout)
            code, human, stderr = invoke("example", as_json=False)
            self.assertEqual((code, stderr), (0, ""))
            self.assertIn("doğrulanmamış iddialardır", human)
            self.assertIn("ham leak-site bağlantısı", human)
            self.assertNotIn(".onion", human)
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()

"""Strict Feodo Tracker parsing and bounded fixed-endpoint transport."""

import json
import unittest
from urllib.error import URLError

from xti.adapters.feodo_tracker import (
    FeodoTrackerSource,
    MAX_RESPONSE_BYTES,
    parse_feodo_response,
)
from xti.domain.cti_feeds import FEODO_CONFIDENCE, FEODO_SOURCE, FEODO_URL
from xti.ports.discovery import SourceError


def record(
    ip="192.0.2.10", *, port=443, status="online", malware="Emotet",
    first_seen="2026-10-28 10:30:00", last_online="2026-10-30",
):
    return {
        "ip_address": ip, "port": port, "status": status, "hostname": None,
        "as_number": 64500, "as_name": " Example   Network ", "country": "tr",
        "first_seen": first_seen, "last_online": last_online, "malware": malware,
    }


def content(records=None):
    records = [record()] if records is None else records
    return json.dumps(records, separators=(",", ":")).encode()


class Response:
    def __init__(self, body, *, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = {
            "Content-Type": "application/json", "Content-Encoding": "identity",
            "Content-Length": str(len(body)), **(headers or {}),
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def read(self, limit=-1):
        return self.body if limit < 0 else self.body[:limit]


class FeodoTrackerTests(unittest.TestCase):
    def test_parser_merges_rows_per_ip_and_preserves_complete_snapshot_counts(self):
        body = content([
            record(port=443, malware="Emotet", first_seen="2026-10-28 10:30:00"),
            record(port=8443, status="offline", malware="QakBot",
                   first_seen="2026-10-27 08:00:00"),
            record(ip="2001:0db8::1", port=80, malware="Dridex"),
        ])
        snapshot = parse_feodo_response(body)
        self.assertEqual((snapshot.source_name, snapshot.source_url), (FEODO_SOURCE, FEODO_URL))
        self.assertEqual((snapshot.source_record_count, len(snapshot.indicators)), (3, 2))
        item = snapshot.indicators[0]
        self.assertEqual((item.indicator_type, item.value), ("ipv4", "192.0.2.10"))
        self.assertEqual(item.confidence, FEODO_CONFIDENCE)
        self.assertIn("Emotet, QakBot", item.description)
        self.assertIn("443, 8443", item.description)
        self.assertIn("offline, online", item.description)
        self.assertEqual(item.valid_from, "2026-10-27T08:00:00+00:00")
        self.assertEqual(item.last_seen_at, "2026-10-30T00:00:00+00:00")
        self.assertEqual(
            item.source_reference,
            "https://feodotracker.abuse.ch/browse/host/192.0.2.10/",
        )
        self.assertEqual(len(item.state_sha256), 64)
        self.assertEqual(len(snapshot.content_sha256), 64)

    def test_empty_complete_list_is_valid_and_malformed_record_fails_whole_snapshot(self):
        empty = parse_feodo_response(b"[]")
        self.assertEqual((empty.source_record_count, empty.indicators), (0, ()))
        invalid_records = [
            {**record(), "ip_address": "not-an-ip"},
            {**record(), "port": True},
            {**record(), "status": "unknown"},
            {**record(), "country": "TUR"},
            {**record(), "first_seen": "2026-10-30"},
            {**record(), "last_online": "2026-99-99"},
            {**record(), "malware": "bad\nname"},
            {**record(), "unexpected": "field"},
        ]
        fixtures = [
            *(content([value]) for value in invalid_records),
            content([record(), record()]),
            b'{"x":1,"x":2}',
            b"[NaN]",
            b"[" + b" " * MAX_RESPONSE_BYTES,
        ]
        for body in fixtures:
            with self.subTest(size=len(body)), self.assertRaises(SourceError):
                parse_feodo_response(body)

    def test_transport_uses_fixed_endpoint_identity_encoding_and_bounds(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(content())

        snapshot = FeodoTrackerSource(opener=opener).fetch()
        self.assertEqual(len(snapshot.indicators), 1)
        request, timeout = calls[0]
        self.assertEqual((request.full_url, timeout), (FEODO_URL, 30))
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
                FeodoTrackerSource(
                    opener=lambda *args, value=response, **kwargs: value,
                ).fetch()
        with self.assertRaisesRegex(SourceError, "önceki IOC'ler korundu"):
            FeodoTrackerSource(
                opener=lambda *args, **kwargs: (_ for _ in ()).throw(
                    URLError("private remote detail"),
                ),
            ).fetch()


if __name__ == "__main__":
    unittest.main()

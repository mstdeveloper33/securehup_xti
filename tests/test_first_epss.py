"""Strict FIRST EPSS daily CSV parsing and bounded transport."""

import gzip
import unittest
from urllib.error import URLError

from xti.adapters.first_epss import (
    FirstEpssSource,
    MAX_COMPRESSED_BYTES,
    parse_epss_response,
)
from xti.domain.vulnerability import FIRST_EPSS_URL
from xti.ports.discovery import SourceError


def content(rows=None, *, metadata=None, header="cve,epss,percentile"):
    rows = rows or ["CVE-2021-44228,0.123400,0.987600"]
    metadata = metadata or "#model_version:v2026.06.15,score_date:2026-10-29T12:03:14Z"
    return gzip.compress(("\n".join([metadata, header, *rows]) + "\n").encode())


class Response:
    def __init__(self, body, *, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = {
            "Content-Type": "binary/octet-stream",
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


class FirstEpssTests(unittest.TestCase):
    def test_parser_normalizes_probability_and_sorts(self):
        snapshot = parse_epss_response(content([
            "CVE-2024-9999,1.000000,1.0",
            "CVE-2021-44228,0.123400,6e-05",
        ]))
        self.assertEqual(snapshot.model_version, "v2026.06.15")
        self.assertEqual(snapshot.score_date, "2026-10-29")
        self.assertEqual([item.cve_id for item in snapshot.entries], [
            "CVE-2021-44228", "CVE-2024-9999",
        ])
        self.assertEqual(snapshot.entries[0].epss, "0.1234")
        self.assertEqual(snapshot.entries[0].percentile, "0.00006")
        self.assertEqual(snapshot.entries[1].epss, "1")
        self.assertEqual(len(snapshot.content_sha256), 64)

    def test_invalid_metadata_header_rows_duplicates_controls_and_gzip_fail_whole_file(self):
        fixtures = (
            content(metadata="#model_version:bad,score_date:2026-10-29T12:00:00Z"),
            content(header="cve,percentile,epss"),
            content(["CVE-2021-44228,1.1,0.9"]),
            content(["CVE-2021-44228,1e-99,0.9"]),
            content(["CVE-2021-44228,0.1,0.9", "CVE-2021-44228,0.2,0.8"]),
            content(["CVE-2021-44228,0.1,0.9,extra"]),
            b"not-gzip",
            b"x" * (MAX_COMPRESSED_BYTES + 1),
        )
        for body in fixtures:
            with self.subTest(size=len(body)):
                with self.assertRaises(SourceError):
                    parse_epss_response(body)

    def test_transport_uses_fixed_daily_url_and_bounded_identity_response(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(content())

        snapshot = FirstEpssSource(opener=opener).fetch()
        self.assertEqual(len(snapshot.entries), 1)
        request, timeout = calls[0]
        self.assertEqual(request.full_url, FIRST_EPSS_URL)
        self.assertEqual(timeout, 30)
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        for response in (
            Response(content(), status=500),
            Response(content(), headers={"Content-Type": "text/html"}),
            Response(content(), headers={"Content-Encoding": "gzip"}),
            Response(content(), headers={"Content-Length": str(MAX_COMPRESSED_BYTES + 1)}),
        ):
            with self.subTest(headers=response.headers, status=response.status):
                with self.assertRaises(SourceError):
                    FirstEpssSource(opener=lambda *args, value=response, **kwargs: value).fetch()
        with self.assertRaisesRegex(SourceError, "önceki katalog korundu"):
            FirstEpssSource(opener=lambda *args, **kwargs: (_ for _ in ()).throw(
                URLError("private remote detail"),
            )).fetch()


if __name__ == "__main__":
    unittest.main()

"""Strict CISA KEV parsing and bounded official-source transport."""

import json
import unittest
from urllib.error import URLError

from xti.adapters.cisa_kev import CisaKevSource, MAX_RESPONSE_BYTES, parse_kev_response
from xti.domain.vulnerability import CISA_KEV_URL
from xti.ports.discovery import SourceError


def entry(cve="CVE-2021-44228", *, product="Log4j2"):
    return {
        "cveID": cve,
        "vendorProject": "Apache",
        "product": product,
        "vulnerabilityName": "Apache Log4j2 Remote Code Execution",
        "dateAdded": "2021-12-10",
        "shortDescription": "A remote code execution vulnerability exists.",
        "requiredAction": "Apply updates per vendor instructions.",
        "dueDate": "2021-12-24",
        "knownRansomwareCampaignUse": "Known",
        "notes": "https://example.invalid/advisory",
        "cwes": ["CWE-502", "CWE-20"],
    }


def content(entries=None, *, count=None):
    entries = [entry()] if entries is None else entries
    return json.dumps({
        "title": "CISA Known Exploited Vulnerabilities Catalog",
        "catalogVersion": "2026.10.29",
        "dateReleased": "2026-10-29T12:00:00Z",
        "count": len(entries) if count is None else count,
        "vulnerabilities": entries,
    }, separators=(",", ":")).encode()


class Response:
    def __init__(self, body, *, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = {
            "Content-Type": "application/json",
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


class CisaKevTests(unittest.TestCase):
    def test_parser_normalizes_sorted_unique_entries_and_metadata(self):
        body = content([
            {
                **entry("CVE-2024-9999", product=" Second Product "),
                "vulnerabilityName": " Leading source whitespace ",
            },
            entry("CVE-2021-44228", product="Log4j2"),
        ])
        snapshot = parse_kev_response(body)
        self.assertEqual(snapshot.source_url, CISA_KEV_URL)
        self.assertEqual(snapshot.catalog_version, "2026.10.29")
        self.assertEqual(
            [item.cve_id for item in snapshot.entries],
            ["CVE-2021-44228", "CVE-2024-9999"],
        )
        self.assertEqual(snapshot.entries[0].cwes, ("CWE-20", "CWE-502"))
        self.assertEqual(snapshot.entries[1].product, "Second Product")
        self.assertEqual(snapshot.entries[1].vulnerability_name, "Leading source whitespace")
        self.assertEqual(len(snapshot.content_sha256), 64)

    def test_invalid_count_duplicate_date_control_and_size_fail_whole_catalog(self):
        fixtures = [
            content(count=2),
            content([entry(), entry()]),
            content([{**entry(), "dateAdded": "2026-99-99"}]),
            content([{**entry(), "product": "bad\nproduct"}]),
            b"{" + b" " * MAX_RESPONSE_BYTES,
        ]
        for body in fixtures:
            with self.subTest(size=len(body)):
                with self.assertRaises(SourceError):
                    parse_kev_response(body)

    def test_transport_uses_only_fixed_json_endpoint_and_bounded_identity_response(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(content())

        snapshot = CisaKevSource(opener=opener).fetch()
        self.assertEqual(len(snapshot.entries), 1)
        request, timeout = calls[0]
        self.assertEqual(request.full_url, CISA_KEV_URL)
        self.assertEqual(timeout, 30)
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("Accept-encoding"), "identity")

        for response in (
            Response(content(), status=500),
            Response(content(), headers={"Content-Type": "text/html"}),
            Response(content(), headers={"Content-Encoding": "gzip"}),
            Response(content(), headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)}),
        ):
            with self.subTest(headers=response.headers, status=response.status):
                with self.assertRaises(SourceError):
                    CisaKevSource(opener=lambda *args, value=response, **kwargs: value).fetch()
        with self.assertRaisesRegex(SourceError, "önceki katalog korundu"):
            CisaKevSource(opener=lambda *args, **kwargs: (_ for _ in ()).throw(
                URLError("private remote detail"),
            )).fetch()


if __name__ == "__main__":
    unittest.main()

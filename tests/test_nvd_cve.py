"""Strict single-CVE NVD API parsing and bounded transport."""

import json
import unittest
from urllib.error import URLError

from xti.adapters.nvd_cve import MAX_RESPONSE_BYTES, NvdCveSource, parse_nvd_response
from xti.domain.vulnerability import nvd_cve_url
from xti.ports.discovery import SourceError


def payload(*, cve_id="CVE-2021-44228", score=10.0, total=1):
    cve = {
        "id": cve_id,
        "sourceIdentifier": "security@example.org",
        "published": "2021-12-10T10:15:09.143",
        "lastModified": "2026-08-11T19:33:44.513",
        "vulnStatus": "Analyzed",
        "descriptions": [
            {"lang": "es", "value": "Descripción"},
            {"lang": "en", "value": "Line one.\nLine two."},
        ],
        "metrics": {
            "cvssMetricV31": [{
                "source": "nvd@nist.gov", "type": "Primary",
                "cvssData": {
                    "version": "3.1", "vectorString": "CVSS:3.1/AV:N/AC:L",
                    "baseScore": score, "baseSeverity": "CRITICAL",
                },
                "exploitabilityScore": 3.9, "impactScore": 6.0,
            }],
        },
        "weaknesses": [{
            "description": [{"lang": "en", "value": "CWE-917"}],
        }],
        "references": [{"url": "https://example.org/advisory"}],
        "configurations": [{"nodes": []}],
    }
    body = {
        "resultsPerPage": total, "startIndex": 0, "totalResults": total,
        "format": "NVD_CVE", "version": "2.0",
        "timestamp": "2026-10-29T15:01:05.762",
        "vulnerabilities": [{"cve": cve}] if total else [],
    }
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()


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


class NvdCveSourceTests(unittest.TestCase):
    def test_parser_keeps_source_cvss_and_canonical_complete_record(self):
        result = parse_nvd_response(payload(), "cve-2021-44228")
        self.assertEqual(result.record.cve_id, "CVE-2021-44228")
        self.assertEqual(result.record.english_description, "Line one. Line two.")
        self.assertEqual(result.record.cwes, ("CWE-917",))
        self.assertEqual(result.record.reference_count, 1)
        metric = result.record.cvss_metrics[0]
        self.assertEqual(
            (metric.source, metric.version, metric.base_score, metric.base_severity),
            ("nvd@nist.gov", "3.1", "10", "CRITICAL"),
        )
        self.assertEqual(json.loads(result.record_json)["configurations"], [{"nodes": []}])
        self.assertEqual(result.source_url, nvd_cve_url("CVE-2021-44228"))

    def test_mismatch_missing_duplicate_bad_metric_reference_and_size_fail_whole_record(self):
        duplicate = payload().replace(
            b'"format":"NVD_CVE"', b'"format":"NVD_CVE","format":"NVD_CVE"',
        )
        bad_reference = json.loads(payload())
        bad_reference["vulnerabilities"][0]["cve"]["references"][0]["url"] = "file:///tmp/x"
        fixtures = (
            (payload(cve_id="CVE-2024-9999"), "CVE-2021-44228"),
            (payload(total=0), "CVE-2021-44228"),
            (duplicate, "CVE-2021-44228"),
            (payload(score=11.0), "CVE-2021-44228"),
            (json.dumps(bad_reference).encode(), "CVE-2021-44228"),
            (b"x" * (MAX_RESPONSE_BYTES + 1), "CVE-2021-44228"),
        )
        for body, expected in fixtures:
            with self.subTest(size=len(body)):
                with self.assertRaises(SourceError):
                    parse_nvd_response(body, expected)

    def test_transport_uses_one_fixed_identity_json_request_and_bounds(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(payload())

        result = NvdCveSource(opener=opener).fetch("CVE-2021-44228")
        self.assertEqual(result.record.cve_id, "CVE-2021-44228")
        request, timeout = calls[0]
        self.assertEqual(request.full_url, nvd_cve_url("CVE-2021-44228"))
        self.assertEqual(timeout, 30)
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        for response in (
            Response(payload(), status=500),
            Response(payload(), headers={"Content-Type": "text/html"}),
            Response(payload(), headers={"Content-Encoding": "gzip"}),
            Response(payload(), headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)}),
        ):
            with self.subTest(headers=response.headers, status=response.status):
                with self.assertRaises(SourceError):
                    NvdCveSource(opener=lambda *args, value=response, **kwargs: value).fetch(
                        "CVE-2021-44228"
                    )
        with self.assertRaisesRegex(SourceError, "önceki kayıt korundu"):
            NvdCveSource(opener=lambda *args, **kwargs: (_ for _ in ()).throw(
                URLError("private remote detail"),
            )).fetch("CVE-2021-44228")


if __name__ == "__main__":
    unittest.main()

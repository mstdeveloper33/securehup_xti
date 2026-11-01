"""Bounded OSV advisory preview without automatic exposure decisions."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from xti.adapters.osv_dev import (
    MAX_RESPONSE_BYTES,
    OsvDevAdvisorySource,
    parse_osv_response,
)
from xti.application.osv_advisory import OsvAdvisoryPreviewService
from xti.domain.assets import ValidationError
from xti.domain.osv_advisory import osv_vulnerability_url
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


CVE = "CVE-2026-4001"


def payload(*, record_id="GHSA-abcd-1234-5678", alias=CVE):
    return json.dumps({
        "schema_version": "1.6.0",
        "id": record_id,
        "aliases": [alias],
        "upstream": [],
        "modified": "2026-10-29T18:00:00Z",
        "published": "2026-10-20T12:00:00Z",
        "summary": "Example package vulnerability",
        "details": "Line one.\nLine two.",
        "affected": [{
            "package": {
                "ecosystem": "PyPI", "name": "example-package",
                "purl": "pkg:pypi/example-package",
            },
            "versions": ["1.0.0", "1.0.1"],
            "ranges": [{
                "type": "ECOSYSTEM",
                "events": [{"introduced": "1.0.0"}, {"fixed": "1.0.2"}],
            }],
        }],
        "references": [
            {"type": "ADVISORY", "url": "https://vendor.example/security/4001"},
            {"type": "WEB", "url": "https://osv.example/record/4001"},
        ],
    }, ensure_ascii=False, separators=(",", ":")).encode()


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


class OsvAdvisoryTests(unittest.TestCase):
    def test_parser_keeps_alias_package_ranges_and_advisory_references_separate(self):
        result = parse_osv_response(payload(), CVE.lower())
        advisory = result.advisory
        self.assertEqual(advisory.queried_cve_id, CVE)
        self.assertEqual(advisory.record_id, "GHSA-abcd-1234-5678")
        self.assertEqual(advisory.aliases, (CVE,))
        self.assertEqual(advisory.details, "Line one. Line two.")
        self.assertEqual(advisory.advisory_references,
                         ("https://vendor.example/security/4001",))
        self.assertEqual(advisory.other_reference_count, 1)
        affected = advisory.affected[0]
        self.assertEqual((affected.ecosystem, affected.name),
                         ("PyPI", "example-package"))
        self.assertEqual(affected.versions_count, 2)
        self.assertEqual(affected.range_count, 1)
        self.assertEqual(affected.range_types, ("ECOSYSTEM",))
        self.assertEqual(affected.single_range_event_order, ("introduced", "fixed"))
        self.assertEqual(affected.introduced_versions, ("1.0.0",))
        self.assertEqual(affected.fixed_versions, ("1.0.2",))
        self.assertEqual(result.source_url, osv_vulnerability_url(CVE))

    def test_mismatch_duplicate_bad_event_url_time_and_size_fail_whole_preview(self):
        duplicate = payload().replace(
            b'"id":"GHSA-abcd-1234-5678"',
            b'"id":"GHSA-abcd-1234-5678","id":"GHSA-abcd-1234-5678"',
        )
        mismatch = payload(alias="CVE-2026-4999")
        bad_event = json.loads(payload())
        bad_event["affected"][0]["ranges"][0]["events"][0]["fixed"] = "1.0.0"
        bad_url = json.loads(payload())
        bad_url["references"][0]["url"] = "file:///tmp/advisory"
        bad_time = json.loads(payload())
        bad_time["published"] = "2027-10-20T12:00:00Z"
        fixtures = (
            duplicate, mismatch, json.dumps(bad_event).encode(),
            json.dumps(bad_url).encode(), json.dumps(bad_time).encode(),
            b"x" * (MAX_RESPONSE_BYTES + 1),
        )
        for body in fixtures:
            with self.subTest(size=len(body)):
                with self.assertRaises(SourceError):
                    parse_osv_response(body, CVE)

    def test_transport_uses_fixed_identity_endpoint_and_bounded_json(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(payload())

        result = OsvDevAdvisorySource(opener=opener).fetch(CVE.lower())
        self.assertEqual(result.advisory.queried_cve_id, CVE)
        request, timeout = calls[0]
        self.assertEqual(request.full_url, osv_vulnerability_url(CVE))
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
                    OsvDevAdvisorySource(
                        opener=lambda *args, value=response, **kwargs: value,
                    ).fetch(CVE)
        with self.assertRaisesRegex(SourceError, "güvenli bağlantı"):
            OsvDevAdvisorySource(opener=lambda *args, **kwargs: (_ for _ in ()).throw(
                URLError("private remote detail"),
            )).fetch(CVE)

    def test_service_limits_before_network_and_preview_does_not_create_storage(self):
        snapshot = parse_osv_response(payload(), CVE)

        class Source:
            calls = 0

            def fetch(self, cve_id):
                self.calls += 1
                return snapshot

        source = Source()
        service = OsvAdvisoryPreviewService(source)
        with self.assertRaises(ValidationError):
            service.preview(CVE, affected_limit=0)
        self.assertEqual(source.calls, 0)
        report = service.preview(CVE, affected_limit=1, reference_limit=1)
        self.assertEqual((report.total_affected_count, len(report.affected)), (1, 1))
        self.assertIn("üretici kararı", report.notes[0])

        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "missing-data"
            stdout, stderr = StringIO(), StringIO()
            with patch.object(OsvDevAdvisorySource, "fetch", return_value=snapshot) as fetch:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([
                        "--data-dir", str(data), "--json", "vuln",
                        "advisory-preview", CVE,
                    ])
            self.assertEqual((code, stderr.getvalue()), (0, ""))
            result = json.loads(stdout.getvalue())["data"]
            self.assertEqual(result["record_id"], "GHSA-abcd-1234-5678")
            self.assertEqual(result["total_advisory_reference_count"], 1)
            fetch.assert_called_once_with(CVE)
            self.assertFalse(data.exists())

            stdout, stderr = StringIO(), StringIO()
            with patch.object(
                OsvDevAdvisorySource, "fetch",
                side_effect=SourceError("OSV bağlantısı tamamlanamadı."),
            ):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([
                        "--data-dir", str(data), "--json", "vuln",
                        "advisory-preview", CVE,
                    ])
            self.assertEqual(code, 3)
            error = json.loads(stderr.getvalue())["error"]
            self.assertEqual(error["code"], "source_error")
            self.assertEqual(error["message"], "OSV bağlantısı tamamlanamadı.")
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()

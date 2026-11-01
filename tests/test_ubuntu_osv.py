"""Bounded Canonical Ubuntu OSV single-record preview."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from xti.adapters.osv_dev import MAX_RESPONSE_BYTES
from xti.adapters.ubuntu_osv import (
    UbuntuOsvAdvisorySource,
    parse_ubuntu_osv_response,
)
from xti.application.ubuntu_osv import UbuntuOsvPreviewService
from xti.domain.assets import ValidationError
from xti.domain.ubuntu_osv import UBUNTU_OSV_SOURCE, ubuntu_osv_url
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


CVE = "CVE-2025-6491"


def payload(*, record_id=f"UBUNTU-{CVE}", upstream=CVE, ecosystem="Ubuntu:24.04:LTS"):
    return json.dumps({
        "schema_version": "1.7.0",
        "id": record_id,
        "aliases": [],
        "upstream": [upstream],
        "modified": "2026-10-20T18:00:00Z",
        "published": "2025-07-13T22:15:00Z",
        "details": "Ubuntu package vulnerability",
        "affected": [{
            "package": {
                "ecosystem": ecosystem,
                "name": "php8.4",
                "purl": "pkg:deb/ubuntu/php8.4@8.4.5-1ubuntu1",
            },
            "versions": ["8.4.5-1ubuntu1"],
            "ranges": [{
                "type": "ECOSYSTEM",
                "events": [{"introduced": "0"}, {"fixed": "8.4.5-1ubuntu1.1"}],
            }],
        }],
        "references": [
            {"type": "ADVISORY", "url": "https://ubuntu.com/security/notices/USN-7648-1"},
            {"type": "REPORT", "url": f"https://ubuntu.com/security/{CVE}"},
        ],
    }, separators=(",", ":")).encode()


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


class UbuntuOsvTests(unittest.TestCase):
    def test_parser_requires_exact_ubuntu_record_upstream_and_ecosystem(self):
        snapshot = parse_ubuntu_osv_response(payload(), CVE.lower())
        self.assertEqual(snapshot.source, UBUNTU_OSV_SOURCE)
        self.assertEqual(snapshot.source_url, ubuntu_osv_url(CVE))
        self.assertEqual(snapshot.advisory.record_id, f"UBUNTU-{CVE}")
        self.assertEqual(snapshot.advisory.upstream, (CVE,))
        affected = snapshot.advisory.affected[0]
        self.assertEqual((affected.ecosystem, affected.name), ("Ubuntu:24.04:LTS", "php8.4"))
        self.assertEqual(affected.range_count, 1)
        self.assertEqual(affected.single_range_event_order, ("introduced", "fixed"))
        self.assertEqual(affected.introduced_versions, ("0",))
        self.assertEqual(affected.fixed_versions, ("8.4.5-1ubuntu1.1",))

        invalid = (
            payload(record_id="UBUNTU-CVE-2025-9999"),
            payload(upstream="CVE-2025-9999"),
            payload(ecosystem="Debian:12"),
            payload().replace(b'"id":"UBUNTU-CVE-2025-6491"',
                              b'"id":"UBUNTU-CVE-2025-6491","id":"UBUNTU-CVE-2025-6491"'),
            b"x" * (MAX_RESPONSE_BYTES + 1),
        )
        for body in invalid:
            with self.subTest(size=len(body)):
                with self.assertRaises(SourceError):
                    parse_ubuntu_osv_response(body, CVE)

    def test_transport_uses_fixed_canonical_path_no_redirect_and_bounds(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(payload())

        snapshot = UbuntuOsvAdvisorySource(opener=opener).fetch(CVE.lower())
        self.assertEqual(snapshot.advisory.queried_cve_id, CVE)
        request, timeout = calls[0]
        self.assertEqual(request.full_url, ubuntu_osv_url(CVE))
        self.assertEqual(timeout, 30)
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        for response in (
            Response(payload(), status=500),
            Response(payload(), headers={"Content-Type": "application/octet-stream"}),
            Response(payload(), headers={"Content-Encoding": "gzip"}),
            Response(payload(), headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)}),
        ):
            with self.subTest(headers=response.headers, status=response.status):
                with self.assertRaises(SourceError):
                    UbuntuOsvAdvisorySource(
                        opener=lambda *args, value=response, **kwargs: value,
                    ).fetch(CVE)
        with self.assertRaisesRegex(SourceError, "güvenli bağlantı"):
            UbuntuOsvAdvisorySource(
                opener=lambda *args, **kwargs: (_ for _ in ()).throw(URLError("private")),
            ).fetch(CVE)

    def test_service_and_terminal_are_bounded_write_free_and_clear_about_scope(self):
        snapshot = parse_ubuntu_osv_response(payload(), CVE)

        class Source:
            calls = 0

            def fetch(self, cve_id):
                self.calls += 1
                return snapshot

        source = Source()
        service = UbuntuOsvPreviewService(source)
        with self.assertRaises(ValidationError):
            service.preview(CVE, affected_limit=0)
        self.assertEqual(source.calls, 0)
        report = service.preview(CVE, affected_limit=1, reference_limit=1)
        self.assertEqual(report.source, UBUNTU_OSV_SOURCE)
        self.assertEqual(report.total_affected_count, 1)
        self.assertIn("başka dağıtımlar", report.notes[0])

        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "missing"
            stdout, stderr = StringIO(), StringIO()
            with patch.object(UbuntuOsvAdvisorySource, "fetch", return_value=snapshot):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([
                        "--data-dir", str(data), "--json", "vuln", "ubuntu-preview", CVE,
                        "--affected-limit", "1", "--reference-limit", "1",
                    ])
            self.assertEqual((code, stderr.getvalue()), (0, ""))
            result = json.loads(stdout.getvalue())["data"]
            self.assertEqual(result["record_id"], f"UBUNTU-{CVE}")
            self.assertEqual(result["affected"][0]["ecosystem"], "Ubuntu:24.04:LTS")
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()

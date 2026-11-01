"""Official SUSE per-CVE CSAF VEX preview."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from xti.adapters.suse_csaf_vex import SuseCsafVexSource, parse_suse_vex_response
from xti.application.vendor_advisory import VendorAdvisoryPreviewService
from xti.domain.vendor_advisory import suse_vex_url
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


CVE = "CVE-2014-0160"
COMPONENT = "SUSE Linux Enterprise Server 12:openssl-1.0.1i-2.7"


def payload():
    return json.dumps({
        "document": {
            "category": "csaf_vex", "csaf_version": "2.0",
            "publisher": {
                "category": "vendor", "name": "SUSE Product Security Team",
                "namespace": "https://www.suse.com/",
            },
            "title": "SUSE CVE CVE-2014-0160",
            "tracking": {
                "id": CVE, "status": "interim", "version": "29",
                "initial_release_date": "2023-02-15T05:32:37Z",
                "current_release_date": "2026-10-17T02:36:25Z",
                "revision_history": [{
                    "date": "2023-02-15T05:32:37Z", "number": "2",
                    "summary": "Current version",
                }],
            },
            "aggregate_severity": {"text": "important"},
        },
        "product_tree": {
            "branches": [{
                "category": "vendor", "name": "SUSE", "branches": [{
                    "category": "product_name", "name": "SLES 12",
                    "product": {
                        "name": "SUSE Linux Enterprise Server 12",
                        "product_id": "SUSE Linux Enterprise Server 12",
                        "product_identification_helper": {
                            "cpe": "cpe:/o:suse:sles:12",
                        },
                    },
                }, {
                    "category": "product_version", "name": "openssl-1.0.1i-2.7",
                    "product": {
                        "name": "openssl-1.0.1i-2.7", "product_id": "openssl-1.0.1i-2.7",
                        "product_identification_helper": {
                            "purl": "pkg:rpm/suse/openssl@1.0.1i-2.7",
                            "cpe": "cpe:2.3:a:openssl:openssl:1.0.1i:*:*:*:*:*:*:*",
                        },
                    },
                }],
            }],
            "relationships": [{
                "category": "default_component_of",
                "product_reference": "openssl-1.0.1i-2.7",
                "relates_to_product_reference": "SUSE Linux Enterprise Server 12",
                "full_product_name": {"name": "openssl in SLES 12", "product_id": COMPONENT},
            }],
        },
        "vulnerabilities": [{
            "cve": CVE, "title": CVE,
            "product_status": {"known_affected": [], "recommended": [COMPONENT]},
            "remediations": [{
                "category": "vendor_fix", "details": "Install the SUSE update.",
                "product_ids": [COMPONENT],
            }],
        }],
    }, separators=(",", ":")).encode()


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


class SuseVendorAdvisoryTests(unittest.TestCase):
    def test_url_uses_2023_backfill_and_current_cve_year(self):
        self.assertEqual(
            suse_vex_url(CVE),
            "https://ftp.suse.com/pub/projects/security/csaf-vex/2023/cve-2014-0160.json",
        )
        self.assertEqual(
            suse_vex_url("CVE-2026-4001"),
            "https://ftp.suse.com/pub/projects/security/csaf-vex/2026/cve-2026-4001.json",
        )

    def test_parser_accepts_official_empty_bucket_spaces_and_cpe23(self):
        result = parse_suse_vex_response(payload(), CVE.lower())
        self.assertEqual(result.advisory.provider, "SUSE Product Security Team")
        self.assertEqual(result.source_url, suse_vex_url(CVE))
        self.assertEqual(
            [(item.status, len(item.products)) for item in result.advisory.product_statuses],
            [("recommended", 1)],
        )
        product = result.advisory.product_statuses[0].products[0]
        self.assertEqual(product.product_id, COMPONENT)
        self.assertTrue(product.component_purl.startswith("pkg:rpm/suse/"))
        self.assertEqual(result.advisory.remediations[0].target_count, 1)

    def test_publisher_identity_and_all_empty_statuses_fail_closed(self):
        wrong = json.loads(payload())
        wrong["document"]["publisher"]["namespace"] = "https://example.invalid/"
        empty = json.loads(payload())
        empty["vulnerabilities"][0]["product_status"] = {"known_affected": []}
        for document in (wrong, empty):
            with self.subTest(document=document):
                with self.assertRaises(SourceError):
                    parse_suse_vex_response(json.dumps(document).encode(), CVE)

    def test_transport_uses_fixed_endpoint_and_cli_is_write_free(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(payload())

        snapshot = SuseCsafVexSource(opener=opener).fetch(CVE)
        request, timeout = calls[0]
        self.assertEqual(request.full_url, suse_vex_url(CVE))
        self.assertEqual(timeout, 30)
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        report = VendorAdvisoryPreviewService(
            SuseCsafVexSource(opener=lambda *args, **kwargs: Response(payload())),
        ).preview(CVE)
        self.assertIn("yalnız SUSE", report.notes[0])

        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "missing-data"
            stdout, stderr = StringIO(), StringIO()
            with patch.object(SuseCsafVexSource, "fetch", return_value=snapshot) as fetch:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([
                        "--data-dir", str(data), "--json", "vuln", "vendor-preview",
                        CVE, "--provider", "suse",
                    ])
            self.assertEqual((code, stderr.getvalue()), (0, ""))
            self.assertEqual(
                json.loads(stdout.getvalue())["data"]["provider"],
                "SUSE Product Security Team",
            )
            fetch.assert_called_once_with(CVE)
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()

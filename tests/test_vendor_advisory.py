"""Direct Red Hat per-CVE CSAF VEX preview."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

from xti.adapters.redhat_csaf_vex import (
    MAX_RESPONSE_BYTES,
    RedHatCsafVexSource,
    parse_redhat_vex_response,
)
from xti.application.vendor_advisory import VendorAdvisoryPreviewService
from xti.domain.assets import ValidationError
from xti.domain.vendor_advisory import redhat_vex_url
from xti.interfaces.cli import main
from xti.ports.discovery import SourceError


CVE = "CVE-2026-4001"
COMPONENT_ID = "rhel-9:openssl-0:3.2.2-1.el9.x86_64"


def payload():
    return json.dumps({
        "document": {
            "category": "csaf_vex",
            "csaf_version": "2.0",
            "publisher": {
                "category": "vendor", "name": "Red Hat Product Security",
                "namespace": "https://www.redhat.com",
            },
            "title": "openssl: example vulnerability",
            "tracking": {
                "id": CVE, "status": "final", "version": "3",
                "initial_release_date": "2026-10-20T12:00:00+00:00",
                "current_release_date": "2026-10-29T18:00:00+00:00",
                "revision_history": [
                    {"date": "2026-10-20T12:00:00+00:00", "number": "1",
                     "summary": "Initial version"},
                    {"date": "2026-10-29T18:00:00+00:00", "number": "3",
                     "summary": "Current version"},
                ],
            },
            "aggregate_severity": {"text": "Important"},
        },
        "product_tree": {
            "branches": [{
                "category": "product_family", "name": "RHEL",
                "branches": [{
                    "category": "product_name", "name": "RHEL 9",
                    "product": {
                        "name": "Red Hat Enterprise Linux 9", "product_id": "rhel-9",
                        "product_identification_helper": {
                            "cpe": "cpe:/o:redhat:enterprise_linux:9",
                        },
                    },
                }, {
                    "category": "product_name", "name": "openssl package",
                    "product": {
                        "name": "openssl-0:3.2.2-1.el9.x86_64",
                        "product_id": "openssl-0:3.2.2-1.el9.x86_64",
                        "product_identification_helper": {
                            "purl": "pkg:rpm/redhat/openssl@3.2.2-1.el9?arch=x86_64",
                        },
                    },
                }],
            }],
            "relationships": [{
                "category": "default_component_of",
                "product_reference": "openssl-0:3.2.2-1.el9.x86_64",
                "relates_to_product_reference": "rhel-9",
                "full_product_name": {
                    "name": "openssl 3.2.2 as a component of Red Hat Enterprise Linux 9",
                    "product_id": COMPONENT_ID,
                },
            }],
        },
        "vulnerabilities": [{
            "cve": CVE,
            "title": "openssl: example vulnerability",
            "product_status": {
                "fixed": [COMPONENT_ID],
                "known_not_affected": ["rhel-9"],
            },
            "remediations": [{
                "category": "vendor_fix", "details": "Apply the signed vendor update.",
                "date": "2026-10-29T17:00:00+00:00",
                "url": "https://access.redhat.com/errata/RHSA-2026:4001",
                "product_ids": [COMPONENT_ID],
            }],
        }],
    }, separators=(",", ":")).encode()


def payload_with_product_ids(replacements):
    """Keep opaque fixture IDs and their references in sync without trimming."""
    def replace(value):
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        return replacements.get(value, value) if isinstance(value, str) else value
    return json.dumps(replace(json.loads(payload())), separators=(",", ":")).encode()


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


class VendorAdvisoryTests(unittest.TestCase):
    def test_product_ids_preserve_spaces_across_relationships_statuses_and_remediations(self):
        identifiers = {
            COMPONENT_ID: " relationship product ",
            "rhel-9": "Red Hat Enterprise Linux 9 ",
            "openssl-0:3.2.2-1.el9.x86_64": " component product ",
        }
        result = parse_redhat_vex_response(payload_with_product_ids(identifiers), CVE)
        fixed = result.advisory.product_statuses[0].products[0]
        self.assertEqual(fixed.product_id, identifiers[COMPONENT_ID])
        self.assertEqual(fixed.component_product_id, identifiers["openssl-0:3.2.2-1.el9.x86_64"])
        self.assertEqual(fixed.context_product_id, identifiers["rhel-9"])
        self.assertEqual(result.advisory.remediations[0].target_count, 1)

    def test_similar_opaque_ids_do_not_merge_and_trimmed_references_do_not_resolve(self):
        body = json.loads(payload())
        body["product_tree"]["full_product_names"] = [
            {"name": "First product", "product_id": "same"},
            {"name": "Second product", "product_id": "same "},
        ]
        statuses = body["vulnerabilities"][0]["product_status"]
        statuses["fixed"] = ["same"]
        statuses["known_affected"] = ["same "]
        result = parse_redhat_vex_response(json.dumps(body).encode(), CVE)
        self.assertEqual(result.advisory.product_statuses[0].products[0].name, "First product")
        self.assertEqual(result.advisory.product_statuses[1].products[0].name, "Second product")
        body = json.loads(payload_with_product_ids({COMPONENT_ID: COMPONENT_ID + " "}))
        body["vulnerabilities"][0]["product_status"]["fixed"] = [COMPONENT_ID]
        with self.assertRaisesRegex(SourceError, "ürün ağacında bulunmuyor"):
            parse_redhat_vex_response(json.dumps(body).encode(), CVE)

    def test_opaque_ids_keep_control_character_and_size_limits_and_structured_tokens_stay_strict(self):
        for value in ("", "x" * 2001, "product\n", "\x1bproduct", "product\x00", "product\x7f"):
            with self.subTest(product_id=repr(value)), self.assertRaises(SourceError):
                parse_redhat_vex_response(payload_with_product_ids({COMPONENT_ID: value}), CVE)
        for index, field in ((0, "cpe"), (1, "purl")):
            body = json.loads(payload())
            helper = body["product_tree"]["branches"][0]["branches"][index]["product"]["product_identification_helper"]
            helper[field] += " "
            with self.subTest(field=field), self.assertRaises(SourceError):
                parse_redhat_vex_response(json.dumps(body).encode(), CVE)

    def test_parser_keeps_vendor_status_products_and_remediation_separate(self):
        result = parse_redhat_vex_response(payload(), CVE.lower())
        advisory = result.advisory
        self.assertEqual(advisory.provider, "Red Hat Product Security")
        self.assertEqual(advisory.cve_id, CVE)
        self.assertEqual(advisory.severity, "Important")
        self.assertEqual(
            [(item.status, len(item.products)) for item in advisory.product_statuses],
            [("fixed", 1), ("known_not_affected", 1)],
        )
        self.assertEqual(advisory.product_statuses[0].products[0].product_id, COMPONENT_ID)
        self.assertEqual(
            advisory.product_statuses[0].products[0].component_purl,
            "pkg:rpm/redhat/openssl@3.2.2-1.el9?arch=x86_64",
        )
        self.assertEqual(
            advisory.product_statuses[0].products[0].context_cpe,
            "cpe:/o:redhat:enterprise_linux:9",
        )
        self.assertEqual(advisory.remediations[0].category, "vendor_fix")
        self.assertEqual(advisory.remediations[0].target_count, 1)
        self.assertEqual(result.source_url, redhat_vex_url(CVE))

    def test_duplicate_mismatch_publisher_conflict_missing_product_time_and_size_fail(self):
        duplicate = payload().replace(
            b'"category":"csaf_vex"',
            b'"category":"csaf_vex","category":"csaf_vex"',
        )
        mismatch = json.loads(payload())
        mismatch["vulnerabilities"][0]["cve"] = "CVE-2026-4999"
        publisher = json.loads(payload())
        publisher["document"]["publisher"]["name"] = "Another Vendor"
        conflict = json.loads(payload())
        conflict["vulnerabilities"][0]["product_status"]["known_affected"] = [COMPONENT_ID]
        missing = json.loads(payload())
        missing["vulnerabilities"][0]["product_status"]["fixed"] = ["missing-product"]
        bad_time = json.loads(payload())
        bad_time["document"]["tracking"]["current_release_date"] = "2025-01-01T00:00:00Z"
        bad_helper = json.loads(payload())
        bad_helper["product_tree"]["branches"][0]["branches"][1]["product"][
            "product_identification_helper"
        ]["purl"] = "https://not-a-purl.example"
        bad_relation = json.loads(payload())
        bad_relation["product_tree"]["relationships"][0]["product_reference"] = "missing"
        fixtures = (
            duplicate, json.dumps(mismatch).encode(), json.dumps(publisher).encode(),
            json.dumps(conflict).encode(), json.dumps(missing).encode(),
            json.dumps(bad_time).encode(), json.dumps(bad_helper).encode(),
            json.dumps(bad_relation).encode(), b"x" * (MAX_RESPONSE_BYTES + 1),
        )
        for body in fixtures:
            with self.subTest(size=len(body)):
                with self.assertRaises(SourceError):
                    parse_redhat_vex_response(body, CVE)

    def test_transport_uses_fixed_year_endpoint_identity_json_and_bounds(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return Response(payload())

        result = RedHatCsafVexSource(opener=opener).fetch(CVE.lower())
        self.assertEqual(result.advisory.cve_id, CVE)
        request, timeout = calls[0]
        self.assertEqual(request.full_url, redhat_vex_url(CVE))
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
                    RedHatCsafVexSource(
                        opener=lambda *args, value=response, **kwargs: value,
                    ).fetch(CVE)
        with self.assertRaisesRegex(SourceError, "güvenli bağlantı"):
            RedHatCsafVexSource(opener=lambda *args, **kwargs: (_ for _ in ()).throw(
                URLError("private remote detail"),
            )).fetch(CVE)

    def test_service_limits_before_network_and_cli_preview_is_write_free(self):
        snapshot = parse_redhat_vex_response(payload(), CVE)

        class Source:
            calls = 0

            def fetch(self, cve_id):
                self.calls += 1
                return snapshot

        source = Source()
        service = VendorAdvisoryPreviewService(source)
        with self.assertRaises(ValidationError):
            service.preview(CVE, product_limit=0)
        self.assertEqual(source.calls, 0)
        report = service.preview(CVE, product_limit=1, remediation_limit=1)
        self.assertEqual(report.product_statuses[0].total_count, 1)
        self.assertIn("yalnız Red Hat", report.notes[0])

        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "missing-data"
            stdout, stderr = StringIO(), StringIO()
            with patch.object(RedHatCsafVexSource, "fetch", return_value=snapshot) as fetch:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([
                        "--data-dir", str(data), "--json", "vuln", "vendor-preview",
                        CVE, "--provider", "redhat",
                    ])
            self.assertEqual((code, stderr.getvalue()), (0, ""))
            result = json.loads(stdout.getvalue())["data"]
            self.assertEqual(result["provider"], "Red Hat Product Security")
            self.assertEqual(result["product_statuses"][0]["status"], "fixed")
            fetch.assert_called_once_with(CVE)
            self.assertFalse(data.exists())

            stdout, stderr = StringIO(), StringIO()
            with patch.object(
                RedHatCsafVexSource, "fetch",
                side_effect=SourceError("Red Hat bağlantısı tamamlanamadı."),
            ):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main([
                        "--data-dir", str(data), "--json", "vuln", "vendor-preview", CVE,
                    ])
            self.assertEqual(code, 3)
            self.assertEqual(
                json.loads(stderr.getvalue())["error"]["code"], "source_error",
            )
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertFalse(data.exists())


if __name__ == "__main__":
    unittest.main()

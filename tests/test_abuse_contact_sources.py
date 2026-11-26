"""Bounded source orchestration for RDAP, security.txt and WHOIS fallback."""

from datetime import datetime, timezone
import json
import unittest

from xti.adapters.abuse_contact_sources import (
    AbuseContactSourceAdapter, BoundedPublicHTTPS, BoundedResponse,
    ContactSourceFailure, DNS_BOOTSTRAP,
)


NOW = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)


class HTTP:
    def __init__(self, responses):
        self.responses = list(responses); self.calls = []

    def get(self, url, **options):
        self.calls.append((url, options))
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        response = self.responses.pop(0)
        if callable(response):
            return response(url)
        return response


def response(url, body, *, content_type="application/json", status=200):
    return BoundedResponse(
        url=url, final_url=url, status=status,
        headers={"content-type": content_type}, body=body,
        request_count=1, received_bytes=len(body),
    )


class Whois:
    def __init__(self, *, body=None, error=None):
        self.body = body; self.error = error; self.calls = []

    def run(self, subject, *, timeout):
        self.calls.append((subject, timeout))
        if self.error:
            raise self.error
        return self.body or b""


class AbuseContactSourceTests(unittest.TestCase):
    def test_domain_rdap_prevents_unneeded_whois_and_collects_security_txt(self):
        bootstrap = json.dumps({
            "services": [["com".split(), ["https://rdap.registrar.example/"]]],
        }).encode()
        rdap = json.dumps({
            "ldhName": "example.com",
            "entities": [{
                "roles": ["abuse"],
                "vcardArray": ["vcard", [["email", {}, "text", "abuse@registrar.example"]]],
            }],
        }).encode()
        security = (
            "Contact: mailto:security@example.com\n"
            "Expires: 2027-01-01T00:00:00Z\n"
        ).encode()
        http = HTTP([
            response(DNS_BOOTSTRAP, bootstrap),
            lambda url: response(url, rdap, content_type="application/rdap+json"),
            lambda url: response(url, security, content_type="text/plain"),
        ])
        whois = Whois(body=b"Registrar Abuse Contact Email: fallback@example.com\n")
        adapter = AbuseContactSourceAdapter(
            http=http, whois=whois, clock=lambda: NOW, monotonic=lambda: 10.0,
        )
        outcomes = adapter.collect(
            "domain", "example.com", include_whois=True, timeout_seconds=60,
        )
        self.assertEqual(
            [(item.source_key, item.status) for item in outcomes],
            [("domain_rdap", "complete"), ("security_txt", "complete"), ("whois", "skipped")],
        )
        self.assertEqual(outcomes[0].candidates[0].contact_value, "abuse@registrar.example")
        self.assertEqual(outcomes[1].candidates[0].confidence, "low")
        self.assertEqual(whois.calls, [])
        self.assertEqual(len(http.calls), 3)

    def test_missing_local_whois_is_requirement_state_not_product_crash(self):
        bootstrap = json.dumps({
            "services": [["com".split(), ["https://rdap.registrar.example/"]]],
        }).encode()
        rdap = json.dumps({"ldhName": "example.com", "entities": []}).encode()
        http = HTTP([
            response(DNS_BOOTSTRAP, bootstrap),
            lambda url: response(url, rdap, content_type="application/rdap+json"),
            lambda url: response(url, b"", content_type="text/plain", status=404),
        ])
        whois = Whois(error=ContactSourceFailure(
            "whois_not_installed", "WHOIS fallback aracı kurulu değil.",
            source_reference="whois://example.com",
        ))
        adapter = AbuseContactSourceAdapter(
            http=http, whois=whois, clock=lambda: NOW, monotonic=lambda: 10.0,
        )
        outcomes = adapter.collect(
            "domain", "example.com", include_whois=True, timeout_seconds=60,
        )
        self.assertEqual(outcomes[0].status, "empty")
        self.assertEqual(outcomes[1].status, "empty")
        self.assertEqual(outcomes[2].status, "requirement_missing")
        self.assertEqual(outcomes[2].error_code, "whois_not_installed")
        self.assertEqual(whois.calls, [("example.com", 15.0)])

    def test_malformed_security_txt_keeps_bounded_request_receipt_without_raw_body(self):
        bootstrap = json.dumps({
            "services": [["com".split(), ["https://rdap.registrar.example/"]]],
        }).encode()
        rdap = json.dumps({"ldhName": "example.com", "entities": []}).encode()
        malformed = (
            "Contact: mailto:security@example.com\n"
            "Expires: 2027-01-01T00:00:00Z\n"
            "Canonical: /.well-known/security.txt\n"
        ).encode()
        http = HTTP([
            response(DNS_BOOTSTRAP, bootstrap),
            lambda url: response(url, rdap, content_type="application/rdap+json"),
            lambda url: response(url, malformed, content_type="text/plain"),
        ])
        outcomes = AbuseContactSourceAdapter(
            http=http, whois=Whois(), clock=lambda: NOW, monotonic=lambda: 10.0,
        ).collect("domain", "example.com", include_whois=False, timeout_seconds=60)
        security = outcomes[1]
        self.assertEqual((security.status, security.error_code), ("failed", "invalid_security_txt"))
        self.assertEqual(security.source_reference, "https://example.com/.well-known/security.txt")
        self.assertEqual((security.request_count, security.received_bytes), (1, len(malformed)))
        self.assertIsNotNone(security.content_sha256)
        self.assertNotIn("security@example.com", json.dumps(security.summary()))

    def test_http_reader_rejects_cross_host_redirect(self):
        reader = BoundedPublicHTTPS(
            resolver=lambda host, timeout: "93.184.216.34",
            requester=lambda host, address, path, timeout: (
                302, {"location": "https://evil.example/collect"}, b""
            ),
            monotonic=lambda: 10.0,
        )
        with self.assertRaisesRegex(ContactSourceFailure, "başka sunucuya"):
            reader.get(
                "https://example.com/.well-known/security.txt", timeout=5,
                max_bytes=32768, same_host_redirects=True,
            )


if __name__ == "__main__":
    unittest.main()

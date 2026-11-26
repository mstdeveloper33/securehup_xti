"""Pure abuse-contact parsers reject broad or untrusted source claims."""

from datetime import datetime, timezone
import json
import unittest

from xti.domain.abuse_contacts import (
    AbuseContactError, parse_rdap, parse_security_txt, parse_whois,
    strict_json,
)
from xti.domain.assets import ValidationError


NOW = datetime(2026, 11, 25, 9, tzinfo=timezone.utc).isoformat()


class AbuseContactDomainTests(unittest.TestCase):
    def test_domain_rdap_uses_only_explicit_abuse_entities(self):
        body = json.dumps({
            "ldhName": "EXAMPLE.COM",
            "entities": [
                {
                    "handle": "REGISTRAR-ABUSE",
                    "roles": ["abuse"],
                    "vcardArray": ["vcard", [
                        ["version", {}, "text", "4.0"],
                        ["email", {}, "text", "Abuse@Registrar.Example"],
                        ["tel", {}, "uri", "tel:+1-555-123-4567"],
                    ]],
                },
                {
                    "handle": "REGISTRANT",
                    "roles": ["registrant"],
                    "vcardArray": ["vcard", [
                        ["email", {}, "text", "person@example.com"],
                    ]],
                },
            ],
        }).encode()
        result = parse_rdap(
            subject_kind="domain", subject_value="example.com",
            source_key="domain_rdap", source_reference="https://rdap.example/domain/example.com",
            body=body, observed_at=NOW,
        )
        self.assertEqual(
            {(item.channel, item.contact_value) for item in result},
            {("email", "Abuse@registrar.example"), ("phone", "tel:+15551234567")},
        )
        self.assertTrue(all(item.confidence == "high" for item in result))
        self.assertNotIn("person@example.com", {item.contact_value for item in result})
        self.assertNotIn("person@example.com", json.dumps([item.evidence for item in result]))

    def test_rdap_scope_mismatch_and_duplicate_json_fail_closed(self):
        with self.assertRaisesRegex(AbuseContactError, "istenen hedefe"):
            parse_rdap(
                subject_kind="domain", subject_value="example.com",
                source_key="domain_rdap", source_reference="https://rdap.example/domain/example.com",
                body=b'{"ldhName":"other.example","entities":[]}', observed_at=NOW,
            )
        with self.assertRaisesRegex(AbuseContactError, "güvenli JSON"):
            strict_json(b'{"ldhName":"example.com","ldhName":"other.example"}')

    def test_ip_rdap_requires_returned_range_to_cover_public_target(self):
        body = json.dumps({
            "startAddress": "1.1.1.0", "endAddress": "1.1.1.255",
            "entities": [{
                "roles": ["abuse"],
                "vcardArray": ["vcard", [["email", {}, "text", "abuse@network.example"]]],
            }],
        }).encode()
        result = parse_rdap(
            subject_kind="ip", subject_value="1.1.1.1", source_key="ip_rdap",
            source_reference="https://rdap.example/ip/1.1.1.1", body=body,
            observed_at=NOW,
        )
        self.assertEqual(result[0].contact_kind, "network_abuse")
        with self.assertRaisesRegex(AbuseContactError, "kapsamıyor"):
            parse_rdap(
                subject_kind="ip", subject_value="8.8.8.8", source_key="ip_rdap",
                source_reference="https://rdap.example/ip/8.8.8.8", body=body,
                observed_at=NOW,
            )
        with self.assertRaisesRegex(ValidationError, "genel IP"):
            parse_rdap(
                subject_kind="ip", subject_value="127.0.0.1", source_key="ip_rdap",
                source_reference="https://rdap.example/ip/127.0.0.1", body=body,
                observed_at=NOW,
            )

    def test_security_txt_is_low_trust_scoped_and_must_not_be_expired(self):
        body = (
            "Contact: mailto:security@Example.COM\n"
            "Contact: https://example.com/report\n"
            "Canonical: https://example.com/.well-known/security.txt\n"
            "Expires: 2027-01-01T00:00:00Z\n"
        ).encode()
        result = parse_security_txt(
            domain="example.com", source_reference="https://example.com/.well-known/security.txt",
            body=body, observed_at=NOW,
        )
        self.assertEqual(len(result), 2)
        self.assertTrue(all(item.confidence == "low" for item in result))
        with self.assertRaisesRegex(AbuseContactError, "hedef domaini"):
            parse_security_txt(
                domain="other.example", source_reference="https://other.example/.well-known/security.txt",
                body=body, observed_at=NOW,
            )
        expired = body.replace(b"2027-01-01", b"2026-01-01")
        with self.assertRaisesRegex(AbuseContactError, "süresi dolmuş"):
            parse_security_txt(
                domain="example.com", source_reference="https://example.com/.well-known/security.txt",
                body=expired, observed_at=NOW,
            )

    def test_whois_accepts_only_narrow_abuse_fields(self):
        body = (
            "Registrant Email: owner@example.com\n"
            "Registrar Abuse Contact Email: abuse@registrar.example\n"
            "OrgAbusePhone: +1 555 111 2222\n"
            "Comment: contact security@example.com\n"
        ).encode()
        result = parse_whois(
            subject_kind="domain", subject_value="example.com",
            source_reference="whois://example.com", body=body, observed_at=NOW,
        )
        self.assertEqual(
            {(item.channel, item.contact_value) for item in result},
            {("email", "abuse@registrar.example"), ("phone", "tel:+15551112222")},
        )
        self.assertTrue(all(item.confidence == "low" for item in result))
        self.assertNotIn("owner@example.com", json.dumps([item.evidence for item in result]))


if __name__ == "__main__":
    unittest.main()

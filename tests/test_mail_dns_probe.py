"""No real network: strict, bounded MX/SPF/DMARC DNS evidence."""

import json
import ssl
import unittest

from xti.adapters.https_probe import (
    GoogleMailDnsProbe, _ProbeFailure, parse_mail_dns_response,
)
from xti.domain.assets import ValidationError


DOMAIN = "example.com"


def response(name, kind, *, answer=(), status=0):
    return json.dumps({
        "Status": status, "TC": False, "CD": False,
        "Question": [{"name": name + ".", "type": kind}],
        "Answer": list(answer),
    }).encode()


def row(name, kind, data):
    return {"name": name + ".", "type": kind, "TTL": 300, "data": data}


class Context:
    check_hostname = True
    verify_mode = ssl.CERT_REQUIRED

    def __init__(self):
        self.alpn = None

    def set_alpn_protocols(self, values):
        self.alpn = values


class FixtureProbe(GoogleMailDnsProbe):
    def __init__(self, fixtures, context=None):
        self.fixtures = fixtures
        self.calls = []
        self.context = context or Context()
        super().__init__(
            context_factory=lambda: self.context,
            monotonic=lambda: 0.0,
            now=lambda: "2026-10-29T12:00:00+00:00",
        )

    def _dns_content(self, context, domain, record_type, overall_deadline):
        self.calls.append((domain, record_type))
        value = self.fixtures[(domain, record_type)]
        if isinstance(value, BaseException):
            raise value
        return value


class MailDnsParserTests(unittest.TestCase):
    def test_mx_is_canonical_deduplicated_and_sorted(self):
        content = response(DOMAIN, 15, answer=(
            row(DOMAIN, 15, "20 MX2.EXAMPLE.COM."),
            row(DOMAIN, 15, "10 mx1.example.com."),
            row(DOMAIN, 15, "10 mx1.example.com."),
        ))
        self.assertEqual(parse_mail_dns_response(content, DOMAIN, 15), (
            0, ("10 mx1.example.com", "20 mx2.example.com"),
        ))

    def test_txt_fragments_and_dmarc_underscore_are_supported(self):
        name = "_dmarc.example.com"
        content = response(name, 16, answer=(
            row(name, 16, '"v=DMARC1; p=" "reject"'),
        ))
        self.assertEqual(
            parse_mail_dns_response(content, name, 16),
            (0, ("v=DMARC1; p=reject",)),
        )

    def test_cname_chain_is_finite_and_bound_to_question(self):
        content = response(DOMAIN, 16, answer=(
            row(DOMAIN, 5, "policy.example.net."),
            row("policy.example.net", 16, '"v=spf1 -all"'),
        ))
        self.assertEqual(
            parse_mail_dns_response(content, DOMAIN, 16),
            (0, ("v=spf1 -all",)),
        )
        unrelated = response(DOMAIN, 16, answer=(
            row("other.example", 16, '"v=spf1 -all"'),
        ))
        with self.assertRaises(_ProbeFailure):
            parse_mail_dns_response(unrelated, DOMAIN, 16)

    def test_malformed_txt_mixed_null_mx_and_wrong_question_fail_closed(self):
        fixtures = (
            response(DOMAIN, 16, answer=(row(DOMAIN, 16, "v=spf1 -all"),)),
            response(DOMAIN, 15, answer=(
                row(DOMAIN, 15, "0 ."), row(DOMAIN, 15, "10 mail.example.com."),
            )),
            response("other.example", 15),
        )
        for content, kind in ((fixtures[0], 16), (fixtures[1], 15), (fixtures[2], 15)):
            with self.subTest(kind=kind):
                with self.assertRaises(_ProbeFailure):
                    parse_mail_dns_response(content, DOMAIN, kind)


class MailDnsProbeTests(unittest.TestCase):
    def fixtures(self):
        return {
            (DOMAIN, 15): response(DOMAIN, 15, answer=(
                row(DOMAIN, 15, "10 mail.example.com."),
            )),
            (DOMAIN, 16): response(DOMAIN, 16, answer=(
                row(DOMAIN, 16, '"google-site-verification=fixture"'),
                row(DOMAIN, 16, '"v=spf1 include:_spf.example.net -all"'),
            )),
            ("_dmarc." + DOMAIN, 16): response("_dmarc." + DOMAIN, 16),
        }

    def test_exact_three_queries_filter_policies_and_do_not_guess_dkim(self):
        probe = FixtureProbe(self.fixtures())
        result = probe.check(DOMAIN)
        self.assertEqual(probe.calls, [
            (DOMAIN, 15), (DOMAIN, 16), ("_dmarc." + DOMAIN, 16),
        ])
        self.assertEqual((result.mx_status, result.spf_status, result.dmarc_status), (
            "present", "present", "missing",
        ))
        self.assertEqual(result.mx_records, ("10 mail.example.com",))
        self.assertEqual(result.spf_records, ("v=spf1 include:_spf.example.net -all",))
        self.assertEqual(result.dmarc_records, ())
        self.assertEqual(result.errors, ())
        self.assertIn("DKIM seçicisi tahmin edilmez", " ".join(result.notes))

    def test_one_query_failure_does_not_hide_other_two_results(self):
        fixtures = self.fixtures()
        fixtures[(DOMAIN, 16)] = OSError("untrusted remote detail")
        probe = FixtureProbe(fixtures)
        result = probe.check(DOMAIN)
        self.assertEqual(len(probe.calls), 3)
        self.assertEqual((result.mx_status, result.spf_status, result.dmarc_status), (
            "present", "failed", "missing",
        ))
        self.assertEqual(len(result.errors), 1)
        self.assertNotIn("untrusted remote detail", result.errors[0])

    def test_invalid_root_stops_before_context_or_query(self):
        contexts = []
        probe = GoogleMailDnsProbe(
            context_factory=lambda: contexts.append(True),
            monotonic=lambda: 0.0,
            now=lambda: "2026-10-29T12:00:00+00:00",
        )
        with self.assertRaises(ValidationError):
            probe.check("https://example.com/path")
        self.assertEqual(contexts, [])

    def test_disabled_tls_validation_fails_all_without_dns_request(self):
        context = Context()
        context.check_hostname = False
        probe = FixtureProbe(self.fixtures(), context=context)
        result = probe.check(DOMAIN)
        self.assertEqual(probe.calls, [])
        self.assertEqual(
            (result.mx_status, result.spf_status, result.dmarc_status),
            ("failed", "failed", "failed"),
        )
        self.assertEqual(len(result.errors), 3)


if __name__ == "__main__":
    unittest.main()

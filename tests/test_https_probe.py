"""No real network: validate DNS binding, target boundaries and failure evidence."""

import json
import hashlib
import os
import socket
import ssl
import unittest
from unittest.mock import patch

from xti.adapters.https_probe import (
    CHECK_TIMEOUT, DNS_ADDRESS, DNS_HOST, HttpsTargetProbe, MAX_DNS_BYTES,
    MAX_HEADER_BYTES, POLICY_VERSION, _ProbeFailure, is_public_address,
    certificate_evidence, parse_dns_response,
)
from xti.domain.assets import ValidationError


DOMAIN = "sample-brand.net"
PUBLIC4 = "93.184.215.14"
PUBLIC6 = "2606:4700:4700::1111"
CERTIFICATE_DER = b"bounded-fixture-certificate"
CERTIFICATE = {
    "subject": ((('commonName', DOMAIN),),),
    "issuer": ((('organizationName', 'Fixture CA'),), (('commonName', 'Fixture Root'),)),
    "serialNumber": "01A2",
    "notBefore": "Oct  1 00:00:00 2026 GMT",
    "notAfter": "Dec 31 23:59:59 2026 GMT",
    "subjectAltName": (("DNS", DOMAIN), ("DNS", "*.sample-brand.net")),
}


def dns_data(kind=1, addresses=None, *, status=0, domain=DOMAIN, answer=None):
    if addresses is None:
        addresses = [PUBLIC4] if kind == 1 else []
    rows = answer if answer is not None else [
        {"name": domain + ".", "type": kind, "TTL": 30, "data": address}
        for address in addresses
    ]
    return {"Status": status, "TC": False, "CD": False,
            "Question": [{"name": domain + ".", "type": kind}], "Answer": rows}


def json_bytes(value):
    return json.dumps(value).encode("utf-8")


def http_response(content=b"", *, status=200, headers=None):
    if headers is None:
        headers = {"Content-Type": "application/json", "Content-Length": str(len(content))}
    text = f"HTTP/1.1 {status} Response\r\n" + "".join(
        f"{key}: {value}\r\n" for key, value in headers.items()
    ) + "\r\n"
    return text.encode("ascii") + content


def dns_response(kind=1, addresses=None, **kwargs):
    return http_response(json_bytes(dns_data(kind, addresses, **kwargs)))


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class FakeSocket:
    def __init__(self, content=b"", *, connect_error=None, recv_error=None,
                 clock=None, recv_delay=0.0, connect_delay=0.0,
                 certificate=None, certificate_der=CERTIFICATE_DER):
        self.content = bytearray(content)
        self.connect_error = connect_error
        self.recv_error = recv_error
        self.clock = clock
        self.recv_delay = recv_delay
        self.connect_delay = connect_delay
        self.address = None
        self.sent = bytearray()
        self.timeouts = []
        self.closed = False
        self.received = 0
        self.certificate = CERTIFICATE if certificate is None else certificate
        self.certificate_der = certificate_der

    def settimeout(self, timeout):
        if timeout <= 0:
            raise AssertionError("Timeout must be positive")
        self.timeouts.append(timeout)

    def connect(self, address):
        self.address = address
        if self.clock:
            self.clock.value += self.connect_delay
        if self.connect_error:
            raise self.connect_error

    def sendall(self, data):
        self.sent.extend(data)

    def recv(self, size):
        if self.clock:
            self.clock.value += self.recv_delay
        if self.recv_error:
            raise self.recv_error
        chunk = bytes(self.content[:size])
        del self.content[:size]
        self.received += len(chunk)
        return chunk

    def close(self):
        self.closed = True

    def getpeercert(self, binary_form=False):
        return self.certificate_der if binary_form else self.certificate


class SocketFactory:
    def __init__(self, sockets):
        self.sockets = sockets
        self.calls = []

    def __call__(self, family, kind):
        self.calls.append((family, kind))
        if len(self.calls) > len(self.sockets):
            raise AssertionError("Unexpected additional connection")
        return self.sockets[len(self.calls) - 1]


class Context:
    check_hostname = True
    verify_mode = ssl.CERT_REQUIRED

    def __init__(self, errors=None):
        self.errors = errors or {}
        self.names = []
        self.alpn = None

    def set_alpn_protocols(self, values):
        self.alpn = values

    def wrap_socket(self, raw, *, server_hostname):
        self.names.append(server_hostname)
        if server_hostname in self.errors:
            raise self.errors[server_hostname]
        return raw


def build_probe(first=None, second=None, target=None, *, context=None, clock=None):
    sockets = [
        first if first is not None else FakeSocket(dns_response()),
        second if second is not None else FakeSocket(dns_response(28)),
        target if target is not None else FakeSocket(http_response(headers={})),
    ]
    factory = SocketFactory(sockets)
    context = context or Context()
    probe = HttpsTargetProbe(socket_factory=factory, context_factory=lambda: context,
                            monotonic=clock or Clock(),
                            now=lambda: "2026-10-28T10:00:00+00:00")
    return probe, factory, context


class AddressBoundaryTests(unittest.TestCase):
    def test_only_native_public_unicast_addresses_are_allowed(self):
        for value in (PUBLIC4, "8.8.8.8", PUBLIC6, "2001:4860:4860::8888"):
            with self.subTest(value=value):
                self.assertTrue(is_public_address(value))

    def test_local_reserved_metadata_multicast_and_transition_addresses_blocked(self):
        values = (
            "0.0.0.0", "0.1.2.3", "10.0.0.1", "100.64.0.1", "127.0.0.1",
            "169.254.169.254", "172.16.0.1", "192.168.1.1", "192.0.0.9",
            "192.88.99.1", "192.0.2.1", "198.18.0.1", "198.51.100.1",
            "203.0.113.1", "224.0.0.1", "255.255.255.255", "::", "::1",
            "fd00::1", "fe80::1", "ff02::1", "::ffff:127.0.0.1",
            "::ffff:8.8.8.8", "64:ff9b::7f00:1", "64:ff9b:1::1",
            "2002:7f00:1::", "2001::1", "2001:db8::1", "3fff::1",
            "2606:4700:4700::1111%lo0", "127.1", "2130706433", "bad",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(is_public_address(value))


class DnsResponseTests(unittest.TestCase):
    def test_cname_chain_and_dnssec_records_are_supported(self):
        rows = [
            {"name": DOMAIN + ".", "type": 5, "data": "edge.host.net."},
            {"name": "edge.host.net.", "type": 1, "data": PUBLIC4},
            {"name": DOMAIN + ".", "type": 46, "data": "ignored DNSSEC signature"},
        ]
        self.assertEqual(parse_dns_response(json_bytes(dns_data(answer=rows)), DOMAIN, 1),
                         (0, (PUBLIC4,)))

    def test_echoed_question_cannot_change_name_type_or_cardinality(self):
        cases = [[], [{"name": "other.net.", "type": 1}],
                 [{"name": DOMAIN + ".", "type": 28}],
                 [{"name": DOMAIN + ".", "type": True}],
                 [{"name": DOMAIN + ".", "type": 1}] * 2]
        for question in cases:
            payload = dns_data()
            payload["Question"] = question
            with self.subTest(question=question), self.assertRaises(_ProbeFailure):
                parse_dns_response(json_bytes(payload), DOMAIN, 1)

    def test_truncation_bad_status_and_disabled_validation_are_rejected(self):
        for key, value in (("TC", True), ("TC", None), ("CD", True),
                           ("Status", 2), ("Status", False), ("Status", "0")):
            payload = dns_data()
            payload[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(_ProbeFailure):
                parse_dns_response(json_bytes(payload), DOMAIN, 1)

    def test_unrelated_address_wrong_family_and_malformed_ip_rejected(self):
        for row in (
            {"name": "other.net", "type": 1, "data": PUBLIC4},
            {"name": DOMAIN, "type": 1, "data": PUBLIC6},
            {"name": DOMAIN, "type": 1, "data": "127.1"},
            {"name": DOMAIN, "type": 28, "data": PUBLIC6},
        ):
            with self.subTest(row=row), self.assertRaises(_ProbeFailure):
                parse_dns_response(json_bytes(dns_data(answer=[row])), DOMAIN, 1)

    def test_cycles_conflicting_cnames_and_mixed_alias_address_rejected(self):
        a = {"name": DOMAIN, "type": 5, "data": "edge.host.net"}
        bad_rows = [
            [a, {"name": "edge.host.net", "type": 5, "data": DOMAIN}],
            [a, {"name": DOMAIN, "type": 5, "data": "other.host.net"}],
            [a, {"name": DOMAIN, "type": 1, "data": PUBLIC4}],
            [{"name": "unrelated.net", "type": 5, "data": "edge.host.net"}],
        ]
        for rows in bad_rows:
            with self.subTest(rows=rows), self.assertRaises(_ProbeFailure):
                parse_dns_response(json_bytes(dns_data(answer=rows)), DOMAIN, 1)

    def test_invalid_json_duplicate_keys_and_oversize_response_rejected(self):
        cases = [b"null", b"[]", b"{bad", b'{"Status":0,"Status":3}',
                 b'{"Status":NaN}', b" " * (MAX_DNS_BYTES + 1)]
        for content in cases:
            with self.subTest(content=content[:50]), self.assertRaises(_ProbeFailure):
                parse_dns_response(content, DOMAIN, 1)

    def test_answer_count_and_negative_answer_with_address_rejected(self):
        for payload in (dns_data(answer=dns_data()["Answer"] * 33), dns_data(status=3)):
            with self.assertRaises(_ProbeFailure):
                parse_dns_response(json_bytes(payload), DOMAIN, 1)


class TargetProbeTests(unittest.TestCase):
    def test_success_pins_every_connection_and_preserves_original_host_sni(self):
        probe, factory, context = build_probe()
        with patch("socket.getaddrinfo", side_effect=AssertionError("DNS re-resolution")), \
                patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:1"}):
            result = probe.check(DOMAIN.upper() + ".")
        self.assertEqual((result.dns_status, result.tls_status, result.http_status),
                         ("resolved", "valid", "responded"))
        self.assertEqual(result.http_status_code, 200)
        self.assertEqual(result.connected_address, PUBLIC4)
        self.assertEqual(result.policy_version, POLICY_VERSION)
        self.assertEqual(result.certificate.sha256, hashlib.sha256(CERTIFICATE_DER).hexdigest())
        self.assertEqual(result.certificate.issuer, "Fixture CA")
        self.assertEqual(result.certificate.serial_number, "01a2")
        self.assertEqual(
            result.certificate.dns_names, ("*.sample-brand.net", "sample-brand.net"),
        )
        self.assertEqual(context.names, [DNS_HOST, DNS_HOST, DOMAIN])
        self.assertEqual(context.alpn, ["http/1.1"])
        self.assertEqual([sock.address for sock in factory.sockets],
                         [(DNS_ADDRESS, 443), (DNS_ADDRESS, 443), (PUBLIC4, 443)])
        self.assertTrue(all(sock.closed for sock in factory.sockets))
        self.assertIn(b"HEAD / HTTP/1.1\r\nHost: sample-brand.net\r\n", factory.sockets[2].sent)
        self.assertIn(b"edns_client_subnet=0.0.0.0%2F0", factory.sockets[0].sent)
        self.assertNotIn(b"GET ", factory.sockets[2].sent)

    def test_head_body_is_never_read_and_redirect_is_not_followed(self):
        body = b"<script>untrusted body must stay unread</script>"
        target = FakeSocket(http_response(body, status=302, headers={
            "Location": "http://169.254.169.254/latest/meta-data/", "Content-Length": str(len(body))}))
        probe, factory, _ = build_probe(target=target)
        result = probe.check(DOMAIN)
        self.assertEqual(result.http_status_code, 302)
        self.assertEqual(bytes(target.content), body)
        self.assertEqual(len(factory.calls), 3)
        self.assertTrue(any("Yönlendirme" in note for note in result.notes))
        self.assertNotIn("169.254", repr(result))

    def test_http_error_and_head_unsupported_are_recorded_without_get_fallback(self):
        for status in (401, 403, 405, 500, 501):
            probe, factory, _ = build_probe(target=FakeSocket(http_response(status=status)))
            with self.subTest(status=status):
                result = probe.check(DOMAIN)
                self.assertEqual((result.http_status, result.http_status_code), ("responded", status))
                self.assertEqual(len(factory.calls), 3)

    def test_both_dns_families_checked_before_public_private_mix_is_blocked(self):
        probe, factory, context = build_probe(
            first=FakeSocket(dns_response(addresses=[PUBLIC4, "127.0.0.1"])))
        result = probe.check(DOMAIN)
        self.assertEqual(result.dns_status, "blocked")
        self.assertIn("127.0.0.1", result.addresses)
        self.assertEqual(len(factory.calls), 2)
        self.assertEqual(context.names, [DNS_HOST, DNS_HOST])
        self.assertIsNone(result.connected_address)
        self.assertEqual((result.tls_status, result.http_status), ("not_checked", "not_checked"))

    def test_private_ipv6_prevents_probe_of_public_ipv4(self):
        probe, factory, _ = build_probe(second=FakeSocket(dns_response(28, ["fd00::1"])))
        result = probe.check(DOMAIN)
        self.assertEqual(result.dns_status, "blocked")
        self.assertEqual(len(factory.calls), 2)

    def test_aaaa_failure_does_not_allow_probe_of_known_public_a_record(self):
        probe, factory, _ = build_probe(second=FakeSocket(dns_response(28, status=2)))
        result = probe.check(DOMAIN)
        self.assertEqual(result.dns_status, "failed")
        self.assertEqual(result.tls_status, "not_checked")
        self.assertEqual(len(factory.calls), 2)

    def test_nxdomain_empty_and_conflicting_responses_are_distinct(self):
        for status4, status6, expected in ((3, 3, "nxdomain"), (0, 0, "no_address"),
                                           (0, 3, "failed")):
            probe, factory, _ = build_probe(
                first=FakeSocket(dns_response(1, [], status=status4)),
                second=FakeSocket(dns_response(28, [], status=status6)))
            with self.subTest(status4=status4, status6=status6):
                result = probe.check(DOMAIN)
                self.assertEqual(result.dns_status, expected)
                self.assertEqual(result.addresses, ())
                self.assertEqual(len(factory.calls), 2)

    def test_ipv6_only_uses_native_numeric_ipv6_socket(self):
        probe, factory, _ = build_probe(first=FakeSocket(dns_response(1, [])),
                                        second=FakeSocket(dns_response(28, [PUBLIC6])))
        result = probe.check(DOMAIN)
        self.assertEqual(result.connected_address, PUBLIC6)
        self.assertEqual(factory.calls[2], (socket.AF_INET6, socket.SOCK_STREAM))
        self.assertEqual(factory.sockets[2].address, (PUBLIC6, 443))

    def test_only_first_sorted_ip_checked_and_no_retry_if_it_fails(self):
        target = FakeSocket(connect_error=ConnectionRefusedError())
        probe, factory, _ = build_probe(first=FakeSocket(dns_response(1, [PUBLIC4, "8.8.8.8"])),
                                        target=target)
        result = probe.check(DOMAIN)
        self.assertEqual(result.addresses, ("8.8.8.8", PUBLIC4))
        self.assertEqual(target.address, ("8.8.8.8", 443))
        self.assertEqual(len(factory.calls), 3)
        self.assertIsNone(result.connected_address)
        self.assertEqual(result.tls_status, "failed")
        self.assertEqual(result.http_status, "not_checked")
        self.assertTrue(target.closed)

    def test_tls_verification_failure_stops_before_any_target_http_request(self):
        context = Context({DOMAIN: ssl.SSLCertVerificationError("untrusted remote content")})
        probe, factory, _ = build_probe(context=context)
        result = probe.check(DOMAIN)
        self.assertEqual(result.tls_status, "failed")
        self.assertEqual(result.http_status, "not_checked")
        self.assertEqual(result.connected_address, PUBLIC4)
        self.assertEqual(factory.sockets[2].sent, b"")
        self.assertTrue(factory.sockets[2].closed)
        self.assertNotIn("untrusted remote content", repr(result))
        self.assertTrue(any("sertifikası doğrulanamadı" in error for error in result.errors))
        self.assertIsNone(result.certificate)

    def test_certificate_identity_is_bounded_normalized_and_requires_valid_fields(self):
        evidence = certificate_evidence(FakeSocket(certificate={
            **CERTIFICATE,
            "subjectAltName": (
                ("DNS", DOMAIN.upper() + "."), ("DNS", DOMAIN),
                ("DNS", "*.Sample-Brand.NET."), ("IP Address", PUBLIC4),
            ),
        }))
        self.assertEqual(evidence.dns_names, ("*.sample-brand.net", "sample-brand.net"))
        self.assertEqual(evidence.not_before, "2026-10-01T00:00:00+00:00")
        self.assertEqual(evidence.not_after, "2026-12-31T23:59:59+00:00")

        invalid = (
            {**CERTIFICATE, "serialNumber": "not-hex"},
            {**CERTIFICATE, "notAfter": "bad"},
            {**CERTIFICATE, "subjectAltName": (("DNS", "bad name"),)},
            {**CERTIFICATE, "issuer": ()},
        )
        for certificate in invalid:
            target = FakeSocket(http_response(), certificate=certificate)
            probe, _, _ = build_probe(target=target)
            with self.subTest(certificate=certificate):
                result = probe.check(DOMAIN)
                self.assertEqual((result.tls_status, result.http_status), ("failed", "not_checked"))
                self.assertIsNone(result.certificate)
                self.assertEqual(target.sent, b"")

    def test_dns_tls_failure_never_reaches_target_or_second_query(self):
        probe, factory, _ = build_probe(context=Context({DNS_HOST: ssl.SSLCertVerificationError()}))
        result = probe.check(DOMAIN)
        self.assertEqual(result.dns_status, "failed")
        self.assertEqual(len(factory.calls), 1)
        self.assertEqual(factory.sockets[0].sent, b"")
        self.assertTrue(factory.sockets[0].closed)

    def test_certificate_checks_cannot_be_disabled_by_injected_context(self):
        for field, value in (("check_hostname", False), ("verify_mode", ssl.CERT_NONE)):
            context = Context()
            setattr(context, field, value)
            probe, factory, _ = build_probe(context=context)
            with self.subTest(field=field):
                self.assertEqual(probe.check(DOMAIN).dns_status, "failed")
                self.assertEqual(factory.calls, [])

    def test_invalid_domains_raise_before_context_creation_or_connection(self):
        for domain in ("https://example.com", "127.0.0.1", "example.com:80", "x.test/path",
                       "example.com\r\nInjected: yes", "xn--abc-.de", "bücher.de"):
            probe, factory, context = build_probe()
            with self.subTest(domain=domain), self.assertRaises(ValidationError):
                probe.check(domain)
            self.assertEqual(factory.calls, [])
            self.assertEqual(context.names, [])

    def test_dns_redirect_is_rejected_without_following_location(self):
        first = FakeSocket(http_response(status=302, headers={"Location": "https://127.0.0.1/"}))
        probe, factory, _ = build_probe(first=first)
        result = probe.check(DOMAIN)
        self.assertEqual(result.dns_status, "failed")
        self.assertEqual(len(factory.calls), 1)
        self.assertIn("HTTP 302", result.errors[0])

    def test_more_than_sixteen_addresses_prevents_target_connection(self):
        probe, factory, _ = build_probe(first=FakeSocket(dns_response(1,
            [f"93.184.215.{index}" for index in range(1, 18)])))
        result = probe.check(DOMAIN)
        self.assertEqual(result.dns_status, "failed")
        self.assertEqual(len(factory.calls), 2)
        self.assertIn("16 adres", result.errors[0])

    def test_oversized_target_headers_are_bounded_and_tls_evidence_is_retained(self):
        target = FakeSocket(http_response(headers={"X-Large": "x" * MAX_HEADER_BYTES}))
        probe, _, _ = build_probe(target=target)
        result = probe.check(DOMAIN)
        self.assertEqual((result.tls_status, result.http_status), ("valid", "failed"))
        self.assertIsNone(result.http_status_code)
        self.assertLessEqual(target.received, MAX_HEADER_BYTES)
        self.assertTrue(target.closed)

    def test_repeated_interim_responses_share_same_header_limit(self):
        target = FakeSocket(b"HTTP/1.1 100 Continue\r\n\r\n" * 1000)
        probe, _, _ = build_probe(target=target)
        result = probe.check(DOMAIN)
        self.assertEqual(result.http_status, "failed")
        self.assertLessEqual(target.received, MAX_HEADER_BYTES)

    def test_slow_drip_headers_hit_total_deadline_despite_receiving_bytes(self):
        clock = Clock()
        target = FakeSocket(http_response(), clock=clock, recv_delay=1)
        probe, _, _ = build_probe(target=target, clock=clock)
        result = probe.check(DOMAIN)
        self.assertEqual(result.http_status, "failed")
        self.assertEqual(result.tls_status, "valid")
        self.assertEqual(target.received, 8)
        self.assertLessEqual(clock.value, CHECK_TIMEOUT)

    def test_global_deadline_is_shared_across_dns_queries_and_target(self):
        clock = Clock()
        # Local CA setup and both DNS queries consume part of the global budget.
        # The target has less than a full request budget left.
        first = FakeSocket(dns_response(), clock=clock, connect_delay=7)
        second = FakeSocket(dns_response(28), clock=clock, connect_delay=7)
        target = FakeSocket(http_response(), clock=clock, connect_delay=5, recv_delay=1)
        probe, _, context = build_probe(first=first, second=second, target=target, clock=clock)

        def load_context():
            clock.value += 5
            return context

        probe.context_factory = load_context
        result = probe.check(DOMAIN)
        self.assertEqual(result.http_status, "failed")
        self.assertEqual(clock.value, CHECK_TIMEOUT)
        self.assertEqual(target.received, 1)
        self.assertEqual(max(target.timeouts), 6)

    def test_incomplete_or_invalid_target_response_does_not_claim_http_success(self):
        for content in (b"HTTP/1.1 200 OK", b"HTTP/1.1 200 OK\r\nX: y\r\n",
                        b"garbage\r\n\r\n", b"HTTP/1.1 999 Invalid\r\n\r\n",
                        b"HTTP/1.1 101 Switching Protocols\r\n\r\n"):
            probe, _, _ = build_probe(target=FakeSocket(content))
            with self.subTest(content=content):
                result = probe.check(DOMAIN)
                self.assertEqual(result.http_status, "failed")
                self.assertEqual(result.tls_status, "valid")
                self.assertIsNone(result.http_status_code)

    def test_malformed_numeric_status_tokens_are_not_normalized_into_success(self):
        for token in (b"+200", b"0200", b"20", b"2e2", b"200\tOK"):
            target = FakeSocket(b"HTTP/1.1 " + token + b" Response\r\n\r\n")
            probe, _, _ = build_probe(target=target)
            with self.subTest(token=token):
                result = probe.check(DOMAIN)
                self.assertEqual(result.http_status, "failed")
                self.assertIsNone(result.http_status_code)

    def test_valid_empty_reason_and_interim_continue_remain_supported(self):
        for content in (b"HTTP/1.1 200\r\n\r\n", b"HTTP/1.0 200 \r\n\r\n",
                        b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\n\r\n"):
            probe, _, _ = build_probe(target=FakeSocket(content))
            with self.subTest(content=content):
                self.assertEqual(probe.check(DOMAIN).http_status_code, 200)

    def test_dns_content_length_encoding_and_type_are_validated_before_body(self):
        for headers in (
            {"Content-Type": "application/json", "Content-Length": str(MAX_DNS_BYTES + 1)},
            {"Content-Type": "application/json", "Content-Encoding": "gzip"},
            {"Content-Type": "text/html"},
            {"Content-Type": "application/json", "Content-Length": "-1"},
            {"Content-Type": "application/json", "Transfer-Encoding": "gzip"},
            {"Content-Type": "application/json", "Transfer-Encoding": "chunked", "Content-Length": "2"},
        ):
            body = b"this body must stay unread"
            first = FakeSocket(http_response(body, headers=headers))
            probe, factory, _ = build_probe(first=first)
            with self.subTest(headers=headers):
                self.assertEqual(probe.check(DOMAIN).dns_status, "failed")
                self.assertEqual(bytes(first.content), body)
                self.assertEqual(len(factory.calls), 1)

    def test_dns_incomplete_content_length_is_failed_even_if_json_is_parseable(self):
        body = json_bytes(dns_data())
        first = FakeSocket(http_response(body, headers={
            "Content-Type": "application/json", "Content-Length": str(len(body) + 10)}))
        probe, _, _ = build_probe(first=first)
        self.assertEqual(probe.check(DOMAIN).dns_status, "failed")

    def test_chunked_dns_is_supported_and_still_bounded(self):
        body = json_bytes(dns_data())
        chunked = f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n"
        first = FakeSocket(http_response(chunked, headers={
            "Content-Type": "application/dns-json", "Transfer-Encoding": "chunked"}))
        probe, _, _ = build_probe(first=first)
        self.assertEqual(probe.check(DOMAIN).http_status, "responded")
        # A declared huge chunk must not turn into an unbounded read/allocation.
        large = b"100000000\r\n" + b"x" * (MAX_DNS_BYTES + 2)
        first = FakeSocket(http_response(large, headers={
            "Content-Type": "application/json", "Transfer-Encoding": "chunked"}))
        probe, _, _ = build_probe(first=first)
        self.assertEqual(probe.check(DOMAIN).dns_status, "failed")
        self.assertLess(first.received, MAX_DNS_BYTES + MAX_HEADER_BYTES)

    def test_chunked_dns_requires_complete_trailer_terminator(self):
        body = json_bytes(dns_data())
        prefix = f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n"
        for suffix in (b"", b"X-Trailer: yes\r\n", b"X-Trailer: incomplete"):
            first = FakeSocket(http_response(prefix + suffix, headers={
                "Content-Type": "application/json", "Transfer-Encoding": "chunked"}))
            probe, factory, _ = build_probe(first=first)
            with self.subTest(suffix=suffix):
                self.assertEqual(probe.check(DOMAIN).dns_status, "failed")
                self.assertEqual(len(factory.calls), 1)

    def test_close_delimited_dns_body_remains_supported(self):
        first = FakeSocket(http_response(json_bytes(dns_data()), headers={
            "Content-Type": "application/json", "Connection": "close"}))
        probe, _, _ = build_probe(first=first)
        self.assertEqual(probe.check(DOMAIN).http_status, "responded")

    def test_socket_errors_do_not_leak_remote_error_strings(self):
        target = FakeSocket(recv_error=OSError("untrusted\x1b[2J remote message"))
        probe, _, _ = build_probe(target=target)
        result = probe.check(DOMAIN)
        self.assertEqual(result.http_status, "failed")
        self.assertNotIn("untrusted", repr(result))
        self.assertTrue(target.closed)


if __name__ == "__main__":
    unittest.main()

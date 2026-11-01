"""Deterministic public-source contract tests; never use the live network."""

from io import BytesIO
from datetime import datetime, timezone
import json
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from xti.adapters.crtsh import CrtShSource, _NoRedirects, parse_response
from xti.domain.assets import ValidationError
from xti.ports.discovery import SourceError


def row(certificate_id=123, names="example-support.net", timestamp="2026-10-28T08:00:00.123"):
    return {"id": certificate_id, "name_value": names, "entry_timestamp": timestamp}


def encode(rows):
    return json.dumps(rows).encode("utf-8")


class Response(BytesIO):
    def __init__(self, body, *, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

    def getcode(self):
        return self.status


class CrtShParsingTests(unittest.TestCase):
    def test_certificate_provenance_preserves_wildcard_and_utc_entry_time(self):
        batch = parse_response(encode([row(names="*.EXAMPLE-SUPPORT.NET\nexampel.com")]))
        self.assertEqual(batch.record_count, 1)
        self.assertEqual(batch.skipped_names, 0)
        self.assertEqual(len(batch.documents), 2)
        by_name = {item.records[0].domain: item for item in batch.documents}
        wildcard = by_name["example-support.net"]
        self.assertEqual(wildcard.source_name, "https://crt.sh/?id=123")
        self.assertEqual(wildcard.records[0].raw_domain, "*.EXAMPLE-SUPPORT.NET")
        self.assertEqual(wildcard.records[0].source_line, 1)
        self.assertEqual(wildcard.records[0].observed_at, "2026-10-28T08:00:00.123000+00:00")
        self.assertEqual(len(wildcard.sha256), 64)

    def test_query_order_duplicates_and_san_subsets_preserve_identity(self):
        complete = parse_response(encode([row(names="one.example.net\ntwo.example.net")]))
        split = parse_response(encode([
            row(names="two.example.net"), row(names="one.example.net"),
            row(names="two.example.net"),
        ]))
        self.assertEqual(complete.documents, split.documents)
        subset = parse_response(encode([row(names="one.example.net")]))
        self.assertIn(subset.documents[0], complete.documents)
        other_cert = parse_response(encode([row(124, "one.example.net")]))
        self.assertNotEqual(subset.documents[0].sha256, other_cert.documents[0].sha256)

    def test_missing_time_stays_unknown_and_not_before_is_not_observation_time(self):
        value = row(timestamp=None)
        value["not_before"] = "2026-10-20T00:00:00"
        batch = parse_response(encode([value]))
        self.assertIsNone(batch.documents[0].records[0].observed_at)
        del value["entry_timestamp"]
        self.assertEqual(parse_response(encode([value])).documents, batch.documents)

    def test_timezone_offset_normalizes_to_utc(self):
        utc = parse_response(encode([row(timestamp="2026-10-28T08:00:00Z")]))
        offset = parse_response(encode([row(timestamp="2026-10-28T11:00:00+03:00")]))
        self.assertEqual(utc.documents, offset.documents)

    def test_idn_names_are_canonicalized_while_invalid_names_are_counted(self):
        names = "\n".join([
            "good.example.net", "xn--bcher-kva.example", "bücher.example", "localhost",
            "https://evil.example", "*.invalid.*.net", "bad\x1b[31m.example", "",
            "\tbad.example.net", " " * 1025 + "valid.example.net",
        ])
        batch = parse_response(encode([row(names=names)]))
        self.assertEqual(len(batch.documents), 3)
        self.assertEqual(
            {item.records[0].domain for item in batch.documents},
            {"good.example.net", "xn--bcher-kva.example"},
        )
        self.assertEqual(batch.skipped_names, 7)
        idn_raw = {
            item.records[0].raw_domain for item in batch.documents
            if item.records[0].domain == "xn--bcher-kva.example"
        }
        self.assertEqual(idn_raw, {"xn--bcher-kva.example", "bücher.example"})

    def test_empty_valid_response_is_distinct_from_invalid_response(self):
        batch = parse_response(b"[]")
        self.assertEqual(batch.documents, ())
        self.assertEqual(batch.record_count, 0)
        for body in (b"", b"<html>error</html>", b"{}", b"null", b"[", b"\xff",
                     b'[{"id":1,"id":2}]', b"[NaN]"):
            with self.subTest(body=body), self.assertRaises(SourceError):
                parse_response(body)

    def test_malformed_row_is_not_silently_converted_to_empty_results(self):
        values = [None, [], 123, {}, row(True), row(0), row(-1), row(2**63),
                  row("123"), row(names=None), row(timestamp="yesterday"),
                  row(timestamp="2026-13-28T08:00:00"),
                  row(timestamp="0001-01-01T00:00:00+23:00"),
                  {**row(), "result_count": "10000"}]
        for value in values:
            with self.subTest(value=value), self.assertRaises(SourceError):
                parse_response(encode([row(122), value]))

    def test_provider_result_limit_is_visible(self):
        batch = parse_response(encode([{**row(), "result_count": 10_000}]))
        self.assertTrue(batch.warnings)
        self.assertIn("eksik", batch.warnings[0])

    def test_all_response_limits_fail_without_partial_batch(self):
        cases = [
            ("MAX_RESPONSE_BYTES", 4, encode([row()])),
            ("MAX_ROWS", 1, encode([row(), row(124)])),
            ("MAX_NAMES_PER_ROW", 1, encode([row(names="one.example.net\ntwo.example.net")])),
            ("MAX_NAMES", 1, encode([row(), row(124)])),
            ("MAX_DOCUMENTS", 1, encode([row(), row(124)])),
        ]
        for constant, value, body in cases:
            with self.subTest(limit=constant), patch(f"xti.adapters.crtsh.{constant}", value):
                with self.assertRaises(SourceError):
                    parse_response(body)


class CrtShTransportTests(unittest.TestCase):
    def test_fixed_https_encoded_query_headers_and_timeout(self):
        opener = Mock(return_value=Response(encode([row()])))
        source = CrtShSource(opener=opener)
        batch = source.search("%example%")
        self.assertEqual(len(batch.documents), 1)
        request = opener.call_args.args[0]
        url = urlsplit(request.full_url)
        self.assertEqual((url.scheme, url.netloc, url.path), ("https", "crt.sh", "/"))
        self.assertEqual(parse_qs(url.query), {
            "dNSName": ["%example%"], "match": ["ILIKE"], "output": ["json"],
        })
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        self.assertIn("XTI/", request.get_header("User-agent"))
        self.assertEqual(opener.call_args.kwargs["timeout"], 20)
        self.assertEqual(source.search_url("%example%"), request.full_url)

    def test_untrusted_patterns_do_not_reach_network(self):
        opener = Mock()
        source = CrtShSource(opener=opener)
        for value in ("%", "ab%", "https://evil.example/", "example&output=html", "éxample%",
                      "example\n", "x" * 256, None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                source.search(value)
        opener.assert_not_called()

    def test_redirects_are_rejected_without_following_new_host(self):
        handler = _NoRedirects()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1"))
        opener = Mock(side_effect=HTTPError("https://crt.sh/", 302, "Found", {}, None))
        with self.assertRaisesRegex(SourceError, "yönlendirme"):
            CrtShSource(opener=opener, sleep=Mock()).search("example%")
        self.assertEqual(opener.call_count, 1)

    def test_retryable_status_is_retried_once_with_bounded_wait(self):
        for status in (429, 502, 503):
            with self.subTest(status=status):
                opener = Mock(side_effect=[
                    HTTPError("https://crt.sh/", status, "busy", {"Retry-After": "3"}, None),
                    Response(b"[]"),
                ])
                sleep = Mock()
                self.assertEqual(CrtShSource(opener=opener, sleep=sleep).search("example%").documents, ())
                self.assertEqual(opener.call_count, 2)
                sleep.assert_called_once_with(3.0)

    def test_long_or_unknown_retry_after_does_not_retry_early(self):
        for value in ("120", "99999999999999999999", "invalid",
                      "Fri, 31 Dec 9999 23:59:59 GMT"):
            with self.subTest(value=value):
                opener = Mock(side_effect=HTTPError(
                    "https://crt.sh/", 429, "busy", {"Retry-After": value}, None,
                ))
                sleep = Mock()
                with self.assertRaisesRegex(SourceError, "daha sonra"):
                    CrtShSource(opener=opener, sleep=sleep).search("example%")
                self.assertEqual(opener.call_count, 1)
                sleep.assert_not_called()

    def test_calls_on_same_source_are_paced(self):
        now = [10.0]
        waits = []

        def sleep(seconds):
            waits.append(seconds)
            now[0] += seconds

        opener = Mock(side_effect=[Response(b"[]"), Response(b"[]"), Response(b"[]")])
        source = CrtShSource(opener=opener, sleep=sleep, clock=lambda: now[0])
        source.search("example%")
        source.search("%example%")
        now[0] += 2
        source.search("exampel%")
        self.assertEqual(waits, [1.0])
        self.assertEqual(opener.call_count, 3)

    def test_long_retry_after_blocks_other_patterns_until_cooldown_expires(self):
        for status in (429, 503):
            with self.subTest(status=status):
                now = [10.0]
                opener = Mock(side_effect=[
                    HTTPError("https://crt.sh/", status, "busy", {"Retry-After": "120"}, None),
                    Response(b"[]"),
                ])
                sleep = Mock()
                source = CrtShSource(opener=opener, sleep=sleep, clock=lambda: now[0])
                with self.assertRaises(SourceError):
                    source.search("example%")
                now[0] += 119
                with self.assertRaisesRegex(SourceError, "yeni istek gönderilmedi"):
                    source.search("exampel%")
                self.assertEqual(opener.call_count, 1)
                now[0] += 1
                self.assertEqual(source.search("exampel%").documents, ())
                self.assertEqual(opener.call_count, 2)
                sleep.assert_not_called()

    def test_http_date_cooldown_applies_across_different_patterns(self):
        now = [10.0]
        opener = Mock(side_effect=[
            HTTPError("https://crt.sh/", 503, "busy", {
                "Retry-After": "Wed, 28 Oct 2026 12:02:00 GMT",
            }, None), Response(b"[]"),
        ])
        sleep = Mock()
        source = CrtShSource(opener=opener, sleep=sleep, clock=lambda: now[0])
        with patch("xti.adapters.crtsh.datetime", wraps=datetime) as wall_clock:
            wall_clock.now.return_value = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
            with self.assertRaises(SourceError):
                source.search("example%")
        now[0] += 119
        with self.assertRaisesRegex(SourceError, "yeni istek gönderilmedi"):
            source.search("exampel%")
        self.assertEqual(opener.call_count, 1)
        now[0] += 1
        self.assertEqual(source.search("exampel%").documents, ())
        sleep.assert_not_called()

    def test_exhausted_429_without_header_blocks_new_search_for_sixty_seconds(self):
        now = [10.0]
        waits = []

        def sleep(seconds):
            waits.append(seconds)
            now[0] += seconds

        opener = Mock(side_effect=[
            HTTPError("https://crt.sh/", 429, "busy", {}, None),
            HTTPError("https://crt.sh/", 429, "busy", {}, None),
            Response(b"[]"),
        ])
        source = CrtShSource(opener=opener, sleep=sleep, clock=lambda: now[0])
        with self.assertRaises(SourceError):
            source.search("example%")
        now[0] += 59
        with self.assertRaisesRegex(SourceError, "yeni istek gönderilmedi"):
            source.search("exampel%")
        self.assertEqual(opener.call_count, 2)
        now[0] += 1
        self.assertEqual(source.search("exampel%").documents, ())
        self.assertEqual(opener.call_count, 3)
        self.assertEqual(waits, [1.0])

    def test_repeated_rate_limit_is_an_error_not_empty_success(self):
        opener = Mock(side_effect=[HTTPError("https://crt.sh/", 429, "busy", {}, None)
                                   for _ in range(2)])
        with self.assertRaisesRegex(SourceError, "istek sınırına"):
            CrtShSource(opener=opener, sleep=Mock()).search("example%")
        self.assertEqual(opener.call_count, 2)

    def test_timeouts_are_retried_once_and_reported(self):
        for error in (TimeoutError(), URLError(TimeoutError())):
            with self.subTest(error=error):
                opener = Mock(side_effect=error)
                with self.assertRaisesRegex(SourceError, "zamanında"):
                    CrtShSource(opener=opener, sleep=Mock()).search("example%")
                self.assertEqual(opener.call_count, 2)

    def test_dns_tls_and_nonretryable_http_failures_are_source_errors(self):
        errors = [URLError("DNS failure"), URLError(ssl.SSLCertVerificationError("untrusted")),
                  HTTPError("https://crt.sh/", 403, "denied", {}, None), OSError("closed")]
        for error in errors:
            with self.subTest(error=error):
                opener = Mock(side_effect=error)
                with self.assertRaises(SourceError):
                    CrtShSource(opener=opener, sleep=Mock()).search("example%")
                self.assertEqual(opener.call_count, 1)

    def test_malformed_html_truncated_and_compressed_responses_fail(self):
        responses = [Response(b"<html>temporary error</html>"),
                     Response(b"[]", headers={"Content-Length": "5"}),
                     Response(b"[]", headers={"Content-Length": "invalid"}),
                     Response(b"[]", headers={"Content-Encoding": "gzip"})]
        for response in responses:
            with self.subTest(headers=response.headers):
                opener = Mock(return_value=response)
                with self.assertRaises(SourceError):
                    CrtShSource(opener=opener, sleep=Mock()).search("example%")
                self.assertEqual(opener.call_count, 1)

    def test_declared_and_streamed_body_limits_are_enforced(self):
        for response in (Response(b"[]", headers={"Content-Length": "100"}), Response(b" " * 10)):
            with self.subTest(headers=response.headers), patch("xti.adapters.crtsh.MAX_RESPONSE_BYTES", 4):
                with self.assertRaisesRegex(SourceError, "8 MiB"):
                    CrtShSource(opener=Mock(return_value=response)).search("example%")


if __name__ == "__main__":
    unittest.main()

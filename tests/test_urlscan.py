"""Public archive parsing and transport behavior; all requests are simulated."""

from datetime import datetime, timezone
from io import BytesIO
import json
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from xti.adapters.urlscan import UrlscanSource, _NoRedirects, parse_response
from xti.domain.assets import ValidationError
from xti.ports.discovery import SourceError


SCAN_ID = "01a18404-3aeb-720c-849a-d09f69cfe1a9"
SECOND_ID = "e142b92c-153b-42a6-b36b-262b22462e7f"


def row(domain="example-support.net", *, task_domain=None, scan_id=SCAN_ID, time="2026-10-28T12:00:00Z"):
    return {
        "_id": scan_id,
        "task": {"uuid": scan_id, "domain": task_domain or domain, "time": time},
        "page": {"domain": domain},
    }


def body(rows=None, **metadata):
    rows = [] if rows is None else rows
    return json.dumps({"results": rows, "total": len(rows), "has_more": False, **metadata}).encode()


class Response(BytesIO):
    def __init__(self, data, *, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}

    def getcode(self):
        return self.status


class Clock:
    def __init__(self):
        self.now = 10.0
        self.waits = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


class UrlscanParsingTests(unittest.TestCase):
    def test_uuid7_and_redirect_domains_have_stable_source_provenance(self):
        result = parse_response(body([row("EXAMPLE-SUPPORT.NET", task_domain="exampel.com")]))
        self.assertEqual(result.record_count, 1)
        self.assertEqual(result.skipped_names, 0)
        self.assertEqual(len(result.documents), 2)
        by_domain = {document.records[0].domain: document for document in result.documents}
        saved = by_domain["example-support.net"]
        self.assertEqual(saved.source_name, f"https://urlscan.io/result/{SCAN_ID}/")
        self.assertEqual(saved.records[0].raw_domain, "EXAMPLE-SUPPORT.NET")
        self.assertEqual(saved.records[0].observed_at, "2026-10-28T12:00:00+00:00")
        self.assertEqual(saved.records[0].source_line, 1)
        self.assertEqual(len(saved.sha256), 64)

    def test_repeated_rows_reordered_queries_and_domain_subsets_deduplicate(self):
        first = parse_response(body([
            row("one.example.net", task_domain="two.example.net"), row("one.example.net"),
        ]))
        second = parse_response(body([
            row("two.example.net"), row("one.example.net"), row("two.example.net"),
        ]))
        self.assertEqual(first.documents, second.documents)
        self.assertEqual(first.record_count, second.record_count)
        new_scan = parse_response(body([row("one.example.net", scan_id=SECOND_ID)]))
        self.assertNotIn(new_scan.documents[0], first.documents)

    def test_date_limit_is_coverage_not_partial_result_warning(self):
        result = parse_response(body([row()], search_date_limit_days=30))
        self.assertEqual(result.warnings, ())
        self.assertEqual(len(result.coverage_notes), 1)
        self.assertIn("30", result.coverage_notes[0])
        for value in (0, None):
            result = parse_response(body([row()], search_date_limit_days=value))
            self.assertEqual(result.coverage_notes, ())

    def test_more_results_are_reported_even_when_has_more_is_false(self):
        result = parse_response(body([row()], total=52, has_more=False))
        self.assertTrue(result.warnings)
        self.assertIn("1 kayıt", result.warnings[0])
        self.assertNotIn("100 kayıt", result.warnings[0])
        self.assertTrue(parse_response(body([row()], total=10000, has_more=True)).warnings)
        unknown = json.loads(body([row(scan_id=f"00000000-0000-4000-8000-{i:012d}") for i in range(100)]))
        del unknown["total"]
        result = parse_response(json.dumps(unknown).encode())
        self.assertTrue(result.warnings)
        self.assertTrue(result.coverage_notes)

    def test_extra_properties_and_missing_optional_fields_are_handled(self):
        value = {"_id": SCAN_ID, "page": {"domain": "example.net", "future": {}}, "future": []}
        result = parse_response(body([value], future={"extra": "value"}))
        self.assertEqual(result.record_count, 1)
        self.assertEqual(result.skipped_names, 1)
        self.assertIsNone(result.documents[0].records[0].observed_at)
        self.assertTrue(result.coverage_notes)
        self.assertFalse(result.warnings)
        task_only = {"task": {"uuid": SCAN_ID, "domain": "example.net"}}
        self.assertEqual(parse_response(body([task_only])).documents, result.documents)

    def test_timestamp_is_utc_and_not_replaced_by_certificate_date(self):
        utc = parse_response(body([row()]))
        offset = parse_response(body([row(time="2026-10-28T15:00:00+03:00")]))
        self.assertEqual(utc.documents, offset.documents)
        value = row(time=None)
        value["page"]["tlsValidFrom"] = "2026-10-28T12:00:00Z"
        self.assertIsNone(parse_response(body([value])).documents[0].records[0].observed_at)

    def test_idn_domains_are_canonicalized_without_visiting_or_saving_urls(self):
        supported_idn = ["xn--bcher-kva.example", "bücher.example"]
        invalid = ["127.0.0.1", "*.example.com",
                   "https://example.com/path?secret=abc", "bad\x1b[31m.example", " ", None,
                   " " * 1025 + "example.net"]
        values = []
        for index, name in enumerate(supported_idn + invalid):
            value = row(scan_id=f"00000000-0000-4000-8000-{index + 1:012d}")
            value["page"]["domain"] = name
            value["task"]["domain"] = "example.net"
            value["task"]["url"] = "http://localhost/private?secret=password"
            value["result"] = "http://127.0.0.1/admin"
            values.append(value)
        result = parse_response(body(values))
        self.assertEqual(result.skipped_names, len(invalid))
        self.assertEqual(
            {document.records[0].domain for document in result.documents},
            {"example.net", "xn--bcher-kva.example"},
        )
        self.assertTrue(all(document.source_name.startswith("https://urlscan.io/result/") for document in result.documents))
        self.assertNotIn("secret", repr(result))

    def test_invalid_ids_times_and_nested_shapes_fail_the_entire_response(self):
        invalid = [
            {}, [], None, {**row(), "_id": SECOND_ID}, {**row(), "_id": "../evil"},
            {**row(), "_id": "00000000-0000-0000-0000-000000000000"},
            {**row(), "page": []}, {**row(), "task": "invalid"},
            row(time="2026-10-28T12:00:00"), row(time="2026-13-28T12:00:00Z"),
            row(time="0001-01-01T00:00:00+23:00"),
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(SourceError):
                parse_response(body([row(), value]))

    def test_metadata_and_top_level_errors_are_not_successful_empty_results(self):
        invalid = [b"", b"null", b"[]", b"{}", b"<html>busy</html>", b"\xff", b'{"results":NaN}',
                   b'{"results":[],"results":[]}', body(total=-1), body(total=True),
                   body(total={"value": 0}), body(has_more="false"),
                   body(search_date_limit_days=-1), body(search_date_limit_days=True),
                   body([row()], total=0)]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(SourceError):
                parse_response(value)
        empty = parse_response(body())
        self.assertEqual(empty.documents, ())
        self.assertEqual(empty.record_count, 0)
        self.assertFalse(empty.warnings)

    def test_response_byte_and_result_limits_fail_before_returning_documents(self):
        with patch("xti.adapters.urlscan.MAX_RESPONSE_BYTES", 5), self.assertRaises(SourceError):
            parse_response(body([row()]))
        with patch("xti.adapters.urlscan.MAX_RESULTS", 1), self.assertRaises(SourceError):
            parse_response(body([row(), row(scan_id=SECOND_ID)]))


class UrlscanTransportTests(unittest.TestCase):
    def source(self, opener):
        clock = Clock()
        return UrlscanSource(opener=opener, clock=clock, sleep=clock.sleep), clock

    def test_fixed_https_get_prefix_query_and_versioned_headers(self):
        opener = Mock(return_value=Response(body([row()])))
        source, _ = self.source(opener)
        source.search("markam-destek*")
        request = opener.call_args.args[0]
        url = urlsplit(request.full_url)
        self.assertEqual((url.scheme, url.netloc, url.path), ("https", "urlscan.io", "/api/v1/search/"))
        self.assertEqual(parse_qs(url.query), {
            "q": [r"(page.domain:markam\-destek* OR task.domain:markam\-destek*)"], "size": ["100"],
        })
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header("Accept"), "application/json")
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        self.assertIn("XTI/", request.get_header("User-agent"))
        self.assertEqual(opener.call_args.kwargs["timeout"], 20)
        self.assertEqual(source.search_url("markam-destek*"), request.full_url)

    def test_untrusted_patterns_are_rejected_before_any_request(self):
        opener = Mock()
        source, _ = self.source(opener)
        invalid = ["*", "abc*", "abcd", "*abcd", "ab*cd", "%abcd%", "https://example.com",
                   "abcd OR domain:evil", "abcd&size=1000", "abcd\n*", "-abcd*", "abcd-*",
                   "ünicode*", "a" * 64 + "*", "abcd.*", None]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                source.search(value)
        opener.assert_not_called()

    def test_requests_are_serial_and_paced_by_two_seconds(self):
        opener = Mock(side_effect=[Response(body()), Response(body()), Response(body())])
        source, clock = self.source(opener)
        source.search("example*")
        source.search("exampel*")
        clock.now += 4
        source.search("another*")
        self.assertEqual(clock.waits, [2.0])

    def test_redirects_and_nonretryable_errors_do_not_follow_or_retry(self):
        self.assertIsNone(_NoRedirects().redirect_request(None, None, 302, "found", {}, "http://localhost"))
        for status in (302, 401, 403, 404):
            with self.subTest(status=status):
                opener = Mock(side_effect=HTTPError("https://urlscan.io/", status, "failure", {}, None))
                source, clock = self.source(opener)
                with self.assertRaisesRegex(SourceError, "urlscan"):
                    source.search("example*")
                self.assertEqual(opener.call_count, 1)
                self.assertEqual(clock.waits, [])

    def test_nonretryable_error_also_preserves_provider_quota_cooldown(self):
        opener = Mock(side_effect=[
            HTTPError("https://urlscan.io/", 403, "denied", {
                "X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset-After": "120",
            }, None),
            Response(body()),
        ])
        source, clock = self.source(opener)
        with self.assertRaises(SourceError):
            source.search("example*")
        with self.assertRaisesRegex(SourceError, "bekleme süresi"):
            source.search("another*")
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(clock.waits, [])

    def test_transient_errors_retry_once_and_respect_short_provider_delay(self):
        for status in (429, 502, 503):
            with self.subTest(status=status):
                opener = Mock(side_effect=[
                    HTTPError("https://urlscan.io/", status, "busy", {"Retry-After": "3"}, None),
                    Response(body()),
                ])
                source, clock = self.source(opener)
                self.assertEqual(source.search("example*").record_count, 0)
                self.assertEqual(opener.call_count, 2)
                self.assertEqual(clock.waits, [3.0])

    def test_long_retry_after_blocks_subsequent_patterns_until_expiry(self):
        opener = Mock(side_effect=[
            HTTPError("https://urlscan.io/", 503, "busy", {"Retry-After": "120"}, None),
            Response(body()),
        ])
        source, clock = self.source(opener)
        with self.assertRaises(SourceError):
            source.search("example*")
        clock.now += 110
        with self.assertRaisesRegex(SourceError, "yeni istek gönderilmedi"):
            source.search("exampel*")
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(clock.waits, [])
        clock.now += 10
        self.assertEqual(source.search("exampel*").record_count, 0)

    def test_success_with_exhausted_quota_preserves_results_and_stops_next_query(self):
        opener = Mock(side_effect=[Response(body([row()]), headers={
            "X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset-After": "120",
        }), Response(body())])
        source, clock = self.source(opener)
        self.assertEqual(source.search("example*").record_count, 1)
        with self.assertRaisesRegex(SourceError, "bekleme süresi"):
            source.search("another*")
        self.assertEqual(opener.call_count, 1)
        clock.now += 120
        source.search("another*")
        self.assertEqual(opener.call_count, 2)

    def test_short_quota_wait_still_obeys_minimum_request_spacing(self):
        opener = Mock(side_effect=[Response(body(), headers={
            "X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset-After": "1",
        }), Response(body())])
        source, clock = self.source(opener)
        source.search("example*")
        source.search("another*")
        self.assertEqual(sum(clock.waits), 2.0)

    def test_rate_limit_reset_date_and_retry_http_date_are_honored(self):
        headers_list = [
            {"X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset": "2026-10-28T12:02:00Z"},
            {"Retry-After": "Wed, 28 Oct 2026 12:02:00 GMT"},
        ]
        for headers in headers_list:
            with self.subTest(headers=headers):
                opener = Mock(side_effect=HTTPError("https://urlscan.io/", 429, "busy", headers, None))
                source, clock = self.source(opener)
                with patch("xti.adapters.urlscan.datetime", wraps=datetime) as wall:
                    wall.now.return_value = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
                    with self.assertRaises(SourceError):
                        source.search("example*")
                clock.now += 110
                with self.assertRaisesRegex(SourceError, "bekleme süresi"):
                    source.search("another*")
                self.assertEqual(opener.call_count, 1)
                self.assertEqual(clock.waits, [])

    def test_long_invalid_or_huge_retry_delay_never_sleeps_unboundedly(self):
        for delay in ("bad", "999999999999999999999999", "Fri, 31 Dec 9999 23:59:59 GMT"):
            with self.subTest(delay=delay):
                opener = Mock(side_effect=HTTPError("https://urlscan.io/", 429, "busy", {"Retry-After": delay}, None))
                source, clock = self.source(opener)
                with self.assertRaises(SourceError):
                    source.search("example*")
                with self.assertRaises(SourceError):
                    source.search("another*")
                self.assertEqual(opener.call_count, 1)
                self.assertEqual(clock.waits, [])

    def test_exhausted_429_without_headers_has_cross_query_cooldown(self):
        opener = Mock(side_effect=[HTTPError("https://urlscan.io/", 429, "busy", {}, None) for _ in range(2)])
        source, clock = self.source(opener)
        with self.assertRaisesRegex(SourceError, "istek sınırına"):
            source.search("example*")
        with self.assertRaisesRegex(SourceError, "bekleme süresi"):
            source.search("another*")
        self.assertEqual(opener.call_count, 2)
        self.assertEqual(clock.waits, [2.0])

    def test_body_timeout_after_quota_header_does_not_retry_early(self):
        response = Response(body(), headers={"X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset-After": "120"})
        response.read1 = Mock(side_effect=TimeoutError())
        opener = Mock(return_value=response)
        source, clock = self.source(opener)
        with self.assertRaises(SourceError):
            source.search("example*")
        with self.assertRaisesRegex(SourceError, "bekleme süresi"):
            source.search("another*")
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(clock.waits, [])

    def test_timeouts_retry_once_but_dns_tls_and_connection_errors_do_not(self):
        errors = [(TimeoutError(), 2), (URLError(TimeoutError()), 2),
                  (URLError("dns"), 1), (URLError(ssl.SSLCertVerificationError()), 1), (OSError(), 1)]
        for error, calls in errors:
            with self.subTest(error=error):
                opener = Mock(side_effect=error)
                source, _ = self.source(opener)
                with self.assertRaises(SourceError):
                    source.search("example*")
                self.assertEqual(opener.call_count, calls)

    def test_html_truncation_bad_length_and_compression_never_become_empty_success(self):
        values = [Response(b"<html>busy</html>"), Response(body(), headers={"Content-Length": "9999"}),
                  Response(body(), headers={"Content-Length": "bad"}),
                  Response(body(), headers={"Content-Length": "-1"}),
                  Response(body(), headers={"Content-Encoding": "gzip"})]
        for response in values:
            with self.subTest(headers=response.headers):
                opener = Mock(return_value=response)
                source, _ = self.source(opener)
                with self.assertRaises(SourceError):
                    source.search("example*")
                self.assertEqual(opener.call_count, 1)

    def test_response_limit_is_checked_in_headers_and_stream(self):
        for response in (Response(body(), headers={"Content-Length": "9999"}), Response(b" " * 20)):
            with self.subTest(headers=response.headers), patch("xti.adapters.urlscan.MAX_RESPONSE_BYTES", 5):
                source, _ = self.source(Mock(return_value=response))
                with self.assertRaisesRegex(SourceError, "2 MiB"):
                    source.search("example*")


if __name__ == "__main__":
    unittest.main()

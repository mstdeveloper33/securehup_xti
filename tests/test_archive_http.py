"""Offline request-boundary, failure, deadline and scope checks for archives."""

from datetime import datetime, timezone
from http.client import RemoteDisconnected
from io import BytesIO
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPSHandler, ProxyHandler

from xti.adapters.archive_http import (
    ArchiveHTTPClient, ArchiveHTTPError, MAX_HEADER_BYTES, MAX_RESPONSE_BYTES,
    _NoRedirects, _SourceGate,
)


CATALOG = "https://index.commoncrawl.org/collinfo.json"
CC = "https://index.commoncrawl.org/CC-MAIN-2026-40-index?"
WB = "https://web.archive.org/cdx/search/cdx?"
TARGET = {"url": "example.com", "matchType": "domain"}


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, value):
        self.sleeps.append(value)
        self.now += value


class Response:
    def __init__(self, body=b"[]", *, status=200, headers=None, clock=None, delay=0, chunk=65536):
        self.body = BytesIO(body)
        self.status = status
        self.headers = headers or {}
        self.clock = clock
        self.delay = delay
        self.chunk = chunk
        self.closed = False

    def read1(self, size):
        if self.clock:
            self.clock.now += self.delay
        return self.body.read(min(size, self.chunk))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True
        self.body.close()


class ArchiveHTTPTests(unittest.TestCase):
    def client(self, source="commoncrawl", *, responses=None, opener=None, **kwargs):
        clock = kwargs.pop("clock", Clock())
        opener = opener or Mock(side_effect=responses or [Response()])
        self.clock = clock
        self.opener = opener
        return ArchiveHTTPClient(
            source, "example.com", opener=opener, clock=clock, sleep=clock.sleep,
            gate=kwargs.pop("gate", _SourceGate()), **kwargs,
        )

    def assert_reason(self, reason, function):
        with self.assertRaises(ArchiveHTTPError) as caught:
            function()
        self.assertEqual(caught.exception.reason, reason)
        return caught.exception

    def test_default_transport_disables_environment_proxies_redirects_and_keeps_tls(self):
        with patch("xti.adapters.archive_http.build_opener") as build:
            ArchiveHTTPClient("commoncrawl", "example.com")
        handlers = build.call_args.args
        proxy = next(item for item in handlers if isinstance(item, ProxyHandler))
        https = next(item for item in handlers if isinstance(item, HTTPSHandler))
        redirect = next(item for item in handlers if isinstance(item, _NoRedirects))
        self.assertEqual(proxy.proxies, {})
        self.assertTrue(https._context.check_hostname)
        self.assertEqual(https._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertIsNone(redirect.redirect_request(None, None, 302, "Found", {}, "https://other.test/"))

    def test_headers_identify_xti_and_true_empty_response_remains_success(self):
        response = Response(b"", headers={"Content-Type": "text/plain", "Content-Length": "0"})
        client = self.client(responses=[response])
        result = client.get(CATALOG)
        self.assertEqual((result.status, result.body), (200, b""))
        self.assertEqual(result.headers["content-type"], "text/plain")
        request = self.opener.call_args.args[0]
        self.assertIn("XTI/", request.get_header("User-agent"))
        self.assertEqual(request.get_header("Accept-encoding"), "identity")
        self.assertEqual(self.opener.call_args.kwargs["timeout"], 30)
        self.assertTrue(response.closed)

    def test_canonical_provider_paths_and_explicit_domain_scope_are_accepted(self):
        client = self.client(responses=[Response(b'{"pages":2}'), Response(b'{"url":"https://a.example.com/"}')])
        self.assertEqual(client.get_json(CC + urlencode({**TARGET, "output": "json", "pageSize": 1, "showNumPages": "true"})), {"pages": 2})
        self.assertEqual(client.get(CC + urlencode({**TARGET, "output": "json", "pageSize": 1, "page": 0})).status, 200)
        self.assertEqual(self.clock.sleeps, [1.0])
        client = self.client("waybackarchive")
        url = WB + urlencode({**TARGET, "fl": "original", "collapse": "urlkey", "limit": 50, "showResumeKey": "true", "resumeKey": "com,example)/ 20260101000000!"})
        self.assertEqual(client.get(url).status, 200)

    def test_unknown_host_path_scope_credentials_fragment_and_query_never_reach_network(self):
        client = self.client()
        bad = [
            "http://index.commoncrawl.org/collinfo.json",
            "https://index.commoncrawl.org.evil.test/collinfo.json",
            "https://user:pass@index.commoncrawl.org/collinfo.json",
            "https://index.commoncrawl.org:444/collinfo.json",
            "https://index.commoncrawl.org/collinfo.json#anything",
            "https://index.commoncrawl.org/collinfo.json#",
            "https://index.commoncrawl.org/collinfo.json?ignored=yes",
            "https://index.commoncrawl.org/CC-MAIN-2026-40-index/../other",
            CATALOG + "\n",
            CC + urlencode({"url": "example.com"}),
            CC + urlencode({"url": "*.example.com", "matchType": "domain"}),
            CC + urlencode({"url": "other.test", "matchType": "domain"}),
            CC + urlencode({**TARGET, "filter": "anything"}),
            CC + urlencode({**TARGET, "pageSize": 500}),
            CC + urlencode({**TARGET, "page": -1}),
            CC + urlencode({**TARGET, "output": "xml"}),
            CC + urlencode({**TARGET, "url2": "example.com"}),
            CC + urlencode(TARGET) + "&url=example.com",
            WB + urlencode(TARGET),
        ]
        for url in bad:
            with self.subTest(url=url):
                self.assert_reason("invalid-url", lambda: client.get(url))
        self.opener.assert_not_called()

    def test_wayback_cursor_controls_and_excessive_query_values_are_rejected(self):
        client = self.client("waybackarchive")
        for change in ({"resumeKey": "a\nb"}, {"resumeKey": "\u202eevil"}, {"resumeKey": "x" * 2049}, {"limit": 1001}, {"fl": "original,secret"}, {"showResumeKey": "false"}, {"collapse": "timestamp"}):
            with self.subTest(change=change):
                self.assert_reason("invalid-url", lambda: client.get(WB + urlencode({**TARGET, **change})))
        self.opener.assert_not_called()

    def test_invalid_constructor_domain_and_budgets_are_rejected(self):
        for domain in ("EXAMPLE.COM", "example.com.", "localhost", "127.0.0.1", "evil/path.com", "*.example.com", "-bad.example", "bücher.example"):
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                ArchiveHTTPClient("commoncrawl", domain)
        for options in ({"budget_seconds": float("inf")}, {"budget_seconds": 0}, {"request_timeout": 31}, {"max_requests": True}, {"max_requests": 101}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                ArchiveHTTPClient("commoncrawl", "example.com", **options)

    def test_strict_json_rejects_empty_invalid_duplicate_and_nonfinite_values(self):
        for body in (b"", b"<html>error</html>", b"\xff", b'{"x":1,"x":2}', b"[NaN]", b"[Infinity]", b"[1e999]"):
            with self.subTest(body=body):
                client = self.client(responses=[Response(body)])
                self.assert_reason("invalid-json", lambda: client.get_json(CATALOG))
                self.assertEqual(self.opener.call_count, 1)
        self.assertEqual(self.client().get_json(CATALOG), [])

    def test_narrow_404_body_is_preserved_for_worker_not_converted_to_empty_success(self):
        body = b'{"message":"No Captures found for: example.com"}'
        error = HTTPError(CC, 404, "Not Found", {"Content-Type": "application/json"}, BytesIO(body))
        client = self.client(responses=[error])
        response = client.get(CC + urlencode(TARGET))
        self.assertEqual(response.status, 404)
        self.assertEqual(response.body, body)
        client = self.client(responses=[Response(body, status=404)])
        self.assert_reason("http-404", lambda: client.get_json(CC + urlencode(TARGET)))

    def test_rate_limit_and_service_unavailable_preserve_retry_after_without_retry(self):
        for status in (429, 503):
            with self.subTest(status=status):
                response = Response(status=status, headers={"Retry-After": "120"})
                client = self.client(responses=[response])
                error = self.assert_reason(f"http-{status}", lambda: client.get(CATALOG))
                self.assertEqual(error.status, status)
                self.assertEqual(error.retry_after_seconds, 120)
                self.assertEqual(self.opener.call_count, 1)
                self.assertEqual(self.clock.sleeps, [])
                self.assertTrue(response.closed)

    def test_http_date_retry_after_uses_injected_wall_clock(self):
        client = self.client(
            responses=[Response(status=429, headers={"Retry-After": "Thu, 01 Jan 2026 00:02:00 GMT"})],
            wall_clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        error = self.assert_reason("http-429", lambda: client.get(CATALOG))
        self.assertEqual(error.retry_after_seconds, 120)

    def test_redirect_and_tls_fail_without_retry(self):
        for status in (301, 302, 307, 308):
            client = self.client(responses=[Response(status=status, headers={"Location": "https://other.test"})])
            self.assert_reason("redirect-rejected", lambda: client.get(CATALOG))
            self.assertEqual(self.opener.call_count, 1)
        for error in (ssl.SSLCertVerificationError("private detail"), URLError(ssl.SSLError("private detail"))):
            client = self.client(responses=[error])
            result = self.assert_reason("tls-error", lambda: client.get(CATALOG))
            self.assertNotIn("private detail", str(result))
            self.assertEqual(self.opener.call_count, 1)

    def test_transient_disconnect_timeout_and_5xx_retry_only_once(self):
        for failure, wait in (
            (RemoteDisconnected("private endpoint"), 60.0),
            (TimeoutError(), 60.0),
            (Response(status=502), 2.0),
        ):
            client = self.client(responses=[failure, Response()])
            self.assertEqual(client.get(CATALOG).status, 200)
            self.assertEqual(self.opener.call_count, 2)
            self.assertEqual(self.clock.sleeps, [wait])
        for failures, reason in (([TimeoutError(), TimeoutError()], "timeout"), ([RemoteDisconnected(), RemoteDisconnected()], "connection-closed"), ([Response(status=500), Response(status=500)], "http-500")):
            client = self.client(responses=failures)
            self.assert_reason(reason, lambda: client.get(CATALOG))
            self.assertEqual(self.opener.call_count, 2)

    def test_other_client_http_error_is_not_retried(self):
        client = self.client(responses=[Response(status=403)])
        self.assert_reason("http-403", lambda: client.get(CATALOG))
        self.assertEqual(self.opener.call_count, 1)

    def test_request_budget_counts_retries_and_pacing_across_calls(self):
        client = self.client(responses=[Response(), Response()], max_requests=1)
        client.get(CATALOG)
        self.assert_reason("request-limit", lambda: client.get(CATALOG))
        self.assertEqual(self.opener.call_count, 1)
        client = self.client(responses=[TimeoutError(), Response()], max_requests=1)
        self.assert_reason("timeout", lambda: client.get(CATALOG))
        self.assertEqual(self.opener.call_count, 1)
        self.assertEqual(self.clock.sleeps, [])

    def test_commoncrawl_interval_starts_after_slow_response_and_is_shared(self):
        clock = Clock()
        gate = _SourceGate()
        first = self.client(
            clock=clock, gate=gate,
            responses=[Response(b"{}", clock=clock, delay=3.0)],
        )
        first.get(CATALOG)
        self.assertEqual(clock.now, 6.0)  # Body and final EOF read each took time.
        starts = []
        def second_opener(request, **kwargs):
            starts.append(clock.now)
            return Response()
        second = self.client(clock=clock, gate=gate, opener=second_opener)
        second.get(CATALOG)
        self.assertEqual(starts, [7.0])
        self.assertEqual(clock.sleeps, [1.0])

    def test_commoncrawl_failure_also_leaves_interval_for_next_client(self):
        clock = Clock()
        gate = _SourceGate()
        def failed_opener(request, **kwargs):
            clock.now += 4.0
            raise RemoteDisconnected()
        first = self.client(clock=clock, gate=gate, opener=failed_opener, max_requests=1)
        self.assert_reason("connection-closed", lambda: first.get(CATALOG))
        self.assertEqual(clock.sleeps, [])
        second = self.client(clock=clock, gate=gate)
        self.assertEqual(second.get(CATALOG).status, 200)
        self.assertEqual(clock.now, 5.0)
        self.assertEqual(clock.sleeps, [1.0])

    def test_commoncrawl_insufficient_retry_time_keeps_original_reason_without_sleep(self):
        for failure, reason, budget, elapsed in (
            (RemoteDisconnected(), "connection-closed", 60.0, 0.0),
            (TimeoutError(), "timeout", 90.0, 30.0),
            (Response(status=502), "http-502", 2.0, 0.0),
        ):
            with self.subTest(reason=reason):
                clock = Clock()
                calls = []
                def opener(request, **kwargs):
                    calls.append(request)
                    clock.now += elapsed
                    if isinstance(failure, Exception):
                        raise failure
                    return failure
                client = self.client(clock=clock, opener=opener, budget_seconds=budget)
                self.assert_reason(reason, lambda: client.get(CATALOG))
                self.assertEqual(len(calls), 1)
                self.assertEqual(clock.sleeps, [])

    def test_no_remaining_attempt_does_not_sleep_for_network_or_http_retry(self):
        for failure, reason in (
            (RemoteDisconnected(), "connection-closed"),
            (Response(status=500), "http-500"),
        ):
            with self.subTest(reason=reason):
                client = self.client(responses=[failure, Response()], max_requests=1)
                self.assert_reason(reason, lambda: client.get(CATALOG))
                self.assertEqual(self.opener.call_count, 1)
                self.assertEqual(self.clock.sleeps, [])

    def test_wayback_retains_short_retry_without_commoncrawl_spacing(self):
        url = WB + urlencode(TARGET)
        for failure in (RemoteDisconnected(), TimeoutError(), Response(status=502)):
            with self.subTest(failure=type(failure).__name__):
                client = self.client("waybackarchive", responses=[failure, Response(), Response()])
                self.assertEqual(client.get(url).status, 200)
                self.assertEqual(self.clock.sleeps, [1.0])
                self.assertEqual(client.get(url).status, 200)
                self.assertEqual(self.clock.sleeps, [1.0])

    def test_retry_wakeup_past_deadline_preserves_original_error(self):
        clock = Clock()
        def late_sleep(delay):
            clock.sleeps.append(delay)
            clock.now += 100.0
        clock.sleep = late_sleep
        client = self.client(clock=clock, responses=[RemoteDisconnected(), Response()])
        self.assert_reason("connection-closed", lambda: client.get(CATALOG))
        self.assertEqual(self.opener.call_count, 1)
        self.assertEqual(clock.sleeps, [60.0])

    def test_total_budget_stops_slow_stream_and_closes_response(self):
        clock = Clock()
        response = Response(b"123456", clock=clock, delay=1.1, chunk=1)
        client = self.client(responses=[response], clock=clock, budget_seconds=2)
        self.assert_reason("deadline-exceeded", lambda: client.get(CATALOG))
        self.assertEqual(self.opener.call_count, 1)
        self.assertTrue(response.closed)

    def test_per_request_budget_retries_without_resetting_global_deadline(self):
        clock = Clock()
        response = Response(b"123456", clock=clock, delay=1.1, chunk=1)
        client = self.client("waybackarchive", responses=[response, Response()], clock=clock, request_timeout=2, budget_seconds=10)
        self.assertEqual(client.get(WB + urlencode(TARGET)).status, 200)
        self.assertEqual(self.opener.call_count, 2)
        self.assertTrue(response.closed)

    def test_declared_or_streamed_excess_and_encoding_are_rejected(self):
        for response, reason in (
            (Response(headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)}), "response-too-large"),
            (Response(b"x" * (MAX_RESPONSE_BYTES + 1)), "response-too-large"),
            (Response(headers={"Content-Encoding": "gzip"}), "response-encoding"),
            (Response(headers={"X-Data": "a" * MAX_HEADER_BYTES}), "response-headers-too-large"),
        ):
            with self.subTest(reason=reason):
                client = self.client(responses=[response])
                self.assert_reason(reason, lambda: client.get(CATALOG))
                self.assertEqual(self.opener.call_count, 1)
                self.assertTrue(response.closed)

    def test_incomplete_content_length_is_a_transport_failure_not_partial_success(self):
        client = self.client(responses=[Response(b"a", headers={"Content-Length": "2"}), Response(b"a", headers={"Content-Length": "2"})])
        self.assert_reason("transport-error", lambda: client.get(CATALOG))
        self.assertEqual(self.opener.call_count, 2)

    def test_same_source_clients_cannot_run_parallel_requests(self):
        gate = _SourceGate()
        clock = Clock()
        second_opener = Mock(return_value=Response())
        second = self.client(clock=clock, gate=gate, opener=second_opener)
        def first_opener(request, **kwargs):
            self.assert_reason("source-busy", lambda: second.get(CATALOG))
            return Response()
        first = self.client(clock=clock, gate=gate, opener=first_opener)
        self.assertEqual(first.get(CATALOG).status, 200)
        second_opener.assert_not_called()
        self.assertEqual(second.get(CATALOG).status, 200)
        self.assertEqual(clock.sleeps, [1.0])


if __name__ == "__main__":
    unittest.main()

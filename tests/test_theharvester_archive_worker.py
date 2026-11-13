"""Archive pagination and truthful source outcomes without installed tools/network."""

from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import stat
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from xti.adapters.archive_http import (
    ArchiveHTTPClient, ArchiveHTTPError, ArchiveHTTPResponse, _SourceGate,
)
from xti.adapters.theharvester_archive import parse_theharvester_jsonl
from xti.adapters.theharvester_archive_worker import (
    collect_commoncrawl, collect_wayback, run_archive_sources, write_report,
)


DOMAIN = "example.com"
INDEX = "https://index.commoncrawl.org/CC-MAIN-2026-40-index"


def response(body=b"", *, status=200):
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
    elif isinstance(body, str):
        body = body.encode()
    return ArchiveHTTPResponse(status, body, {})


def catalog(*indexes):
    return response([
        {"id": f"CC-MAIN-2026-{40 - number:02d}", "cdx-api": endpoint,
         "to": "2026-10-01T00:00:00Z"}
        for number, endpoint in enumerate(indexes or (INDEX,))
    ])


def page(*hosts):
    return response("\n".join(json.dumps({"url": "https://" + host + "/"}) for host in hosts))


class Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if not self.responses:
            raise AssertionError("unexpected extra request")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class Helpers:
    def __init__(self, domain, *, limit):
        self.domain = domain
        self.limit = limit

    @staticmethod
    def _select_indexes(entries):
        return entries

    @staticmethod
    def _extract_domain_from_url(value):
        try:
            return (urlsplit(value).hostname or "").lower().rstrip(".")
        except ValueError:
            return ""

    @staticmethod
    def _parse_page(payload):
        if payload.lstrip().startswith("<"):
            return None
        body, separator, continuation = payload.replace("\r\n", "\n").rpartition("\n\n")
        if not separator:
            return payload.splitlines(), None
        lines = [line.strip() for line in continuation.splitlines() if line.strip()]
        return body.splitlines(), lines[0] if len(lines) == 1 else None


class ArchiveWorkerTests(unittest.TestCase):
    def setUp(self):
        self.helper = Helpers(DOMAIN, limit=250)

    def cc(self, client, limit=250):
        return collect_commoncrawl(DOMAIN, limit, client, self.helper)

    def wb(self, client, limit=250):
        return collect_wayback(DOMAIN, limit, client, self.helper)

    def test_combined_report_keeps_provenance_and_parent_schema(self):
        clients = {
            "commoncrawl": Client([catalog(), response({"pages": 1, "pageSize": 1}),
                                    page("api.example.com", DOMAIN, "outside.test")]),
            "waybackarchive": Client([response("https://api.example.com/\nhttps://mail.example.com/\n")]),
        }
        constructed = []

        def factory(source, domain, **kwargs):
            if source == "waybackarchive":
                self.assertEqual(len(clients["commoncrawl"].calls), 3)
            self.assertEqual(domain, DOMAIN)
            self.assertEqual(kwargs, {
                "budget_seconds": 150 if source == "commoncrawl" else 90,
                "request_timeout": 30, "max_requests": 30,
            })
            constructed.append(source)
            return clients[source]

        records = run_archive_sources(
            DOMAIN, 250, commoncrawl_helpers=Helpers, wayback_helpers=Helpers,
            client_factory=factory, now=lambda: datetime(2026, 11, 13, tzinfo=timezone.utc),
        )
        self.assertEqual(constructed, ["commoncrawl", "waybackarchive"])
        self.assertEqual(records[0]["evidence_status"], "complete")
        self.assertEqual(records[0]["action_executions"], [])
        self.assertEqual(records[0]["artifacts"], [])
        self.assertEqual(records[1:], [
            {"type": "hostname", "value": "api.example.com", "sources": ["commoncrawl", "waybackarchive"]},
            {"type": "hostname", "value": "mail.example.com", "sources": ["waybackarchive"]},
        ])
        body = b"".join(json.dumps(record).encode() + b"\n" for record in records)
        batch = parse_theharvester_jsonl(body, domain=DOMAIN, limit=250)
        self.assertEqual(batch.record_count, 2)
        self.assertEqual(len(batch.documents), 3)
        self.assertEqual(batch.warnings, ())

    def test_cc_reads_whole_page_without_truncation_or_duplicate_pattern(self):
        hosts = [f"host-{index}.example.com" for index in range(65)]
        client = Client([catalog(), response({"pages": 1}), page(*hosts)])
        result = self.cc(client)
        self.assertEqual(result.status, "completed")
        self.assertEqual(set(result.hosts), set(hosts))
        self.assertEqual(len(client.calls), 3)
        query = parse_qs(urlsplit(client.calls[-1]).query)
        self.assertEqual(query["url"], [DOMAIN])
        self.assertEqual(query["matchType"], ["domain"])
        self.assertEqual(query["pageSize"], ["1"])
        self.assertNotIn("limit", query)

    def test_thirteen_slow_indexes_complete_with_current_budget_and_wayback_is_independent(self):
        # The observed yearly catalog selected 13 indexes. Individually healthy
        # metadata requests took long enough to exhaust the former 90s budget.
        indexes = [
            f"https://index.commoncrawl.org/CC-MAIN-2026-{40 - number:02d}-index"
            for number in range(13)
        ]

        class HTTPResponse(BytesIO):
            status = 200
            headers = {}

        for previous_budget in (True, False):
            with self.subTest(previous_budget=previous_budget):
                elapsed = [0.0]
                calls = []
                constructed = []

                def clock():
                    return elapsed[0]

                def sleep(delay):
                    elapsed[0] += delay

                def opener(request, *, timeout):
                    parsed = urlsplit(request.full_url)
                    calls.append(parsed)
                    if parsed.path == "/collinfo.json":
                        delay, body = 0, catalog(*indexes).body
                    elif parsed.hostname == "index.commoncrawl.org":
                        delay, body = 7, b'{"pages":0,"pageSize":1}'
                    else:
                        delay, body = 20, b"https://mail.example.com/\n"
                    if delay >= timeout:
                        elapsed[0] += timeout
                        raise TimeoutError("response headers exceeded request deadline")
                    elapsed[0] += delay
                    return HTTPResponse(body)

                def factory(source, domain, **kwargs):
                    constructed.append((source, clock(), kwargs["budget_seconds"]))
                    if previous_budget and source == "commoncrawl":
                        kwargs["budget_seconds"] = 90
                    return ArchiveHTTPClient(
                        source, domain, opener=opener, clock=clock, sleep=sleep,
                        gate=_SourceGate(), **kwargs,
                    )

                records = run_archive_sources(
                    DOMAIN, 250, commoncrawl_helpers=Helpers, wayback_helpers=Helpers,
                    client_factory=factory, monotonic=clock,
                )
                summary = records[0]
                cc, wb = summary["source_executions"]
                self.assertEqual(
                    (cc["status"], cc["stop_reason"]),
                    ("partial", "timeout") if previous_budget else ("completed", None),
                )
                self.assertEqual(wb["status"], "completed")
                self.assertEqual(wb["duration_ms"], 20_000)
                self.assertEqual(
                    constructed,
                    [("commoncrawl", 0.0, 150),
                     ("waybackarchive", 90.0 if previous_budget else 104.0, 90)],
                )
                metadata = [call for call in calls if call.query and "showNumPages" in call.query]
                self.assertEqual(
                    [call.path for call in metadata],
                    [urlsplit(index).path for index in indexes[:12 if previous_budget else 13]],
                )
                self.assertEqual(summary["evidence_status"], "partial" if previous_budget else "complete")
                self.assertEqual(records[1:], [
                    {"type": "hostname", "value": "mail.example.com", "sources": ["waybackarchive"]},
                ])

    def test_cc_no_capture_404_requires_exact_source_message(self):
        for body in (f"No Captures found for: {DOMAIN}\n",
                     {"message": f"No Captures found for: {DOMAIN}"}):
            with self.subTest(body=body):
                result = self.cc(Client([catalog(), response(body, status=404)]))
                self.assertEqual((result.status, result.hosts), ("completed", ()))
        for body in ("<html>Not found</html>", "No Captures found for: other.com",
                     {"message": f"No Captures found for: {DOMAIN}", "extra": 1},
                     '{"message":"wrong","message":"No Captures found for: example.com"}'):
            with self.subTest(body=body):
                result = self.cc(Client([catalog(), response(body, status=404)]))
                self.assertEqual((result.status, result.stop_reason), ("failed", "http-404"))

    def test_cc_transport_and_malformed_catalog_are_not_empty_success(self):
        for value, reason in (
            (ArchiveHTTPError("transport-error"), "transport-error"),
            (response([]), "invalid-catalog"),
            (response(b""), "invalid-json"),
            (response('{"a":1,"a":2}'), "invalid-json"),
            (response('[1e999]'), "invalid-json"),
        ):
            with self.subTest(reason=reason):
                result = self.cc(Client([value]))
                self.assertEqual((result.status, result.stop_reason, result.hosts), ("failed", reason, ()))

    def test_cc_partial_pages_and_empty_completed_index_survive_later_failure(self):
        client = Client([catalog(), response({"pages": 2}), page("api.example.com"),
                         ArchiveHTTPError("deadline-exceeded")])
        result = self.cc(client)
        self.assertEqual((result.status, result.stop_reason, result.hosts),
                         ("partial", "deadline-exceeded", ("api.example.com",)))
        second = "https://index.commoncrawl.org/CC-MAIN-2026-39-index"
        client = Client([catalog(INDEX, second), response({"pages": 0}),
                         ArchiveHTTPError("http-429", status=429, retry_after_seconds=60)])
        result = self.cc(client)
        self.assertEqual((result.status, result.stop_reason), ("partial", "http-429; retry-after=60s"))
        self.assertEqual(result.hosts, ())

    def test_cc_page_validation_keeps_only_previously_complete_pages(self):
        malformed_pages = (b"", b'{"url":"https://api.example.com"}\nnot-json',
                           b'{"url":"https://api.example.com","url":"https://other.example.com"}',
                           b'{"url":123}')
        for body in malformed_pages:
            with self.subTest(body=body):
                result = self.cc(Client([catalog(), response({"pages": 2}),
                                         page("saved.example.com"), response(body)]))
                self.assertEqual(result.status, "partial")
                self.assertEqual(result.hosts, ("saved.example.com",))

    def test_cc_result_limit_and_rejected_catalog_entries_are_partial(self):
        result = self.cc(Client([catalog(), response({"pages": 1}),
                                 page("api.example.com", "mail.example.com")]), limit=1)
        self.assertEqual((result.status, result.stop_reason), ("partial", "result-limit"))
        self.assertEqual(len(result.hosts), 1)
        records = json.loads(catalog().body)
        records.append({"cdx-api": "http://127.0.0.1/internal", "to": "2026-11-13"})
        client = Client([response(records), response({"pages": 0})])
        result = self.cc(client)
        self.assertEqual((result.status, result.stop_reason), ("partial", "catalog-entries-rejected"))
        self.assertTrue(all("127.0.0.1" not in url for url in client.calls))

    def test_wayback_uses_one_domain_pattern_small_pages_and_resumes(self):
        client = Client([response("https://api.example.com/\n\nnext%2Bcursor\n"),
                         response("https://mail.example.com/\n")])
        result = self.wb(client)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.hosts, ("api.example.com", "mail.example.com"))
        self.assertEqual(len(client.calls), 2)
        first = parse_qs(urlsplit(client.calls[0]).query)
        second = parse_qs(urlsplit(client.calls[1]).query)
        self.assertEqual(first["url"], [DOMAIN])
        self.assertEqual(first["matchType"], ["domain"])
        self.assertEqual(first["limit"], ["50"])
        self.assertEqual(second["resumeKey"], ["next+cursor"])

    def test_wayback_real_empty_success_is_distinct_from_transport_failure(self):
        for empty in (b"", b"\n", b"\n\n"):
            with self.subTest(empty=empty):
                result = self.wb(Client([response(empty)]))
                self.assertEqual((result.status, result.hosts), ("completed", ()))
        for error in (ArchiveHTTPError("timeout"), ArchiveHTTPError("transport-error")):
            result = self.wb(Client([error]))
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.stop_reason, error.reason)
        result = self.wb(Client([response("", status=404)]))
        self.assertEqual((result.status, result.stop_reason), ("failed", "http-404"))

    def test_wayback_rate_limit_and_partial_progress_remain_distinct(self):
        for code in (429, 503):
            with self.subTest(code=code):
                error = ArchiveHTTPError(f"http-{code}", status=code, retry_after_seconds=60)
                result = self.wb(Client([error]))
                self.assertEqual((result.status, result.stop_reason),
                                 ("rate-limited", f"http-{code}; retry-after=60s"))
                result = self.wb(Client([response("https://api.example.com/\n\nnext\n"), error]))
                self.assertEqual(result.status, "partial")
                self.assertEqual(result.hosts, ("api.example.com",))

    def test_wayback_result_request_and_cursor_limits_are_not_complete(self):
        result = self.wb(Client([response("https://api.example.com/\nhttps://mail.example.com/\n")]), limit=1)
        self.assertEqual((result.status, result.stop_reason), ("partial", "result-limit"))
        result = self.wb(Client([response("https://api.example.com/\n\nnext\n"),
                                 ArchiveHTTPError("request-limit")]))
        self.assertEqual((result.status, result.stop_reason), ("partial", "request-limit"))
        result = self.wb(Client([response("https://api.example.com/\n\nnext\n"),
                                 response("https://mail.example.com/\n\nnext\n")]))
        self.assertEqual((result.status, result.stop_reason), ("partial", "repeated-cursor"))
        self.assertEqual(len(result.hosts), 2)

    def test_malformed_wayback_page_does_not_fabricate_empty_success(self):
        for body in ("<html>error</html>", "https://api.example.com/\n\none\ntwo\n",
                     "[]", "https://api.example.com/\n\nnext\x1b\n"):
            with self.subTest(body=body):
                result = self.wb(Client([response(body)]))
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.hosts, ())

    def test_one_failed_source_does_not_stop_other_and_two_failures_stay_failed(self):
        def execute(second):
            clients = {"commoncrawl": Client([ArchiveHTTPError("transport-error")]),
                       "waybackarchive": Client([second])}
            return run_archive_sources(
                DOMAIN, 250, commoncrawl_helpers=Helpers, wayback_helpers=Helpers,
                client_factory=lambda source, domain, **kwargs: clients[source],
            )
        records = execute(response("https://api.example.com/"))
        self.assertEqual(records[0]["evidence_status"], "partial")
        self.assertEqual(records[1]["sources"], ["waybackarchive"])
        records = execute(ArchiveHTTPError("http-429", status=429))
        self.assertEqual(records[0]["evidence_status"], "failed")
        self.assertEqual(records[0]["result_count"], 0)

    def test_report_is_private_exclusive_and_keeps_original_on_second_write(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.jsonl"
            write_report(path, [{"type": "summary", "marker": "first"}])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                write_report(path, [{"marker": "second"}])
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

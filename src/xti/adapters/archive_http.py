"""Bounded HTTPS transport for the two reviewed passive archive endpoints.

The transport preserves HTTP failures instead of turning them into empty
archive results. It never follows redirects, uses environment proxies, or
disables TLS verification. Only the provider worker interprets a narrow 404.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException, IncompleteRead, RemoteDisconnected
import json
import math
import re
import ssl
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_HEADER_BYTES = 64 * 1024
MAX_URL_LENGTH = 8192
READ_CHUNK_BYTES = 64 * 1024
_CC_PATH = re.compile(r"/CC-MAIN-[0-9]{4}-[0-9]{2}-index\Z")
_HOSTS = {
    "commoncrawl": "index.commoncrawl.org",
    "waybackarchive": "web.archive.org",
}
USER_AGENT = "XTI/archive-p0-v3 (passive archive index research)"


class ArchiveHTTPError(Exception):
    """A bounded, non-sensitive reason suitable for a source execution report."""

    def __init__(
        self, reason: str, *, status: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class ArchiveHTTPResponse:
    status: int
    body: bytes
    headers: dict[str, str]


@dataclass
class _SourceGate:
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_finished: float | None = None


# A second client in this process cannot make concurrent requests to the same
# archive. XTI's outer execution lock also prevents concurrent discovery runs.
_SOURCE_GATES = {source: _SourceGate() for source in _HOSTS}


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate-json-key")
        result[key] = value
    return result


def _json_constant(value):
    raise ValueError("non-finite-json-number")


def _json_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite-json-number")
    return number


def _canonical_domain(value: object) -> bool:
    if (
        not isinstance(value, str) or not 1 <= len(value) <= 253
        or not value.isascii() or value != value.lower()
    ):
        return False
    labels = value.split(".")
    return len(labels) > 1 and all(
        1 <= len(label) <= 63
        and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) is not None
        for label in labels
    ) and not all(label.isdigit() for label in labels)


def _number(value: object, *, maximum: float) -> bool:
    return (
        type(value) in (int, float) and math.isfinite(value)
        and 0 < value <= maximum
    )


class ArchiveHTTPClient:
    def __init__(
        self, source: str, domain: str, *, budget_seconds: float = 90,
        request_timeout: float = 30, max_requests: int = 30,
        opener: Callable | None = None, clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        wall_clock: Callable[[], datetime] | None = None,
        gate: _SourceGate | None = None,
    ) -> None:
        if source not in _HOSTS:
            raise ValueError("Unknown archive source")
        if not _canonical_domain(domain):
            raise ValueError("Archive domain must be canonical")
        if (
            not _number(budget_seconds, maximum=180)
            or not _number(request_timeout, maximum=30)
            or type(max_requests) is not int or not 1 <= max_requests <= 100
        ):
            raise ValueError("Invalid archive request budget")
        self.source = source
        self.domain = domain
        self.request_timeout = float(request_timeout)
        self.max_requests = max_requests
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._gate = gate or _SOURCE_GATES[source]
        self._deadline = self._clock() + budget_seconds
        self._requests = 0
        self._opener = opener or build_opener(
            ProxyHandler({}), _NoRedirects(),
            HTTPSHandler(context=ssl.create_default_context()),
        ).open

    @staticmethod
    def _integer(value: str, *, minimum: int, maximum: int) -> bool:
        return (
            value.isascii() and value.isdigit() and len(value) <= 8
            and minimum <= int(value) <= maximum
        )

    def _validate_url(self, url: str) -> None:
        if (
            not isinstance(url, str) or not 1 <= len(url) <= MAX_URL_LENGTH
            or not url.isascii() or any(ord(char) <= 32 or ord(char) == 127 for char in url)
        ):
            raise ArchiveHTTPError("invalid-url")
        try:
            parsed = urlsplit(url)
            host = _HOSTS[self.source]
            if (
                parsed.scheme != "https" or parsed.hostname != host
                or parsed.netloc not in (host, host + ":443")
                or parsed.port not in (None, 443) or parsed.username is not None
                or parsed.password is not None or "#" in url
            ):
                raise ValueError("scope")
            if self.source == "commoncrawl" and parsed.path == "/collinfo.json":
                if parsed.query or "?" in url:
                    raise ValueError("catalog-query")
                return
            if self.source == "commoncrawl":
                if _CC_PATH.fullmatch(parsed.path) is None:
                    raise ValueError("path")
                allowed = {"url", "matchType", "output", "fl", "limit", "showNumPages", "pageSize", "page"}
            else:
                if parsed.path != "/cdx/search/cdx":
                    raise ValueError("path")
                allowed = {"url", "matchType", "output", "fl", "collapse", "limit", "showResumeKey", "resumeKey"}
            pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=12)
            query = dict(pairs)
            if len(query) != len(pairs) or not set(query) <= allowed:
                raise ValueError("query-fields")
            if query.get("url") != self.domain or query.get("matchType") != "domain":
                raise ValueError("target")
            for key, value in pairs:
                if not value or any(not char.isprintable() for char in value):
                    raise ValueError("query-value")
                if key == "output" and value != "json":
                    raise ValueError("output")
                if key == "fl" and value != ("url" if self.source == "commoncrawl" else "original"):
                    raise ValueError("fields")
                if key == "collapse" and value != "urlkey":
                    raise ValueError("collapse")
                if key in ("showNumPages", "showResumeKey") and value != "true":
                    raise ValueError("boolean")
                if key == "limit" and not self._integer(value, minimum=1, maximum=1000):
                    raise ValueError("limit")
                if key == "pageSize" and not self._integer(value, minimum=1, maximum=5):
                    raise ValueError("page-size")
                if key == "page" and not self._integer(value, minimum=0, maximum=100_000):
                    raise ValueError("page")
                if key == "resumeKey" and (len(value) > 2048 or not value.isascii()):
                    raise ValueError("cursor")
        except (ValueError, TypeError) as error:
            raise ArchiveHTTPError("invalid-url") from error

    def _remaining(self, deadline: float | None = None) -> float:
        now = self._clock()
        remaining = self._deadline - now
        if remaining <= 0:
            raise ArchiveHTTPError("deadline-exceeded")
        if deadline is not None and deadline <= now:
            raise TimeoutError("Archive request deadline reached")
        return min(remaining, deadline - now) if deadline is not None else remaining

    def _pause(self, delay: float) -> None:
        if delay >= self._remaining():
            raise ArchiveHTTPError("deadline-exceeded")
        self._sleep(delay)
        self._remaining()

    def _retry_pause(self, delay: float) -> bool:
        """Wait only when another attempt can start, preserving its cause otherwise."""
        if self._requests >= self.max_requests or delay >= self._deadline - self._clock():
            return False
        self._sleep(delay)
        # A slow wakeup must not replace the observed network/HTTP failure with
        # a synthetic deadline error. The caller still owns the original cause.
        return self._clock() < self._deadline

    def _headers(self, raw) -> dict[str, str]:
        result: dict[str, str] = {}
        size = 0
        if not hasattr(raw, "items"):
            raise ArchiveHTTPError("invalid-response")
        for index, (name, value) in enumerate(raw.items()):
            if not isinstance(name, str) or not isinstance(value, str):
                raise ArchiveHTTPError("invalid-response")
            size += len(name) + len(value) + 4
            if index >= 100 or size > MAX_HEADER_BYTES:
                raise ArchiveHTTPError("response-headers-too-large")
            if (
                not name.isascii() or not name or not name.isprintable()
                or any(not char.isprintable() for char in value)
            ):
                raise ArchiveHTTPError("invalid-response")
            key = name.lower()
            if key in result and key in {"content-length", "content-encoding", "retry-after"}:
                raise ArchiveHTTPError("invalid-response")
            result[key] = value
        return result

    def _retry_after(self, headers: dict[str, str]) -> float | None:
        value = headers.get("retry-after", "").strip()
        if not value:
            return None
        if value.isascii() and value.isdigit() and len(value) <= 10:
            return float(min(int(value), 2_147_483_647))
        try:
            parsed = parsedate_to_datetime(value)
            now = self._wall_clock()
            if parsed.tzinfo is None or now.tzinfo is None:
                return None
            return max(0.0, min((parsed - now).total_seconds(), 2_147_483_647.0))
        except (ValueError, TypeError, OverflowError):
            return None

    @staticmethod
    def _read_timeout(response, timeout: float) -> None:
        # urllib's HTTPSResponse exposes its socket through the buffered reader.
        # read1() below makes one raw read; updating this timeout each iteration
        # prevents a slow stream from restarting the complete request budget.
        fp = getattr(response, "fp", None)
        raw = getattr(fp, "raw", None)
        sock = getattr(raw, "_sock", None) or getattr(fp, "_sock", None)
        if sock is not None:
            sock.settimeout(timeout)

    def _consume(self, response, deadline: float) -> ArchiveHTTPResponse:
        status = getattr(response, "status", None)
        if status is None:
            status = response.getcode()
        if type(status) is not int or not 100 <= status <= 599:
            raise ArchiveHTTPError("invalid-response")
        headers = self._headers(response.headers)
        retry_after = self._retry_after(headers)
        if 300 <= status <= 399:
            raise ArchiveHTTPError("redirect-rejected", status=status)
        if status not in (200, 404):
            raise ArchiveHTTPError(
                f"http-{status}", status=status, retry_after_seconds=retry_after,
            )
        if headers.get("content-encoding", "identity").lower() not in ("identity", ""):
            raise ArchiveHTTPError("response-encoding", status=status)
        length = headers.get("content-length")
        if length is not None:
            if not self._integer(length, minimum=0, maximum=MAX_RESPONSE_BYTES):
                raise ArchiveHTTPError("response-too-large", status=status)
            expected = int(length)
        else:
            expected = None
        parts: list[bytes] = []
        total = 0
        reader = getattr(response, "read1", None) or response.read
        while True:
            self._read_timeout(response, self._remaining(deadline))
            chunk = reader(min(READ_CHUNK_BYTES, MAX_RESPONSE_BYTES - total + 1))
            self._remaining(deadline)
            if not isinstance(chunk, bytes):
                raise ArchiveHTTPError("invalid-response")
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise ArchiveHTTPError("response-too-large", status=status)
            parts.append(chunk)
        if expected is not None and total != expected:
            raise IncompleteRead(b"", max(0, expected - total))
        return ArchiveHTTPResponse(status, b"".join(parts), headers)

    def _once(self, url: str) -> ArchiveHTTPResponse:
        self._remaining()
        if self._requests >= self.max_requests:
            raise ArchiveHTTPError("request-limit")
        if self.source == "commoncrawl" and self._gate.last_finished is not None:
            delay = 1.0 - (self._clock() - self._gate.last_finished)
            if delay > 0:
                self._pause(delay)
        self._requests += 1
        request_deadline = self._clock() + min(self.request_timeout, self._remaining())
        request = Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain;q=0.9",
            "Accept-Encoding": "identity",
        })
        try:
            try:
                response = self._opener(request, timeout=self._remaining(request_deadline))
            except HTTPError as error:
                response = error
            with response:
                return self._consume(response, request_deadline)
        finally:
            # Common Crawl's recommended client leaves the interval after a
            # completed request, including when that request was slow or failed.
            self._gate.last_finished = self._clock()

    def get(self, url: str) -> ArchiveHTTPResponse:
        self._validate_url(url)
        if not self._gate.lock.acquire(blocking=False):
            raise ArchiveHTTPError("source-busy")
        try:
            for attempt in range(2):
                try:
                    return self._once(url)
                except ArchiveHTTPError as error:
                    if (
                        attempt == 0 and error.status is not None
                        and 500 <= error.status <= 599 and error.status != 503
                        and error.retry_after_seconds is None
                        and self._retry_pause(2.0 if self.source == "commoncrawl" else 1.0)
                    ):
                        continue
                    raise
                except (URLError, HTTPException, OSError) as error:
                    cause = error.reason if isinstance(error, URLError) else error
                    if isinstance(cause, ssl.SSLError):
                        raise ArchiveHTTPError("tls-error") from error
                    reason = (
                        "timeout" if isinstance(cause, TimeoutError)
                        else "connection-closed" if isinstance(cause, (RemoteDisconnected, ConnectionResetError, BrokenPipeError))
                        else "transport-error"
                    )
                    delay = 60.0 if self.source == "commoncrawl" else 1.0
                    if attempt == 0 and self._retry_pause(delay):
                        continue
                    raise ArchiveHTTPError(reason) from error
            raise AssertionError("Unreachable archive retry state")
        finally:
            self._gate.lock.release()

    def get_json(self, url: str):
        response = self.get(url)
        if response.status != 200:
            raise ArchiveHTTPError(f"http-{response.status}", status=response.status)
        try:
            return json.loads(
                response.body.decode("utf-8"), object_pairs_hook=_json_object,
                parse_constant=_json_constant, parse_float=_json_float,
            )
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ArchiveHTTPError("invalid-json") from error

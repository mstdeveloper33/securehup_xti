"""Passive archive worker using the pinned tool's parsing helpers.

This module runs in the optional theHarvester Python environment.  The core
application does not import that tool or its dependencies.  Only the two
archive sources below can be contacted through the bounded HTTP transport.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable
from urllib.parse import unquote_plus, urlencode, urlsplit
from uuid import uuid4

from xti.adapters.archive_http import ArchiveHTTPClient, ArchiveHTTPError
from xti.domain.assets import ValidationError, normalize_domain


SOURCES = ("commoncrawl", "waybackarchive")
SOURCE_BUDGET_SECONDS = {"commoncrawl": 150, "waybackarchive": 90}
CC_CATALOG = "https://index.commoncrawl.org/collinfo.json"
WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_CATALOG_ENTRIES = 1_000
MAX_PAGE_COUNT = 10_000
MAX_LINE_BYTES = 64 * 1024
WAYBACK_PAGE_SIZE = 50


class ArchiveDataError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ArchiveOutcome:
    source: str
    status: str
    hosts: tuple[str, ...]
    stop_reason: str | None = None


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("non-finite JSON number")


def _float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite JSON number")
    return number


def _json(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8"), object_pairs_hook=_object,
                          parse_constant=_constant, parse_float=_float)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ArchiveDataError("invalid-json") from error


def _text(body: bytes) -> str:
    try:
        return body.decode("utf-8")
    except UnicodeError as error:
        raise ArchiveDataError("invalid-encoding") from error


def _reason(error: Exception) -> str:
    value = getattr(error, "reason", "unexpected-source-error")
    if not isinstance(value, str) or not value or not value.isprintable():
        return "unexpected-source-error"
    result = value[:160]
    retry_after = getattr(error, "retry_after_seconds", None)
    if (type(retry_after) in (int, float) and math.isfinite(retry_after)
            and 0 <= retry_after <= 2_147_483_647):
        result += f"; retry-after={math.ceil(retry_after)}s"
    return result


def _outcome(
    source: str, hosts: set[str], *, reason: str | None = None,
    progress: bool = False, rate_limited: bool = False,
) -> ArchiveOutcome:
    status = "completed"
    if reason:
        status = "partial" if progress or hosts else (
            "rate-limited" if rate_limited else "failed"
        )
    return ArchiveOutcome(source, status, tuple(sorted(hosts)), reason)


def _is_rate_limited(error: Exception) -> bool:
    return getattr(error, "status", None) in (429, 503) or getattr(error, "reason", None) in {
        "http-429", "http-503",
    }


def _http_success(response: Any) -> bytes:
    if response.status != 200:
        raise ArchiveDataError(f"http-{response.status}")
    if not isinstance(response.body, bytes):
        raise ArchiveDataError("invalid-response")
    return response.body


def _cc_no_captures(response: Any, domain: str) -> bool:
    if response.status != 404 or not isinstance(response.body, bytes):
        return False
    expected = f"No Captures found for: {domain}"
    try:
        text = response.body.decode("utf-8").rstrip("\r\n")
    except UnicodeError:
        return False
    if text == expected:
        return True
    try:
        return _json(response.body) == {"message": expected}
    except ArchiveDataError:
        return False


def _catalog_entry_valid(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    endpoint = entry.get("cdx-api")
    if not isinstance(endpoint, str):
        return False
    try:
        parsed = urlsplit(endpoint)
        date = entry.get("to")
        if not isinstance(date, str):
            return False
        datetime.fromisoformat(date.replace("Z", "+00:00"))
        return (
            parsed.scheme == "https" and parsed.netloc == "index.commoncrawl.org"
            and parsed.path.startswith("/CC-MAIN-") and parsed.path.endswith("-index")
            and not parsed.query and not parsed.fragment
        )
    except ValueError:
        return False


def _scoped_host(value: object, *, domain: str, extractor: Callable[[str], str]) -> str | None:
    if not isinstance(value, str) or not value or not value.isprintable():
        raise ArchiveDataError("invalid-url-record")
    extracted = extractor(value)
    if not extracted:
        raise ArchiveDataError("invalid-url-record")
    try:
        host = normalize_domain(extracted)
    except ValidationError as error:
        raise ArchiveDataError("invalid-url-record") from error
    return host if host.endswith("." + domain) else None


def _add_bounded(hosts: set[str], new_hosts: set[str], limit: int) -> bool:
    for host in sorted(new_hosts):
        hosts.add(host)
        if len(hosts) >= limit:
            return True
    return False


def collect_commoncrawl(domain: str, limit: int, client: Any, helper: Any) -> ArchiveOutcome:
    """Read the selected yearly indexes, never truncate a fetched index page."""
    hosts: set[str] = set()
    progress = False
    degraded: str | None = None
    try:
        catalog = _json(_http_success(client.get(CC_CATALOG)))
        if not isinstance(catalog, list) or not 1 <= len(catalog) <= MAX_CATALOG_ENTRIES:
            raise ArchiveDataError("invalid-catalog")
        valid_catalog = [entry for entry in catalog if _catalog_entry_valid(entry)]
        if len(valid_catalog) != len(catalog):
            degraded = "catalog-entries-rejected"
        indexes = helper._select_indexes(valid_catalog)
        if not indexes:
            raise ArchiveDataError("no-usable-indexes")
        for index in indexes:
            endpoint = index["cdx-api"]
            base = {"url": domain, "matchType": "domain", "output": "json", "pageSize": 1}
            try:
                response = client.get(endpoint + "?" + urlencode({**base, "showNumPages": "true"}))
                if _cc_no_captures(response, domain):
                    progress = True
                    continue
                metadata = _json(_http_success(response))
                if not isinstance(metadata, dict):
                    raise ArchiveDataError("invalid-page-count")
                pages = metadata.get("pages")
                if (type(pages) is not int or not 0 <= pages <= MAX_PAGE_COUNT
                        or ("pageSize" in metadata and (
                            type(metadata["pageSize"]) is not int or metadata["pageSize"] != 1))):
                    raise ArchiveDataError("invalid-page-count")
                if pages == 0:
                    progress = True
                for page in range(pages):
                    # No per-page `limit`: skipping the rest of a CDX page would
                    # silently omit evidence before advancing to the next page.
                    body = _http_success(client.get(endpoint + "?" + urlencode({**base, "page": page})))
                    text = _text(body)
                    if not text.strip():
                        raise ArchiveDataError("empty-index-page")
                    page_hosts: set[str] = set()
                    for line in text.splitlines():
                        if not line.strip():
                            continue
                        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                            raise ArchiveDataError("record-too-large")
                        record = _json(line.encode("utf-8"))
                        if not isinstance(record, dict) or "url" not in record:
                            raise ArchiveDataError("invalid-index-record")
                        host = _scoped_host(record["url"], domain=domain,
                                            extractor=helper._extract_domain_from_url)
                        if host:
                            page_hosts.add(host)
                    progress = True
                    if _add_bounded(hosts, page_hosts, limit):
                        return _outcome("commoncrawl", hosts, reason="result-limit", progress=True)
            except (ArchiveHTTPError, ArchiveDataError) as error:
                reason = _reason(error)
                # Retrying another index on a quota, exhausted budget or a
                # transport outage would spend requests without useful work.
                if isinstance(error, ArchiveHTTPError):
                    return _outcome("commoncrawl", hosts, reason=reason, progress=progress,
                                    rate_limited=_is_rate_limited(error))
                degraded = degraded or reason
        return _outcome("commoncrawl", hosts, reason=degraded, progress=progress)
    except (ArchiveHTTPError, ArchiveDataError) as error:
        return _outcome("commoncrawl", hosts, reason=_reason(error), progress=progress,
                        rate_limited=_is_rate_limited(error))


def _wayback_page(body: bytes, helper: Any) -> tuple[list[str], str | None]:
    text = _text(body)
    if not text.strip():
        return [], None
    parsed = helper._parse_page(text)
    if parsed is None:
        raise ArchiveDataError("invalid-page")
    lines, cursor = parsed
    # The upstream parser ignores malformed continuation blocks.  Reject them
    # instead of incorrectly declaring an incomplete traversal complete.
    _body, separator, continuation = text.replace("\r\n", "\n").rpartition("\n\n")
    if separator:
        cursor_lines = [line.strip() for line in continuation.splitlines() if line.strip()]
        if cursor_lines and (len(cursor_lines) != 1 or cursor is None):
            raise ArchiveDataError("invalid-cursor")
    if cursor is not None and (
        not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048
        or not cursor.isascii() or not cursor.isprintable()
    ):
        raise ArchiveDataError("invalid-cursor")
    return lines, cursor


def collect_wayback(domain: str, limit: int, client: Any, helper: Any) -> ArchiveOutcome:
    """Use one domain match and a small cursor-driven sequence of CDX pages."""
    hosts: set[str] = set()
    progress = False
    cursor: str | None = None
    cursors: set[str] = set()
    try:
        while True:
            query: dict[str, object] = {
                "url": domain, "matchType": "domain", "fl": "original",
                "collapse": "urlkey", "limit": WAYBACK_PAGE_SIZE, "showResumeKey": "true",
            }
            if cursor is not None:
                query["resumeKey"] = unquote_plus(cursor)
            response = client.get(WAYBACK_CDX + "?" + urlencode(query))
            lines, next_cursor = _wayback_page(_http_success(response), helper)
            page_hosts: set[str] = set()
            for line in lines:
                if not line.strip():
                    continue
                if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                    raise ArchiveDataError("record-too-large")
                host = _scoped_host(line.strip(), domain=domain,
                                    extractor=helper._extract_domain_from_url)
                if host:
                    page_hosts.add(host)
            progress = True
            if _add_bounded(hosts, page_hosts, limit):
                return _outcome("waybackarchive", hosts, reason="result-limit", progress=True)
            if next_cursor is None:
                return _outcome("waybackarchive", hosts)
            if next_cursor in cursors:
                raise ArchiveDataError("repeated-cursor")
            cursors.add(next_cursor)
            cursor = next_cursor
    except (ArchiveHTTPError, ArchiveDataError) as error:
        return _outcome("waybackarchive", hosts, reason=_reason(error), progress=progress,
                        rate_limited=_is_rate_limited(error))


def _timestamp(now: Callable[[], datetime]) -> str:
    value = now()
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("worker clock must be timezone aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def run_archive_sources(
    domain: str, limit: int, *, commoncrawl_helpers: Any, wayback_helpers: Any,
    client_factory: Callable[..., Any] = ArchiveHTTPClient,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    monotonic: Callable[[], float] = time.monotonic,
) -> list[dict[str, Any]]:
    domain = normalize_domain(domain)
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("archive result limit must be between 1 and 500")
    started_at = _timestamp(now)
    executions: list[dict[str, Any]] = []
    provenance: dict[str, list[str]] = {}
    for name, collector, helper_class in (
        ("commoncrawl", collect_commoncrawl, commoncrawl_helpers),
        ("waybackarchive", collect_wayback, wayback_helpers),
    ):
        started = monotonic()
        try:
            client = client_factory(
                name, domain, budget_seconds=SOURCE_BUDGET_SECONDS[name],
                request_timeout=30, max_requests=30,
            )
            helper = helper_class(domain, limit=limit)
            outcome = collector(domain, limit, client, helper)
        except Exception:
            # A broken optional dependency must not fabricate success or prevent
            # the independent second source from producing its own evidence.
            outcome = ArchiveOutcome(name, "failed", (), "unexpected-worker-error")
        duration_ms = max(0.0, (monotonic() - started) * 1000)
        executions.append({
            "source": name, "status": outcome.status, "duration_ms": duration_ms,
            "result_count": len(outcome.hosts), "error_type": None,
            "stop_reason": outcome.stop_reason,
        })
        for hostname in outcome.hosts:
            provenance.setdefault(hostname, []).append(name)
    statuses = [execution["status"] for execution in executions]
    evidence_status = (
        "failed" if all(status in {"failed", "rate-limited", "skipped"} for status in statuses)
        else "complete" if all(status == "completed" for status in statuses)
        else "partial"
    )
    count = len(provenance)
    summary = {
        "type": "summary", "run_id": str(uuid4()), "target": domain,
        "started_at": started_at, "completed_at": _timestamp(now),
        "action_executions": [], "artifacts": [], "source_executions": executions,
        "evidence_status": evidence_status, "counts": {"hostname": count} if count else {},
        "result_count": count,
    }
    return [summary, *[
        {"type": "hostname", "value": host, "sources": sorted(sources)}
        for host, sources in sorted(provenance.items())
    ]]


def write_report(path: Path, records: list[dict[str, Any]]) -> None:
    payload = b"".join(
        json.dumps(record, ensure_ascii=True, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
        for record in records
    )
    if len(payload) > MAX_REPORT_BYTES:
        raise ValueError("archive report exceeds size limit")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="XTI bounded passive archive worker")
    parser.add_argument("--domain", required=True)
    parser.add_argument("--limit", required=True, type=int)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        domain = normalize_domain(args.domain)
        if not 1 <= args.limit <= 500:
            raise ValueError("invalid result limit")
        # These imports belong solely to the optional tool environment.
        from theHarvester.discovery.commoncrawl import SearchCommoncrawl
        from theHarvester.discovery.waybackarchive import SearchWaybackarchive
        records = run_archive_sources(
            domain, args.limit, commoncrawl_helpers=SearchCommoncrawl,
            wayback_helpers=SearchWaybackarchive,
        )
        write_report(args.report, records)
    except (ImportError, OSError, ValidationError, ValueError):
        print("theHarvester arşiv çalıştırıcısı başlatılamadı veya rapor yazılamadı.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

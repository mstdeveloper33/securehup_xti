"""Bounded, read-only searches of public historical urlscan records.

This adapter never submits a URL, opens a result link, or visits a discovered
website. A historic scan is evidence of past observation, not present risk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
from http.client import HTTPException
import json
import re
import socket
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from xti import __version__
from xti.adapters.source_cooldown import SourceCooldownGate
from xti.adapters.unicode_security import canonicalize_observed_domain
from xti.domain.assets import ValidationError
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.ports.discovery import SourceError
from xti.ports.operations import CooldownRepository


BASE_URL = "https://urlscan.io/"
SEARCH_URL = BASE_URL + "api/v1/search/"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RESULTS = 100
REQUEST_TIMEOUT = 20
MAX_ATTEMPTS = 2
REQUEST_INTERVAL = 2.0
MAX_INLINE_WAIT = 5.0
_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{2,61}[a-z0-9]\*", re.ASCII)
_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", re.ASCII)
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})"
)


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON number")


def _scan_id(value) -> str:
    if not isinstance(value, str) or _UUID.fullmatch(value) is None:
        raise SourceError("urlscan geçerli bir tarama kimliği göndermedi.")
    parsed = UUID(value)
    if not parsed.int:
        raise SourceError("urlscan boş bir tarama kimliği gönderdi.")
    # UUIDv7 is already used by the service; do not restrict to UUIDv4.
    return str(parsed)


def _timestamp(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        raise SourceError("urlscan geçerli ve saat dilimli bir tarama zamanı göndermedi.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError) as exc:
        raise SourceError("urlscan geçersiz bir tarama zamanı gönderdi.") from exc


def parse_response(content: bytes) -> SourceBatch:
    """Turn public archive results into stable, separately attributable observations."""
    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceError("urlscan yanıtı 2 MiB sınırını aştı; arama tamamlanamadı.")
    try:
        payload = json.loads(content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise SourceError("urlscan geçerli JSON göndermedi; arama tamamlanamadı.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise SourceError("urlscan beklenen arama sonuç listesini göndermedi.")
    rows = payload["results"]
    if len(rows) > MAX_RESULTS:
        raise SourceError("urlscan yanıtı 100 sonuç sınırını aştı; arama tamamlanamadı.")
    total = payload.get("total")
    if total is not None and (type(total) is not int or total < len(rows)):
        raise SourceError("urlscan geçersiz toplam sonuç sayısı gönderdi.")
    has_more = payload.get("has_more", False)
    if type(has_more) is not bool:
        raise SourceError("urlscan geçersiz ek sonuç bilgisi gönderdi.")
    date_limit = payload.get("search_date_limit_days")
    if date_limit is not None and (type(date_limit) is not int or date_limit < 0):
        raise SourceError("urlscan geçersiz geçmiş arama sınırı gönderdi.")
    warnings = []
    coverage_notes = []
    if has_more or (total is not None and total > len(rows)) or (total is None and len(rows) == MAX_RESULTS):
        warnings.append(f"urlscan aramasında ek sonuçlar olabilir; bu yanıttaki {len(rows)} kayıt alındı.")
    if date_limit is not None and date_limit > 0:
        coverage_notes.append(f"urlscan bu aramanın geçmişini son {date_limit} günle sınırlandırıyor.")
    if total is None:
        coverage_notes.append("urlscan toplam sonuç sayısını bildirmedi.")

    documents: dict[str, ImportDocument] = {}
    scan_ids: set[str] = set()
    skipped_names = 0
    missing_time = False
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError("urlscan sonuç listesinde geçersiz kayıt gönderdi.")
        task = row.get("task")
        page = row.get("page")
        if task is None:
            task = {}
        if page is None:
            page = {}
        if not isinstance(task, dict) or not isinstance(page, dict):
            raise SourceError("urlscan tarama kaydının alanları beklenen biçimde değil.")
        identities = [value for value in (row.get("_id"), task.get("uuid")) if value is not None]
        if not identities:
            raise SourceError("urlscan kaydında tarama kimliği eksik.")
        ids = {_scan_id(value) for value in identities}
        if len(ids) != 1:
            raise SourceError("urlscan aynı kayıtta çelişen tarama kimlikleri gönderdi.")
        scan_id = ids.pop()
        scan_ids.add(scan_id)
        observed_at = _timestamp(task.get("time"))
        missing_time = missing_time or observed_at is None
        raw_names: set[str] = set()
        for raw_domain in (page.get("domain"), task.get("domain")):
            if not isinstance(raw_domain, str) or not 1 <= len(raw_domain) <= 1024:
                skipped_names += 1
                continue
            if raw_domain in raw_names:
                continue
            raw_names.add(raw_domain)
            try:
                domain = canonicalize_observed_domain(raw_domain)
            except ValidationError:
                skipped_names += 1
                continue
            canonical = json.dumps(
                {"provider": "urlscan.io", "scan_id": scan_id, "raw_domain": raw_domain,
                 "observed_at": observed_at},
                sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            ).encode("utf-8")
            digest = hashlib.sha256(canonical).hexdigest()
            documents[digest] = ImportDocument(
                source_name=f"{BASE_URL}result/{scan_id}/", sha256=digest,
                records=(DomainInput(domain, raw_domain, 1, observed_at),),
            )
    if missing_time:
        coverage_notes.append("Bazı urlscan kayıtlarında kaynak zamanı belirtilmemiş; tarih atanmadı.")
    return SourceBatch(
        documents=tuple(documents[key] for key in sorted(documents)),
        skipped_names=skipped_names, record_count=len(scan_ids),
        warnings=tuple(warnings), coverage_notes=tuple(coverage_notes),
    )


def _seconds(value, *, http_date: bool = False, now: datetime | None = None) -> float | None:
    if not isinstance(value, str):
        return None
    if value.isascii() and value.isdigit():
        return max(0.0, float(value) if len(value) <= 20 else float("inf"))
    if not http_date:
        return None
    try:
        moment = parsedate_to_datetime(value)
        if moment.tzinfo is None:
            return None
        return max(0.0, (moment - (now or datetime.now(timezone.utc))).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def _provider_delay(headers, *, now: datetime | None = None) -> float | None:
    """Respect both retry requests and the service's documented quota headers."""
    if headers is None:
        return None
    delays = []
    retry = headers.get("Retry-After")
    if retry is not None:
        parsed = _seconds(retry, http_date=True, now=now)
        delays.append(60.0 if parsed is None else parsed)
    remaining = headers.get("X-Rate-Limit-Remaining")
    if isinstance(remaining, str) and remaining.isascii() and re.fullmatch(r"-?\d{1,20}", remaining):
        exhausted = int(remaining) <= 0
    else:
        exhausted = False
    if exhausted:
        delay = _seconds(headers.get("X-Rate-Limit-Reset-After"))
        if delay is None:
            try:
                moment = datetime.fromisoformat(headers.get("X-Rate-Limit-Reset", "").replace("Z", "+00:00"))
                if moment.tzinfo is None:
                    raise ValueError
                delay = max(0.0, (moment - (now or datetime.now(timezone.utc))).total_seconds())
            except (ValueError, TypeError, AttributeError, OverflowError):
                delay = 60.0
        delays.append(delay)
    return max(delays) if delays else None


class UrlscanSource:
    def __init__(self, *, opener: Callable | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 cooldowns: CooldownRepository | None = None,
                 wall_clock: Callable[[], datetime] | None = None) -> None:
        self._open = opener or build_opener(_NoRedirects()).open
        self._sleep = sleep
        self._clock = clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._gate = SourceCooldownGate(
            "urlscan", cooldowns, clock=clock, wall_clock=self._wall_clock, sleep=sleep,
        ) if cooldowns is not None else None
        self._last_attempt: float | None = None
        self._cooldown_until = 0.0

    def search_url(self, pattern: str) -> str:
        if not isinstance(pattern, str) or _PATTERN.fullmatch(pattern) is None:
            raise ValidationError("urlscan araması 4–63 karakterlik ad ve sonda '*' içermeli.")
        escaped = pattern[:-1].replace("-", "\\-") + "*"
        query = f"(page.domain:{escaped} OR task.domain:{escaped})"
        return SEARCH_URL + "?" + urlencode({"q": query, "size": MAX_RESULTS})

    def _wait(self, seconds: float) -> None:
        self._sleep(seconds)
        if seconds >= REQUEST_INTERVAL:
            self._last_attempt = None
        self._cooldown_until = 0.0

    def _can_retry(self, attempt: int, delay: float = 0.0) -> bool:
        required = max(REQUEST_INTERVAL, delay, self._cooldown_until - self._clock())
        if attempt + 1 == MAX_ATTEMPTS or required > MAX_INLINE_WAIT:
            return False
        self._wait(required)
        return True

    def _pace(self) -> None:
        if self._last_attempt is not None:
            delay = REQUEST_INTERVAL - (self._clock() - self._last_attempt)
            if delay > 0:
                self._sleep(delay)
        self._last_attempt = self._clock()

    def _record_cooldown(self, delay: float | None, reason: str = "provider_wait") -> None:
        if delay is not None:
            self._cooldown_until = max(self._cooldown_until, self._clock() + delay)
            if self._gate is not None:
                self._gate.record(delay, reason)

    def search(self, pattern: str) -> SourceBatch:
        url = self.search_url(pattern)
        cooldown = self._cooldown_until - self._clock()
        if cooldown > MAX_INLINE_WAIT:
            raise SourceError("urlscan bekleme süresi devam ediyor; yeni istek gönderilmedi. Daha sonra yeniden dene.")
        if cooldown > 0:
            self._wait(cooldown)
        request = Request(url, headers={
            "User-Agent": f"XTI/{__version__} (personal public archive search)",
            "Accept": "application/json", "Accept-Encoding": "identity",
        })
        for attempt in range(MAX_ATTEMPTS):
            try:
                if self._gate is not None:
                    self._gate.before_request(REQUEST_INTERVAL)
                else:
                    self._pace()
                with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                    status = response.getcode()
                    if status != 200:
                        raise HTTPError(url, status, "Unexpected HTTP status", response.headers, None)
                    self._record_cooldown(_provider_delay(response.headers, now=self._wall_clock()))
                    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                        raise SourceError("urlscan desteklenmeyen sıkıştırılmış bir yanıt gönderdi.")
                    raw_length = response.headers.get("Content-Length")
                    length = None
                    if raw_length is not None:
                        try:
                            length = int(raw_length)
                        except (TypeError, ValueError) as exc:
                            raise SourceError("urlscan geçersiz yanıt uzunluğu bildirdi.") from exc
                        if length < 0 or length > MAX_RESPONSE_BYTES:
                            raise SourceError("urlscan yanıtı 2 MiB sınırını aşıyor; arama tamamlanamadı.")
                    body = bytearray()
                    started = self._clock()
                    read = getattr(response, "read1", response.read)
                    while True:
                        if self._clock() - started > REQUEST_TIMEOUT:
                            raise TimeoutError("Response deadline exceeded")
                        chunk = read(min(65536, MAX_RESPONSE_BYTES + 1 - len(body)))
                        if not chunk:
                            break
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise SourceError("urlscan yanıtı 2 MiB sınırını aştı; arama tamamlanamadı.")
                    if length is not None and len(body) != length:
                        raise SourceError("urlscan yanıtı eksik geldi; sonuçlar kabul edilmedi.")
                return parse_response(bytes(body))
            except HTTPError as exc:
                status = exc.code
                requested = _provider_delay(exc.headers, now=self._wall_clock())
                retryable = status == 429 or 500 <= status <= 599
                exc.close()
                if self._gate is not None and status == 429 and requested is None:
                    requested = 60.0
                self._record_cooldown(requested)
                if retryable:
                    if self._can_retry(attempt, requested or 0.0):
                        continue
                    self._record_cooldown(requested if requested is not None else (60.0 if status == 429 else None))
                if status == 429:
                    message = "urlscan istek sınırına ulaşıldı; daha sonra yeniden dene."
                elif 300 <= status <= 399:
                    message = "urlscan beklenmeyen yönlendirme gönderdi; arama durduruldu."
                elif status in {401, 403}:
                    message = f"urlscan erişimi HTTP {status} ile reddetti; arama tamamlanamadı."
                else:
                    message = f"urlscan hizmeti HTTP {status} hatası verdi; arama tamamlanamadı."
                raise SourceError(message) from exc
            except (TimeoutError, socket.timeout) as exc:
                if self._can_retry(attempt):
                    continue
                raise SourceError("urlscan zamanında yanıt vermedi; daha sonra yeniden dene.") from exc
            except URLError as exc:
                if isinstance(exc.reason, (TimeoutError, socket.timeout)) and self._can_retry(attempt):
                    continue
                raise SourceError("urlscan bağlantısı kurulamadı; arama tamamlanamadı.") from exc
            except (OSError, HTTPException) as exc:
                raise SourceError("urlscan bağlantısı kesildi; arama tamamlanamadı.") from exc
        raise SourceError("urlscan araması tamamlanamadı.")

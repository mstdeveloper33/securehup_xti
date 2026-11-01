"""Bounded, read-only Certificate Transparency searches against crt.sh.

The service returns certificate identities, not proof that a site exists or is
malicious. HTTP errors and invalid responses must never become empty successes.
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

from xti import __version__
from xti.adapters.source_cooldown import SourceCooldownGate
from xti.adapters.unicode_security import canonicalize_observed_domain
from xti.domain.assets import ValidationError
from xti.domain.discovery import SourceBatch
from xti.domain.findings import DomainInput, ImportDocument
from xti.ports.discovery import SourceError
from xti.ports.operations import CooldownRepository


BASE_URL = "https://crt.sh/"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ROWS = 5_000
MAX_NAMES_PER_ROW = 1_000
MAX_NAMES = 50_000
MAX_DOCUMENTS = 10_000
REQUEST_TIMEOUT = 20
MAX_ATTEMPTS = 2
_PATTERN = re.compile(r"[A-Za-z0-9.%\-]{1,255}", re.ASCII)
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?"
)


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _timestamp(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        raise SourceError("crt.sh geçersiz bir sertifika kayıt zamanı gönderdi.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # crt.sh's timezone-less CT entry_timestamp values are UTC, not local time.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError) as exc:
        raise SourceError("crt.sh geçersiz bir sertifika kayıt zamanı gönderdi.") from exc


def parse_response(content: bytes) -> SourceBatch:
    """Validate the entire response before exposing any importable documents.

    One document represents one certificate identity. Query order, duplicate rows,
    and different SAN subsets therefore do not change an observation's identity.
    """
    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceError("crt.sh yanıtı 8 MiB sınırını aştı; sonuçlar eksik kabul edilmedi.")
    try:
        rows = json.loads(content.decode("utf-8"), object_pairs_hook=_object,
                          parse_constant=_constant)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise SourceError("crt.sh geçerli JSON göndermedi; arama tamamlanamadı.") from exc
    if not isinstance(rows, list):
        raise SourceError("crt.sh beklenen sertifika listesini göndermedi.")
    if len(rows) > MAX_ROWS:
        raise SourceError("crt.sh yanıtı 5000 kayıt sınırını aştı; aramayı daraltmak gerekiyor.")

    documents: dict[str, ImportDocument] = {}
    certificates: set[int] = set()
    skipped_names = 0
    total_names = 0
    result_count = 0
    for row in rows:
        if not isinstance(row, dict):
            raise SourceError("crt.sh sertifika listesinde geçersiz bir kayıt gönderdi.")
        certificate_id = row.get("id")
        names_value = row.get("name_value")
        if (type(certificate_id) is not int or not 0 < certificate_id < 2**63
                or not isinstance(names_value, str)):
            raise SourceError("crt.sh kaydında geçerli kimlik veya alan adı listesi eksik.")
        observed_at = _timestamp(row.get("entry_timestamp"))
        if "result_count" in row:
            count = row["result_count"]
            if type(count) is not int or count < 0:
                raise SourceError("crt.sh geçersiz sonuç sayısı gönderdi.")
            result_count += count
        certificates.add(certificate_id)
        names = names_value.split("\n")
        total_names += len(names)
        if len(names) > MAX_NAMES_PER_ROW or total_names > MAX_NAMES:
            raise SourceError("crt.sh yanıtındaki alan adı sayısı güvenli işlem sınırını aştı.")
        for raw_name in names:
            raw_name = raw_name.removesuffix("\r")
            if (len(raw_name) > 1024
                    or any(ord(char) < 32 or ord(char) == 127 for char in raw_name)):
                skipped_names += 1
                continue
            candidate = raw_name.strip()
            if candidate.startswith("*."):
                candidate = candidate[2:]
            try:
                domain = canonicalize_observed_domain(candidate)
            except ValidationError:
                skipped_names += 1
                continue
            canonical = json.dumps(
                {"provider": "crt.sh", "certificate_id": certificate_id,
                 "raw_name": raw_name, "entry_timestamp": observed_at},
                sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            ).encode("utf-8")
            digest = hashlib.sha256(canonical).hexdigest()
            documents[digest] = ImportDocument(
                source_name=f"{BASE_URL}?id={certificate_id}",
                sha256=digest,
                records=(DomainInput(domain, raw_name, 1, observed_at),),
            )
            if len(documents) > MAX_DOCUMENTS:
                raise SourceError("crt.sh yanıtı 10000 gözlem sınırını aştı; aramayı daraltmak gerekiyor.")
    return SourceBatch(
        documents=tuple(documents[key] for key in sorted(documents)),
        skipped_names=skipped_names,
        record_count=len(certificates),
        warnings=(
            ("crt.sh kaynak sınırına ulaşmış olabilir; arama sonuçları eksik olabilir.",)
            if result_count >= 10_000 else ()
        ),
    )


def _retry_after_seconds(headers, *, now: datetime | None = None) -> float | None:
    """Parse a provider delay without shortening its requested cooldown."""
    raw = headers.get("Retry-After") if headers is not None else None
    if raw is None:
        return 1.0
    if not isinstance(raw, str):
        return None
    if raw.isascii() and raw.isdigit():
        # An implausibly large value still means "do not retry this session".
        seconds = float(raw) if len(raw) <= 20 else float("inf")
    else:
        try:
            retry_at = parsedate_to_datetime(raw)
            if retry_at.tzinfo is None:
                return None
            seconds = (retry_at - (now or datetime.now(timezone.utc))).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(1.0, seconds)


class CrtShSource:
    provider = "crt.sh"

    def __init__(self, *, opener: Callable | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 cooldowns: CooldownRepository | None = None,
                 wall_clock: Callable[[], datetime] | None = None) -> None:
        # urllib's default HTTPS handler verifies both trust chain and hostname.
        self._open = opener or build_opener(_NoRedirects()).open
        self._sleep = sleep
        self._clock = clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._gate = SourceCooldownGate(
            "crt.sh", cooldowns, clock=clock, wall_clock=self._wall_clock, sleep=sleep,
        ) if cooldowns is not None else None
        self._last_attempt: float | None = None
        self._cooldown_until = 0.0

    def _wait_for_slot(self) -> None:
        if self._last_attempt is not None:
            delay = 1.0 - (self._clock() - self._last_attempt)
            if delay > 0:
                self._sleep(delay)
        self._last_attempt = self._clock()

    def _retry_after(self, seconds: float) -> None:
        self._sleep(seconds)
        # Every retry delay is at least one second, so pacing is satisfied.
        self._last_attempt = None

    def search_url(self, pattern: str) -> str:
        if (not isinstance(pattern, str) or _PATTERN.fullmatch(pattern) is None
                or len(pattern.replace("%", "").replace(".", "")) < 3):
            raise ValidationError("Sertifika araması için geçerli ve yeterince belirgin bir ad gerekli.")
        return BASE_URL + "?" + urlencode({
            "dNSName": pattern, "match": "ILIKE", "output": "json",
        })

    def search(self, pattern: str) -> SourceBatch:
        url = self.search_url(pattern)
        if self._clock() < self._cooldown_until:
            raise SourceError(
                "crt.sh bekleme süresi devam ediyor; yeni istek gönderilmedi. Daha sonra yeniden dene."
            )
        request = Request(url, headers={
            "User-Agent": f"XTI/{__version__} (personal certificate transparency monitor)",
            "Accept": "application/json", "Accept-Encoding": "identity",
        })
        for attempt in range(MAX_ATTEMPTS):
            try:
                if self._gate is not None:
                    self._gate.before_request(1.0)
                else:
                    self._wait_for_slot()
                with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                    status = response.getcode()
                    if status != 200:
                        raise HTTPError(url, status, "Unexpected HTTP status", response.headers, None)
                    if self._gate is not None and response.headers.get("Retry-After") is not None:
                        requested = _retry_after_seconds(response.headers, now=self._wall_clock())
                        self._gate.record(requested if requested is not None else 60.0, "retry_after")
                    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                        raise SourceError("crt.sh desteklenmeyen sıkıştırılmış bir yanıt gönderdi.")
                    raw_length = response.headers.get("Content-Length")
                    if raw_length is not None:
                        try:
                            length = int(raw_length)
                        except (TypeError, ValueError) as exc:
                            raise SourceError("crt.sh geçersiz yanıt uzunluğu bildirdi.") from exc
                        if length < 0 or length > MAX_RESPONSE_BYTES:
                            raise SourceError("crt.sh yanıtı 8 MiB sınırını aşıyor; arama tamamlanamadı.")
                    else:
                        length = None
                    body = bytearray()
                    started = self._clock()
                    # read1 issues one underlying read, allowing a wall-clock check
                    # even if a peer continually dribbles small amounts of data.
                    read = getattr(response, "read1", response.read)
                    while True:
                        if self._clock() - started > REQUEST_TIMEOUT:
                            raise TimeoutError("Response deadline exceeded")
                        chunk = read(min(65_536, MAX_RESPONSE_BYTES + 1 - len(body)))
                        if not chunk:
                            break
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise SourceError("crt.sh yanıtı 8 MiB sınırını aştı; arama tamamlanamadı.")
                    if length is not None and len(body) != length:
                        raise SourceError("crt.sh yanıtı eksik geldi; sonuçlar kaydedilmedi.")
                return parse_response(bytes(body))
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                requested_delay = _retry_after_seconds(exc.headers, now=self._wall_clock())
                has_retry_after = exc.headers is not None and exc.headers.get("Retry-After") is not None
                exc.close()
                if self._gate is not None and (has_retry_after or exc.code == 429):
                    # Save the provider hold before any retry sleep or response
                    # parsing; interruption must not erase a rate-limit request.
                    requested_delay = requested_delay if has_retry_after and requested_delay is not None else 60.0
                    self._gate.record(requested_delay, "retry_after" if has_retry_after else "rate_limit")
                delay = requested_delay if requested_delay is not None and requested_delay <= 5 else None
                if retryable and delay is not None and attempt + 1 < MAX_ATTEMPTS:
                    self._retry_after(delay)
                    continue
                if retryable and (has_retry_after or exc.code == 429):
                    cooldown = requested_delay if has_retry_after and requested_delay is not None else 60.0
                    self._cooldown_until = max(self._cooldown_until, self._clock() + cooldown)
                if exc.code == 429:
                    message = "crt.sh istek sınırına ulaşıldı; daha sonra yeniden dene."
                elif 300 <= exc.code <= 399:
                    message = "crt.sh beklenmeyen bir yönlendirme gönderdi; arama durduruldu."
                else:
                    message = f"crt.sh hizmeti HTTP {exc.code} hatası verdi; arama tamamlanamadı."
                if retryable and delay is None:
                    message += " Kaynağın bekleme isteği nedeniyle daha sonra yeniden dene."
                raise SourceError(message) from exc
            except (TimeoutError, socket.timeout) as exc:
                if attempt + 1 < MAX_ATTEMPTS:
                    self._retry_after(1.0)
                    continue
                raise SourceError("crt.sh zamanında yanıt vermedi; daha sonra yeniden dene.") from exc
            except URLError as exc:
                if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                    if attempt + 1 < MAX_ATTEMPTS:
                        self._retry_after(1.0)
                        continue
                    raise SourceError("crt.sh zamanında yanıt vermedi; daha sonra yeniden dene.") from exc
                raise SourceError("crt.sh bağlantısı kurulamadı; internet bağlantısını kontrol et.") from exc
            except (OSError, HTTPException) as exc:
                raise SourceError("crt.sh bağlantısı kesildi; arama tamamlanamadı.") from exc
        raise SourceError("crt.sh araması tamamlanamadı.")

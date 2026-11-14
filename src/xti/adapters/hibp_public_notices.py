"""Read only the documented, unauthenticated HIBP public breach catalog."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
from http.client import HTTPException
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.public_notices import (
    HIBP_SOURCE_URL, MAX_NOTICES, PublicNotice, PublicNoticeFeed, validate_notice,
)
from xti.ports.discovery import SourceError


MAX_RESPONSE_BYTES = 16 * 1024 * 1024
REQUEST_TIMEOUT = 20
READ_DEADLINE_SECONDS = 45
_FLAGS = {
    "IsVerified": "is_verified", "IsFabricated": "is_fabricated",
    "IsSensitive": "is_sensitive", "IsRetired": "is_retired",
    "IsSpamList": "is_spam_list", "IsMalware": "is_malware",
    "IsStealerLog": "is_stealer_log",
}


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
    raise ValueError("Nonfinite JSON constant")


def _time(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64 or value != value.strip():
        raise ValueError("Invalid date")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Naive date")
    return parsed.astimezone(timezone.utc).isoformat()


def parse_hibp_public_notices_response(content: bytes, *, fetched_at: datetime) -> PublicNoticeFeed:
    try:
        if not isinstance(fetched_at, datetime) or fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
            raise ValueError("Invalid fetch time")
        fetched_at = fetched_at.astimezone(timezone.utc)
        if not isinstance(content, bytes) or not 1 <= len(content) <= MAX_RESPONSE_BYTES:
            raise ValueError("Response size")
        raw = json.loads(content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
        # An unexpectedly empty global catalog is treated as a failed fetch, never mass removal.
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_NOTICES:
            raise ValueError("Invalid catalog")
        notices = []
        identities = set()
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("Invalid record")
            if not isinstance(item["Domain"], str):
                raise ValueError("Invalid domain")
            if not isinstance(item["DataClasses"], list):
                raise ValueError("Invalid categories")
            # HIBP documents that new fields can appear without a version bump. Only
            # this explicit safe allowlist crosses the source boundary; HTML, logos,
            # disclosure links and any future raw-data fields are discarded.
            record = PublicNotice(
                id=item["Name"], title=item["Title"],
                domain=normalize_domain(item["Domain"]) if item["Domain"] else None,
                breach_date=item["BreachDate"], added_at=_time(item["AddedDate"]),
                modified_at=_time(item["ModifiedDate"]), pwn_count=item["PwnCount"],
                data_classes=tuple(item["DataClasses"]),
                **{name: item[key] for key, name in _FLAGS.items()},
                source_attribution=item.get("Attribution"),
                source_url=f"https://haveibeenpwned.com/api/v3/breach/{item['Name']}",
            )
            validate_notice(record)
            if record.id in identities:
                raise ValueError("Duplicate stable identity")
            identities.add(record.id)
            if datetime.fromisoformat(record.modified_at) > fetched_at + timedelta(minutes=15):
                raise ValueError("Future record")
            notices.append(record)
        return PublicNoticeFeed(
            fetched_at=fetched_at.isoformat(), content_sha256=hashlib.sha256(content).hexdigest(),
            notices=tuple(sorted(notices, key=lambda record: record.id)),
        )
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, RecursionError, OverflowError) as error:
        raise SourceError("HIBP kamu olay kataloğu eksik, geçersiz veya güvenli sınırları aşıyor; önceki kayıtlar korunur.") from error


class HibpPublicNoticeSource:
    def __init__(self, *, opener: Callable | None = None,
                 clock: Callable[[], datetime] | None = None,
                 monotonic: Callable[[], float] | None = None) -> None:
        self._open = opener or build_opener(_NoRedirects()).open
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic or time.monotonic

    def fetch(self) -> PublicNoticeFeed:
        request = Request(HIBP_SOURCE_URL, headers={
            "User-Agent": f"XTI/{__version__} (personal defensive OSINT; public breach metadata)",
            "Accept": "application/json", "Accept-Encoding": "identity",
        })
        deadline = self._monotonic() + READ_DEADLINE_SECONDS
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200 or response.geturl() != HIBP_SOURCE_URL:
                    raise SourceError("HIBP kamu kataloğu beklenen HTTPS yanıtını vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("HIBP kamu kataloğu desteklenmeyen sıkıştırma kullandı.")
                if response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                    raise SourceError("HIBP kamu kataloğu JSON içerik türü göndermedi.")
                declared = response.headers.get("Content-Length")
                if declared is not None:
                    try:
                        length = int(declared)
                    except (TypeError, ValueError) as error:
                        raise SourceError("HIBP kamu kataloğu yanıt uzunluğu geçersiz.") from error
                    if not 1 <= length <= MAX_RESPONSE_BYTES:
                        raise SourceError("HIBP kamu kataloğu 16 MiB yanıt sınırını aşıyor veya boş.")
                chunks, received = [], 0
                while True:
                    if self._monotonic() > deadline:
                        raise SourceError("HIBP kamu kataloğu okuma süresi doldu.")
                    chunk = response.read(min(65536, MAX_RESPONSE_BYTES + 1 - received))
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > MAX_RESPONSE_BYTES:
                        raise SourceError("HIBP kamu kataloğu 16 MiB yanıt sınırını aştı.")
                    chunks.append(chunk)
                if declared is not None and received != length:
                    raise SourceError("HIBP kamu kataloğu yanıtı eksik alındı.")
                return parse_hibp_public_notices_response(b"".join(chunks), fetched_at=self._clock())
        except SourceError:
            raise
        except HTTPError as error:
            if error.code == 429:
                raise SourceError("HIBP kamu kataloğu istek sınırına ulaştı (HTTP 429); daha sonra yeniden deneyin.") from error
            raise SourceError(f"HIBP kamu kataloğu HTTP {error.code} verdi; önceki kayıtlar korunur.") from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError("HIBP kamu kataloğuna bağlantı tamamlanamadı; önceki kayıtlar korunur.") from error

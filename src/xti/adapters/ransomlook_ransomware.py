"""Bounded adapter for RansomLook's public recent ransomware posts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
from http.client import HTTPException
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.domain.ransomlook_ransomware import (
    RANSOMLOOK_SOURCE_LICENSE,
    RANSOMLOOK_SOURCE_NAME,
    RANSOMLOOK_SOURCE_URL,
    RansomLookClaim,
    RansomLookClaimFeed,
)
from xti.ports.discovery import SourceError


SOURCE_NAME = RANSOMLOOK_SOURCE_NAME
SOURCE_URL = RANSOMLOOK_SOURCE_URL
SOURCE_LICENSE = RANSOMLOOK_SOURCE_LICENSE
WINDOW_DAYS = 7
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 10_000
REQUEST_TIMEOUT = 30
_TOP_FIELDS = {"posts"}
_POST_FIELDS = {"group_name", "post_title", "discovered"}


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


def _text(value: object, field: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum + 100:
        raise SourceError(f"RansomLook kaydında geçersiz {field} alanı var.")
    if not all(character.isprintable() for character in value):
        raise SourceError(f"RansomLook kaydında geçersiz {field} alanı var.")
    normalized = " ".join(value.strip().split())
    if not normalized or len(normalized) > maximum:
        raise SourceError(f"RansomLook kaydında geçersiz {field} alanı var.")
    return normalized


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or value != value.strip() or len(value) > 64:
        raise SourceError("RansomLook kaydında geçersiz keşif zamanı var.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as error:
        raise SourceError("RansomLook kaydında geçersiz keşif zamanı var.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourceError("RansomLook kaydında geçersiz keşif zamanı var.")
    return parsed.astimezone(timezone.utc).isoformat()


def _claim_id(group: str, victim: str, discovered_at: str) -> str:
    canonical = json.dumps(
        [group, victim, discovered_at], ensure_ascii=True, separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def _fetch_time(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SourceError("RansomLook indirme zamanı geçersiz; sonuç üretilmedi.")
    return value.astimezone(timezone.utc)


def parse_ransomlook_ransomware_response(
    content: bytes, *, fetched_at: datetime,
) -> RansomLookClaimFeed:
    fetched_at = _fetch_time(fetched_at)
    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceError("RansomLook yanıtı 2 MiB sınırını aştı; sonuç üretilmedi.")
    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant,
        )
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise SourceError("RansomLook geçerli JSON göndermedi; sonuç üretilmedi.") from error
    if not isinstance(payload, dict) or set(payload) != _TOP_FIELDS:
        raise SourceError("RansomLook yanıtı beklenen açık API biçiminde değil.")
    posts = payload["posts"]
    if not isinstance(posts, list) or len(posts) > MAX_RECORDS:
        raise SourceError("RansomLook kayıt listesi güvenli sınırı aşıyor veya geçersiz.")

    claims: list[RansomLookClaim] = []
    identities: set[tuple[str, str, str]] = set()
    earliest = fetched_at - timedelta(days=WINDOW_DAYS + 1)
    latest = fetched_at + timedelta(minutes=15)
    for raw in posts:
        if not isinstance(raw, dict) or set(raw) != _POST_FIELDS:
            raise SourceError("RansomLook akışında beklenmeyen alanlara sahip kayıt var.")
        group = _text(raw["group_name"], "grup", maximum=100)
        victim = _text(raw["post_title"], "kuruluş", maximum=300)
        discovered_at = _timestamp(raw["discovered"])
        discovered = datetime.fromisoformat(discovered_at)
        if discovered < earliest or discovered > latest:
            raise SourceError("RansomLook kaydı sabit son yedi günlük pencerenin dışında.")
        identity = (group.casefold(), victim.casefold(), discovered_at)
        if identity in identities:
            raise SourceError("RansomLook akışında yinelenen iddia kaydı var.")
        identities.add(identity)
        claims.append(RansomLookClaim(
            id=_claim_id(group, victim, discovered_at),
            group=group,
            victim=victim,
            discovered_at=discovered_at,
        ))
    claims.sort(
        key=lambda claim: (
            claim.discovered_at, claim.victim.casefold(), claim.group.casefold(), claim.id,
        ),
        reverse=True,
    )
    return RansomLookClaimFeed(
        source_name=SOURCE_NAME,
        source_url=SOURCE_URL,
        fetched_at=fetched_at.isoformat(),
        window_days=WINDOW_DAYS,
        source_record_count=len(claims),
        content_sha256=hashlib.sha256(content).hexdigest(),
        license=SOURCE_LICENSE,
        source_note=(
            "Public ransomware-group post claims; not verified breach confirmations."
        ),
        claims=tuple(claims),
    )


class RansomLookRansomwareSource:
    def __init__(
        self, *, opener: Callable | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._open = opener or build_opener(_NoRedirects()).open
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def fetch(self) -> RansomLookClaimFeed:
        request = Request(SOURCE_URL, headers={
            "User-Agent": f"XTI/{__version__} (personal defensive OSINT)",
            "Accept": "application/json", "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError("RansomLook başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("RansomLook desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "application/json":
                    raise SourceError("RansomLook JSON içerik türü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise SourceError("RansomLook geçersiz yanıt uzunluğu bildirdi.") from error
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise SourceError(
                            "RansomLook yanıtı 2 MiB sınırını aşıyor; sonuç üretilmedi."
                        )
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceError(
                        "RansomLook yanıtı 2 MiB sınırını aştı; sonuç üretilmedi."
                    )
                return parse_ransomlook_ransomware_response(
                    content, fetched_at=_fetch_time(self._clock()),
                )
        except SourceError:
            raise
        except HTTPError as error:
            raise SourceError(
                f"RansomLook HTTP {error.code} verdi; sonuç üretilmedi."
            ) from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError(
                "RansomLook bağlantısı tamamlanamadı; sonuç üretilmedi."
            ) from error

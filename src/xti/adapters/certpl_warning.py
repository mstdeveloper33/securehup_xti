"""Bounded adapter for CERT Polska's recent active Warning List domains."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
from http.client import HTTPException
import socket
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cti_feeds import (
    CERTPL_CONFIDENCE,
    CERTPL_SOURCE,
    CERTPL_URL,
    CtiFeedIndicator,
    CtiFeedSnapshot,
    feed_indicator_state_sha256,
)
from xti.ports.discovery import SourceError


MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 50_000
REQUEST_TIMEOUT = 30
_TITLE = "! Title: CERT.PL's Warning List"
_EXPIRES = "! Expires: 1 hours"
_HOMEPAGE = "! Homepage: https://cert.pl/lista-ostrzezen/"
_DESCRIPTION = (
    "CERT Polska Warning List son bir ayda eklenen etkin aldatıcı domain kaydı."
)


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _normalize_fetch_time(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise SourceError("CERT Polska indirme zamanı geçersiz; IOC'ler değiştirilmedi.")
    return value.astimezone(timezone.utc)


def parse_certpl_warning_response(
    content: bytes, *, fetched_at: datetime,
) -> CtiFeedSnapshot:
    """Validate one complete recent-active snapshot without accepting partial data."""
    fetched_at = _normalize_fetch_time(fetched_at)
    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceError("CERT Polska yanıtı 8 MiB sınırını aştı; IOC'ler değiştirilmedi.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceError(
            "CERT Polska geçerli UTF-8 metin göndermedi; IOC'ler değiştirilmedi."
        ) from error
    if "\r" in text:
        raise SourceError("CERT Polska yanıtı beklenen satır biçiminde değil.")
    lines = text.splitlines()
    if len(lines) < 4 or lines[0] != _TITLE or lines[2] != _EXPIRES or lines[3] != _HOMEPAGE:
        raise SourceError("CERT Polska yanıtı beklenen Warning List başlığını taşımıyor.")
    version_prefix = "! Version: "
    if not lines[1].startswith(version_prefix):
        raise SourceError("CERT Polska liste sürümü eksik.")
    version_text = lines[1][len(version_prefix):]
    if len(version_text) != 12 or not version_text.isascii() or not version_text.isdigit():
        raise SourceError("CERT Polska liste sürümü geçersiz.")
    try:
        version = datetime.strptime(version_text, "%Y%m%d%H%M").replace(
            tzinfo=timezone.utc,
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise SourceError("CERT Polska liste sürümü geçersiz.") from error
    if version > fetched_at + timedelta(hours=1):
        raise SourceError("CERT Polska liste zamanı sistem saatinden ileride.")
    if fetched_at - version > timedelta(hours=48):
        raise SourceError(
            "CERT Polska listesi 48 saatten eski; önceki IOC'ler korundu."
        )

    raw_domains = lines[4:]
    if len(raw_domains) > MAX_RECORDS:
        raise SourceError(
            "CERT Polska listesi 50000 kayıt sınırını aştı; IOC'ler değiştirilmedi."
        )
    domains: list[str] = []
    seen: set[str] = set()
    for raw in raw_domains:
        if not raw or raw != raw.strip() or raw.startswith("!"):
            raise SourceError("CERT Polska listesinde geçersiz veya beklenmeyen satır var.")
        try:
            domain = normalize_domain(raw)
        except ValidationError as error:
            raise SourceError("CERT Polska listesinde geçersiz domain var.") from error
        if domain != raw:
            raise SourceError("CERT Polska listesinde kanonik olmayan domain var.")
        if domain in seen:
            raise SourceError("CERT Polska listesinde yinelenen domain var.")
        seen.add(domain)
        domains.append(domain)

    observed_at = version.isoformat()
    indicators = []
    for domain in sorted(domains):
        state_sha256 = feed_indicator_state_sha256(
            indicator_type="domain", value=domain, source_reference=CERTPL_URL,
            confidence=CERTPL_CONFIDENCE, description=_DESCRIPTION,
            valid_from=observed_at, last_seen_at=observed_at,
        )
        indicators.append(CtiFeedIndicator(
            indicator_type="domain", value=domain, source_reference=CERTPL_URL,
            confidence=CERTPL_CONFIDENCE, description=_DESCRIPTION,
            valid_from=observed_at, last_seen_at=observed_at,
            state_sha256=state_sha256,
        ))
    return CtiFeedSnapshot(
        source_name=CERTPL_SOURCE, source_url=CERTPL_URL,
        content_sha256=hashlib.sha256(content).hexdigest(),
        source_record_count=len(domains), indicators=tuple(indicators),
    )


class CertPlWarningSource:
    def __init__(
        self, *, opener: Callable | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._open = opener or build_opener(_NoRedirects()).open
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def fetch(self) -> CtiFeedSnapshot:
        request = Request(CERTPL_URL, headers={
            "User-Agent": f"XTI/{__version__} (defensive IOC catalog)",
            "Accept": "text/plain", "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError("CERT Polska başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("CERT Polska desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "text/plain":
                    raise SourceError("CERT Polska metin içerik türü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise SourceError(
                            "CERT Polska geçersiz yanıt uzunluğu bildirdi."
                        ) from error
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise SourceError(
                            "CERT Polska yanıtı 8 MiB sınırını aşıyor; IOC'ler değiştirilmedi."
                        )
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceError(
                        "CERT Polska yanıtı 8 MiB sınırını aştı; IOC'ler değiştirilmedi."
                    )
                return parse_certpl_warning_response(
                    content, fetched_at=_normalize_fetch_time(self._clock()),
                )
        except SourceError:
            raise
        except HTTPError as error:
            raise SourceError(
                f"CERT Polska HTTP {error.code} verdi; önceki IOC'ler korundu."
            ) from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError(
                "CERT Polska bağlantısı tamamlanamadı; önceki IOC'ler korundu."
            ) from error

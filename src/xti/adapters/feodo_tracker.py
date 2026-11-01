"""Bounded, strict adapter for Feodo Tracker's non-aggressive 30-day IOC feed."""

from __future__ import annotations

from datetime import datetime, time, timezone
import hashlib
from http.client import HTTPException
import ipaddress
import json
import socket
from typing import Callable
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cti_feeds import (
    CtiFeedIndicator,
    CtiFeedSnapshot,
    FEODO_CONFIDENCE,
    FEODO_SOURCE,
    FEODO_URL,
    feed_indicator_state_sha256,
)
from xti.domain.cti_indicators import normalize_indicator_value
from xti.ports.discovery import SourceError


MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 50_000
REQUEST_TIMEOUT = 30


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


def _text(
    value: object, field: str, *, maximum: int, allow_empty: bool = False,
) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise SourceError(f"Feodo Tracker kaydında geçersiz {field} alanı var.")
    characters: list[str] = []
    for character in value:
        if unicodedata.category(character) == "Zs":
            characters.append(" ")
        elif character.isprintable():
            characters.append(character)
        else:
            raise SourceError(f"Feodo Tracker kaydında geçersiz {field} alanı var.")
    normalized = " ".join("".join(characters).strip().split())
    if len(normalized) > maximum or (not allow_empty and not normalized):
        raise SourceError(f"Feodo Tracker kaydında geçersiz {field} alanı var.")
    return normalized


def _utc_timestamp(value: object, field: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise SourceError(f"Feodo Tracker kaydında geçersiz {field} zamanı var.")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc,
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise SourceError(
            f"Feodo Tracker kaydında geçersiz {field} zamanı var."
        ) from error
    return parsed.isoformat()


def _last_online(value: object) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise SourceError("Feodo Tracker kaydında geçersiz son çevrimiçi tarihi var.")
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError, OverflowError) as error:
        raise SourceError(
            "Feodo Tracker kaydında geçersiz son çevrimiçi tarihi var."
        ) from error
    # The source publishes date precision only. Midnight is the conservative
    # lower bound; the record's exact first-seen time below prevents reversal.
    return datetime.combine(day, time.min, tzinfo=timezone.utc).isoformat()


def parse_feodo_response(content: bytes) -> CtiFeedSnapshot:
    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceError("Feodo Tracker yanıtı 8 MiB sınırını aştı; IOC'ler değiştirilmedi.")
    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant,
        )
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise SourceError(
            "Feodo Tracker geçerli JSON göndermedi; IOC'ler değiştirilmedi."
        ) from error
    if not isinstance(payload, list):
        raise SourceError("Feodo Tracker yanıtı beklenen tam liste biçiminde değil.")
    if len(payload) > MAX_RECORDS:
        raise SourceError(
            "Feodo Tracker listesi 50000 kayıt sınırını aştı; IOC'ler değiştirilmedi."
        )

    grouped: dict[str, dict[str, object]] = {}
    exact_records: set[tuple[object, ...]] = set()
    for raw in payload:
        if not isinstance(raw, dict) or set(raw) != {
            "ip_address", "port", "status", "hostname", "as_number", "as_name",
            "country", "first_seen", "last_online", "malware",
        }:
            raise SourceError("Feodo Tracker listesinde beklenmeyen alanlara sahip kayıt var.")
        try:
            ip = ipaddress.ip_address(raw["ip_address"])
            indicator_type = "ipv4" if ip.version == 4 else "ipv6"
            value = normalize_indicator_value(indicator_type, str(ip))
        except (TypeError, ValueError, ValidationError) as error:
            raise SourceError("Feodo Tracker kaydında geçersiz IP adresi var.") from error
        port = raw["port"]
        if type(port) is not int or not 1 <= port <= 65535:
            raise SourceError("Feodo Tracker kaydında geçersiz port var.")
        status = _text(raw["status"], "durum", maximum=16).lower()
        if status not in {"online", "offline"}:
            raise SourceError("Feodo Tracker kaydında bilinmeyen kaynak durumu var.")
        hostname_raw = raw["hostname"]
        if hostname_raw is not None:
            try:
                hostname = normalize_domain(_text(hostname_raw, "hostname", maximum=253))
            except ValidationError as error:
                raise SourceError("Feodo Tracker kaydında geçersiz hostname var.") from error
        else:
            hostname = None
        as_number = raw["as_number"]
        if as_number is not None and (
            type(as_number) is not int or not 1 <= as_number <= 4_294_967_295
        ):
            raise SourceError("Feodo Tracker kaydında geçersiz AS numarası var.")
        as_name = _text(
            raw["as_name"] or "", "AS adı", maximum=300, allow_empty=True,
        )
        country = _text(raw["country"] or "", "ülke", maximum=2, allow_empty=True)
        if country and (len(country) != 2 or not country.isascii() or not country.isalpha()):
            raise SourceError("Feodo Tracker kaydında geçersiz ülke kodu var.")
        country = country.upper()
        first_seen = _utc_timestamp(raw["first_seen"], "ilk görülme")
        last_online = _last_online(raw["last_online"])
        if datetime.fromisoformat(first_seen).date() > datetime.fromisoformat(last_online).date():
            raise SourceError("Feodo Tracker kaydında gözlem tarihleri ters sırada.")
        last_seen = max(first_seen, last_online)
        malware = _text(raw["malware"], "zararlı yazılım", maximum=200)
        exact = (
            indicator_type, value, port, status, hostname, as_number, as_name, country,
            first_seen, last_seen, malware,
        )
        if exact in exact_records:
            raise SourceError("Feodo Tracker listesinde yinelenen kayıt var.")
        exact_records.add(exact)
        entry = grouped.setdefault(value, {
            "indicator_type": indicator_type, "ports": set(), "statuses": set(),
            "malware": set(), "first_seen": first_seen, "last_seen": last_seen,
        })
        if entry["indicator_type"] != indicator_type:
            raise SourceError("Feodo Tracker IP türü tutarsız.")
        entry["ports"].add(port)
        entry["statuses"].add(status)
        entry["malware"].add(malware)
        entry["first_seen"] = min(entry["first_seen"], first_seen)
        entry["last_seen"] = max(entry["last_seen"], last_seen)

    indicators: list[CtiFeedIndicator] = []
    for value in sorted(grouped, key=lambda item: (ipaddress.ip_address(item).version, ipaddress.ip_address(item))):
        entry = grouped[value]
        ports = ", ".join(str(item) for item in sorted(entry["ports"]))
        malware = ", ".join(sorted(entry["malware"], key=str.casefold))
        statuses = ", ".join(sorted(entry["statuses"]))
        description = (
            f"Feodo Tracker 30 günlük botnet C2 kaydı; zararlı yazılım: {malware}; "
            f"portlar: {ports}; kaynak durumu: {statuses}."
        )
        source_reference = f"https://feodotracker.abuse.ch/browse/host/{value}/"
        state_sha256 = feed_indicator_state_sha256(
            indicator_type=entry["indicator_type"], value=value,
            source_reference=source_reference, confidence=FEODO_CONFIDENCE,
            description=description, valid_from=entry["first_seen"],
            last_seen_at=entry["last_seen"],
        )
        indicators.append(CtiFeedIndicator(
            indicator_type=entry["indicator_type"], value=value,
            source_reference=source_reference, confidence=FEODO_CONFIDENCE,
            description=description, valid_from=entry["first_seen"],
            last_seen_at=entry["last_seen"], state_sha256=state_sha256,
        ))
    return CtiFeedSnapshot(
        source_name=FEODO_SOURCE, source_url=FEODO_URL,
        content_sha256=hashlib.sha256(content).hexdigest(),
        source_record_count=len(payload), indicators=tuple(indicators),
    )


class FeodoTrackerSource:
    def __init__(self, *, opener: Callable | None = None) -> None:
        self._open = opener or build_opener(_NoRedirects()).open

    def fetch(self) -> CtiFeedSnapshot:
        request = Request(FEODO_URL, headers={
            "User-Agent": f"XTI/{__version__} (personal defensive IOC catalog)",
            "Accept": "application/json", "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError("Feodo Tracker başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("Feodo Tracker desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "application/json":
                    raise SourceError("Feodo Tracker JSON içerik türü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise SourceError("Feodo Tracker geçersiz yanıt uzunluğu bildirdi.") from error
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise SourceError(
                            "Feodo Tracker yanıtı 8 MiB sınırını aşıyor; IOC'ler değiştirilmedi."
                        )
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceError(
                        "Feodo Tracker yanıtı 8 MiB sınırını aştı; IOC'ler değiştirilmedi."
                    )
                return parse_feodo_response(content)
        except SourceError:
            raise
        except HTTPError as error:
            raise SourceError(
                f"Feodo Tracker HTTP {error.code} verdi; önceki IOC'ler korundu."
            ) from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError(
                "Feodo Tracker bağlantısı tamamlanamadı; önceki IOC'ler korundu."
            ) from error

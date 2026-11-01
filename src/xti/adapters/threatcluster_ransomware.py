"""Bounded adapter for ThreatCluster's public ransomware victim claim feed."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
from http.client import HTTPException
import json
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.domain.ransomware_claims import (
    RANSOMWARE_SOURCE_LICENSE,
    RANSOMWARE_SOURCE_NAME,
    RANSOMWARE_SOURCE_URL,
    RansomwareClaim,
    RansomwareClaimFeed,
)
from xti.ports.discovery import SourceError


SOURCE_NAME = RANSOMWARE_SOURCE_NAME
SOURCE_URL = RANSOMWARE_SOURCE_URL
EXPECTED_FEED = "ThreatCluster dark-web victims"
EXPECTED_LICENSE = RANSOMWARE_SOURCE_LICENSE
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 10_000
REQUEST_TIMEOUT = 30
_TOP_FIELDS = {
    "feed", "generated_at", "window_days", "count", "note", "license", "victims",
}
_REQUIRED_CLAIM_FIELDS = {
    "group", "victim", "country", "sector", "discovered", "post_url", "status",
}
_OPTIONAL_CLAIM_FIELDS = {
    "website", "last_seen_at", "delisted_at", "first_party",
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
    raise ValueError("Non-finite JSON number")


def _text(
    value: object, field: str, *, maximum: int, allow_none: bool = False,
) -> str | None:
    if allow_none and value is None:
        return None
    if not isinstance(value, str) or value != value.strip() or not 1 <= len(value) <= maximum:
        raise SourceError(f"ThreatCluster kaydında geçersiz {field} alanı var.")
    if not all(character.isprintable() for character in value):
        raise SourceError(f"ThreatCluster kaydında geçersiz {field} alanı var.")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise SourceError(f"ThreatCluster kaydında geçersiz {field} alanı var.")
    return normalized


def _timestamp(value: object, field: str, *, allow_none: bool = False) -> str | None:
    if allow_none and value is None:
        return None
    if not isinstance(value, str) or value != value.strip() or len(value) > 64:
        raise SourceError(f"ThreatCluster kaydında geçersiz {field} zamanı var.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError) as error:
        raise SourceError(f"ThreatCluster kaydında geçersiz {field} zamanı var.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourceError(f"ThreatCluster kaydında geçersiz {field} zamanı var.")
    return parsed.astimezone(timezone.utc).isoformat()


def _source_url(value: object) -> bool:
    if value is None:
        return False
    url = _text(value, "kaynak gönderi adresi", maximum=2048)
    assert url is not None
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise SourceError("ThreatCluster kaydında geçersiz kaynak gönderi adresi var.") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and not 1 <= port <= 65_535)
    ):
        raise SourceError("ThreatCluster kaydında geçersiz kaynak gönderi adresi var.")
    return True


def _claim_id(group: str, victim: str, discovered_at: str) -> str:
    canonical = json.dumps(
        [group, victim, discovered_at], ensure_ascii=True, separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def _normalize_fetch_time(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SourceError("ThreatCluster indirme zamanı geçersiz; sonuç üretilmedi.")
    return value.astimezone(timezone.utc)


def parse_threatcluster_ransomware_response(
    content: bytes, *, fetched_at: datetime,
) -> RansomwareClaimFeed:
    fetched_at = _normalize_fetch_time(fetched_at)
    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceError("ThreatCluster yanıtı 8 MiB sınırını aştı; sonuç üretilmedi.")
    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant,
        )
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise SourceError("ThreatCluster geçerli JSON göndermedi; sonuç üretilmedi.") from error
    if not isinstance(payload, dict) or set(payload) != _TOP_FIELDS:
        raise SourceError("ThreatCluster yanıtı beklenen açık akış biçiminde değil.")
    if payload["feed"] != EXPECTED_FEED or payload["license"] != EXPECTED_LICENSE:
        raise SourceError("ThreatCluster akış kimliği veya veri lisansı beklenenden farklı.")
    generated_at = _timestamp(payload["generated_at"], "akış üretim")
    assert generated_at is not None
    generated = datetime.fromisoformat(generated_at)
    if generated > fetched_at + timedelta(minutes=15):
        raise SourceError("ThreatCluster akış zamanı sistem saatinden ileride.")
    if fetched_at - generated > timedelta(hours=48):
        raise SourceError("ThreatCluster akışı 48 saatten eski; sonuç üretilmedi.")
    window_days = payload["window_days"]
    count = payload["count"]
    if type(window_days) is not int or not 1 <= window_days <= 365:
        raise SourceError("ThreatCluster akış zaman penceresi geçersiz.")
    if type(count) is not int or not 0 <= count <= MAX_RECORDS:
        raise SourceError("ThreatCluster akış kayıt sayısı geçersiz.")
    source_note = _text(payload["note"], "kaynak notu", maximum=2000)
    assert source_note is not None
    victims = payload["victims"]
    if not isinstance(victims, list) or len(victims) != count:
        raise SourceError("ThreatCluster akış sayacı kayıt listesiyle uyuşmuyor.")

    claims: list[RansomwareClaim] = []
    identities: set[tuple[str, str, str]] = set()
    for raw in victims:
        if (
            not isinstance(raw, dict)
            or not _REQUIRED_CLAIM_FIELDS.issubset(raw)
            or not set(raw).issubset(_REQUIRED_CLAIM_FIELDS | _OPTIONAL_CLAIM_FIELDS)
        ):
            raise SourceError("ThreatCluster akışında beklenmeyen alanlara sahip kayıt var.")
        group = _text(raw["group"], "grup", maximum=100)
        victim = _text(raw["victim"], "kuruluş", maximum=300)
        country = _text(raw["country"], "ülke", maximum=2, allow_none=True)
        sector = _text(raw["sector"], "sektör", maximum=100, allow_none=True)
        discovered_at = _timestamp(raw["discovered"], "ilk gözlem")
        assert group is not None and victim is not None and discovered_at is not None
        if country is not None and (
            len(country) != 2 or not country.isascii() or not country.isalpha()
            or country != country.upper()
        ):
            raise SourceError("ThreatCluster kaydında geçersiz ülke kodu var.")
        status = raw["status"]
        if not isinstance(status, str) or status not in {"listed", "delisted"}:
            raise SourceError("ThreatCluster kaydında bilinmeyen ilan durumu var.")
        website = _text(raw.get("website"), "web adresi", maximum=300, allow_none=True)
        last_seen_at = _timestamp(
            raw.get("last_seen_at"), "son gözlem", allow_none=True,
        )
        delisted_at = _timestamp(
            raw.get("delisted_at"), "kaldırılma gözlemi", allow_none=True,
        )
        first_party = raw.get("first_party")
        if first_party is not None and type(first_party) is not bool:
            raise SourceError("ThreatCluster kaydında geçersiz doğrudan kaynak işareti var.")
        discovered = datetime.fromisoformat(discovered_at)
        if discovered > generated + timedelta(minutes=15):
            raise SourceError("ThreatCluster kaydında akıştan ileride ilk gözlem zamanı var.")
        for label, timestamp in (("son gözlem", last_seen_at), ("kaldırılma", delisted_at)):
            if timestamp is not None and datetime.fromisoformat(timestamp) < discovered:
                raise SourceError(f"ThreatCluster kaydında {label} zamanı ilk gözlemden önce.")
        if status == "listed" and delisted_at is not None:
            raise SourceError("ThreatCluster ilan durumu kaldırılma zamanı ile çelişiyor.")
        identity = (group.casefold(), victim.casefold(), discovered_at)
        if identity in identities:
            raise SourceError("ThreatCluster akışında yinelenen iddia kaydı var.")
        identities.add(identity)
        claims.append(RansomwareClaim(
            id=_claim_id(group, victim, discovered_at),
            group=group,
            victim=victim,
            country=country,
            sector=sector,
            discovered_at=discovered_at,
            status=status,
            website=website,
            last_seen_at=last_seen_at,
            delisted_at=delisted_at,
            first_party=first_party,
            source_post_available=_source_url(raw["post_url"]),
        ))

    claims.sort(
        key=lambda claim: (
            claim.discovered_at,
            claim.victim.casefold(),
            claim.group.casefold(),
            claim.id,
        ),
        reverse=True,
    )
    return RansomwareClaimFeed(
        source_name=SOURCE_NAME,
        source_url=SOURCE_URL,
        fetched_at=fetched_at.isoformat(),
        generated_at=generated_at,
        window_days=window_days,
        source_record_count=count,
        content_sha256=hashlib.sha256(content).hexdigest(),
        license=EXPECTED_LICENSE,
        source_note=source_note,
        claims=tuple(claims),
    )


class ThreatClusterRansomwareSource:
    def __init__(
        self, *, opener: Callable | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._open = opener or build_opener(_NoRedirects()).open
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def fetch(self) -> RansomwareClaimFeed:
        request = Request(SOURCE_URL, headers={
            "User-Agent": f"XTI/{__version__} (personal defensive OSINT)",
            "Accept": "application/json", "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError("ThreatCluster başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("ThreatCluster desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "application/json":
                    raise SourceError("ThreatCluster JSON içerik türü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise SourceError("ThreatCluster geçersiz yanıt uzunluğu bildirdi.") from error
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise SourceError(
                            "ThreatCluster yanıtı 8 MiB sınırını aşıyor; sonuç üretilmedi."
                        )
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceError(
                        "ThreatCluster yanıtı 8 MiB sınırını aştı; sonuç üretilmedi."
                    )
                return parse_threatcluster_ransomware_response(
                    content, fetched_at=_normalize_fetch_time(self._clock()),
                )
        except SourceError:
            raise
        except HTTPError as error:
            raise SourceError(
                f"ThreatCluster HTTP {error.code} verdi; sonuç üretilmedi."
            ) from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError(
                "ThreatCluster bağlantısı tamamlanamadı; sonuç üretilmedi."
            ) from error

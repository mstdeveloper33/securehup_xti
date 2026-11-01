"""Bounded retrieval and strict normalization of CISA's public KEV catalog."""

from __future__ import annotations

import hashlib
from http.client import HTTPException
import json
import socket
from typing import Callable
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError
from xti.domain.vulnerability import (
    CISA_KEV_SOURCE,
    CISA_KEV_URL,
    KevCatalogSnapshot,
    KevEntry,
    normalize_cve_id,
    validate_cwe_id,
    validate_iso_date,
)
from xti.ports.discovery import SourceError


MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 10_000
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
        raise SourceError(f"CISA KEV kaydında geçersiz {field} alanı var.")
    characters: list[str] = []
    for character in value:
        if unicodedata.category(character) == "Zs":
            characters.append(" ")
        elif character.isprintable():
            characters.append(character)
        else:
            raise SourceError(f"CISA KEV kaydında geçersiz {field} alanı var.")
    normalized = "".join(characters).strip()
    if len(normalized) > maximum or (not allow_empty and not normalized):
        raise SourceError(f"CISA KEV kaydında geçersiz {field} alanı var.")
    return normalized


def parse_kev_response(content: bytes) -> KevCatalogSnapshot:
    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceError("CISA KEV yanıtı 16 MiB sınırını aştı; katalog değiştirilmedi.")
    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant,
        )
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise SourceError("CISA geçerli KEV JSON verisi göndermedi; katalog değiştirilmedi.") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("vulnerabilities"), list):
        raise SourceError("CISA KEV yanıtı beklenen katalog biçiminde değil.")
    raw_entries = payload["vulnerabilities"]
    if len(raw_entries) > MAX_ENTRIES:
        raise SourceError("CISA KEV kataloğu 10000 kayıt sınırını aştı; katalog değiştirilmedi.")
    count = payload.get("count")
    if type(count) is not int or count != len(raw_entries):
        raise SourceError("CISA KEV toplam kayıt sayısı içerikle uyuşmuyor.")
    title = _text(payload.get("title"), "katalog başlığı", maximum=500)
    version = _text(payload.get("catalogVersion"), "katalog sürümü", maximum=100)
    released = _text(payload.get("dateReleased"), "yayın zamanı", maximum=100)

    entries: list[KevEntry] = []
    seen: set[str] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise SourceError("CISA KEV listesinde geçersiz bir kayıt var.")
        try:
            cve_id = normalize_cve_id(raw.get("cveID"))
            date_added = validate_iso_date(raw.get("dateAdded"), field="eklenme")
            due_date = validate_iso_date(raw.get("dueDate"), field="son işlem")
        except ValidationError as error:
            raise SourceError(str(error)) from error
        if cve_id in seen:
            raise SourceError("CISA KEV kataloğunda yinelenen CVE kimliği var.")
        seen.add(cve_id)
        raw_cwes = raw.get("cwes", ())
        if raw_cwes is None:
            raw_cwes = ()
        if not isinstance(raw_cwes, (list, tuple)) or len(raw_cwes) > 100:
            raise SourceError("CISA KEV kaydında geçersiz CWE listesi var.")
        try:
            cwes = tuple(sorted({validate_cwe_id(value) for value in raw_cwes}))
        except ValidationError as error:
            raise SourceError(str(error)) from error
        entries.append(KevEntry(
            cve_id=cve_id,
            vendor_project=_text(raw.get("vendorProject"), "üretici", maximum=500),
            product=_text(raw.get("product"), "ürün", maximum=500),
            vulnerability_name=_text(
                raw.get("vulnerabilityName"), "zafiyet adı", maximum=1000,
            ),
            date_added=date_added,
            short_description=_text(
                raw.get("shortDescription"), "kısa açıklama", maximum=8000,
            ),
            required_action=_text(
                raw.get("requiredAction"), "gerekli işlem", maximum=8000,
            ),
            due_date=due_date,
            known_ransomware_campaign_use=_text(
                raw.get("knownRansomwareCampaignUse"), "ransomware kullanımı", maximum=100,
            ),
            notes=_text(raw.get("notes", ""), "not", maximum=8000, allow_empty=True),
            cwes=cwes,
        ))
    entries.sort(key=lambda item: item.cve_id)
    return KevCatalogSnapshot(
        source=CISA_KEV_SOURCE,
        source_url=CISA_KEV_URL,
        catalog_title=title,
        catalog_version=version,
        date_released=released,
        content_sha256=hashlib.sha256(content).hexdigest(),
        entries=tuple(entries),
    )


class CisaKevSource:
    def __init__(self, *, opener: Callable | None = None) -> None:
        self._open = opener or build_opener(_NoRedirects()).open

    def fetch(self) -> KevCatalogSnapshot:
        request = Request(CISA_KEV_URL, headers={
            "User-Agent": f"XTI/{__version__} (personal defensive KEV catalog)",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError("CISA KEV kaynağı başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("CISA KEV kaynağı desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "application/json":
                    raise SourceError("CISA KEV kaynağı JSON içerik türü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise SourceError("CISA KEV geçersiz yanıt uzunluğu bildirdi.") from error
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise SourceError(
                            "CISA KEV yanıtı 16 MiB sınırını aşıyor; katalog değiştirilmedi."
                        )
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceError(
                        "CISA KEV yanıtı 16 MiB sınırını aştı; katalog değiştirilmedi."
                    )
                return parse_kev_response(content)
        except SourceError:
            raise
        except HTTPError as error:
            raise SourceError(
                f"CISA KEV kaynağı HTTP {error.code} verdi; önceki katalog korundu."
            ) from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError(
                "CISA KEV kaynağına güvenli bağlantı tamamlanamadı; önceki katalog korundu."
            ) from error

"""Bounded, explicit single-CVE preview from the official OSV API."""

from datetime import datetime, timezone
import hashlib
from http.client import HTTPException
import json
import re
import socket
from typing import Callable
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError
from xti.domain.osv_advisory import (
    OSV_SOURCE,
    OsvAdvisory,
    OsvAdvisorySnapshot,
    OsvAffectedPackage,
    osv_vulnerability_url,
)
from xti.domain.vulnerability import normalize_cve_id
from xti.ports.discovery import SourceError


MAX_RESPONSE_BYTES = 8 * 1024 * 1024
REQUEST_TIMEOUT = 30
_IDENTIFIER = re.compile(r"[A-Za-z0-9:_.-]{1,200}", re.ASCII)
_SCHEMA_VERSION = re.compile(r"[0-9]{1,4}(?:\.[0-9]{1,4}){1,2}", re.ASCII)
_REFERENCE_TYPE = re.compile(r"[A-Z_]{1,50}", re.ASCII)
_RANGE_TYPES = {"GIT", "SEMVER", "ECOSYSTEM"}
_EVENT_FIELDS = {"introduced", "fixed", "last_affected", "limit"}


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


def _text(value: object, field: str, maximum: int, *, optional: bool = False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise SourceError(f"OSV kaydında geçersiz {field} alanı var.")
    characters = []
    for character in value:
        if unicodedata.category(character) == "Zs" or character in "\r\n\t":
            characters.append(" ")
        elif character.isprintable():
            characters.append(character)
        else:
            raise SourceError(f"OSV kaydında geçersiz {field} alanı var.")
    normalized = " ".join("".join(characters).split())
    if not normalized or len(normalized) > maximum:
        raise SourceError(f"OSV kaydında geçersiz {field} alanı var.")
    return normalized


def _identifier(value: object, field: str) -> str:
    value = _text(value, field, 200)
    if _IDENTIFIER.fullmatch(value) is None:
        raise SourceError(f"OSV kaydında geçersiz {field} kimliği var.")
    return value


def _timestamp(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    text = _text(value, field, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as error:
        raise SourceError(f"OSV kaydında geçersiz {field} zamanı var.") from error
    return parsed.isoformat()


def _identifiers(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > 1000:
        raise SourceError(f"OSV kaydında geçersiz {field} listesi var.")
    return tuple(sorted({_identifier(item, field) for item in value}))


def _url(value: object, field: str) -> str:
    value = _text(value, field, 4096)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise SourceError(f"OSV kaydında geçersiz {field} adresi var.") from error
    if (
        parsed.scheme not in {"http", "https"} or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or port is not None and not 1 <= port <= 65535
    ):
        raise SourceError(f"OSV kaydında geçersiz {field} adresi var.")
    return value


def _version(value: object, field: str) -> str:
    return _text(value, field, 500)


def _affected(value: object) -> tuple[OsvAffectedPackage, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > 2000:
        raise SourceError("OSV kaydında geçersiz etkilenen paket listesi var.")
    result = []
    total_versions = 0
    for item in value:
        if not isinstance(item, dict):
            raise SourceError("OSV kaydında geçersiz etkilenen paket kaydı var.")
        package = item.get("package")
        if package is None:
            ecosystem = name = purl = None
        elif isinstance(package, dict):
            ecosystem = _text(package.get("ecosystem"), "paket ekosistemi", 200)
            name = _text(package.get("name"), "paket adı", 500)
            purl = _text(package.get("purl"), "paket URL kimliği", 2000, optional=True)
        else:
            raise SourceError("OSV kaydında geçersiz paket kimliği var.")

        versions = item.get("versions", [])
        if not isinstance(versions, list) or len(versions) > 100_000:
            raise SourceError("OSV kaydında geçersiz etkilenen sürüm listesi var.")
        for version in versions:
            _version(version, "etkilenen sürüm")
        total_versions += len(versions)
        if total_versions > 100_000:
            raise SourceError("OSV kaydındaki toplam etkilenen sürüm sınırı aşıldı.")

        ranges = item.get("ranges", [])
        if not isinstance(ranges, list) or len(ranges) > 1000:
            raise SourceError("OSV kaydında geçersiz sürüm aralığı listesi var.")
        range_types, introduced, fixed, last_affected = set(), set(), set(), set()
        single_range_event_order = None
        for range_item in ranges:
            if not isinstance(range_item, dict):
                raise SourceError("OSV kaydında geçersiz sürüm aralığı var.")
            range_type = _text(range_item.get("type"), "sürüm aralığı türü", 20).upper()
            if range_type not in _RANGE_TYPES:
                raise SourceError("OSV kaydında desteklenmeyen sürüm aralığı türü var.")
            range_types.add(range_type)
            if range_type == "GIT":
                _url(range_item.get("repo"), "Git deposu")
            events = range_item.get("events")
            if not isinstance(events, list) or not events or len(events) > 1000:
                raise SourceError("OSV kaydında geçersiz sürüm aralığı olayı var.")
            event_order = []
            for event in events:
                if not isinstance(event, dict):
                    raise SourceError("OSV kaydında geçersiz sürüm aralığı olayı var.")
                fields = _EVENT_FIELDS.intersection(event)
                if len(fields) != 1:
                    raise SourceError("OSV sürüm aralığı olayı tek bir sınır taşımalı.")
                field = next(iter(fields))
                event_order.append(field)
                version = _version(event[field], f"{field} sürümü")
                if field == "introduced":
                    introduced.add(version)
                elif field == "fixed":
                    fixed.add(version)
                elif field == "last_affected":
                    last_affected.add(version)
            if len(ranges) == 1:
                single_range_event_order = tuple(event_order)
        if package is None and not ranges:
            raise SourceError("OSV etkilenen kaydı paket veya sürüm aralığı taşımıyor.")
        result.append(OsvAffectedPackage(
            ecosystem=ecosystem, name=name, purl=purl, versions_count=len(versions),
            range_count=len(ranges), range_types=tuple(sorted(range_types)),
            single_range_event_order=single_range_event_order,
            introduced_versions=tuple(sorted(introduced)),
            fixed_versions=tuple(sorted(fixed)),
            last_affected_versions=tuple(sorted(last_affected)),
        ))
    return tuple(result)


def _references(value: object) -> tuple[tuple[str, ...], int]:
    if value is None:
        return (), 0
    if not isinstance(value, list) or len(value) > 5000:
        raise SourceError("OSV kaydında geçersiz referans listesi var.")
    advisories, other = set(), 0
    for item in value:
        if not isinstance(item, dict):
            raise SourceError("OSV kaydında geçersiz referans kaydı var.")
        reference_type = _text(item.get("type"), "referans türü", 50).upper()
        if _REFERENCE_TYPE.fullmatch(reference_type) is None:
            raise SourceError("OSV kaydında geçersiz referans türü var.")
        reference_url = _url(item.get("url"), "referans")
        if reference_type == "ADVISORY":
            advisories.add(reference_url)
        else:
            other += 1
    return tuple(sorted(advisories)), other


def parse_osv_response(content: bytes, expected_cve_id: str) -> OsvAdvisorySnapshot:
    cve_id = normalize_cve_id(expected_cve_id)
    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceError("OSV yanıtı 8 MiB sınırını aştı.")
    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant,
        )
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise SourceError("OSV geçerli zafiyet JSON verisi göndermedi.") from error
    if not isinstance(payload, dict):
        raise SourceError("OSV yanıtı beklenen nesne biçiminde değil.")
    record_id = _identifier(payload.get("id"), "kayıt")
    aliases = _identifiers(payload.get("aliases"), "alias")
    upstream = _identifiers(payload.get("upstream"), "upstream")
    if cve_id not in {record_id, *aliases, *upstream}:
        raise SourceError("OSV yanıtı istenenden farklı bir zafiyet içeriyor.")
    schema_version = _text(
        payload.get("schema_version"), "şema sürümü", 30, optional=True,
    )
    if schema_version is not None and _SCHEMA_VERSION.fullmatch(schema_version) is None:
        raise SourceError("OSV kaydında geçersiz şema sürümü var.")
    modified_at = _timestamp(payload.get("modified"), "son değişiklik")
    published_at = _timestamp(payload.get("published"), "yayın", optional=True)
    withdrawn_at = _timestamp(payload.get("withdrawn"), "geri çekilme", optional=True)
    modified = datetime.fromisoformat(modified_at)
    if published_at is not None and datetime.fromisoformat(published_at) > modified:
        raise SourceError("OSV yayın zamanı son değişiklik zamanından sonra.")
    if withdrawn_at is not None and datetime.fromisoformat(withdrawn_at) > modified:
        raise SourceError("OSV geri çekilme zamanı son değişiklik zamanından sonra.")
    advisory_references, other_reference_count = _references(payload.get("references"))
    advisory = OsvAdvisory(
        queried_cve_id=cve_id, record_id=record_id, schema_version=schema_version,
        modified_at=modified_at, published_at=published_at, withdrawn_at=withdrawn_at,
        summary=_text(payload.get("summary"), "özet", 5000, optional=True),
        details=_text(payload.get("details"), "ayrıntı", 50_000, optional=True),
        aliases=aliases, upstream=upstream, affected=_affected(payload.get("affected")),
        advisory_references=advisory_references,
        other_reference_count=other_reference_count,
    )
    return OsvAdvisorySnapshot(
        source=OSV_SOURCE, source_url=osv_vulnerability_url(cve_id), api_version="1.0",
        content_sha256=hashlib.sha256(content).hexdigest(), advisory=advisory,
    )


class OsvDevAdvisorySource:
    def __init__(self, *, opener: Callable | None = None) -> None:
        self._open = opener or build_opener(_NoRedirects()).open

    def fetch(self, cve_id: str) -> OsvAdvisorySnapshot:
        cve_id = normalize_cve_id(cve_id)
        request = Request(osv_vulnerability_url(cve_id), headers={
            "User-Agent": f"XTI/{__version__} (personal defensive OSV advisory preview)",
            "Accept": "application/json", "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError("OSV kaynağı başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("OSV kaynağı desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "application/json":
                    raise SourceError("OSV kaynağı JSON içerik türü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise SourceError("OSV geçersiz yanıt uzunluğu bildirdi.") from error
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise SourceError("OSV yanıtı 8 MiB sınırını aşıyor.")
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceError("OSV yanıtı 8 MiB sınırını aştı.")
                return parse_osv_response(content, cve_id)
        except SourceError:
            raise
        except HTTPError as error:
            if error.code == 404:
                raise SourceError("CVE için OSV kaydı bulunamadı.") from error
            raise SourceError(f"OSV kaynağı HTTP {error.code} verdi.") from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError("OSV kaynağına güvenli bağlantı tamamlanamadı.") from error
        except ValidationError as error:
            raise SourceError(str(error)) from error

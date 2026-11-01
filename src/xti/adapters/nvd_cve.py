"""Bounded single-CVE retrieval from the official NVD 2.0 API."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from http.client import HTTPException
import json
import re
import socket
from typing import Callable
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError
from xti.domain.vulnerability import (
    CvssMetric,
    NVD_CVE_SOURCE,
    NvdCve,
    NvdCveSnapshot,
    normalize_cve_id,
    nvd_cve_url,
)
from xti.ports.discovery import SourceError


MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_RECORD_BYTES = 4 * 1024 * 1024
REQUEST_TIMEOUT = 30
_CWE = re.compile(r"(?:CWE-[0-9]{1,10}|NVD-CWE-(?:noinfo|Other))", re.ASCII)
_METRIC_VERSIONS = {
    "cvssMetricV40": "4.0",
    "cvssMetricV31": "3.1",
    "cvssMetricV30": "3.0",
    "cvssMetricV2": "2.0",
}
_SEVERITIES = {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}


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
        raise SourceError(f"NVD kaydında geçersiz {field} alanı var.")
    characters = []
    for character in value:
        if unicodedata.category(character) == "Zs" or character in "\r\n\t":
            characters.append(" ")
        elif character.isprintable():
            characters.append(character)
        else:
            raise SourceError(f"NVD kaydında geçersiz {field} alanı var.")
    normalized = " ".join("".join(characters).split())
    if not normalized or len(normalized) > maximum:
        raise SourceError(f"NVD kaydında geçersiz {field} alanı var.")
    return normalized


def _timestamp(value: object, field: str) -> str:
    text = _text(value, field, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as error:
        raise SourceError(f"NVD yanıtında geçersiz {field} zamanı var.") from error
    return parsed.isoformat()


def _number(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise SourceError(f"NVD CVSS kaydında geçersiz {field} değeri var.")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise SourceError(f"NVD CVSS kaydında geçersiz {field} değeri var.") from error
    if not number.is_finite() or not Decimal(0) <= number <= Decimal(10):
        raise SourceError(f"NVD CVSS kaydında geçersiz {field} değeri var.")
    normalized = format(number, "f").rstrip("0").rstrip(".")
    return normalized or "0"


def _metrics(value: object) -> tuple[CvssMetric, ...]:
    if value is None:
        return ()
    if not isinstance(value, dict) or len(value) > 20:
        raise SourceError("NVD kaydında geçersiz CVSS bölümü var.")
    result = []
    for key, expected_version in _METRIC_VERSIONS.items():
        rows = value.get(key)
        if rows is None:
            continue
        if not isinstance(rows, list) or len(rows) > 100:
            raise SourceError("NVD kaydında geçersiz CVSS listesi var.")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("cvssData"), dict):
                raise SourceError("NVD kaydında geçersiz CVSS kaydı var.")
            data = row["cvssData"]
            version = _text(data.get("version"), "CVSS sürümü", 10)
            if version != expected_version:
                raise SourceError("NVD CVSS sürümü bulunduğu bölümle uyuşmuyor.")
            severity = data.get("baseSeverity", row.get("baseSeverity"))
            if severity is not None:
                severity = _text(severity, "CVSS önem düzeyi", 20).upper()
                if severity not in _SEVERITIES:
                    raise SourceError("NVD CVSS önem düzeyi geçersiz.")
            result.append(CvssMetric(
                source=_text(row.get("source"), "CVSS kaynağı", 500),
                metric_type=_text(row.get("type", "Unknown"), "CVSS türü", 50),
                version=version,
                vector=_text(data.get("vectorString"), "CVSS vektörü", 1000),
                base_score=_number(data.get("baseScore"), "taban skoru"),
                base_severity=severity,
                exploitability_score=_number(
                    row.get("exploitabilityScore"), "istismar edilebilirlik skoru",
                    optional=True,
                ),
                impact_score=_number(
                    row.get("impactScore"), "etki skoru", optional=True,
                ),
            ))
    return tuple(result)


def _cwes(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > 100:
        raise SourceError("NVD kaydında geçersiz CWE bölümü var.")
    result = set()
    for weakness in value:
        if not isinstance(weakness, dict):
            raise SourceError("NVD kaydında geçersiz CWE kaydı var.")
        descriptions = weakness.get("description", ())
        if not isinstance(descriptions, list) or len(descriptions) > 100:
            raise SourceError("NVD kaydında geçersiz CWE açıklaması var.")
        for description in descriptions:
            if not isinstance(description, dict):
                raise SourceError("NVD kaydında geçersiz CWE açıklaması var.")
            value = _text(description.get("value"), "CWE", 100)
            if _CWE.fullmatch(value) is None:
                raise SourceError("NVD kaydında geçersiz CWE kimliği var.")
            result.add(value)
    return tuple(sorted(result))


def _description(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > 100:
        raise SourceError("NVD kaydında geçersiz açıklama listesi var.")
    english = None
    for item in value:
        if not isinstance(item, dict):
            raise SourceError("NVD kaydında geçersiz açıklama kaydı var.")
        language = _text(item.get("lang"), "açıklama dili", 20)
        text = _text(item.get("value"), "açıklama", 20_000)
        if language == "en" and english is None:
            english = text
    return english


def _reference_count(value: object) -> int:
    if value is None:
        return 0
    if not isinstance(value, list) or len(value) > 5000:
        raise SourceError("NVD kaydında geçersiz referans listesi var.")
    for item in value:
        if not isinstance(item, dict):
            raise SourceError("NVD kaydında geçersiz referans kaydı var.")
        url = _text(item.get("url"), "referans URL", 4096)
        if not (url.startswith("https://") or url.startswith("http://")):
            raise SourceError("NVD kaydında güvenli biçimde gösterilemeyen referans var.")
    return len(value)


def parse_nvd_record(raw: object) -> tuple[NvdCve, str]:
    """Parse one CVE object shared by single-record and window responses."""
    if not isinstance(raw, dict):
        raise SourceError("NVD yanıtında geçersiz CVE kaydı var.")
    try:
        actual_id = normalize_cve_id(raw.get("id"))
    except ValidationError as error:
        raise SourceError(str(error)) from error
    record_json = json.dumps(
        raw, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    if len(record_json.encode("utf-8")) > MAX_RECORD_BYTES:
        raise SourceError("NVD CVE kaydı 4 MiB sınırını aştı; kayıt değiştirilmedi.")
    record = NvdCve(
        cve_id=actual_id,
        source_identifier=_text(raw.get("sourceIdentifier"), "CVE kaynağı", 500),
        published_at=_timestamp(raw.get("published"), "yayın"),
        last_modified_at=_timestamp(raw.get("lastModified"), "son değişiklik"),
        vuln_status=_text(raw.get("vulnStatus"), "CVE durumu", 100),
        english_description=_description(raw.get("descriptions")),
        cvss_metrics=_metrics(raw.get("metrics")),
        cwes=_cwes(raw.get("weaknesses")),
        reference_count=_reference_count(raw.get("references")),
    )
    if datetime.fromisoformat(record.last_modified_at) < datetime.fromisoformat(record.published_at):
        raise SourceError("NVD CVE değişiklik zamanı yayın zamanından önce.")
    return record, record_json


def parse_nvd_response(content: bytes, expected_cve_id: str) -> NvdCveSnapshot:
    cve_id = normalize_cve_id(expected_cve_id)
    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceError("NVD yanıtı 8 MiB sınırını aştı; kayıt değiştirilmedi.")
    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant,
        )
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise SourceError("NVD geçerli CVE JSON verisi göndermedi; kayıt değiştirilmedi.") from error
    if not isinstance(payload, dict):
        raise SourceError("NVD yanıtı beklenen nesne biçiminde değil.")
    if (
        payload.get("format") != "NVD_CVE" or payload.get("version") != "2.0"
        or payload.get("startIndex") != 0 or payload.get("totalResults") != 1
        or payload.get("resultsPerPage") != 1
    ):
        raise SourceError("NVD tek CVE yanıtının sayfa bilgisi beklenen biçimde değil.")
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, list) or len(vulnerabilities) != 1:
        raise SourceError("CVE, NVD kaynağında bulunamadı; önceki kayıt korundu.")
    envelope = vulnerabilities[0]
    if not isinstance(envelope, dict) or not isinstance(envelope.get("cve"), dict):
        raise SourceError("NVD yanıtında geçersiz CVE kaydı var.")
    raw = envelope["cve"]
    record, record_json = parse_nvd_record(raw)
    actual_id = record.cve_id
    if actual_id != cve_id:
        raise SourceError("NVD yanıtı istenenden farklı bir CVE içeriyor.")
    return NvdCveSnapshot(
        source=NVD_CVE_SOURCE,
        source_url=nvd_cve_url(cve_id),
        api_version="2.0",
        response_timestamp=_timestamp(payload.get("timestamp"), "yanıt"),
        content_sha256=hashlib.sha256(content).hexdigest(),
        record_json=record_json,
        record=record,
    )


class NvdCveSource:
    def __init__(self, *, opener: Callable | None = None) -> None:
        self._open = opener or build_opener(_NoRedirects()).open

    def fetch(self, cve_id: str) -> NvdCveSnapshot:
        cve_id = normalize_cve_id(cve_id)
        url = nvd_cve_url(cve_id)
        request = Request(url, headers={
            "User-Agent": f"XTI/{__version__} (personal defensive NVD CVE lookup)",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError("NVD kaynağı başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("NVD kaynağı desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "application/json":
                    raise SourceError("NVD kaynağı JSON içerik türü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise SourceError("NVD geçersiz yanıt uzunluğu bildirdi.") from error
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise SourceError("NVD yanıtı 8 MiB sınırını aşıyor.")
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceError("NVD yanıtı 8 MiB sınırını aştı.")
                return parse_nvd_response(content, cve_id)
        except SourceError:
            raise
        except HTTPError as error:
            raise SourceError(
                f"NVD kaynağı HTTP {error.code} verdi; önceki kayıt korundu."
            ) from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError(
                "NVD kaynağına güvenli bağlantı tamamlanamadı; önceki kayıt korundu."
            ) from error

"""Bounded, resumable page retrieval from the official NVD CVE 2.0 API."""

from __future__ import annotations

from datetime import datetime
from http.client import HTTPException
import hashlib
import json
import socket
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from xti import __version__
from xti.adapters.nvd_cve import (
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT,
    _NoRedirects,
    _constant,
    _object,
    _timestamp,
    parse_nvd_record,
)
from xti.domain.vulnerability import (
    NVD_CVE_SOURCE,
    NvdWindowPage,
    NvdWindowRecord,
    normalize_nvd_window,
    nvd_window_url,
    validate_nvd_window_page,
)
from xti.ports.discovery import SourceError


def _integer(value: object, field: str, *, maximum: int = 2_147_483_647) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise SourceError(f"NVD pencere yanıtında geçersiz {field} alanı var.")
    return value


def parse_nvd_window_response(
    content: bytes,
    *,
    window_start: str,
    window_end: str,
    page_size: int,
    start_index: int,
) -> NvdWindowPage:
    window_start, window_end = normalize_nvd_window(window_start, window_end)
    page_size, start_index = validate_nvd_window_page(page_size, start_index)
    if len(content) > MAX_RESPONSE_BYTES:
        raise SourceError("NVD pencere yanıtı 8 MiB sınırını aştı; kayıt değiştirilmedi.")
    try:
        payload = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant,
        )
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise SourceError(
            "NVD geçerli pencere JSON verisi göndermedi; kayıt değiştirilmedi."
        ) from error
    if not isinstance(payload, dict):
        raise SourceError("NVD pencere yanıtı beklenen nesne biçiminde değil.")
    if payload.get("format") != "NVD_CVE" or payload.get("version") != "2.0":
        raise SourceError("NVD pencere yanıtının biçim veya API sürümü geçersiz.")
    actual_start = _integer(payload.get("startIndex"), "başlangıç sırası")
    returned_count = _integer(
        payload.get("resultsPerPage"), "dönen kayıt sayısı", maximum=page_size,
    )
    total_results = _integer(payload.get("totalResults"), "toplam kayıt sayısı")
    if actual_start != start_index:
        raise SourceError("NVD istenenden farklı bir sayfa döndürdü.")
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, list) or len(vulnerabilities) != returned_count:
        raise SourceError("NVD pencere kayıt sayısı sayfa bilgisiyle uyuşmuyor.")
    if start_index > total_results or start_index + returned_count > total_results:
        raise SourceError("NVD pencere sayfa sınırları toplam kayıt sayısıyla uyuşmuyor.")
    if returned_count == 0 and start_index < total_results:
        raise SourceError("NVD tamamlanmamış pencere için boş sayfa döndürdü.")
    if returned_count < page_size and start_index + returned_count < total_results:
        raise SourceError("NVD tamamlanmamış pencere için eksik sayfa döndürdü.")

    lower = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
    upper = datetime.fromisoformat(window_end.replace("Z", "+00:00"))
    records: list[NvdWindowRecord] = []
    seen: set[str] = set()
    for envelope in vulnerabilities:
        if not isinstance(envelope, dict) or not isinstance(envelope.get("cve"), dict):
            raise SourceError("NVD pencere yanıtında geçersiz CVE zarfı var.")
        record, record_json = parse_nvd_record(envelope["cve"])
        if record.cve_id in seen:
            raise SourceError("NVD pencere yanıtı yinelenen CVE içeriyor.")
        modified = datetime.fromisoformat(record.last_modified_at)
        if not lower <= modified <= upper:
            raise SourceError("NVD pencere yanıtı istenen zaman aralığı dışında CVE içeriyor.")
        seen.add(record.cve_id)
        records.append(NvdWindowRecord(record_json=record_json, record=record))

    return NvdWindowPage(
        source=NVD_CVE_SOURCE,
        source_url=nvd_window_url(window_start, window_end, page_size, start_index),
        api_version="2.0",
        window_start=window_start,
        window_end=window_end,
        requested_page_size=page_size,
        start_index=start_index,
        results_per_page=returned_count,
        total_results=total_results,
        response_timestamp=_timestamp(payload.get("timestamp"), "yanıt"),
        content_sha256=hashlib.sha256(content).hexdigest(),
        records=tuple(records),
    )


class NvdWindowSource:
    """Fetch exactly one bounded page; the application controls all repetition."""

    def __init__(self, *, opener: Callable | None = None) -> None:
        self._open = opener or build_opener(_NoRedirects()).open

    def fetch(
        self, *, window_start: str, window_end: str, page_size: int, start_index: int,
    ) -> NvdWindowPage:
        window_start, window_end = normalize_nvd_window(window_start, window_end)
        page_size, start_index = validate_nvd_window_page(page_size, start_index)
        url = nvd_window_url(window_start, window_end, page_size, start_index)
        request = Request(url, headers={
            "User-Agent": f"XTI/{__version__} (personal defensive NVD window lookup)",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError("NVD pencere kaynağı başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("NVD pencere kaynağı desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "application/json":
                    raise SourceError("NVD pencere kaynağı JSON içerik türü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise SourceError("NVD geçersiz pencere yanıt uzunluğu bildirdi.") from error
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise SourceError("NVD pencere yanıtı 8 MiB sınırını aşıyor.")
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceError("NVD pencere yanıtı 8 MiB sınırını aştı.")
                return parse_nvd_window_response(
                    content,
                    window_start=window_start,
                    window_end=window_end,
                    page_size=page_size,
                    start_index=start_index,
                )
        except SourceError:
            raise
        except HTTPError as error:
            raise SourceError(
                f"NVD pencere kaynağı HTTP {error.code} verdi; ilerleme korunuyor."
            ) from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError(
                "NVD pencere kaynağına güvenli bağlantı tamamlanamadı; ilerleme korunuyor."
            ) from error

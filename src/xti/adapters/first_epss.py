"""Bounded retrieval and strict normalization of FIRST's daily EPSS CSV."""

from __future__ import annotations

import csv
from datetime import datetime
import gzip
import hashlib
from http.client import HTTPException
from io import BytesIO, StringIO
import re
import socket
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError
from xti.domain.vulnerability import (
    EpssCatalogSnapshot,
    EpssScore,
    FIRST_EPSS_SOURCE,
    FIRST_EPSS_URL,
    normalize_cve_id,
    normalize_probability,
)
from xti.ports.discovery import SourceError


MAX_COMPRESSED_BYTES = 16 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 1_000_000
REQUEST_TIMEOUT = 30
_MODEL_VERSION = re.compile(r"v[0-9]{4}\.[0-9]{2}\.[0-9]{2}", re.ASCII)


class _SameHostRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        target = urlsplit(new_url)
        if target.scheme != "https" or target.hostname != "epss.empiricalsecurity.com":
            raise SourceError("EPSS kaynağı güvenilmeyen bir yönlendirme gönderdi.")
        return super().redirect_request(request, fp, code, message, headers, new_url)


def _metadata(row: list[str]) -> tuple[str, str]:
    if len(row) != 2 or not row[0].startswith("#"):
        raise SourceError("EPSS CSV model ve tarih başlığı geçersiz.")
    values = {}
    for item in (row[0][1:], row[1]):
        key, separator, value = item.partition(":")
        if not separator or key in values or not value:
            raise SourceError("EPSS CSV model ve tarih başlığı geçersiz.")
        values[key] = value
    if set(values) != {"model_version", "score_date"}:
        raise SourceError("EPSS CSV model ve tarih başlığı geçersiz.")
    model = values["model_version"]
    if _MODEL_VERSION.fullmatch(model) is None:
        raise SourceError("EPSS CSV model sürümü geçersiz.")
    try:
        timestamp = datetime.fromisoformat(values["score_date"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Timezone required")
    except (TypeError, ValueError, OverflowError) as error:
        raise SourceError("EPSS CSV puan tarihi geçersiz.") from error
    return model, timestamp.date().isoformat()


def parse_epss_response(content: bytes) -> EpssCatalogSnapshot:
    if len(content) > MAX_COMPRESSED_BYTES:
        raise SourceError("EPSS yanıtı 16 MiB sıkıştırılmış veri sınırını aştı.")
    try:
        with gzip.GzipFile(fileobj=BytesIO(content)) as compressed:
            decoded = compressed.read(MAX_DECOMPRESSED_BYTES + 1)
    except (OSError, EOFError) as error:
        raise SourceError("EPSS kaynağı geçerli gzip verisi göndermedi.") from error
    if len(decoded) > MAX_DECOMPRESSED_BYTES:
        raise SourceError("EPSS CSV 64 MiB açılmış veri sınırını aştı.")
    try:
        text = decoded.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceError("EPSS CSV geçerli UTF-8 değil.") from error
    try:
        reader = csv.reader(StringIO(text, newline=""), strict=True)
        model_version, score_date = _metadata(next(reader))
        if next(reader) != ["cve", "epss", "percentile"]:
            raise SourceError("EPSS CSV sütun başlığı geçersiz.")
        entries: list[EpssScore] = []
        seen: set[str] = set()
        for row in reader:
            if len(entries) >= MAX_ENTRIES:
                raise SourceError("EPSS CSV 1000000 kayıt sınırını aştı.")
            if len(row) != 3:
                raise SourceError("EPSS CSV içinde geçersiz bir kayıt var.")
            try:
                cve_id = normalize_cve_id(row[0])
                epss = normalize_probability(row[1], field="olasılık")
                percentile = normalize_probability(row[2], field="yüzdelik dilim")
            except ValidationError as error:
                raise SourceError(str(error)) from error
            if cve_id in seen:
                raise SourceError("EPSS CSV içinde yinelenen CVE kimliği var.")
            seen.add(cve_id)
            entries.append(EpssScore(cve_id, epss, percentile))
    except StopIteration as error:
        raise SourceError("EPSS CSV gerekli başlıkları içermiyor.") from error
    except (csv.Error, RecursionError) as error:
        raise SourceError("EPSS CSV güvenli biçimde ayrıştırılamadı.") from error
    if not entries:
        raise SourceError("EPSS CSV boş; mevcut katalog değiştirilmedi.")
    entries.sort(key=lambda item: item.cve_id)
    return EpssCatalogSnapshot(
        source=FIRST_EPSS_SOURCE,
        source_url=FIRST_EPSS_URL,
        model_version=model_version,
        score_date=score_date,
        content_sha256=hashlib.sha256(decoded).hexdigest(),
        entries=tuple(entries),
    )


class FirstEpssSource:
    def __init__(self, *, opener: Callable | None = None) -> None:
        self._open = opener or build_opener(_SameHostRedirects()).open

    def fetch(self) -> EpssCatalogSnapshot:
        request = Request(FIRST_EPSS_URL, headers={
            "User-Agent": f"XTI/{__version__} (personal defensive EPSS catalog)",
            "Accept": "application/gzip, application/octet-stream",
            "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError("EPSS kaynağı başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("EPSS kaynağı desteklenmeyen HTTP sıkıştırması kullandı.")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
                if content_type.strip().lower() not in {
                    "application/gzip", "application/x-gzip", "application/octet-stream",
                    "binary/octet-stream",
                }:
                    raise SourceError("EPSS kaynağı beklenen gzip içerik türünü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise SourceError("EPSS kaynağı geçersiz yanıt uzunluğu bildirdi.") from error
                    if length < 0 or length > MAX_COMPRESSED_BYTES:
                        raise SourceError("EPSS yanıtı 16 MiB sıkıştırılmış veri sınırını aşıyor.")
                content = response.read(MAX_COMPRESSED_BYTES + 1)
                if len(content) > MAX_COMPRESSED_BYTES:
                    raise SourceError("EPSS yanıtı 16 MiB sıkıştırılmış veri sınırını aştı.")
                return parse_epss_response(content)
        except SourceError:
            raise
        except HTTPError as error:
            raise SourceError(
                f"EPSS kaynağı HTTP {error.code} verdi; önceki katalog korundu."
            ) from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError(
                "EPSS kaynağına güvenli bağlantı tamamlanamadı; önceki katalog korundu."
            ) from error

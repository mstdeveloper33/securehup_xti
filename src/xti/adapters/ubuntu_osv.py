"""Bounded single-CVE OSV preview from Canonical's official data repository."""

from dataclasses import replace
from http.client import HTTPException
import socket
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.adapters.osv_dev import MAX_RESPONSE_BYTES, parse_osv_response
from xti.domain.assets import ValidationError
from xti.domain.osv_advisory import OsvAdvisorySnapshot
from xti.domain.ubuntu_osv import (
    UBUNTU_OSV_SOURCE,
    ubuntu_osv_record_id,
    ubuntu_osv_url,
)
from xti.domain.ubuntu_package_match import (
    normalize_debian_source_package,
    normalize_ubuntu_ecosystem,
)
from xti.domain.vulnerability import normalize_cve_id
from xti.ports.discovery import SourceError


REQUEST_TIMEOUT = 30


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def parse_ubuntu_osv_response(content: bytes, expected_cve_id: str) -> OsvAdvisorySnapshot:
    cve_id = normalize_cve_id(expected_cve_id)
    snapshot = parse_osv_response(content, cve_id)
    advisory = snapshot.advisory
    if advisory.record_id != ubuntu_osv_record_id(cve_id) or cve_id not in advisory.upstream:
        raise SourceError("Ubuntu OSV kaydı istenen CVE kimliğiyle uyuşmuyor.")
    for affected in advisory.affected:
        if affected.ecosystem is None or not affected.ecosystem.startswith("Ubuntu:"):
            raise SourceError("Ubuntu OSV kaydında Ubuntu dışı paket ekosistemi var.")
        if affected.name is None:
            raise SourceError("Ubuntu OSV kaydında kaynak paket adı yok.")
        try:
            if normalize_ubuntu_ecosystem(affected.ecosystem) != affected.ecosystem:
                raise SourceError("Ubuntu OSV kaydında kanonik olmayan Ubuntu ekosistemi var.")
            if normalize_debian_source_package(affected.name) != affected.name:
                raise SourceError("Ubuntu OSV kaydında kanonik olmayan kaynak paket adı var.")
        except ValidationError as error:
            raise SourceError(str(error)) from error
    return replace(
        snapshot,
        source=UBUNTU_OSV_SOURCE,
        source_url=ubuntu_osv_url(cve_id),
        api_version=f"OSV {advisory.schema_version or 'unknown'}",
    )


class UbuntuOsvAdvisorySource:
    def __init__(self, *, opener: Callable | None = None) -> None:
        self._open = opener or build_opener(_NoRedirects()).open

    def fetch(self, cve_id: str) -> OsvAdvisorySnapshot:
        cve_id = normalize_cve_id(cve_id)
        request = Request(ubuntu_osv_url(cve_id), headers={
            "User-Agent": f"XTI/{__version__} (personal defensive Ubuntu OSV preview)",
            "Accept": "application/json,text/plain;q=0.9",
            "Accept-Encoding": "identity",
        })
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError("Ubuntu OSV kaynağı başarılı HTTP yanıtı vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("Ubuntu OSV kaynağı desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                media_type = content_type.split(";", 1)[0].strip().lower()
                if media_type not in {"application/json", "text/plain"}:
                    raise SourceError("Ubuntu OSV kaynağı JSON metin içerik türü göndermedi.")
                raw_length = response.headers.get("Content-Length")
                if raw_length is not None:
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError) as error:
                        raise SourceError("Ubuntu OSV geçersiz yanıt uzunluğu bildirdi.") from error
                    if length < 0 or length > MAX_RESPONSE_BYTES:
                        raise SourceError("Ubuntu OSV yanıtı 8 MiB sınırını aşıyor.")
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SourceError("Ubuntu OSV yanıtı 8 MiB sınırını aştı.")
                return parse_ubuntu_osv_response(content, cve_id)
        except SourceError:
            raise
        except HTTPError as error:
            if error.code == 404:
                raise SourceError("CVE için Canonical Ubuntu OSV kaydı bulunamadı.") from error
            raise SourceError(f"Ubuntu OSV kaynağı HTTP {error.code} verdi.") from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError("Ubuntu OSV kaynağına güvenli bağlantı tamamlanamadı.") from error
        except ValidationError as error:
            raise SourceError(str(error)) from error

"""Bounded HTTPS to one upstream repository; lookups are never transmitted."""

from http.client import HTTPException
import hashlib
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError
from xti.domain.warninglists import (
    MAX_BYTES, REVIEWED_REVISION, REVIEWED_README_SHA256,
    normalize_revision, parse_warninglist, source_url,
)
from xti.ports.discovery import SourceError


REVISION_URL = "https://api.github.com/repos/MISP/misp-warninglists/commits/main"
TIMEOUT = 15
TOTAL_SECONDS = 60


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


class MispWarninglistSource:
    def __init__(self, *, opener=None, monotonic=None):
        self.opener = opener or build_opener(ProxyHandler({}), _NoRedirects())
        self.monotonic = monotonic or time.monotonic
        self.deadline = None

    def _get(self, url, maximum):
        if self.deadline is None:
            raise SourceError("Warninglist kaynak sürümü önce çözülmeli.")
        remaining = self.deadline - self.monotonic()
        if remaining <= 0:
            raise SourceError("Warninglist güncellemesinin toplam süre sınırı doldu.")
        request = Request(url, headers={"User-Agent": f"XTI/{__version__} warninglists",
                                       "Accept": "application/json", "Accept-Encoding": "identity"})
        try:
            with self.opener.open(request, timeout=min(TIMEOUT, remaining)) as response:
                if response.geturl() != url or response.status != 200:
                    raise SourceError("Warninglist kaynağı beklenen adresten tam yanıt vermedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("Warninglist kaynak sıkıştırması desteklenmiyor.")
                length = response.headers.get("Content-Length")
                if length is not None and (len(length) > 10 or not length.isascii()
                                           or not length.isdigit() or int(length) > maximum):
                    raise SourceError("Warninglist yanıtı boyut sınırını aşıyor.")
                parts, size = [], 0
                while True:
                    if self.monotonic() >= self.deadline:
                        raise SourceError("Warninglist güncellemesinin toplam süre sınırı doldu.")
                    # read1 avoids waiting to fill a large buffer on trickle responses.
                    part = getattr(response, "read1", response.read)(min(65536, maximum + 1 - size))
                    if not part:
                        break
                    size += len(part)
                    if size > maximum:
                        raise SourceError("Warninglist yanıtı boyut sınırını aşıyor.")
                    parts.append(part)
                if length is not None and size != int(length):
                    raise SourceError("Warninglist kaynağı eksik yanıt verdi.")
                return b"".join(parts)
        except HTTPError as error:
            raise SourceError(f"Warninglist kaynağı HTTP {error.code} döndürdü; önceki liste korunur.") from error
        except (URLError, TimeoutError, socket.timeout, HTTPException, OSError) as error:
            raise SourceError("Warninglist kaynağına zamanında erişilemedi; önceki liste korunur.") from error

    def resolve_revision(self):
        self.deadline = self.monotonic() + TOTAL_SECONDS
        try:
            from xti.domain.warninglists import _unique_object
            metadata = json.loads(self._get(REVISION_URL, 256 * 1024).decode("utf-8"), object_pairs_hook=_unique_object)
            revision = normalize_revision(metadata["sha"])
            # A new data revision must retain the source/terms document reviewed
            # for this curated selection. Changed terms require an explicit review.
            if revision != REVIEWED_REVISION:
                readme = self._get(f"https://raw.githubusercontent.com/MISP/misp-warninglists/{revision}/README.md", 128 * 1024)
                if hashlib.sha256(readme).hexdigest() != REVIEWED_README_SHA256:
                    raise SourceError("Warninglist kaynak/koşul belgesi değişti; yeni sürüm incelemesi gerekli. Önceki listeler korunur.")
            return revision
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
            raise SourceError("Warninglist kaynağının commit kimliği doğrulanamadı.") from error

    def fetch(self, list_id, revision):
        body = self._get(source_url(list_id, revision), MAX_BYTES)
        try:
            parse_warninglist(list_id, body)
        except ValidationError as error:
            raise SourceError(str(error)) from error
        return body

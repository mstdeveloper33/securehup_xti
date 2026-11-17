"""One bounded GET to a fixed provider; never opens a target or uploads a file."""
from datetime import datetime, timezone
from http.client import HTTPException
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from xti import __version__
from xti.adapters.source_cooldown import SourceCooldownGate
from xti.adapters.urlscan import _provider_delay
from xti.domain.indicator_enrichment import MAX_BYTES, request_url
from xti.ports.discovery import SourceError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicEnrichmentSource:
    def __init__(self, cooldowns, *, opener=None, clock=time.monotonic,
                 wall_clock=None, sleep=time.sleep):
        self.opener = opener or build_opener(_NoRedirect())
        self.cooldowns = cooldowns
        self.clock, self.sleep = clock, sleep
        self.wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))

    def fetch(self, query):
        gate = SourceCooldownGate(query.provider, self.cooldowns, clock=self.clock,
            wall_clock=self.wall_clock, sleep=self.sleep)
        gate.before_request(2.0)
        req = Request(request_url(query), headers={"Accept": "application/json",
            "User-Agent": f"XTI/{__version__} passive-context", "Accept-Encoding": "identity"})
        try:
            try:
                response = self.opener.open(req, timeout=20)
            except HTTPError as error:
                response = error
            with response:
                status = response.status
                delay = _provider_delay(response.headers, now=self.wall_clock())
                if delay is not None:
                    gate.record(delay, "provider_wait")
                if status not in (200, 404) or (status == 404 and query.provider != "circl"):
                    if status in (429, 503):
                        gate.record(delay if delay is not None else 60, "rate_limit" if status == 429 else "provider_wait")
                    raise SourceError(f"{query.provider} HTTP {status} döndürdü; geçerli sonuç alınamadı.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("Kaynak beklenmeyen sıkıştırılmış yanıt döndürdü.")
                content = response.read(MAX_BYTES + 1)
                if not content or len(content) > MAX_BYTES:
                    raise SourceError("Kaynak yanıtı boş veya 2 MiB sınırını aşıyor.")
                return status, content
        except (URLError, TimeoutError, socket.timeout, OSError, HTTPException) as error:
            raise SourceError(f"{query.provider} yanıtı alınamadı; bağlantı veya süre sınırı hatası.") from error

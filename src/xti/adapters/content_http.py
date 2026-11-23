"""Bounded HTTPS GET with per-hop public DNS pinning and evidence-safe telemetry."""
from datetime import datetime, timezone
import hashlib
import http.client
import json
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit, urljoin

from xti.adapters.publisher_documents import _Connection
from xti.adapters.https_probe import is_public_address
from xti.domain.content_monitoring import ContentError, public_url


def resolve_public(host, seconds):
    program = 'import json,socket,sys; print(json.dumps(list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)))[:17]))'
    try:
        result = subprocess.run([sys.executable, '-I', '-c', program, host], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={'LANG': 'C.UTF-8'}, timeout=max(.05, min(10, seconds)), check=False)
        if result.returncode or len(result.stdout) > 4096: raise ValueError()
        addresses = json.loads(result.stdout)
        if not isinstance(addresses, list) or not 1 <= len(addresses) <= 16 or any(not is_public_address(v) for v in addresses):
            raise ValueError()
        return addresses[0]
    except subprocess.TimeoutExpired:
        raise ContentError('timeout', 'Kaynak DNS süre sınırına ulaşıldı.') from None
    except (OSError, ValueError, TypeError):
        raise ContentError('unsafe_target', 'Kaynak DNS kapsamı genel adres olarak doğrulanamadı.') from None


class ContentHTTP:
    def __init__(self, *, resolve=resolve_public, connect=_Connection, clock=time.monotonic, request_usage=None):
        self.resolve, self.connect, self.clock, self.request_usage = resolve, connect, clock, request_usage

    def get(self, url, *, seconds, max_operations, headers=None):
        started = self.clock(); attempts = []
        headers = headers or {}
        origin = urlsplit(public_url(url)).hostname
        while len(attempts) < min(max_operations, 4):
            url = public_url(url); parsed = urlsplit(url)
            remaining = seconds - (self.clock() - started)
            if remaining <= 0: raise ContentError('budget_exhausted', 'Kaynak süre bütçesi doldu.')
            entry = {'url_sha256': hashlib.sha256(url.encode()).hexdigest(), 'started_at': datetime.now(timezone.utc).isoformat(),
                     'http_status': None, 'body_bytes': 0}
            connection = None
            try:
                address = self.resolve(parsed.hostname, remaining)
                remaining = seconds - (self.clock() - started)
                if remaining <= 0: raise ContentError('budget_exhausted', 'Kaynak DNS sonrasında süre bütçesi doldu.')
                connection = self.connect(parsed.hostname, address, max(.05, min(20, remaining)))
                if self.request_usage is not None: self.request_usage.begin()
                attempts.append(entry)
                request_headers = {'User-Agent': 'XTI/CompanyContent (+read-only public-source monitoring)',
                                   'Accept': 'application/json, application/rss+xml, application/atom+xml, application/xml;q=0.9',
                                   'Accept-Encoding': 'identity', **headers}
                connection.request('GET', (parsed.path or '/') + ('?' + parsed.query if parsed.query else ''), headers=request_headers)
                response = connection.getresponse(); entry['http_status'] = response.status
                if self.request_usage is not None: self.request_usage.received(response.status)
                if response.status in (301, 302, 303, 307, 308):
                    target = public_url(urljoin(url, response.getheader('Location', '')))
                    if headers and urlsplit(target).hostname != origin:
                        raise ContentError('unsafe_redirect', 'Kimlikli kaynak başka sunucuya yönlendirdi; anahtar aktarılmadı.')
                    url = target
                    continue
                status = {401: 'authentication_required', 403: 'access_denied', 404: 'not_found', 429: 'rate_limited'}.get(response.status)
                if status or response.status != 200:
                    return {'status': status or 'unavailable', 'body': b'', 'attempts': attempts,
                            'retry_after_seconds': min(86400, int(response.getheader('Retry-After', '300'))) if response.getheader('Retry-After', '300').isdigit() else 300}
                if response.getheader('Content-Encoding', 'identity').lower() not in ('identity', ''):
                    raise ContentError('invalid_response', 'Sıkıştırılmış içerik yanıtı kabul edilmedi.')
                chunks, size = [], 0
                while True:
                    remaining = seconds - (self.clock() - started)
                    if remaining <= 0: raise ContentError('timeout', 'Kaynak okuma süre sınırına ulaşıldı.')
                    if connection.sock: connection.sock.settimeout(max(.05, min(20, remaining)))
                    block = response.read(16384)
                    if not block: break
                    chunks.append(block); size += len(block)
                    if size > 4 * 1024 * 1024: raise ContentError('response_too_large', 'Kaynak yanıtı 4 MiB sınırını aşıyor.')
                body = b''.join(chunks)
                entry.update(body_bytes=len(body), body_sha256=hashlib.sha256(body).hexdigest())
                return {'status': 'complete', 'body': body, 'final_url': url, 'content_type': response.getheader('Content-Type', ''), 'attempts': attempts}
            except ContentError as error:
                return {'status': error.code, 'body': b'', 'attempts': attempts, 'usage_complete': True}
            except (OSError, http.client.HTTPException):
                if self.request_usage is not None and entry in attempts and entry['http_status'] is None: self.request_usage.failed()
                return {'status': 'timeout' if self.clock() - started >= seconds else 'unavailable', 'body': b'', 'attempts': attempts}
            finally:
                entry['elapsed_seconds'] = round(self.clock() - started, 3)
                if connection is not None: connection.close()
        return {'status': 'budget_exhausted', 'body': b'', 'attempts': attempts}

"""Explicit approved-publisher GET; pinned public DNS, bounded HTML/PDF text."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import http.client
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.parse import urljoin, urlsplit, unquote

from xti.domain.assets import ValidationError
from xti.ports.discovery import SourceError
from xti.domain.publisher_documents import FetchedDocument, publisher_url, validate_fetch, MAX_BODY_BYTES, MAX_TEXT_BYTES, PDF_VERSION
from xti.adapters.https_probe import is_public_address


class _Connection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _resolve(host):
    # A timed child avoids an unbounded libc resolver blocking the company writer.
    program = 'import json,socket,sys; print(json.dumps(list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)))[:17]))'
    try:
        result = subprocess.run([sys.executable, '-I', '-c', program, host], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={'LANG': 'C.UTF-8'}, timeout=10, check=False)
        if result.returncode or len(result.stdout) > 4096:
            raise ValueError('DNS worker')
        addresses = json.loads(result.stdout)
        if not isinstance(addresses, list) or any(not isinstance(address, str) for address in addresses):
            raise ValueError('DNS result')
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise SourceError('Yayıncı DNS çözümlemesi tamamlanamadı; süre sınırı 10 saniye.') from error
    if not addresses or len(addresses) > 16 or any(not is_public_address(address) for address in addresses):
        raise SourceError('Yayıncı DNS yanıtı genel ve sınırlı adres kapsamına ait değil.')
    return addresses[0]


class _MainText(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
    EXCLUDE = {'script', 'style', 'nav', 'footer', 'header', 'form', 'iframe', 'object', 'noscript', 'svg', 'template', 'aside'}
    BLOCK = {'p', 'div', 'li', 'section', 'article', 'main', 'h1', 'h2', 'h3', 'h4', 'tr', 'pre', 'blockquote'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.parts, self.title = [], [], []
        self.size, self.nodes = 0, 0

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > 100000 or len(self.stack) > 256:
            raise SourceError('HTML yapısı ayrıştırma sınırını aşıyor.')
        attrs = dict(attrs)
        parent = self.stack[-1] if self.stack else ('', False, False)
        excluded = parent[2] or tag in self.EXCLUDE or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
        main = parent[1] or tag in ('main', 'article') or attrs.get('role') == 'main'
        if tag in self.BLOCK or tag == 'br':
            self._append('\n', main and not excluded)
        if tag not in self.VOID:
            self.stack.append((tag, main, excluded))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                _, main, excluded = self.stack[index]
                if tag in self.BLOCK:
                    self._append('\n', main and not excluded)
                del self.stack[index:]
                break

    def _append(self, text, enabled):
        if enabled:
            self.size += len(text.encode('utf-8'))
            # Allow markup whitespace overhead, but never materialize unbounded text.
            if self.size > MAX_TEXT_BYTES * 2:
                raise SourceError('HTML ana metni 64 KiB sınırını aşıyor; kısmi belge saklanmadı.')
            self.parts.append(text)

    def handle_data(self, data):
        if not self.stack:
            return
        tag, main, excluded = self.stack[-1]
        clean = ''.join(c for c in data if c.isprintable() or c in '\n\t\r')
        if tag == 'title' and not excluded and not main and sum(map(len, self.title)) < 1000:
            self.title.append(clean[:1000])
        self._append(clean, main and not excluded)


def html_text(body, charset='utf-8'):
    if charset.lower() not in ('utf-8', 'utf8', 'iso-8859-1', 'windows-1252'):
        raise SourceError('HTML karakter kodlaması desteklenmiyor.')
    try:
        parser = _MainText()
        parser.feed(body.decode(charset, errors='strict')); parser.close()
    except (UnicodeError, ValueError, RecursionError) as error:
        raise SourceError('Yayıncı HTML belgesi okunamadı.') from error
    text = '\n'.join(line for part in ''.join(parser.parts).splitlines() if (line := ' '.join(part.split())))
    if not text or len(text.encode('utf-8')) > MAX_TEXT_BYTES:
        raise SourceError('HTML ana metni yok veya 64 KiB sınırını aşıyor; tam metin kaydı oluşturulmadı.')
    return text, ' '.join(''.join(parser.title).split())[:500]


def pdf_text(body):
    try:
        if importlib.metadata.version('pypdf') != PDF_VERSION:
            raise importlib.metadata.PackageNotFoundError('pypdf')
    except importlib.metadata.PackageNotFoundError as error:
        raise SourceError('PDF için sabit pypdf 7.1.1 gerekli; ./setup ile rapor bağımlılığını kurun.') from error
    with tempfile.TemporaryDirectory(prefix='xti-pdf-') as directory:
        source, output = Path(directory) / 'input.pdf', Path(directory) / 'text.json'
        with os.fdopen(os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(body)
        try:
            result = subprocess.run([sys.executable, '-I', str(Path(__file__).with_name('publisher_pdf_worker.py')), str(source), str(output)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env={'LANG': 'C.UTF-8'}, timeout=18, check=False)
            if result.returncode or not output.is_file() or output.stat().st_size > 1024 * 1024:
                raise ValueError('Worker failed')
            value = json.loads(output.read_text(encoding='utf-8'))
            if set(value) != {'text', 'title', 'page_count'}:
                raise ValueError('Worker shape')
            return value['text'], value['title'], value['page_count']
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            raise SourceError('PDF metni çıkarılamadı: şifreli/taramalı/bozuk belge veya sayfa, süre, bellek, metin sınırı. Kısmi kayıt saklanmadı.') from error


class PublisherDocumentSource:
    def __init__(self, *, resolve=None, connect=None, clock=None):
        self.resolve, self.connect = resolve or _resolve, connect or _Connection
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def fetch(self, provider, url):
        original = current = publisher_url(provider, url)
        redirects = []
        deadline = time.monotonic() + 60
        try:
            while True:
                parsed = urlsplit(current)
                address = self.resolve(parsed.hostname)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                connection = self.connect(parsed.hostname, address, min(20, remaining))
                try:
                    connection.request('GET', parsed.path, headers={'User-Agent': 'XTI-Publisher/1', 'Accept': 'text/html, application/pdf', 'Accept-Encoding': 'identity'})
                    response = connection.getresponse()
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.getheader('Location')
                        if not location or len(redirects) >= 3:
                            raise SourceError('Yayıncı yönlendirme sınırı aşıldı veya hedef eksik.')
                        current = publisher_url(provider, urljoin(current, location))
                        if current in [original, *redirects]:
                            raise SourceError('Yayıncı yönlendirme döngüsü.')
                        redirects.append(current)
                        continue
                    if response.status != 200:
                        raise SourceError(f'Yayıncı HTTP {response.status} döndürdü; önceki belge korundu.')
                    if response.getheader('Content-Encoding', 'identity').lower() not in ('', 'identity'):
                        raise SourceError('Yayıncı beklenmeyen HTTP sıkıştırması döndürdü.')
                    content_type = response.getheader('Content-Type', '').lower()
                    media_type = content_type.split(';')[0].strip()
                    if media_type not in ('text/html', 'application/pdf'):
                        raise SourceError('Yayıncı yalnız HTML/PDF içerik döndürmeli.')
                    length = response.getheader('Content-Length')
                    if length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
                        raise SourceError('Yayıncı içerik boyutu sınırı aşıyor veya geçersiz.')
                    chunks, size = [], 0
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError()
                        if connection.sock is not None:
                            connection.sock.settimeout(min(20, remaining))
                        block = response.read1(min(65536, MAX_BODY_BYTES - size + 1))
                        if not block:
                            break
                        chunks.append(block); size += len(block)
                        if size > MAX_BODY_BYTES:
                            raise SourceError('Yayıncı yanıtı 8 MiB sınırını aşıyor.')
                    body = b''.join(chunks)
                    if not body or length is not None and len(body) != int(length):
                        raise SourceError('Yayıncı yanıtı boş veya eksik.')
                    break
                finally:
                    connection.close()
            if media_type == 'application/pdf':
                if not body.startswith(b'%PDF-'):
                    raise SourceError('PDF MIME türü ile dosya içeriği uyuşmuyor.')
                text, title, pages = pdf_text(body)
                parser = 'pypdf/' + PDF_VERSION
            else:
                charset = next((part.split('=', 1)[1].strip(' "\'') for part in content_type.split(';')[1:] if part.strip().startswith('charset=')), 'utf-8')
                text, title = html_text(body, charset)
                pages, parser = None, 'xti-publisher-html-v1'
            title = title or unquote(urlsplit(current).path.rstrip('/').rsplit('/', 1)[-1])[:500]
            return validate_fetch(FetchedDocument(provider, original, current, tuple(redirects), media_type,
                body, text, title, parser, pages, self.clock().isoformat()))
        except (ValidationError, OSError, http.client.HTTPException, UnicodeError, ValueError) as error:
            raise SourceError('Yayıncı belgesi alınamadı veya kapsam/biçim doğrulaması başarısız; önceki belge korundu.') from error

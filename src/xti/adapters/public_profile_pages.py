"""Public HTTPS GET with pinned DNS, host-scoped redirects and bounded parsing."""
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import http.client
import json
import socket
import ssl
import subprocess
import sys
import time
import zlib
from urllib.parse import urljoin, urlsplit

from xti.adapters.https_probe import is_public_address
from xti.domain.assets import ValidationError
from xti.domain.social_discovery import Page, profile_url

MAX_BODY = 2 * 1024 * 1024
MAX_HEADERS = 32 * 1024


class PageFailure(Exception):
    pass


def resolve_public(host, timeout):
    program = ('import json,socket,sys; print(json.dumps(list(dict.fromkeys('
               'r[4][0] for r in socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)))[:17]))')
    result = subprocess.run([sys.executable, '-I', '-c', program, host], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env={'LANG': 'C.UTF-8'},
                            timeout=timeout, check=False)
    if result.returncode or len(result.stdout) > 4096:
        raise PageFailure('dns_error')
    addresses = json.loads(result.stdout)
    if (not isinstance(addresses, list) or not 1 <= len(addresses) <= 16
            or any(not isinstance(a, str) or not is_public_address(a) for a in addresses)):
        raise PageFailure('non_public_address')
    return addresses[0]


class _DeadlineFile:
    def __init__(self, stream, sock, deadline):
        self.stream, self.sock, self.deadline = stream, sock, deadline
        self.header_bytes = 0

    def _remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: raise TimeoutError()
        self.sock.settimeout(remaining)

    def readline(self, limit=-1):
        maximum=min(MAX_HEADERS+1-self.header_bytes,limit if limit>=0 else MAX_HEADERS+1)
        chunks=[]
        for _ in range(maximum):
            self._remaining()
            chunk=self.stream.read1(1)
            if not chunk:break
            chunks.append(chunk)
            if chunk==b'\n':break
        value=b''.join(chunks)
        self.header_bytes += len(value)
        if self.header_bytes > MAX_HEADERS: raise PageFailure('headers_too_large')
        return value

    def read(self, size=-1):
        # BufferedReader.read can perform many socket reads and reset each socket
        # timeout. Check the absolute deadline between individual read1 calls.
        maximum=MAX_BODY+1 if size<0 else min(size,MAX_BODY+1)
        chunks=[];received=0
        while received<maximum:
            self._remaining()
            chunk=self.stream.read1(min(65536,maximum-received))
            if not chunk:break
            chunks.append(chunk);received+=len(chunk)
        return b''.join(chunks)

    def close(self): self.stream.close()
    def flush(self): self.stream.flush()


class _DeadlineSocket:
    def __init__(self, sock, deadline): self.sock, self.deadline = sock, deadline
    def makefile(self, mode): return _DeadlineFile(self.sock.makefile(mode), self.sock, self.deadline)


def _request(host, address, path, timeout):
    deadline = time.monotonic() + timeout
    raw = socket.create_connection((address, 443), timeout=timeout)
    try:
        if time.monotonic() >= deadline: raise TimeoutError()
        raw.settimeout(deadline-time.monotonic())
        tls = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    except BaseException:
        raw.close()
        raise
    try:
        tls.settimeout(max(0.001, deadline - time.monotonic()))
        wire = (f'GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: Mozilla/5.0 (compatible; XTI-Profile/1)\r\n'
                'Accept: text/html,application/xhtml+xml\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n')
        tls.sendall(wire.encode('ascii'))
        response = http.client.HTTPResponse(_DeadlineSocket(tls, deadline))
        try:
            response.begin()
            pairs=response.getheaders()
            for name in ('content-length','content-type','content-encoding','transfer-encoding','location'):
                if sum(k.lower()==name for k,v in pairs)>1:raise PageFailure('ambiguous_headers')
            headers = dict((k.lower(), v) for k,v in pairs)
            if headers.get('transfer-encoding','').lower() not in ('','chunked'):raise PageFailure('unsupported_encoding')
            if 'transfer-encoding' in headers and 'content-length' in headers:raise PageFailure('ambiguous_headers')
            if response.status in (301, 302, 303, 307, 308):
                return response.status, headers, b''
            if headers.get('content-encoding', 'identity').strip().lower() not in ('identity', '', 'gzip'):
                raise PageFailure('unsupported_encoding')
            if 'content-length' in headers and not 0 <= int(headers['content-length']) <= MAX_BODY:
                raise PageFailure('body_too_large')
            chunks, size = [], 0
            while True:
                if time.monotonic() >= deadline: raise TimeoutError()
                chunk = response.read(min(65536, MAX_BODY + 1 - size))
                if not chunk: break
                size += len(chunk)
                if size > MAX_BODY: raise PageFailure('body_too_large')
                chunks.append(chunk)
            if 'content-length' in headers and size!=int(headers['content-length']):raise PageFailure('incomplete_response')
            return response.status, headers, b''.join(chunks)
        finally:
            response.close()
    finally:
        tls.close()


class _ProfileHTML(HTMLParser):
    VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    EXCLUDE = {'script','style','svg','template','noscript','iframe','object'}

    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url, self.stack = url, []
        self.nodes, self.text_size = 0, 0
        self.title, self.meta, self.links, self.visible, self.canonicals = [], {}, [], [], []
        self.structured_urls, self.ld_parts, self.ld_size, self.gitlab_user_page = [], None, 0, False

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > 100000 or len(self.stack) > 128: raise PageFailure('html_limit')
        parent_hidden = self.stack[-1][1] if self.stack else False
        hidden = parent_hidden or tag in self.EXCLUDE
        data = dict(attrs)
        if tag == 'script' and not parent_hidden and (data.get('type') or '').lower() == 'application/ld+json':
            self.ld_parts, self.ld_size = [], 0
        if not hidden and tag == 'body' and data.get('data-page') == 'users:show' and urlsplit(self.url).hostname == 'gitlab.com':
            self.gitlab_user_page = True
        if not hidden:
            if tag == 'meta':
                key = (data.get('property') or data.get('name') or '').lower()
                if key in {'og:title','og:description','description','og:type','og:url','profile:username','octolytics-dimension-user_login'}:
                    value = data.get('content') or ''
                    # Ambiguous metadata cannot silently choose the most favourable value.
                    if key in self.meta and self.meta[key] != value: raise PageFailure('conflicting_metadata')
                    self.meta[key] = value[:2048]
            if tag in {'a','link'} and data.get('href'):
                try: value = urljoin(self.url, data['href'])
                except ValueError: value = ''
                if value and len(value) <= 2048 and value.isascii() and value.isprintable():
                    if tag == 'link' and 'canonical' in (data.get('rel') or '').lower().split(): self.canonicals.append(value)
                    elif tag == 'a' and len(self.links) < 256 and value not in self.links: self.links.append(value)
        if tag not in self.VOID: self.stack.append((tag, hidden))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID: self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == 'script' and self.ld_parts is not None:
            if self.ld_size <= 65536:
                def unique(pairs):
                    value={}
                    for key,item in pairs:
                        if key in value: raise ValueError('Duplicate structured field')
                        value[key]=item
                    return value
                try:
                    data=json.loads(''.join(self.ld_parts),object_pairs_hook=unique)
                    if isinstance(data,dict) and data.get('@context') in ('https://schema.org','http://schema.org'):
                        rows=data.get('@graph',[data])
                        if isinstance(rows,list) and len(rows)<=100:
                            for row in rows:
                                if (isinstance(row,dict) and row.get('@type') in ('Person','Organization')
                                        and isinstance(row.get('name'),str) and row['name'].strip()
                                        and isinstance(row.get('url'),str) and len(self.structured_urls)<8):
                                    self.structured_urls.append(row['url'])
                except (ValueError,TypeError,RecursionError): pass
            self.ld_parts=None
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, value):
        if self.ld_parts is not None:
            self.ld_size+=len(value)
            if self.ld_size<=65536:self.ld_parts.append(value)
        if self.stack and self.stack[-1][1]: return
        if self.stack and self.stack[-1][0] == 'title': self.title.append(value[:1000])
        if self.text_size < 32768:
            value = value[:32768-self.text_size]
            self.visible.append(value); self.text_size += len(value)


def _clean(value, maximum):
    return ' '.join(''.join(c for c in value if c.isprintable() or c.isspace()).split())[:maximum]


def _decode_body(body, encoding):
    """Bound both transfer and expanded sizes; reject truncated/ambiguous gzip."""
    if len(body) > MAX_BODY:
        raise PageFailure('body_too_large')
    encoding = encoding.strip().lower()
    if encoding in ('', 'identity'):
        return body
    if encoding != 'gzip':
        raise PageFailure('unsupported_encoding')
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        decoded = decoder.decompress(body, MAX_BODY + 1)
    except zlib.error:
        raise PageFailure('invalid_compressed_body') from None
    if len(decoded) > MAX_BODY or decoder.unconsumed_tail:
        raise PageFailure('body_too_large')
    if not decoder.eof or decoder.unused_data:
        raise PageFailure('invalid_compressed_body')
    return decoded


def parse_page(url, final_url, status, body, *, checked_at, requests=1, elapsed=0.0,
               content_type='text/html', received_bytes=None):
    if len(body) > MAX_BODY: raise PageFailure('body_too_large')
    base = dict(url=url, final_url=final_url, status=status, checked_at=checked_at,
                body_sha256=hashlib.sha256(body).hexdigest(), requests=requests,
                received_bytes=len(body) if received_bytes is None else received_bytes,
                elapsed_seconds=round(elapsed, 3))
    if content_type.split(';',1)[0].strip().lower() not in ('text/html','application/xhtml+xml','text/plain'):
        return Page(**base, error='unsupported_content_type')
    parser = _ProfileHTML(final_url)
    parser.feed(body.decode('utf-8', errors='replace')); parser.close()
    metadata = parser.meta
    title = _clean(metadata.get('og:title') or ''.join(parser.title), 500)
    description = _clean(metadata.get('og:description') or metadata.get('description',''), 1000)
    canonical_urls = tuple(v for v in dict.fromkeys([*parser.canonicals, *([metadata['og:url']] if metadata.get('og:url') else [])])
                           if v.isascii() and v.isprintable() and len(v)<=2048)
    structured_profile=False
    for value in parser.structured_urls:
        try:
            if profile_url(value)['url']==profile_url(final_url)['url']:structured_profile=True
        except ValidationError:continue
    return Page(**base, title=title, description=description, canonical_urls=canonical_urls[:8],
                profile_type=metadata.get('og:type','').casefold() == 'profile' or structured_profile or parser.gitlab_user_page,
                profile_username=_clean(metadata.get('profile:username') or metadata.get('octolytics-dimension-user_login',''),64),
                visible_text=_clean(' '.join(parser.visible),32768), links=tuple(parser.links))


class PublicProfilePageSource:
    def __init__(self, *, resolve=None, request=None, monotonic=None):
        self.resolve, self.request = resolve or resolve_public, request or _request
        self.monotonic = monotonic or time.monotonic

    def fetch(self, url, *, allowed_hosts, timeout):
        start = self.monotonic(); deadline = start + timeout
        at = datetime.now(timezone.utc).isoformat()
        current, count = url, 0
        try:
            visited = set()
            while True:
                parsed = urlsplit(current)
                if (not current.isascii() or any(ord(c)<=32 or ord(c)==127 for c in current) or '\\' in current
                        or parsed.scheme != 'https' or parsed.hostname not in allowed_hosts
                        or parsed.port not in (None,443) or parsed.username or parsed.password or parsed.fragment):
                    raise PageFailure('redirect_scope_rejected')
                if current in visited or len(visited) >= 3: raise PageFailure('redirect_limit')
                visited.add(current)
                remaining = deadline - self.monotonic()
                if remaining <= 0: raise TimeoutError()
                address = self.resolve(parsed.hostname, min(5,remaining))
                if not is_public_address(address): raise PageFailure('non_public_address')
                remaining = deadline - self.monotonic()
                if remaining <= 0: raise TimeoutError()
                count += 1
                status, headers, body = self.request(parsed.hostname, address,
                    (parsed.path or '/') + ('?' + parsed.query if parsed.query else ''), remaining)
                if status in (301,302,303,307,308):
                    location = headers.get('location')
                    if not location or len(location)>2048: raise PageFailure('redirect_missing')
                    current = urljoin(current, location)
                    continue
                decoded = _decode_body(body, headers.get('content-encoding', 'identity'))
                if self.monotonic() > deadline: raise TimeoutError()
                return parse_page(url, current, status, decoded, checked_at=at, requests=count,
                    elapsed=self.monotonic()-start, content_type=headers.get('content-type','text/html'),
                    received_bytes=len(body))
        except PageFailure as error:
            reason = str(error)
        except (TimeoutError, socket.timeout, subprocess.TimeoutExpired):
            reason = 'timeout'
        except (OSError, ValueError, http.client.HTTPException, RecursionError):
            reason = 'connection_or_parse_error'
        return Page(url=url, final_url=current, status=None, checked_at=at, error=reason,
                    requests=count, elapsed_seconds=round(self.monotonic()-start,3))

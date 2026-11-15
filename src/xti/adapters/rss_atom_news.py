"""Bounded HTTPS publisher feeds parsed by pinned, optional feedparser."""

from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
from http.client import HTTPException
from importlib.metadata import PackageNotFoundError, version
import io
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from xml.etree import ElementTree

from xti import __version__
from xti.domain.news import (
    MAX_FEED_ARTICLES, NewsArticle, NewsFeed, article_json, news_id, news_source,
    news_url, validate_feed,
)
from xti.ports.discovery import SourceError


MAX_RESPONSE_BYTES = 4 * 1024 * 1024
REQUEST_TIMEOUT = 20
READ_DEADLINE_SECONDS = 45
_CONTENT_TYPES = {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "iframe", "object"}:
            self.hidden.append(tag)
        elif tag in {"p", "br", "div", "li", "tr", "h1", "h2", "h3"} and not self.hidden:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self.hidden:
            self.hidden = self.hidden[:self.hidden.index(tag)]
        elif tag in {"p", "div", "li", "tr", "h1", "h2", "h3"} and not self.hidden:
            self.parts.append(" ")

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def _plain(value):
    if not isinstance(value, str):
        raise ValueError("Invalid feed text")
    parser = _PlainText()
    parser.feed(value)
    parser.close()
    return " ".join("".join(c if c.isprintable() or c.isspace() else " "
                            for c in "".join(parser.parts)).split())


def _raw_text(value, maximum):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid source field")
    result = " ".join(value.split())
    if not 1 <= len(result) <= maximum or any(not c.isprintable() for c in result):
        raise ValueError("Invalid source field size")
    return result


def _date(entry, name):
    # FeedParserDict aliases absent updated to published; preserve absence instead.
    raw = _raw_text(dict.get(entry, name), 256)
    parsed = dict.get(entry, name + "_parsed")
    if raw is None or parsed is None:
        return raw, None
    try:
        return raw, datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return raw, None


def _parser():
    try:
        import feedparser
        if version("feedparser") != "6.0.14" or version("feedparser-sgmllib") != "2.1.0":
            raise ImportError("Unsupported parser version")
        return feedparser
    except (ImportError, PackageNotFoundError) as error:
        raise SourceError(
            "Haber ayrıştırıcısı kurulu değil veya sürümü uyumsuz. Repo kurulumunda './scripts/setup-brand'; "
            "paket kurulumunda haber (news) ek bağımlılıklarını kurun."
        ) from error


def parse_news_feed(content: bytes, *, source_key: str, fetched_at: datetime,
                    content_type="application/xml") -> NewsFeed:
    source = news_source(source_key)
    parser = _parser()
    try:
        if (not isinstance(content, bytes) or not 1 <= len(content) <= MAX_RESPONSE_BYTES
                or not isinstance(fetched_at, datetime) or fetched_at.tzinfo is None or fetched_at.utcoffset() is None):
            raise ValueError("Invalid feed size or time")
        # Do not permit DTD/entity expansion or external references, including UTF-16/32 XML.
        probe = content.replace(b"\0", b"")
        if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", probe, re.I) or probe.count(b"<") > 40_000:
            raise ValueError("Unsafe XML declarations or structure size")
        root = ElementTree.fromstring(content)
        if root.tag == "rss":
            if root.find("channel") is None:
                raise ValueError("RSS channel missing")
        elif root.tag not in {"{http://www.w3.org/2005/Atom}feed", "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"}:
            raise ValueError("Not an RSS or Atom feed")
        # BytesIO prevents feedparser from interpreting input as a URL or local path.
        parsed = parser.parse(io.BytesIO(content), response_headers={
            "content-type": content_type, "content-location": source.url,
        }, sanitize_html=True, resolve_relative_uris=True)
        if parsed.get("bozo") or not parsed.get("version", "").startswith(("rss", "atom")):
            raise ValueError("Malformed or unsupported feed")
        entries = parsed.get("entries")
        if not isinstance(entries, list) or len(entries) > MAX_FEED_ARTICLES:
            raise ValueError("Feed entry count")
        articles = {}
        for entry in entries:
            link = _raw_text(entry.get("link"), 2048)
            if link is None:
                link = _raw_text(entry.get("id"), 2048)
            news_url(link)
            native_id = _raw_text(entry.get("id"), 2048) or link
            title = _plain(entry.get("title", ""))
            summary = _plain(entry.get("summary", ""))
            published_raw, published_at = _date(entry, "published")
            updated_raw, updated_at = _date(entry, "updated")
            article = NewsArticle(news_id(source_key, native_id), source_key, native_id,
                link, title, summary[:2000].rstrip(), len(summary) > 2000,
                published_at, updated_at, published_raw, updated_raw)
            state = article_json(article)
            if article.id in articles and article_json(articles[article.id]) != state:
                raise ValueError("Conflicting duplicate publisher identity")
            articles[article.id] = article
        return validate_feed(NewsFeed(source_key, fetched_at.astimezone(timezone.utc).isoformat(),
            hashlib.sha256(content).hexdigest(), tuple(sorted(articles.values(), key=lambda a: a.id))))
    except (ValueError, TypeError, LookupError, OverflowError, RecursionError, ElementTree.ParseError) as error:
        raise SourceError("Haber akışı eksik, bozuk veya güvenli sınırları aşıyor; önceki haberler korunur.") from error


class RssAtomNewsSource:
    def __init__(self, *, opener=None, clock=None, monotonic=None):
        self._open = opener or build_opener(ProxyHandler({}), _NoRedirects()).open
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic or time.monotonic

    def fetch(self, source_key):
        source = news_source(source_key)
        _parser()  # Missing optional dependency must fail before any network access.
        request = Request(source.url, headers={
            "User-Agent": f"XTI/{__version__} (personal defensive OSINT; publisher news feeds)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
            "Accept-Encoding": "identity",
        })
        deadline = self._monotonic() + READ_DEADLINE_SECONDS
        try:
            with self._open(request, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200 or response.geturl() != source.url:
                    raise SourceError("Haber kaynağı beklenen HTTPS yanıtını vermedi; yönlendirme izlenmedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("Haber kaynağı desteklenmeyen sıkıştırma kullandı.")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() not in _CONTENT_TYPES:
                    raise SourceError("Haber kaynağı RSS/Atom XML içerik türü göndermedi.")
                declared = response.headers.get("Content-Length")
                if declared is not None:
                    try:
                        length = int(declared)
                    except (TypeError, ValueError) as error:
                        raise SourceError("Haber yanıtının uzunluğu geçersiz.") from error
                    if not 1 <= length <= MAX_RESPONSE_BYTES:
                        raise SourceError("Haber yanıtı boş veya 4 MiB sınırını aşıyor.")
                chunks, received = [], 0
                while True:
                    if self._monotonic() > deadline:
                        raise SourceError("Haber kaynağı yanıtını okuma süresi doldu.")
                    chunk = response.read(min(65536, MAX_RESPONSE_BYTES + 1 - received))
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > MAX_RESPONSE_BYTES:
                        raise SourceError("Haber yanıtı 4 MiB sınırını aştı.")
                    chunks.append(chunk)
                if declared is not None and received != length:
                    raise SourceError("Haber kaynağı yanıtı eksik alındı.")
                return parse_news_feed(b"".join(chunks), source_key=source_key,
                                       fetched_at=self._clock(), content_type=content_type)
        except SourceError:
            raise
        except HTTPError as error:
            if error.code == 429:
                raise SourceError("Haber kaynağı istek sınırına ulaştı (HTTP 429); daha sonra yeniden deneyin.") from error
            raise SourceError(f"Haber kaynağı HTTP {error.code} verdi; önceki haberler korunur.") from error
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError) as error:
            raise SourceError("Haber kaynağına bağlantı tamamlanamadı; önceki haberler korunur.") from error

"""One bounded Tavily search request; credentials never enter saved evidence."""

from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import secrets
import socket
import stat
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError
from xti.domain.mentions import (
    MentionHit, MentionResponse, build_query, validate_request, validate_response,
)
from xti.domain.news import news_url
from xti.ports.discovery import SourceError


TAVILY_SEARCH_URL = "https://api.tavily.com/search"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT = 20
READ_DEADLINE_SECONDS = 45
MAX_KEY_BYTES = 512


def _validate_key(value):
    if (not isinstance(value, str) or not 16 <= len(value) <= MAX_KEY_BYTES
            or any(not (character.isascii() and (character.isalnum() or character in "_-"))
                   for character in value)):
        raise ValidationError("Tavily API anahtarı eksik veya geçersiz; özel anahtar dosyası ya da TAVILY_API_KEY kullanın.")
    return value


def default_tavily_key_path() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME")
    root = Path(configured) if configured and Path(configured).is_absolute() else Path.home() / ".config"
    return root / "xti" / "tavily.key"


def load_tavily_api_key(path: Path | None = None) -> str:
    """An explicit file wins; otherwise use the environment, then private config."""
    if path is None and "TAVILY_API_KEY" in os.environ:
        return _validate_key(os.environ["TAVILY_API_KEY"])
    path = path if path is not None else default_tavily_key_path()
    descriptor = None
    try:
        target = Path(path).expanduser().absolute()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(target, flags)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValidationError("Tavily anahtarı normal bir dosyada bulunmalı.")
        if details.st_mode & 0o077:
            raise ValidationError("Tavily anahtar dosyası yalnız sahibine açık olmalı (chmod 600).")
        if not 16 <= details.st_size <= MAX_KEY_BYTES + 1:
            raise ValidationError("Tavily anahtar dosyasının boyutu geçersiz.")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = None
            content = stream.read(MAX_KEY_BYTES + 2)
        if content.endswith(b"\n"):
            content = content[:-1]
        return _validate_key(content.decode("ascii"))
    except ValidationError:
        raise
    except FileNotFoundError:
        raise ValidationError("Tavily anahtarı bulunamadı; ./xti mentions configure ile tanımlayın veya TAVILY_API_KEY kullanın.") from None
    except (OSError, UnicodeError, TypeError, ValueError):
        raise ValidationError("Tavily anahtar dosyası güvenle okunamadı; konum, içerik ve izinleri kontrol edin.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def save_tavily_api_key(api_key: str, path: Path | None = None) -> Path:
    """Publish a complete mode600 key atomically without replacing any existing path."""
    content = (_validate_key(api_key) + "\n").encode("ascii")
    destination = Path(path if path is not None else default_tavily_key_path()).expanduser().absolute()
    parent_descriptor, descriptor, temporary_name = None, None, None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent_descriptor = os.open(destination.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        if not stat.S_ISDIR(os.fstat(parent_descriptor).st_mode):
            raise ValidationError("Tavily anahtar klasörü normal bir dizin olmalı.")
        temporary_name = ".tavily-key-" + secrets.token_hex(12) + ".tmp"
        descriptor = os.open(temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600, dir_fd=parent_descriptor)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_name, destination.name, src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor, follow_symlinks=False)
        return destination
    except FileExistsError:
        raise ValidationError("Tavily anahtar dosyası zaten var; üzerine yazılmadı.") from None
    except OSError:
        raise ValidationError("Tavily anahtarı güvenle kaydedilemedi; klasörü ve izinleri kontrol edin.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_name is not None and parent_descriptor is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        if parent_descriptor is not None:
            os.close(parent_descriptor)


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


def _text(value, *, maximum, allow_empty=False, truncate=False):
    if not isinstance(value, str):
        raise ValueError("Unexpected text type")
    cleaned = " ".join("".join(character if character.isprintable() or character.isspace()
                               else " " for character in value).split())
    if not allow_empty and not cleaned:
        raise ValueError("Empty text")
    if not truncate and len(cleaned) > maximum:
        raise ValueError("Oversized text")
    return cleaned[:maximum].rstrip(), len(cleaned) > maximum


def _optional_text(value, *, maximum):
    return None if value is None else _text(value, maximum=maximum)[0]


def _parse_response(content, *, request, query, api_key):
    try:
        raw = json.loads(content.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
        if not isinstance(raw, dict) or raw.get("query") != query:
            raise ValueError("Response does not match query")
        results = raw.get("results")
        if not isinstance(results, list) or len(results) > request.max_results:
            raise ValueError("Invalid results")
        request_id = _optional_text(raw.get("request_id"), maximum=128)
        usage = raw.get("usage")
        credits = None
        if usage is not None:
            if not isinstance(usage, dict) or "credits" not in usage:
                raise ValueError("Invalid usage")
            credits = usage["credits"]
            if type(credits) is not int or not 0 <= credits <= 1_000_000:
                raise ValueError("Invalid credit count")
        hits = []
        for item in results:
            if not isinstance(item, dict):
                raise ValueError("Invalid result record")
            # URLs are validated, never fetched, rewritten or silently shortened.
            url = news_url(item.get("url"))
            title, _ = _text(item.get("title"), maximum=500)
            summary, truncated = _text(item.get("content", ""), maximum=2000,
                                       allow_empty=True, truncate=True)
            published = _optional_text(item.get("published_date"), maximum=128)
            score = item.get("score")
            if score is not None:
                if type(score) not in (float, int) or not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Invalid provider score")
                score = float(score)
            if any(api_key in value for value in (url, title, summary, published or "")):
                raise ValueError("Credential echoed in response")
            hits.append(MentionHit(url=url, title=title, summary=summary,
                                   published_at=published, score=score, summary_truncated=truncated))
        if api_key in query or request_id is not None and api_key in request_id:
            raise ValueError("Credential echoed in response")
        result = MentionResponse(query=query, request_id=request_id, hits=tuple(hits), credits=credits)
        validate_response(result, request)
        return result
    except (UnicodeError, TypeError, ValueError, OverflowError, RecursionError):
        raise SourceError("Tavily yanıtı eksik, bozuk veya güvenli sınırları aşıyor; önceki kayıtlar korunur.") from None


def _http_error(code):
    if code in (401, 403):
        return "Tavily erişimi reddetti; API anahtarını ve hesap yetkisini kontrol edin."
    if code in (402, 432, 433):
        return "Tavily hesap veya kredi sınırına ulaştı; hesap kullanımını kontrol edin."
    if code == 429:
        return "Tavily istek sınırına ulaştı (HTTP 429); otomatik tekrar yapılmadı."
    if code == 434:
        return "Tavily ücretsiz katman kapasitesi şu anda dolu (HTTP 434); otomatik tekrar yapılmadı."
    if type(code) is int and 300 <= code < 400:
        return "Tavily yönlendirme yanıtı verdi; anahtar başka adrese gönderilmedi."
    return "Tavily arama isteğini tamamlamadı; önceki kayıtlar korunur."


class TavilySearchSource:
    def __init__(self, api_key: str, *, opener=None, monotonic=None):
        self._api_key = _validate_key(api_key)
        self._open = opener or build_opener(ProxyHandler({}), _NoRedirects()).open
        self._monotonic = monotonic or time.monotonic

    def fetch(self, request):
        validate_request(request)
        query = build_query(request.target)
        if self._api_key in query:
            raise ValidationError("Tavily arama metni API anahtarı içeremez.")
        payload = {
            "query": query, "topic": request.topic, "max_results": request.max_results,
            "search_depth": "basic", "auto_parameters": False,
            "include_answer": False, "include_raw_content": False, "include_images": False,
            "include_published_date": True, "include_usage": True,
        }
        outgoing = Request(TAVILY_SEARCH_URL,
            data=json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("ascii"),
            headers={"Authorization": "Bearer " + self._api_key,
                     "User-Agent": f"XTI/{__version__} (company content search)",
                     "Content-Type": "application/json", "Accept": "application/json",
                     "Accept-Encoding": "identity"}, method="POST")
        deadline = self._monotonic() + READ_DEADLINE_SECONDS
        try:
            with self._open(outgoing, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise SourceError(_http_error(response.getcode()))
                if response.geturl() != TAVILY_SEARCH_URL:
                    raise SourceError("Tavily beklenen HTTPS adresinden yanıt vermedi; sonuç kaydedilmedi.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("Tavily desteklenmeyen yanıt sıkıştırması kullandı.")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    raise SourceError("Tavily geçerli JSON içerik türü göndermedi.")
                declared = response.headers.get("Content-Length")
                if declared is not None:
                    try:
                        length = int(declared)
                    except (TypeError, ValueError):
                        raise SourceError("Tavily yanıt uzunluğu geçersiz.") from None
                    if not 1 <= length <= MAX_RESPONSE_BYTES:
                        raise SourceError("Tavily yanıtı boş veya 2 MiB sınırını aşıyor.")
                chunks, received = [], 0
                reader = getattr(response, "read1", response.read)
                while True:
                    if self._monotonic() > deadline:
                        raise SourceError("Tavily yanıtını okuma süresi doldu; otomatik tekrar yapılmadı.")
                    chunk = reader(min(65536, MAX_RESPONSE_BYTES + 1 - received))
                    if self._monotonic() > deadline:
                        raise SourceError("Tavily yanıtını okuma süresi doldu; otomatik tekrar yapılmadı.")
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > MAX_RESPONSE_BYTES:
                        raise SourceError("Tavily yanıtı 2 MiB sınırını aştı.")
                    chunks.append(chunk)
                if declared is not None and received != length:
                    raise SourceError("Tavily yanıtı eksik alındı; sonuç kaydedilmedi.")
                return _parse_response(b"".join(chunks), request=request, query=query, api_key=self._api_key)
        except SourceError:
            raise
        except HTTPError as error:
            code = error.code
            error.close()
            raise SourceError(_http_error(code)) from None
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError):
            raise SourceError("Tavily bağlantısı tamamlanamadı; otomatik tekrar yapılmadı. Kredi tüketimi bilinmiyor.") from None

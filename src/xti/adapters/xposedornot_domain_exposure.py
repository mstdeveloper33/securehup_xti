"""Bounded XposedOrNot lookup for one explicitly linked and verified domain."""

from __future__ import annotations

from datetime import datetime, timezone
from http.client import HTTPException
import hashlib
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import normalize_domain
from xti.domain.darkweb_monitoring import mask_alias


BASE = "https://api.xposedornot.com/v1/domain-breaches/"
SOURCE_REFERENCE = "https://github.com/XposedOrNot/XposedOrNot-API"
TERMS_REFERENCE = "https://xposedornot.com/terms"
MAX_RESPONSE = 16 * 1024 * 1024
MAX_RECORDS = 50_000
TIMEOUT = 20
DEADLINE = 45


class XposedOrNotDomainError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _bounded_shape(value: object) -> None:
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > 300_000 or depth > 24:
            raise ValueError("response shape exceeds bounds")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def _domain_summary(metrics: dict, requested_domain: str) -> int:
    summary = metrics.get("Domain_Summary")
    if not isinstance(summary, dict) or len(summary) > 10_000:
        raise ValueError("invalid domain summary")
    requested_counts = []
    for key, count in summary.items():
        if not isinstance(key, str):
            raise ValueError("invalid domain summary entry")
        try:
            normalized = normalize_domain(key)
        except ValueError:
            # The provider may return every domain associated with the API key.
            # An unrelated malformed entry must not cross or influence this scope.
            continue
        if normalized != requested_domain:
            continue
        if type(count) is not int or not 0 <= count <= 2**63 - 1:
            raise ValueError("invalid requested domain summary entry")
        requested_counts.append(count)
    if not requested_counts:
        raise XposedOrNotDomainError(
            "domain_not_verified",
            "Domain bu XposedOrNot anahtarının doğrulanmış kapsamındaki yanıtta bulunmadı.",
        )
    if len(requested_counts) != 1:
        raise ValueError("duplicate normalized requested domain")
    return requested_counts[0]


def _parse(content: bytes, domain: str) -> dict[str, list[str]]:
    try:
        raw = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        _bounded_shape(raw)
        if (not isinstance(raw, dict) or raw.get("status") != "success"
                or not isinstance(raw.get("metrics"), dict)):
            raise ValueError("invalid response envelope")
        metrics = raw["metrics"]
        _domain_summary(metrics, domain)
        details = metrics.get("Breaches_Details")
        if not isinstance(details, list) or len(details) > MAX_RECORDS:
            raise ValueError("invalid breach detail list")
        accounts: dict[str, set[str]] = {}
        for item in details:
            if not isinstance(item, dict):
                raise ValueError("invalid breach detail")
            row_domain = item.get("domain")
            if not isinstance(row_domain, str):
                raise ValueError("invalid breach detail fields")
            try:
                normalized_row_domain = normalize_domain(row_domain)
            except ValueError:
                # Unrelated provider rows do not enter the requested domain boundary.
                continue
            if normalized_row_domain != domain:
                continue
            email, breach = item.get("email"), item.get("breach")
            if not all(isinstance(value, str) for value in (email, breach)):
                raise ValueError("invalid breach detail fields")
            if "@" not in email:
                raise ValueError("invalid breach email")
            alias, email_domain = email.rsplit("@", 1)
            normalized_email_domain = normalize_domain(email_domain)
            if normalized_email_domain != normalized_row_domain:
                raise ValueError("breach email and domain disagree")
            mask_alias(alias, normalized_row_domain)
            if (not 1 <= len(breach) <= 200
                    or any(not character.isprintable() for character in breach)):
                raise ValueError("invalid breach name")
            accounts.setdefault(alias, set()).add(breach)
        return {alias: sorted(names, key=str.casefold) for alias, names in accounts.items()}
    except XposedOrNotDomainError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise XposedOrNotDomainError(
            "source_invalid",
            "XposedOrNot domain yanıtı geçersiz veya güvenli sınırları aşıyor.",
        ) from error


class XposedOrNotDomainExposureSource:
    def __init__(self, *, opener=None, now=None, monotonic=None):
        self.opener = opener or build_opener(ProxyHandler({}), _NoRedirects())
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic

    def fetch(self, domain: str, api_key: str) -> dict:
        domain = normalize_domain(domain)
        request = Request(
            BASE,
            data=b"",
            method="POST",
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Content-Length": "0",
                "User-Agent": f"XTI/{__version__} authorized-domain-exposure",
                "x-api-key": api_key,
            },
        )
        started = self.monotonic()
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                if response.getcode() != 200 or response.geturl() != BASE:
                    raise XposedOrNotDomainError(
                        "source_unexpected",
                        "XposedOrNot beklenen sabit HTTPS yanıtını vermedi.",
                    )
                if response.headers.get("Content-Encoding") not in (None, "identity"):
                    raise XposedOrNotDomainError(
                        "source_invalid", "XposedOrNot desteklenmeyen sıkıştırma kullandı."
                    )
                if "application/json" not in response.headers.get("Content-Type", "").casefold():
                    raise XposedOrNotDomainError(
                        "source_invalid", "XposedOrNot domain yanıtı JSON değil."
                    )
                declared = response.headers.get("Content-Length")
                if declared is not None and (
                    not declared.isascii() or not declared.isdecimal()
                    or int(declared) > MAX_RESPONSE
                ):
                    raise XposedOrNotDomainError(
                        "source_too_large", "XposedOrNot domain yanıtı 16 MiB sınırını aşıyor."
                    )
                chunks, size = [], 0
                while True:
                    if self.monotonic() - started > DEADLINE:
                        raise XposedOrNotDomainError(
                            "source_timeout", "XposedOrNot domain yanıtı okuma süresini aştı."
                        )
                    block = response.read(min(65_536, MAX_RESPONSE + 1 - size))
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_RESPONSE:
                        raise XposedOrNotDomainError(
                            "source_too_large",
                            "XposedOrNot domain yanıtı 16 MiB sınırını aşıyor.",
                        )
                    chunks.append(block)
                content = b"".join(chunks)
                if declared is not None and size != int(declared):
                    raise XposedOrNotDomainError(
                        "source_invalid", "XposedOrNot domain yanıtı eksik alındı."
                    )
                accounts = _parse(content, domain)
        except HTTPError as error:
            if error.code in (401, 403, 422):
                raise XposedOrNotDomainError(
                    "missing_or_invalid_key",
                    "XposedOrNot API anahtarı eksik/geçersiz veya doğrulanmış domain kapsamı yok.",
                ) from None
            if error.code == 429:
                raise XposedOrNotDomainError(
                    "rate_limited", "XposedOrNot istek sınırına ulaşıldı; daha sonra yeniden deneyin."
                ) from None
            raise XposedOrNotDomainError(
                "source_unavailable",
                f"XposedOrNot domain kaynağı HTTP {error.code} verdi; önceki kanıt korunuyor.",
            ) from None
        except XposedOrNotDomainError:
            raise
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError):
            raise XposedOrNotDomainError(
                "source_unavailable",
                "XposedOrNot domain kaynağına güvenli bağlantı tamamlanamadı; "
                "önceki kanıt korunuyor.",
            ) from None
        fetched = self.now()
        if fetched.tzinfo is None or fetched.utcoffset() is None:
            raise XposedOrNotDomainError(
                "clock_error", "XposedOrNot kaynak zamanı saat dilimli olmalı."
            )
        # Never persist a raw-response hash: the endpoint may include aliases
        # from other verified domains and a raw alias hash can become a guessing
        # oracle.  Identity-level change detection is performed later with the
        # organization's secret HMAC key; this receipt contains only safe scope
        # metadata.
        safe_receipt = {
            "provider": "xposedornot_domain",
            "domain": domain,
            "account_count": len(accounts),
            "breach_names": sorted(
                {name for names in accounts.values() for name in names}, key=str.casefold,
            ),
        }
        return {
            "provider": "xposedornot_domain",
            "domain": domain,
            "source_url": BASE,
            "fetched_at": fetched.astimezone(timezone.utc).isoformat(),
            "content_sha256": hashlib.sha256(json.dumps(
                safe_receipt, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
            ).encode("ascii")).hexdigest(),
            "accounts": accounts,
        }

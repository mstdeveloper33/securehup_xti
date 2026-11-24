"""Bounded public Lunar/Webz.io aggregate domain-exposure adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from http.client import HTTPException
import hashlib
import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from xti import __version__
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.content_monitoring import canonical
from xti.domain.darkweb_source_intake import lunar_record


BASE = "https://api.lunarcyber.com/domain-exposure"
SOURCE_REFERENCE = "https://docs.webz.io/docs/webz/dea-introduction"
MAX_RESPONSE = 4 * 1024 * 1024
TIMEOUT = 20
DEADLINE = 45


class LunarDomainExposureError(Exception):
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
    pending, nodes = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > 100_000 or depth > 20:
            raise ValueError("response shape exceeds bounds")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def _parse(content: bytes, requested_domain: str, fetched_at: str) -> dict:
    try:
        raw = json.loads(
            content.decode("utf-8"), object_pairs_hook=_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        _bounded_shape(raw)
        if not isinstance(raw, dict) or set(raw) != {
            "requestUuid", "domain", "periodFrom", "periodTo", "status", "report",
        }:
            raise ValueError("invalid response envelope")
        if (
            not isinstance(raw["requestUuid"], str)
            or not 1 <= len(raw["requestUuid"]) <= 200
            or any(not char.isprintable() for char in raw["requestUuid"])
        ):
            raise ValueError("invalid request identifier")
        if normalize_domain(raw["domain"]) != requested_domain:
            raise ValueError("response scope mismatch")
        status = raw["status"]
        if status == "NOT_AUTHORIZED":
            raise LunarDomainExposureError(
                "source_not_authorized", "Lunar bu domain için toplu rapor üretimine izin vermedi."
            )
        if status == "GENERATING_REPORT":
            if raw["report"] is not None:
                raise ValueError("pending response includes report")
            lunar_record(requested_domain, raw["periodFrom"], raw["periodTo"], {
                "total_events": 0, "infostealer_events": 0, "data_breach_events": 0,
                "employee_events": 0, "client_events": 0,
                "first_seen": None, "last_seen": None,
            })
            return {
                "provider": "lunar_domain", "mode": "snapshot", "status": "pending",
                "domain": requested_domain, "source_url": BASE,
                "source_reference": SOURCE_REFERENCE, "fetched_at": fetched_at,
                "content_sha256": hashlib.sha256(canonical({
                    "domain": requested_domain, "period_from": raw["periodFrom"],
                    "period_to": raw["periodTo"], "status": status,
                }).encode("ascii")).hexdigest(),
                "records": [],
            }
        if status != "REPORT_READY" or not isinstance(raw["report"], dict):
            raise ValueError("invalid report status")
        report = raw["report"]
        if set(report) < {"domain", "period", "summary"}:
            raise ValueError("report fields missing")
        if normalize_domain(report["domain"]) != requested_domain:
            raise ValueError("report scope mismatch")
        period = report["period"]
        if (
            not isinstance(period, dict)
            or set(period) != {"from", "to"}
            or period["from"] != raw["periodFrom"]
            or period["to"] != raw["periodTo"]
        ):
            raise ValueError("report period mismatch")
        record = lunar_record(
            requested_domain, raw["periodFrom"], raw["periodTo"], report["summary"],
        )
        safe = {
            "domain": requested_domain, "period_from": raw["periodFrom"],
            "period_to": raw["periodTo"], "status": status,
            "record_state_sha256": record["state_sha256"],
        }
        return {
            "provider": "lunar_domain", "mode": "snapshot", "status": "complete",
            "domain": requested_domain, "source_url": BASE,
            "source_reference": SOURCE_REFERENCE, "fetched_at": fetched_at,
            "content_sha256": hashlib.sha256(canonical(safe).encode("ascii")).hexdigest(),
            "records": [record],
        }
    except LunarDomainExposureError:
        raise
    except (ValidationError, ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise LunarDomainExposureError(
            "source_invalid", "Lunar domain yanıtı geçersiz veya güvenli sınırları aşıyor."
        ) from error


class LunarDomainExposureSource:
    def __init__(self, *, opener=None, now=None, monotonic=None):
        self.opener = opener or build_opener(ProxyHandler({}), _NoRedirects())
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic

    def fetch(self, domain: str) -> dict:
        domain = normalize_domain(domain)
        url = BASE + "?" + urlencode({"domain": domain})
        request = Request(url, method="GET", headers={
            "Accept": "application/json", "Accept-Encoding": "identity",
            "User-Agent": f"XTI/{__version__} aggregate-domain-exposure",
        })
        started = self.monotonic()
        try:
            with self.opener.open(request, timeout=TIMEOUT) as response:
                if response.getcode() != 200 or response.geturl() != url:
                    raise LunarDomainExposureError(
                        "source_unexpected", "Lunar beklenen sabit HTTPS yanıtını vermedi."
                    )
                if response.headers.get("Content-Encoding") not in (None, "identity"):
                    raise LunarDomainExposureError(
                        "source_invalid", "Lunar desteklenmeyen sıkıştırma kullandı."
                    )
                if "application/json" not in response.headers.get("Content-Type", "").casefold():
                    raise LunarDomainExposureError("source_invalid", "Lunar yanıtı JSON değil.")
                declared = response.headers.get("Content-Length")
                if declared is not None and (
                    not declared.isascii() or not declared.isdecimal()
                    or int(declared) > MAX_RESPONSE
                ):
                    raise LunarDomainExposureError(
                        "source_too_large", "Lunar yanıtı 4 MiB sınırını aşıyor."
                    )
                chunks, size = [], 0
                while True:
                    if self.monotonic() - started > DEADLINE:
                        raise LunarDomainExposureError(
                            "source_timeout", "Lunar yanıtı okuma süresini aştı."
                        )
                    block = response.read(min(65_536, MAX_RESPONSE + 1 - size))
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_RESPONSE:
                        raise LunarDomainExposureError(
                            "source_too_large", "Lunar yanıtı 4 MiB sınırını aşıyor."
                        )
                    chunks.append(block)
                if declared is not None and size != int(declared):
                    raise LunarDomainExposureError("source_invalid", "Lunar yanıtı eksik alındı.")
                content = b"".join(chunks)
        except HTTPError as error:
            if error.code == 429:
                raise LunarDomainExposureError(
                    "rate_limited", "Lunar kullanım sınırına ulaşıldı; daha sonra yeniden deneyin."
                ) from None
            if error.code in (401, 403):
                raise LunarDomainExposureError(
                    "source_not_authorized", "Lunar bu domain sorgusuna izin vermedi."
                ) from None
            raise LunarDomainExposureError(
                "source_unavailable", f"Lunar HTTP {error.code} verdi; önceki kanıt korunuyor."
            ) from None
        except LunarDomainExposureError:
            raise
        except (URLError, HTTPException, socket.timeout, TimeoutError, OSError):
            raise LunarDomainExposureError(
                "source_unavailable", "Lunar kaynağına güvenli bağlantı tamamlanamadı; önceki kanıt korunuyor."
            ) from None
        fetched = self.now()
        if fetched.tzinfo is None or fetched.utcoffset() is None:
            raise LunarDomainExposureError("clock_error", "Lunar kaynak zamanı saat dilimli olmalı.")
        return _parse(content, domain, fetched.astimezone(timezone.utc).isoformat())

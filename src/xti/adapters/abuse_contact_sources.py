"""Bounded passive RDAP, security.txt and optional WHOIS contact sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import selectors
import shutil
import subprocess
import time
from urllib.parse import quote, urljoin, urlsplit

from xti.adapters.public_profile_pages import (
    PageFailure, _decode_body, _request, resolve_public,
)
from xti.domain.abuse_contacts import (
    AbuseContactError, SourceOutcome, normalize_subject, parse_rdap,
    parse_security_txt, parse_whois, source_outcome, strict_json,
)


DNS_BOOTSTRAP = "https://data.iana.org/rdap/dns.json"
IPV4_BOOTSTRAP = "https://data.iana.org/rdap/ipv4.json"
IPV6_BOOTSTRAP = "https://data.iana.org/rdap/ipv6.json"


class ContactSourceFailure(Exception):
    def __init__(
        self, code: str, message: str, *, source_reference: str,
        request_count: int = 0, received_bytes: int = 0,
    ) -> None:
        super().__init__(message)
        self.code, self.message = code, message
        self.source_reference = source_reference
        self.request_count = request_count
        self.received_bytes = received_bytes


@dataclass(frozen=True, slots=True)
class BoundedResponse:
    url: str
    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    request_count: int
    received_bytes: int


class BoundedPublicHTTPS:
    """Pinned public HTTPS reads with no proxy or cross-host redirects."""

    def __init__(self, *, resolver=None, requester=None, monotonic=None) -> None:
        self.resolver = resolver or resolve_public
        self.requester = requester or _request
        self.monotonic = monotonic or time.monotonic

    @staticmethod
    def _url(value: str) -> tuple[str, str]:
        if (
            not isinstance(value, str) or not 1 <= len(value) <= 8192
            or not value.isascii() or any(ord(char) <= 32 or ord(char) == 127 for char in value)
            or "\\" in value
        ):
            raise ContactSourceFailure("invalid_url", "Kaynak HTTPS adresi geçersiz.", source_reference=str(value)[:2048])
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443)
                or parsed.username is not None or parsed.password is not None or parsed.fragment
            ):
                raise ValueError("scope")
        except ValueError as error:
            raise ContactSourceFailure("invalid_url", "Kaynak HTTPS adresi geçersiz.", source_reference=value[:2048]) from error
        path = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
        return parsed.hostname, path

    def get(
        self, url: str, *, timeout: float, max_bytes: int,
        same_host_redirects: bool = False,
    ) -> BoundedResponse:
        started = self.monotonic()
        deadline = started + timeout
        original_host, _path = self._url(url)
        current, visited, request_count, received = url, set(), 0, 0
        try:
            while True:
                host, path = self._url(current)
                if host != original_host:
                    raise ContactSourceFailure(
                        "redirect_scope_rejected", "Kaynak başka sunucuya yönlendirdi; izlenmedi.",
                        source_reference=current, request_count=request_count,
                        received_bytes=received,
                    )
                if current in visited or len(visited) >= 3:
                    raise ContactSourceFailure(
                        "redirect_limit", "Kaynak yönlendirme sınırını aştı.",
                        source_reference=current, request_count=request_count,
                        received_bytes=received,
                    )
                visited.add(current)
                remaining = deadline - self.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                address = self.resolver(host, min(5.0, remaining))
                remaining = deadline - self.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                request_count += 1
                status, headers, raw = self.requester(host, address, path, remaining)
                received += len(raw)
                if status in (301, 302, 303, 307, 308):
                    if not same_host_redirects:
                        raise ContactSourceFailure(
                            "redirect_rejected", "Kaynak yönlendirmesi bu kolektörde kapalı.",
                            source_reference=current, request_count=request_count,
                            received_bytes=received,
                        )
                    location = headers.get("location")
                    if not location or len(location) > 2048:
                        raise ContactSourceFailure(
                            "redirect_missing", "Kaynak yönlendirme adresi geçersiz.",
                            source_reference=current, request_count=request_count,
                            received_bytes=received,
                        )
                    current = urljoin(current, location)
                    continue
                body = _decode_body(raw, headers.get("content-encoding", "identity"))
                if len(body) > max_bytes:
                    raise ContactSourceFailure(
                        "response_too_large", "Kaynak yanıtı boyut sınırını aşıyor.",
                        source_reference=current, request_count=request_count,
                        received_bytes=received,
                    )
                return BoundedResponse(
                    url, current, status, headers, body, request_count, received,
                )
        except ContactSourceFailure:
            raise
        except (TimeoutError, subprocess.TimeoutExpired):
            raise ContactSourceFailure(
                "timeout", "Kaynak zamanında yanıt vermedi.", source_reference=current,
                request_count=request_count, received_bytes=received,
            ) from None
        except (OSError, ValueError, PageFailure, json.JSONDecodeError):
            raise ContactSourceFailure(
                "connection_or_parse_error", "Kaynak güvenli biçimde okunamadı.",
                source_reference=current, request_count=request_count,
                received_bytes=received,
            ) from None


def _rdap_base(bootstrap: object, subject_kind: str, subject_value: str) -> str:
    if not isinstance(bootstrap, dict):
        raise AbuseContactError("invalid_rdap_bootstrap", "IANA RDAP bootstrap nesnesi geçersiz.")
    services = bootstrap.get("services")
    if not isinstance(services, list) or not 1 <= len(services) <= 10_000:
        raise AbuseContactError("invalid_rdap_bootstrap", "IANA RDAP bootstrap servisleri geçersiz.")
    matches: list[tuple[int, str]] = []
    if subject_kind == "domain":
        key = subject_value.rsplit(".", 1)[-1]
        for row in services:
            if not isinstance(row, list) or len(row) != 2:
                raise AbuseContactError("invalid_rdap_bootstrap", "IANA RDAP bootstrap satırı geçersiz.")
            keys, urls = row
            if not isinstance(keys, list) or not isinstance(urls, list) or len(urls) > 20:
                raise AbuseContactError("invalid_rdap_bootstrap", "IANA RDAP bootstrap satırı geçersiz.")
            if any(isinstance(item, str) and item.lower() == key for item in keys):
                for url in urls:
                    matches.append((len(key), url))
    else:
        address = ipaddress.ip_address(subject_value)
        for row in services:
            if not isinstance(row, list) or len(row) != 2:
                raise AbuseContactError("invalid_rdap_bootstrap", "IANA RDAP bootstrap satırı geçersiz.")
            keys, urls = row
            if not isinstance(keys, list) or not isinstance(urls, list) or len(urls) > 20:
                raise AbuseContactError("invalid_rdap_bootstrap", "IANA RDAP bootstrap satırı geçersiz.")
            for key in keys:
                try:
                    network = ipaddress.ip_network(key)
                except (TypeError, ValueError):
                    continue
                if address.version == network.version and address in network:
                    for url in urls:
                        matches.append((network.prefixlen, url))
    for _specificity, base in sorted(matches, key=lambda item: item[0], reverse=True):
        if not isinstance(base, str) or not base.endswith("/"):
            continue
        try:
            parsed = urlsplit(base)
            if (
                parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)
                or parsed.query or parsed.fragment or not base.isascii()
            ):
                continue
        except ValueError:
            continue
        return base
    raise AbuseContactError("rdap_service_not_found", "IANA bootstrap hedef için RDAP servisi vermedi.")


class SystemWhois:
    MAX_BYTES = 1024 * 1024

    def __init__(self, executable: str | None = None, *, monotonic=None) -> None:
        self.executable = executable if executable is not None else shutil.which("whois")
        self.monotonic = monotonic or time.monotonic

    def run(self, subject: str, *, timeout: float) -> bytes:
        if not self.executable:
            raise ContactSourceFailure(
                "whois_not_installed", "WHOIS fallback aracı kurulu değil.",
                source_reference="whois://" + subject,
            )
        executable = str(Path(self.executable).resolve())
        process = subprocess.Popen(
            [executable, subject], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            start_new_session=True,
        )
        assert process.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = self.monotonic() + timeout
        parts: list[bytes] = []
        total = 0
        try:
            while True:
                remaining = deadline - self.monotonic()
                if remaining <= 0:
                    raise ContactSourceFailure(
                        "whois_timeout", "WHOIS aracı zaman sınırını aştı.",
                        source_reference="whois://" + subject,
                        request_count=1, received_bytes=total,
                    )
                events = selector.select(min(0.25, remaining))
                if events:
                    chunk = process.stdout.read1(min(65536, self.MAX_BYTES + 1 - total))
                    if chunk:
                        total += len(chunk)
                        if total > self.MAX_BYTES:
                            raise ContactSourceFailure(
                                "whois_response_too_large", "WHOIS yanıtı boyut sınırını aşıyor.",
                                source_reference="whois://" + subject,
                                request_count=1,
                                received_bytes=total,
                            )
                        parts.append(chunk)
                    elif process.poll() is not None:
                        break
                elif process.poll() is not None:
                    tail = process.stdout.read()
                    if tail:
                        total += len(tail)
                        if total > self.MAX_BYTES:
                            raise ContactSourceFailure(
                                "whois_response_too_large", "WHOIS yanıtı boyut sınırını aşıyor.",
                                source_reference="whois://" + subject,
                                request_count=1,
                                received_bytes=total,
                            )
                        parts.append(tail)
                    break
            if process.wait(timeout=max(0.001, deadline - self.monotonic())) != 0:
                raise ContactSourceFailure(
                    "whois_failed", "WHOIS aracı başarısız oldu.",
                    source_reference="whois://" + subject,
                    request_count=1, received_bytes=total,
                )
            return b"".join(parts)
        finally:
            selector.close()
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()


class AbuseContactSourceAdapter:
    def __init__(self, *, http=None, whois=None, clock=None, monotonic=None) -> None:
        self.monotonic = monotonic or time.monotonic
        self.http = http or BoundedPublicHTTPS(monotonic=self.monotonic)
        self.whois = whois or SystemWhois(monotonic=self.monotonic)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise AbuseContactError("invalid_clock", "Kaynak kanıt saati geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    def local_capabilities(self) -> dict:
        return {
            "whois_available": bool(getattr(self.whois, "executable", None)),
        }

    @staticmethod
    def _media(headers: dict[str, str], allowed: tuple[str, ...]) -> bool:
        media = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        return media in allowed

    def _failed(self, source_key: str, observed_at: str, started: float, error: Exception) -> SourceOutcome:
        if isinstance(error, ContactSourceFailure):
            code, message, reference = error.code, error.message, error.source_reference
            requests, received = error.request_count, error.received_bytes
        elif isinstance(error, AbuseContactError):
            code, message, reference = error.code, error.message, "urn:xti:source:" + source_key
            requests, received = 0, 0
        else:
            code, message, reference = "source_failed", "Kaynak güvenli biçimde işlenemedi.", "urn:xti:source:" + source_key
            requests, received = 0, 0
        return source_outcome(
            source_key, "failed", reference, observed_at,
            request_count=requests, received_bytes=received,
            elapsed_ms=max(0, int((self.monotonic() - started) * 1000)),
            error_code=code, error=message,
        )

    def _rdap(self, kind: str, subject: str, timeout: float) -> SourceOutcome:
        source_key = "domain_rdap" if kind == "domain" else "ip_rdap"
        observed_at, started = self._now(), self.monotonic()
        bootstrap_url = DNS_BOOTSTRAP if kind == "domain" else (
            IPV4_BOOTSTRAP if ipaddress.ip_address(subject).version == 4 else IPV6_BOOTSTRAP
        )
        total_requests = total_bytes = 0
        try:
            remaining = timeout - (self.monotonic() - started)
            if remaining <= 0:
                raise ContactSourceFailure(
                    "timeout", "RDAP kaynak süre bütçesi doldu.",
                    source_reference=bootstrap_url,
                )
            bootstrap = self.http.get(
                bootstrap_url, timeout=min(20.0, remaining),
                max_bytes=2 * 1024 * 1024,
            )
            total_requests += bootstrap.request_count; total_bytes += bootstrap.received_bytes
            if bootstrap.status != 200 or not self._media(bootstrap.headers, ("application/json",)):
                raise ContactSourceFailure(
                    "invalid_bootstrap_response", "IANA RDAP bootstrap yanıtı geçersiz.",
                    source_reference=bootstrap.final_url, request_count=total_requests,
                    received_bytes=total_bytes,
                )
            base = _rdap_base(strict_json(bootstrap.body), kind, subject)
            endpoint = urljoin(base, ("domain/" if kind == "domain" else "ip/") + quote(subject, safe=""))
            remaining = timeout - (self.monotonic() - started)
            if remaining <= 0:
                raise ContactSourceFailure(
                    "timeout", "RDAP kaynak süre bütçesi doldu.",
                    source_reference=endpoint, request_count=total_requests,
                    received_bytes=total_bytes,
                )
            response = self.http.get(
                endpoint, timeout=min(25.0, remaining), max_bytes=2 * 1024 * 1024,
            )
            total_requests += response.request_count; total_bytes += response.received_bytes
            if response.status == 404:
                return source_outcome(
                    source_key, "empty", response.final_url, observed_at, body=response.body,
                    request_count=total_requests, received_bytes=total_bytes,
                    elapsed_ms=int((self.monotonic() - started) * 1000),
                )
            if response.status != 200 or not self._media(
                response.headers, ("application/rdap+json", "application/json"),
            ):
                raise ContactSourceFailure(
                    "invalid_rdap_response", "RDAP yanıtı geçersiz.",
                    source_reference=response.final_url, request_count=total_requests,
                    received_bytes=total_bytes,
                )
            candidates = parse_rdap(
                subject_kind=kind, subject_value=subject, source_key=source_key,
                source_reference=response.final_url, body=response.body,
                observed_at=observed_at,
            )
            return source_outcome(
                source_key, "complete" if candidates else "empty", response.final_url,
                observed_at, body=response.body, candidates=candidates,
                request_count=total_requests, received_bytes=total_bytes,
                elapsed_ms=int((self.monotonic() - started) * 1000),
            )
        except Exception as error:
            failed = self._failed(source_key, observed_at, started, error)
            if total_requests or total_bytes:
                failed = SourceOutcome(
                    failed.source_key, failed.status, failed.source_reference,
                    failed.observed_at, failed.content_sha256, failed.candidates,
                    max(total_requests, failed.request_count), max(total_bytes, failed.received_bytes),
                    failed.elapsed_ms, failed.error_code, failed.error,
                )
            return failed

    def _security_txt(self, domain: str, timeout: float) -> SourceOutcome:
        observed_at, started = self._now(), self.monotonic()
        url = "https://" + domain + "/.well-known/security.txt"
        response = None
        try:
            response = self.http.get(
                url, timeout=min(20.0, timeout), max_bytes=32 * 1024,
                same_host_redirects=True,
            )
            if response.status == 404:
                return source_outcome(
                    "security_txt", "empty", response.final_url, observed_at,
                    body=response.body, request_count=response.request_count,
                    received_bytes=response.received_bytes,
                    elapsed_ms=int((self.monotonic() - started) * 1000),
                )
            if response.status != 200 or not self._media(
                response.headers, ("text/plain", "application/security.txt"),
            ):
                raise ContactSourceFailure(
                    "invalid_security_txt_response", "security.txt yanıtı geçersiz.",
                    source_reference=response.final_url, request_count=response.request_count,
                    received_bytes=response.received_bytes,
                )
            candidates = parse_security_txt(
                domain=domain, source_reference=response.final_url,
                body=response.body, observed_at=observed_at,
            )
            return source_outcome(
                "security_txt", "complete" if candidates else "empty",
                response.final_url, observed_at, body=response.body,
                candidates=candidates, request_count=response.request_count,
                received_bytes=response.received_bytes,
                elapsed_ms=int((self.monotonic() - started) * 1000),
            )
        except Exception as error:
            failed = self._failed("security_txt", observed_at, started, error)
            if response is None:
                return failed
            return source_outcome(
                "security_txt", "failed", response.final_url, observed_at,
                body=response.body, request_count=response.request_count,
                received_bytes=response.received_bytes,
                elapsed_ms=int((self.monotonic() - started) * 1000),
                error_code=failed.error_code, error=failed.error,
            )

    def _whois(self, kind: str, subject: str, *, enabled: bool, rdap_has_contact: bool, timeout: float) -> SourceOutcome:
        observed_at, started = self._now(), self.monotonic()
        reference = "whois://" + subject
        if not enabled:
            return source_outcome(
                "whois", "skipped", reference, observed_at,
                elapsed_ms=int((self.monotonic() - started) * 1000),
                error_code="disabled", error="WHOIS fallback bu izleme için kapalı.",
            )
        if rdap_has_contact:
            return source_outcome(
                "whois", "skipped", reference, observed_at,
                elapsed_ms=int((self.monotonic() - started) * 1000),
                error_code="fallback_not_needed", error="RDAP abuse iletişimi verdi; WHOIS çalıştırılmadı.",
            )
        try:
            body = self.whois.run(subject, timeout=min(15.0, timeout))
            candidates = parse_whois(
                subject_kind=kind, subject_value=subject, source_reference=reference,
                body=body, observed_at=observed_at,
            )
            return source_outcome(
                "whois", "complete" if candidates else "empty", reference, observed_at,
                body=body, candidates=candidates, request_count=1,
                received_bytes=len(body), elapsed_ms=int((self.monotonic() - started) * 1000),
            )
        except ContactSourceFailure as error:
            status = "requirement_missing" if error.code == "whois_not_installed" else "failed"
            return source_outcome(
                "whois", status, reference, observed_at,
                request_count=error.request_count, received_bytes=error.received_bytes,
                elapsed_ms=int((self.monotonic() - started) * 1000),
                error_code=error.code, error=error.message,
            )
        except Exception as error:
            return self._failed("whois", observed_at, started, error)

    def collect(
        self, subject_kind: str, subject_value: str, *, include_whois: bool,
        timeout_seconds: int,
    ) -> tuple[SourceOutcome, ...]:
        kind, subject = normalize_subject(subject_kind, subject_value)
        if type(include_whois) is not bool:
            raise AbuseContactError("invalid_options", "WHOIS seçimi true/false olmalı.")
        if type(timeout_seconds) is not int or not 5 <= timeout_seconds <= 120:
            raise AbuseContactError("invalid_options", "Kaynak süre bütçesi 5–120 saniye olmalı.")
        rdap = self._rdap(kind, subject, timeout_seconds)
        outcomes: list[SourceOutcome] = [rdap]
        if kind == "domain":
            outcomes.append(self._security_txt(subject, timeout_seconds))
        else:
            outcomes.append(source_outcome(
                "security_txt", "skipped", "urn:xti:not-applicable:security-txt",
                self._now(), error_code="not_applicable",
                error="security.txt yalnız domain hedefinde kullanılır.",
            ))
        outcomes.append(self._whois(
            kind, subject, enabled=include_whois,
            rdap_has_contact=bool(rdap.candidates), timeout=timeout_seconds,
        ))
        return tuple(outcomes)

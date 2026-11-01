"""Explicit, bounded present-state checks, separate from passive discovery.

Only Google DoH GET requests and one verified HTTPS HEAD / request are made.
Every connection uses a numeric address; target DNS is never resolved again by
the operating system. No proxy, redirect, plaintext fallback or body fetch is
available for the target.
"""

from __future__ import annotations

from datetime import datetime, timezone
from http.client import HTTPException, HTTPResponse
import hashlib
import ipaddress
import json
import re
import socket
import ssl
import time
from typing import Callable
from urllib.parse import urlencode

from xti import __version__
from xti.domain.assets import ValidationError
from xti.domain.cname import (
    CNAME_POLICY_VERSION,
    CnameDnsResult,
    CnameHop,
    validate_cname_dns_result,
)
from xti.domain.enrichment import CertificateEvidence, ProbeResult
from xti.domain.mail import MailDnsResult, validate_mail_dns_result
from xti.domain.matching import normalize_for_matching
from xti.adapters.unicode_security import unicode_security_profile


POLICY_VERSION = "https-head-public-v2"
DNS_HOST = "dns.google"
DNS_ADDRESS = "8.8.8.8"
CHECK_TIMEOUT = 25.0
REQUEST_TIMEOUT = 8.0
MAX_HEADER_BYTES = 16 * 1024
MAX_DNS_BYTES = 64 * 1024
MAX_WIRE_BYTES = MAX_HEADER_BYTES + MAX_DNS_BYTES + 16 * 1024
MAX_DNS_RECORDS = 32
MAX_ADDRESSES = 16
MAX_CERTIFICATE_BYTES = 64 * 1024
MAX_CERTIFICATE_NAMES = 128
MAIL_DNS_POLICY_VERSION = "mail-dns-google-v1"

# Explicit ranges make the safety boundary conservative across Python 3.11+
# classification changes. IPv6 is restricted to native global unicast; no
# mapped, translated, Teredo or 6to4 destination can reach an embedded local IP.
_V4_SPECIAL = tuple(ipaddress.ip_network(value) for value in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
    "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24",
    "192.88.99.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24",
    "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
))
_V6_GLOBAL = ipaddress.ip_network("2000::/3")
_V6_SPECIAL = tuple(ipaddress.ip_network(value) for value in (
    "2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20",
))


class _ProbeFailure(Exception):
    """A bounded, safe explanation, without remote text or exception contents."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if "%" in value or not address.is_global or any((
        address.is_private, address.is_loopback, address.is_link_local,
        address.is_multicast, address.is_reserved, address.is_unspecified,
    )):
        return False
    if address.version == 4:
        return not any(address in network for network in _V4_SPECIAL)
    return address in _V6_GLOBAL and not any(address in network for network in _V6_SPECIAL)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _json_constant(value):
    raise ValueError("Non-finite JSON number")


def _dns_name(value) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise _ProbeFailure("DNS yanıtındaki alan adı geçerli değil.")
    try:
        normalized = normalize_for_matching(value)
        unicode_security_profile().to_unicode(normalized)
        return normalized
    except ValidationError as exc:
        raise _ProbeFailure("DNS yanıtındaki alan adı desteklenen biçimde değil.") from exc


def _mail_dns_name(value) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise _ProbeFailure("DNS yanıtındaki alan adı geçerli değil.")
    lowered = value.lower().removesuffix(".")
    if lowered.startswith("_dmarc."):
        return "_dmarc." + _dns_name(lowered[len("_dmarc."):])
    return _dns_name(value)


def _dns_payload(
    content: bytes, domain: str, record_type: int,
) -> tuple[int, list[dict]]:
    """Validate one bounded Google DNS JSON envelope and echoed question."""
    if len(content) > MAX_DNS_BYTES:
        raise _ProbeFailure("DNS yanıtı 64 KiB sınırını aştı.")
    try:
        payload = json.loads(content.decode("utf-8"), object_pairs_hook=_json_object,
                             parse_constant=_json_constant)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise _ProbeFailure("DNS sağlayıcısı geçerli JSON göndermedi.") from exc
    if not isinstance(payload, dict):
        raise _ProbeFailure("DNS yanıtı beklenen biçimde değil.")
    status = payload.get("Status")
    if type(status) is not int or status not in (0, 3):
        raise _ProbeFailure("DNS sorgusu başarıyla tamamlanamadı.")
    if payload.get("TC") is not False:
        raise _ProbeFailure("DNS yanıtı eksik veya kesilmiş olabilir.")
    if payload.get("CD", False) is not False:
        raise _ProbeFailure("DNS sağlayıcısı doğrulamayı devre dışı bıraktı.")
    questions = payload.get("Question")
    if not isinstance(questions, list) or len(questions) != 1 or not isinstance(questions[0], dict):
        raise _ProbeFailure("DNS yanıtındaki sorgu bilgisi eksik.")
    question = questions[0]
    if (_mail_dns_name(question.get("name")) != domain
            or type(question.get("type")) is not int or question["type"] != record_type):
        raise _ProbeFailure("DNS yanıtı istenen sorguyla eşleşmiyor.")
    rows = payload.get("Answer", [])
    if not isinstance(rows, list) or len(rows) > MAX_DNS_RECORDS:
        raise _ProbeFailure("DNS yanıtındaki kayıt sayısı sınırı aşıldı.")
    return status, rows


def parse_dns_response(content: bytes, domain: str, record_type: int) -> tuple[int, tuple[str, ...]]:
    """Validate the echoed question and follow only its finite CNAME chain."""
    status, rows = _dns_payload(content, domain, record_type)
    aliases: dict[str, str] = {}
    addresses: dict[str, set[str]] = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("type")) is not int:
            raise _ProbeFailure("DNS yanıtında geçersiz kayıt var.")
        kind = row["type"]
        # DNSSEC records may be included by the provider even when do=false.
        if kind in (46, 47, 48, 50, 51):
            continue
        name = _dns_name(row.get("name"))
        if kind == 5:
            alias = _dns_name(row.get("data"))
            if name in aliases and aliases[name] != alias:
                raise _ProbeFailure("DNS yanıtında çelişen takma ad var.")
            aliases[name] = alias
        elif kind == record_type:
            value = row.get("data")
            try:
                if not isinstance(value, str) or "%" in value:
                    raise ValueError("Invalid IP")
                address = ipaddress.ip_address(value)
                if address.version != (4 if record_type == 1 else 6):
                    raise ValueError("Wrong address family")
            except ValueError as exc:
                raise _ProbeFailure("DNS yanıtında geçersiz IP adresi var.") from exc
            addresses.setdefault(name, set()).add(str(address))
        else:
            raise _ProbeFailure("DNS yanıtında beklenmeyen kayıt türü var.")
    chain: set[str] = set()
    current = domain
    while current in aliases:
        if current in chain or len(chain) >= 8 or current in addresses:
            raise _ProbeFailure("DNS takma ad zinciri geçersiz veya çok uzun.")
        chain.add(current)
        current = aliases[current]
    if current in chain:
        raise _ProbeFailure("DNS takma ad zincirinde döngü var.")
    chain.add(current)
    if set(aliases) - chain or set(addresses) - {current}:
        raise _ProbeFailure("DNS yanıtında sorguyla ilgisiz adres var.")
    found = tuple(sorted(addresses.get(current, ())))
    if status == 3 and found:
        raise _ProbeFailure("DNS yanıtında çelişen adres bilgisi var.")
    return status, found


def parse_cname_dns_response(
    content: bytes, domain: str,
) -> tuple[int, tuple[CnameHop, ...]]:
    """Validate one finite CNAME chain and reject unrelated answer records."""
    status, rows = _dns_payload(content, domain, 5)
    aliases: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("type")) is not int:
            raise _ProbeFailure("CNAME yanıtında geçersiz kayıt var.")
        kind = row["type"]
        if kind in (46, 47, 48, 50, 51):
            continue
        if kind != 5:
            raise _ProbeFailure("CNAME yanıtında beklenmeyen kayıt türü var.")
        owner = _dns_name(row.get("name"))
        target = _dns_name(row.get("data"))
        if owner in aliases and aliases[owner] != target:
            raise _ProbeFailure("CNAME yanıtında çelişen hedefler var.")
        aliases[owner] = target
    if status == 3:
        if aliases:
            raise _ProbeFailure("CNAME NXDOMAIN yanıtı kayıtlarla çelişiyor.")
        return status, ()

    chain: list[CnameHop] = []
    current = domain
    seen = {domain}
    while current in aliases:
        if len(chain) >= 8:
            raise _ProbeFailure("CNAME zinciri sekiz adım sınırını aştı.")
        target = aliases[current]
        if target in seen:
            raise _ProbeFailure("CNAME zincirinde döngü var.")
        chain.append(CnameHop(current, target))
        seen.add(target)
        current = target
    if set(aliases) != {hop.owner for hop in chain}:
        raise _ProbeFailure("CNAME yanıtında sorguyla ilgisiz kayıt var.")
    return status, tuple(chain)


def _txt_data(value: object) -> str:
    """Decode the quoted DNS presentation form used by the JSON endpoint."""
    if not isinstance(value, str) or not 2 <= len(value) <= 8192:
        raise _ProbeFailure("DNS TXT kaydı beklenen biçimde değil.")
    parts: list[str] = []
    index = 0
    while index < len(value):
        while index < len(value) and value[index] == " ":
            index += 1
        if index >= len(value):
            break
        if value[index] != '"':
            raise _ProbeFailure("DNS TXT kaydı tırnaklı sunum biçiminde değil.")
        index += 1
        part: list[str] = []
        while index < len(value) and value[index] != '"':
            character = value[index]
            if character == "\\":
                index += 1
                if index >= len(value):
                    raise _ProbeFailure("DNS TXT kaydındaki kaçış eksik.")
                if (
                    index + 2 < len(value) and value[index:index + 3].isdigit()
                ):
                    code = int(value[index:index + 3])
                    if code > 255:
                        raise _ProbeFailure("DNS TXT kaydındaki kaçış geçersiz.")
                    character = chr(code)
                    index += 3
                else:
                    character = value[index]
                    index += 1
            else:
                index += 1
            part.append(character)
        if index >= len(value) or value[index] != '"':
            raise _ProbeFailure("DNS TXT kaydının tırnağı tamamlanmadı.")
        index += 1
        parts.append("".join(part))
        if index < len(value) and value[index] != " ":
            raise _ProbeFailure("DNS TXT parçaları beklenen biçimde ayrılmadı.")
    decoded = "".join(parts)
    if not 1 <= len(decoded) <= 2048 or not decoded.isprintable():
        raise _ProbeFailure("DNS TXT kaydı desteklenen metin sınırını aştı.")
    return decoded


def _mx_data(value: object) -> str:
    if not isinstance(value, str) or len(value) > 512:
        raise _ProbeFailure("DNS MX kaydı beklenen biçimde değil.")
    parts = value.split()
    if (
        len(parts) != 2 or not parts[0].isascii() or not parts[0].isdigit()
        or not 0 <= int(parts[0]) <= 65535
    ):
        raise _ProbeFailure("DNS MX kaydı beklenen biçimde değil.")
    preference = int(parts[0])
    exchange = "." if parts[1] == "." else _dns_name(parts[1])
    return f"{preference} {exchange}"


def parse_mail_dns_response(
    content: bytes, domain: str, record_type: int,
) -> tuple[int, tuple[str, ...]]:
    """Parse a strict MX or TXT answer, including a finite CNAME chain."""
    if record_type not in (15, 16):
        raise _ProbeFailure("Desteklenmeyen e-posta DNS kayıt türü istendi.")
    status, rows = _dns_payload(content, domain, record_type)
    aliases: dict[str, str] = {}
    records: dict[str, set[str]] = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("type")) is not int:
            raise _ProbeFailure("DNS yanıtında geçersiz kayıt var.")
        kind = row["type"]
        if kind in (46, 47, 48, 50, 51):
            continue
        name = _mail_dns_name(row.get("name"))
        if kind == 5:
            alias = _mail_dns_name(row.get("data"))
            if name in aliases and aliases[name] != alias:
                raise _ProbeFailure("DNS yanıtında çelişen takma ad var.")
            aliases[name] = alias
        elif kind == record_type:
            parsed = _mx_data(row.get("data")) if kind == 15 else _txt_data(row.get("data"))
            records.setdefault(name, set()).add(parsed)
        else:
            raise _ProbeFailure("DNS yanıtında beklenmeyen kayıt türü var.")
    chain: set[str] = set()
    current = domain
    while current in aliases:
        if current in chain or len(chain) >= 8 or current in records:
            raise _ProbeFailure("DNS takma ad zinciri geçersiz veya çok uzun.")
        chain.add(current)
        current = aliases[current]
    if current in chain:
        raise _ProbeFailure("DNS takma ad zincirinde döngü var.")
    chain.add(current)
    if set(aliases) - chain or set(records) - {current}:
        raise _ProbeFailure("DNS yanıtında sorguyla ilgisiz kayıt var.")
    found = records.get(current, set())
    if record_type == 15:
        ordered = tuple(sorted(found, key=lambda item: (int(item.split(" ", 1)[0]), item)))
        if any(item == "0 ." for item in ordered) and ordered != ("0 .",):
            raise _ProbeFailure("Null MX başka MX kayıtlarıyla birlikte kullanılamaz.")
    else:
        ordered = tuple(sorted(found))
    if status == 3 and ordered:
        raise _ProbeFailure("DNS yanıtında çelişen kayıt bilgisi var.")
    return status, ordered


def _certificate_text(value, *, maximum: int = 2048) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value) <= maximum
        or not value.isprintable()
    ):
        raise _ProbeFailure("TLS sertifika kimliği beklenen biçimde değil.")
    return value


def _name_attributes(value) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 64:
        raise _ProbeFailure("TLS sertifika taraf bilgisi beklenen biçimde değil.")
    attributes = []
    for rdn in value:
        if not isinstance(rdn, (list, tuple)) or not 1 <= len(rdn) <= 16:
            raise _ProbeFailure("TLS sertifika taraf bilgisi beklenen biçimde değil.")
        for item in rdn:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise _ProbeFailure("TLS sertifika taraf bilgisi beklenen biçimde değil.")
            key = _certificate_text(item[0], maximum=128)
            text = _certificate_text(item[1])
            attributes.append((key, text))
            if len(attributes) > 128:
                raise _ProbeFailure("TLS sertifika taraf bilgisi sınırı aştı.")
    return tuple(attributes)


def _preferred_name(
    attributes: tuple[tuple[str, str], ...], priorities: tuple[str, ...],
) -> str:
    for preferred in priorities:
        for key, value in attributes:
            if key == preferred:
                return value
    return attributes[0][1]


def _certificate_time(value) -> str:
    value = _certificate_text(value, maximum=64)
    try:
        seconds = ssl.cert_time_to_seconds(value)
        return datetime.fromtimestamp(seconds, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError) as exc:
        raise _ProbeFailure("TLS sertifika geçerlilik zamanı okunamadı.") from exc


def _certificate_dns_name(value: str) -> str:
    value = _certificate_text(value, maximum=255).lower().removesuffix(".")
    wildcard = value.startswith("*.")
    candidate = value[2:] if wildcard else value
    try:
        normalized = normalize_for_matching(candidate)
        unicode_security_profile().to_unicode(normalized)
    except ValidationError as exc:
        raise _ProbeFailure("TLS sertifikasının DNS adı desteklenen biçimde değil.") from exc
    return "*." + normalized if wildcard else normalized


def certificate_evidence(sock) -> CertificateEvidence:
    """Extract bounded identity from the already verified peer certificate."""
    try:
        binary = sock.getpeercert(binary_form=True)
        details = sock.getpeercert()
    except (AttributeError, OSError, ssl.SSLError, ValueError) as exc:
        raise _ProbeFailure("Doğrulanmış TLS sertifika kanıtı okunamadı.") from exc
    if (
        not isinstance(binary, bytes) or not 1 <= len(binary) <= MAX_CERTIFICATE_BYTES
        or not isinstance(details, dict)
    ):
        raise _ProbeFailure("Doğrulanmış TLS sertifika kanıtı beklenen biçimde değil.")
    issuer_attributes = _name_attributes(details.get("issuer"))
    subject_attributes = _name_attributes(details.get("subject"))
    issuer = _preferred_name(issuer_attributes, ("organizationName", "commonName"))
    subject = _preferred_name(subject_attributes, ("commonName", "organizationName"))
    serial = _certificate_text(details.get("serialNumber"), maximum=128).lower()
    if any(character not in "0123456789abcdef" for character in serial):
        raise _ProbeFailure("TLS sertifika seri numarası beklenen biçimde değil.")
    not_before = _certificate_time(details.get("notBefore"))
    not_after = _certificate_time(details.get("notAfter"))
    if datetime.fromisoformat(not_before) >= datetime.fromisoformat(not_after):
        raise _ProbeFailure("TLS sertifika geçerlilik aralığı tutarsız.")
    alt_names = details.get("subjectAltName", ())
    if not isinstance(alt_names, (list, tuple)) or len(alt_names) > 256:
        raise _ProbeFailure("TLS sertifika ad kapsamı beklenen sınırı aştı.")
    dns_names = []
    for item in alt_names:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise _ProbeFailure("TLS sertifika ad kapsamı beklenen biçimde değil.")
        kind = _certificate_text(item[0], maximum=32)
        value = _certificate_text(item[1], maximum=255)
        if kind == "DNS":
            dns_names.append(_certificate_dns_name(value))
    if not dns_names:
        dns_names.append(_certificate_dns_name(subject))
    dns_names = sorted(set(dns_names))
    if not 1 <= len(dns_names) <= MAX_CERTIFICATE_NAMES:
        raise _ProbeFailure("TLS sertifika DNS adı sayısı sınırı aştı.")
    return CertificateEvidence(
        sha256=hashlib.sha256(binary).hexdigest(), serial_number=serial,
        not_before=not_before, not_after=not_after, issuer=issuer, subject=subject,
        dns_names=tuple(dns_names),
    )


class _DeadlineReader:
    """Unbuffered HTTPResponse input: no target body prefetch and total deadline.

    Header bytes are read individually deliberately: a buffered makefile could
    consume a malicious HEAD response body before headers have been checked.
    DNS bodies use bounded blocks after begin() has parsed the headers.
    """

    def __init__(self, sock, deadline: float, monotonic: Callable[[], float]):
        self.sock = sock
        self.deadline = deadline
        self.monotonic = monotonic
        self.headers = True
        self.received = 0
        self.closed = False

    def _receive(self, size: int) -> bytes:
        if self.closed:
            return b""
        remaining = self.deadline - self.monotonic()
        if remaining <= 0:
            raise TimeoutError("Total response deadline")
        limit = MAX_HEADER_BYTES if self.headers else MAX_WIRE_BYTES
        available = limit - self.received
        if available <= 0:
            raise _ProbeFailure("HTTP yanıtı izin verilen boyut sınırını aştı.")
        self.sock.settimeout(remaining)
        data = self.sock.recv(min(size, available))
        self.received += len(data)
        return data

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            raise _ProbeFailure("Sınırsız yanıt okuması reddedildi.")
        parts = []
        remaining = size
        while remaining:
            part = self._receive(min(remaining, 4096))
            if not part:
                break
            parts.append(part)
            remaining -= len(part)
        return b"".join(parts)

    def readline(self, limit: int = -1) -> bytes:
        line = bytearray()
        while limit < 0 or len(line) < limit:
            part = self._receive(1)
            if not part:
                # Header/chunk/trailer lines require a terminating newline.
                # HTTPResponse otherwise accepts EOF in place of the empty
                # line terminating trailers, masking a truncated DNS response.
                raise HTTPException("Incomplete header or framing line")
            line.extend(part)
            if part == b"\n":
                break
        return bytes(line)

    def close(self):
        self.closed = True

    def flush(self):
        pass


class _ResponseSocket:
    def __init__(self, reader: _DeadlineReader):
        self.reader = reader

    def makefile(self, mode: str):
        if mode != "rb":
            raise ValueError("Read-only response")
        return self.reader


class _StrictHTTPResponse(HTTPResponse):
    def _read_status(self):
        # The stdlib accepts int("+200") and int("0200"). Do not turn these
        # malformed wire statuses into apparently valid present-state evidence.
        line = self.fp.readline(MAX_HEADER_BYTES + 1)
        match = re.fullmatch(
            rb"(HTTP/1\.[01]) ([0-9]{3})(?: ([\t\x20-\x7e\x80-\xff]*))?\r\n", line
        )
        if match is None:
            raise HTTPException("Invalid HTTP status line")
        return (match[1].decode("ascii"), int(match[2]),
                (match[3] or b"").decode("iso-8859-1"))


class GoogleDnsJsonClient:
    def __init__(self, *, socket_factory=None, context_factory=None,
                 monotonic: Callable[[], float] = time.monotonic,
                 now: Callable[[], str] = _utc_now):
        self.socket_factory = socket_factory or socket.socket
        self.context_factory = context_factory or ssl.create_default_context
        self.monotonic = monotonic
        self.now = now

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise TimeoutError("Total check deadline")
        return remaining

    def _connect(self, address: str, deadline: float):
        parsed = ipaddress.ip_address(address)
        family = socket.AF_INET if parsed.version == 4 else socket.AF_INET6
        sock = self.socket_factory(family, socket.SOCK_STREAM)
        try:
            sock.settimeout(self._remaining(deadline))
            # No getaddrinfo or hostname connection: the validated IP is pinned.
            sock.connect((str(parsed), 443))
            return sock
        except BaseException:
            sock.close()
            raise

    def _headers(self, sock, host: str, path: str, method: str, deadline: float):
        request = (f"{method} {path} HTTP/1.1\r\nHost: {host}\r\n"
                   f"User-Agent: XTI/{__version__}\r\nAccept: application/json\r\n"
                   "Accept-Encoding: identity\r\nConnection: close\r\n\r\n")
        sock.settimeout(self._remaining(deadline))
        sock.sendall(request.encode("ascii"))
        reader = _DeadlineReader(sock, deadline, self.monotonic)
        response = _StrictHTTPResponse(_ResponseSocket(reader), method=method)
        try:
            response.begin()
            if not 200 <= response.status <= 599 or response.headers.defects:
                raise HTTPException("Invalid final response")
            reader.headers = False
            return response
        except BaseException:
            response.close()
            raise

    def _dns_content(self, context, domain: str, record_type: int, overall_deadline: float):
        deadline = min(overall_deadline, self.monotonic() + REQUEST_TIMEOUT)
        raw = self._connect(DNS_ADDRESS, deadline)
        tls = None
        response = None
        try:
            raw.settimeout(self._remaining(deadline))
            tls = context.wrap_socket(raw, server_hostname=DNS_HOST)
            path = "/resolve?" + urlencode({"name": domain, "type": record_type,
                                             "cd": "false", "do": "false",
                                             "edns_client_subnet": "0.0.0.0/0"})
            response = self._headers(tls, DNS_HOST, path, "GET", deadline)
            if response.status != 200:
                raise _ProbeFailure(f"DNS sağlayıcısı HTTP {response.status} yanıtı verdi.")
            encoding = response.getheader("Content-Encoding", "identity").strip().lower()
            if encoding != "identity":
                raise _ProbeFailure("Sıkıştırılmış DNS yanıtı kabul edilmedi.")
            media_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if media_type not in ("application/json", "application/dns-json"):
                raise _ProbeFailure("DNS sağlayıcısı beklenen JSON biçimini göndermedi.")
            lengths = response.headers.get_all("Content-Length", [])
            transfers = response.headers.get_all("Transfer-Encoding", [])
            if (len(lengths) > 1 or len(transfers) > 1 or (lengths and transfers)
                    or (transfers and transfers[0].lower().strip() != "chunked")):
                raise _ProbeFailure("DNS HTTP yanıtının uzunluk bilgisi belirsiz.")
            expected = None
            if lengths:
                if not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 10:
                    raise _ProbeFailure("DNS yanıtının uzunluk bilgisi geçersiz.")
                expected = int(lengths[0])
                if expected > MAX_DNS_BYTES:
                    raise _ProbeFailure("DNS yanıtı 64 KiB sınırını aştı.")
            content = response.read(MAX_DNS_BYTES + 1)
            if expected is not None and len(content) != expected:
                raise _ProbeFailure("DNS yanıtı tamamlanmadan bağlantı kapandı.")
            return content
        finally:
            if response is not None:
                response.close()
            if tls is not None:
                tls.close()
            raw.close()

    def _resolve(self, context, domain: str, record_type: int, overall_deadline: float):
        return parse_dns_response(
            self._dns_content(context, domain, record_type, overall_deadline),
            domain, record_type,
        )


class HttpsTargetProbe(GoogleDnsJsonClient):

    def check(self, domain: str) -> ProbeResult:
        domain = normalize_for_matching(domain)
        unicode_security_profile().to_unicode(domain)
        started_at = self.now()
        overall_deadline = self.monotonic() + CHECK_TIMEOUT
        addresses: tuple[str, ...] = ()
        connected_address = None
        dns_status = "failed"
        tls_status = "not_checked"
        http_status = "not_checked"
        http_status_code = None
        certificate = None
        errors: list[str] = []
        notes: list[str] = [
            "DNS: Google Public DNS; A ve AAAA birlikte kontrol edilir.",
            "Yalnız HTTPS 443 üzerinde HEAD /; yönlendirme izlenmez, sayfa içeriği alınmaz.",
        ]

        def result():
            return ProbeResult(
                domain=domain, started_at=started_at, finished_at=self.now(),
                policy_version=POLICY_VERSION, dns_status=dns_status, addresses=addresses,
                tls_status=tls_status, http_status=http_status, http_status_code=http_status_code,
                connected_address=connected_address, errors=tuple(errors), notes=tuple(notes),
                certificate=certificate,
            )

        try:
            context = self.context_factory()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                raise _ProbeFailure("TLS sertifika doğrulaması devre dışı bırakılamaz.")
            context.set_alpn_protocols(["http/1.1"])
            answer4 = self._resolve(context, domain, 1, overall_deadline)
            answer6 = self._resolve(context, domain, 28, overall_deadline)
            if answer4[0] != answer6[0]:
                raise _ProbeFailure("A ve AAAA sorguları çelişen DNS durumu bildirdi.")
            addresses = tuple(sorted(set(answer4[1] + answer6[1]),
                                     key=lambda value: (ipaddress.ip_address(value).version,
                                                        int(ipaddress.ip_address(value)))))
            if len(addresses) > MAX_ADDRESSES:
                raise _ProbeFailure("DNS yanıtı 16 adres sınırını aştı.")
            if answer4[0] == 3:
                dns_status = "nxdomain"
                notes.append("DNS sağlayıcısı bu sorguda alan adını bulamadı; tehdit kararı değildir.")
                return result()
            if not addresses:
                dns_status = "no_address"
                notes.append("Bu sorguda A/AAAA adresi bulunamadı; zararsızlık sonucu çıkarılamaz.")
                return result()
            if not all(is_public_address(address) for address in addresses):
                dns_status = "blocked"
                errors.append("Özel, yerel veya özel kullanım IP adresi görüldü; hedef bağlantısı engellendi.")
                return result()
            dns_status = "resolved"
        except _ProbeFailure as exc:
            errors.append(str(exc))
            return result()
        except (OSError, HTTPException, ValueError):
            errors.append("DNS sağlayıcısına güvenli ve süre sınırı içinde erişilemedi veya yanıtı tamamlanamadı.")
            return result()

        # One deterministic public address only; this is a point observation,
        # never an availability claim about every address behind a domain.
        address = addresses[0]
        notes.append("Yalnız listelenen ilk genel IP kontrol edildi; diğer IP'lerin erişimi ölçülmedi.")
        deadline = min(overall_deadline, self.monotonic() + REQUEST_TIMEOUT)
        raw = tls = response = None
        try:
            tls_status = "failed"
            raw = self._connect(address, deadline)
            connected_address = address
            raw.settimeout(self._remaining(deadline))
            tls = context.wrap_socket(raw, server_hostname=domain)
            certificate = certificate_evidence(tls)
            tls_status = "valid"
            http_status = "failed"
            response = self._headers(tls, domain, "/", "HEAD", deadline)
            http_status_code = response.status
            http_status = "responded"
            if 300 <= response.status < 400:
                notes.append("Yönlendirme yanıtı alındı; yönlendirilen adrese bağlanılmadı.")
            if response.status in (405, 501):
                notes.append("Sunucu HEAD isteğini desteklemiyor olabilir; GET isteğine geçilmedi.")
            notes.append("Geçerli TLS ve HTTP yanıtı sitenin güvenilir veya kötü amaçlı olduğunu kanıtlamaz.")
        except ssl.SSLCertVerificationError:
            errors.append("Hedefin TLS sertifikası doğrulanamadı; doğrulamasız bağlantı yapılmadı.")
        except _ProbeFailure as exc:
            errors.append(str(exc))
        except (OSError, HTTPException, ValueError):
            errors.append("Hedefe bağlantı veya yanıt süre sınırı içinde tamamlanamadı; mevcut durum belirsiz.")
        finally:
            if response is not None:
                response.close()
            if tls is not None:
                tls.close()
            if raw is not None:
                raw.close()
        return result()


class GoogleCnameDnsProbe(GoogleDnsJsonClient):
    """CNAME and terminal target evidence without connecting to the target."""

    def check(self, domain: str) -> CnameDnsResult:
        domain = normalize_for_matching(domain)
        unicode_security_profile().to_unicode(domain)
        started_at = self.now()
        overall_deadline = self.monotonic() + CHECK_TIMEOUT
        alias_status = "failed"
        chain: tuple[CnameHop, ...] = ()
        target = None
        target_status = "not_applicable"
        addresses: tuple[str, ...] = ()
        errors: list[str] = []
        notes = (
            "DNS sağlayıcısı: Google Public DNS; yalnız CNAME, A ve AAAA sorguları yapılır.",
            "Hedef siteye bağlanılmaz; sağlayıcı hesabı veya kaynak sahiplenme işlemi yapılmaz.",
            "NXDOMAIN hedefin DNS'te görülmediğini söyler; alınabilir olduğunu kanıtlamaz.",
        )

        def result() -> CnameDnsResult:
            return validate_cname_dns_result(CnameDnsResult(
                domain=domain, started_at=started_at, finished_at=self.now(),
                policy_version=CNAME_POLICY_VERSION,
                alias_status=alias_status, chain=chain, target=target,
                target_status=target_status, addresses=addresses,
                errors=tuple(errors), notes=notes,
            ))

        try:
            context = self.context_factory()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                raise _ProbeFailure("TLS sertifika doğrulaması devre dışı bırakılamaz.")
            context.set_alpn_protocols(["http/1.1"])
            content = self._dns_content(context, domain, 5, overall_deadline)
            status, chain = parse_cname_dns_response(content, domain)
        except _ProbeFailure as exc:
            errors.append(str(exc))
            return result()
        except (OSError, HTTPException, TimeoutError, ValueError):
            errors.append(
                "CNAME sorgusu güvenli ve süre sınırı içinde tamamlanamadı."
            )
            return result()

        if status == 3:
            alias_status = "nxdomain"
            return result()
        if not chain:
            alias_status = "absent"
            return result()

        alias_status = "present"
        target = chain[-1].target
        target_status = "failed"
        try:
            answer4 = self._resolve(context, target, 1, overall_deadline)
            answer6 = self._resolve(context, target, 28, overall_deadline)
            if answer4[0] != answer6[0]:
                raise _ProbeFailure("CNAME hedefinin A ve AAAA durumları çelişiyor.")
            addresses = tuple(sorted(
                set(answer4[1] + answer6[1]),
                key=lambda value: (
                    ipaddress.ip_address(value).version,
                    int(ipaddress.ip_address(value)),
                ),
            ))
            if len(addresses) > MAX_ADDRESSES:
                raise _ProbeFailure("CNAME hedefi 16 adres sınırını aştı.")
            if answer4[0] == 3:
                target_status = "nxdomain"
            elif addresses:
                target_status = "resolved"
            else:
                target_status = "no_address"
        except _ProbeFailure as exc:
            errors.append(str(exc))
        except (OSError, HTTPException, TimeoutError, ValueError):
            errors.append(
                "CNAME hedef sorgusu güvenli ve süre sınırı içinde tamamlanamadı."
            )
        return result()


class GoogleMailDnsProbe(GoogleDnsJsonClient):
    """MX/SPF/DMARC evidence through fixed, verified Google DNS JSON requests."""

    @staticmethod
    def _policy(records: tuple[str, ...], prefix: str) -> tuple[str, ...]:
        separator = ";" if prefix == "v=dmarc1" else " "
        return tuple(
            item for item in records
            if item.lower() == prefix or item.lower().startswith(prefix + separator)
        )

    def check(self, domain: str) -> MailDnsResult:
        domain = normalize_for_matching(domain)
        unicode_security_profile().to_unicode(domain)
        dmarc_domain = f"_dmarc.{domain}"
        if len(dmarc_domain) > 253:
            raise ValidationError("Kök adres _dmarc DNS sorgusu oluşturmak için çok uzun.")
        started_at = self.now()
        overall_deadline = self.monotonic() + CHECK_TIMEOUT
        errors: list[str] = []
        notes = (
            "DNS sağlayıcısı: Google Public DNS; yalnız MX ve TXT kayıtları sorgulanır.",
            "SPF kök TXT içindeki v=spf1, DMARC yalnız _dmarc kökündeki v=DMARC1 kaydıdır.",
            "DKIM seçicisi tahmin edilmez; kayıt varlığı teslim veya güvenlik garantisi değildir.",
        )

        try:
            context = self.context_factory()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                raise _ProbeFailure("TLS sertifika doğrulaması devre dışı bırakılamaz.")
            context.set_alpn_protocols(["http/1.1"])
        except _ProbeFailure as exc:
            errors.extend(f"{label}: {exc}" for label in ("MX", "SPF", "DMARC"))
            return validate_mail_dns_result(MailDnsResult(
                domain, started_at, self.now(), MAIL_DNS_POLICY_VERSION,
                "failed", (), "failed", (), "failed", (), tuple(errors), notes,
            ))
        except (OSError, ValueError):
            message = "DNS sağlayıcısına güvenli bağlantı hazırlanamadı."
            errors.extend(f"{label}: {message}" for label in ("MX", "SPF", "DMARC"))
            return validate_mail_dns_result(MailDnsResult(
                domain, started_at, self.now(), MAIL_DNS_POLICY_VERSION,
                "failed", (), "failed", (), "failed", (), tuple(errors), notes,
            ))

        def query(label: str, name: str, record_type: int, prefix: str | None = None):
            try:
                content = self._dns_content(context, name, record_type, overall_deadline)
                status, records = parse_mail_dns_response(content, name, record_type)
                selected = self._policy(records, prefix) if prefix else records
                if status == 3:
                    return "nxdomain", ()
                return ("present" if selected else "missing"), selected
            except _ProbeFailure as exc:
                errors.append(f"{label}: {exc}")
                return "failed", ()
            except (OSError, HTTPException, TimeoutError, ValueError):
                errors.append(
                    f"{label}: DNS sorgusu güvenli ve süre sınırı içinde tamamlanamadı."
                )
                return "failed", ()

        mx_status, mx_records = query("MX", domain, 15)
        spf_status, spf_records = query("SPF", domain, 16, "v=spf1")
        dmarc_status, dmarc_records = query("DMARC", dmarc_domain, 16, "v=dmarc1")
        return validate_mail_dns_result(MailDnsResult(
            domain=domain, started_at=started_at, finished_at=self.now(),
            policy_version=MAIL_DNS_POLICY_VERSION,
            mx_status=mx_status, mx_records=mx_records,
            spf_status=spf_status, spf_records=spf_records,
            dmarc_status=dmarc_status, dmarc_records=dmarc_records,
            errors=tuple(errors), notes=notes,
        ))

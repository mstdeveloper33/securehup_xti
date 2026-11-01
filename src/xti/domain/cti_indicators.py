"""Canonical local cyber-threat indicators and sourced assertion history."""

from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from xti.domain.assets import ValidationError, normalize_domain


INDICATOR_TYPES = ("domain", "ipv4", "ipv6", "url", "md5", "sha1", "sha256")
ASSERTION_ACTIONS = {"added", "observed", "updated", "reactivated", "revoked"}

_SOURCE_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)
_HASH_LENGTHS = {"md5": 32, "sha1": 40, "sha256": 64}
_HEX = re.compile(r"[0-9a-f]+", re.ASCII)
_BAD_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")


def normalize_indicator_type(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("IOC türü gerekli.")
    normalized = value.strip().lower()
    if normalized not in INDICATOR_TYPES:
        raise ValidationError(
            "IOC türü domain, ipv4, ipv6, url, md5, sha1 veya sha256 olmalı."
        )
    return normalized


def _text(value: str, *, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} gerekli.")
    if any(not character.isprintable() for character in value):
        raise ValidationError(
            f"{field} {minimum}–{maximum} güvenli karakter arasında olmalı."
        )
    normalized = " ".join(value.strip().split())
    if not minimum <= len(normalized) <= maximum:
        raise ValidationError(
            f"{field} {minimum}–{maximum} güvenli karakter arasında olmalı."
        )
    return normalized


def normalize_source_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("IOC kaynak adı gerekli.")
    normalized = value.strip().lower()
    if _SOURCE_NAME.fullmatch(normalized) is None:
        raise ValidationError(
            "IOC kaynak adı 1–64 küçük harf, sayı, nokta, alt çizgi veya tire içermeli."
        )
    return normalized


def normalize_source_reference(value: str) -> str:
    return _text(value, field="IOC kaynak başvurusu", minimum=3, maximum=1000)


def normalize_indicator_description(value: str) -> str:
    return _text(value, field="IOC açıklaması", minimum=5, maximum=2000)


def normalize_assertion_reason(value: str) -> str:
    return _text(value, field="IOC işlem gerekçesi", minimum=5, maximum=1000)


def normalize_confidence(value: int | str) -> int:
    if isinstance(value, bool):
        raise ValidationError("IOC güven puanı 0–100 arasında tam sayı olmalı.")
    try:
        normalized = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("IOC güven puanı 0–100 arasında tam sayı olmalı.") from error
    if isinstance(value, str) and value != str(normalized):
        raise ValidationError("IOC güven puanı kanonik tam sayı olmalı.")
    if not 0 <= normalized <= 100:
        raise ValidationError("IOC güven puanı 0–100 arasında tam sayı olmalı.")
    return normalized


def normalize_cti_timestamp(value: str, *, field: str = "IOC zamanı") -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValidationError(f"{field} saat dilimi içeren geçerli bir zaman olmalı.")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError(
            f"{field} saat dilimi içeren geçerli bir zaman olmalı."
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{field} açık saat dilimi içermeli.")
    return parsed.astimezone(timezone.utc).isoformat()


def normalize_optional_cti_timestamp(
    value: str | None, *, field: str,
) -> str | None:
    if value is None:
        return None
    return normalize_cti_timestamp(value, field=field)


def validate_validity_window(
    valid_from: str | None, valid_until: str | None,
) -> tuple[str | None, str | None]:
    start = normalize_optional_cti_timestamp(valid_from, field="IOC geçerlilik başlangıcı")
    end = normalize_optional_cti_timestamp(valid_until, field="IOC geçerlilik sonu")
    if start is not None and end is not None:
        if datetime.fromisoformat(end) <= datetime.fromisoformat(start):
            raise ValidationError("IOC geçerlilik sonu başlangıçtan sonra olmalı.")
    return start, end


def _normalize_ip(value: str, *, version: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"IPv{version} göstergesi gerekli.")
    normalized = value.strip()
    if not normalized or not normalized.isascii() or "%" in normalized:
        raise ValidationError(f"Geçerli ve kapsam bölgesi içermeyen bir IPv{version} adresi girin.")
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as error:
        raise ValidationError(f"Geçerli bir IPv{version} adresi girin.") from error
    if address.version != version:
        raise ValidationError(f"IOC türü IPv{version}, ancak adres başka IP sürümünde.")
    return address.compressed


def _normalize_percent_escapes(value: str, *, field: str) -> str:
    if _BAD_PERCENT_ESCAPE.search(value):
        raise ValidationError(f"IOC URL {field} geçersiz yüzde kodlaması içeriyor.")
    return _PERCENT_ESCAPE.sub(lambda match: f"%{match.group(1).upper()}", value)


def normalize_url_indicator(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("URL göstergesi gerekli.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValidationError("IOC URL kontrol karakteri içeremez.")
    normalized = value.strip()
    if not 1 <= len(normalized) <= 2048 or not normalized.isascii():
        raise ValidationError("IOC URL 1–2048 ASCII karakter arasında olmalı.")
    if any(ord(character) < 33 or ord(character) == 127 for character in normalized):
        raise ValidationError("IOC URL boşluk veya kontrol karakteri içeremez.")
    if "\\" in normalized:
        raise ValidationError("IOC URL ters eğik çizgi içeremez.")
    try:
        parsed = urlsplit(normalized)
        port = parsed.port
    except ValueError as error:
        raise ValidationError("Geçerli bir HTTP veya HTTPS IOC URL girin.") from error
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname is None:
        raise ValidationError("IOC URL yalnız tam bir http:// veya https:// adresi olabilir.")
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError("IOC URL kullanıcı adı veya parola içeremez.")
    if parsed.fragment:
        raise ValidationError("IOC URL parça (#fragment) içeremez.")
    host_value = parsed.hostname
    try:
        address = ipaddress.ip_address(host_value)
    except ValueError:
        host = normalize_domain(host_value)
    else:
        host = address.compressed
        if address.version == 6:
            host = f"[{host}]"
    if port is not None and not 1 <= port <= 65535:
        raise ValidationError("IOC URL portu 1–65535 arasında olmalı.")
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"
    path = _normalize_percent_escapes(parsed.path or "/", field="yolu")
    query = _normalize_percent_escapes(parsed.query, field="sorgusu")
    return urlunsplit((scheme, host, path, query, ""))


def normalize_indicator_value(indicator_type: str, value: str) -> str:
    indicator_type = normalize_indicator_type(indicator_type)
    if indicator_type == "domain":
        return normalize_domain(value)
    if indicator_type == "ipv4":
        return _normalize_ip(value, version=4)
    if indicator_type == "ipv6":
        return _normalize_ip(value, version=6)
    if indicator_type == "url":
        return normalize_url_indicator(value)
    if not isinstance(value, str):
        raise ValidationError(f"{indicator_type.upper()} göstergesi gerekli.")
    normalized = value.strip().lower()
    length = _HASH_LENGTHS[indicator_type]
    if len(normalized) != length or _HEX.fullmatch(normalized) is None:
        raise ValidationError(
            f"{indicator_type.upper()} göstergesi tam {length} onaltılık karakter olmalı."
        )
    return normalized


def _normalize_uuid(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"Geçerli bir {field} gerekli.")
    try:
        normalized = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError(f"Geçerli bir {field} gerekli.") from error
    if value != normalized:
        raise ValidationError(f"{field} kanonik UUID biçiminde olmalı.")
    return normalized


def normalize_indicator_id(value: str) -> str:
    return _normalize_uuid(value, field="IOC kimliği")


def normalize_assertion_id(value: str) -> str:
    return _normalize_uuid(value, field="IOC kaynak iddiası kimliği")


@dataclass(frozen=True, slots=True)
class CtiIndicator:
    id: str
    indicator_type: str
    value: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CtiIndicatorAssertion:
    id: str
    indicator_id: str
    source_name: str
    source_reference: str
    confidence: int
    valid_from: str | None
    valid_until: str | None
    active: bool
    description: str
    first_seen_at: str
    last_seen_at: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class CtiIndicatorAssertionEvent:
    id: str
    assertion_id: str
    action: str
    confidence: int
    valid_from: str | None
    valid_until: str | None
    description: str
    reason: str
    observed_at: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class CtiIndicatorMutation:
    action: str
    indicator: CtiIndicator
    assertion: CtiIndicatorAssertion


@dataclass(frozen=True, slots=True)
class CtiIndicatorSummary:
    indicator: CtiIndicator
    active_assertion_count: int
    current_assertion_count: int
    total_assertion_count: int
    max_current_confidence: int | None


@dataclass(frozen=True, slots=True)
class CtiIndicatorExportItem:
    """One IOC and the source assertions that are current at export time."""

    indicator: CtiIndicator
    current_assertions: tuple[CtiIndicatorAssertion, ...]


@dataclass(frozen=True, slots=True)
class CtiIndicatorExportSnapshot:
    """Complete bounded IOC snapshot used by portable export formats."""

    checked_at: str
    indicator_type: str | None
    items: tuple[CtiIndicatorExportItem, ...]


@dataclass(frozen=True, slots=True)
class CtiIndicatorDetails:
    indicator: CtiIndicator
    assertions: tuple[CtiIndicatorAssertion, ...]
    events: tuple[CtiIndicatorAssertionEvent, ...]
    total_assertion_count: int
    total_event_count: int


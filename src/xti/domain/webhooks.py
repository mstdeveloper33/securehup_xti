"""Durable webhook destinations and delivery evidence without transport details."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from urllib.parse import SplitResult, urlsplit, urlunsplit

from xti.domain.assets import ValidationError


WEBHOOK_DELIVERY_STATUSES = frozenset({"queued", "retryable", "failed", "delivered"})
WEBHOOK_ATTEMPT_OUTCOMES = frozenset({"retryable", "failed", "delivered"})
MAX_WEBHOOK_PAYLOAD_BYTES = 256 * 1024
MAX_WEBHOOK_ATTEMPTS = 100
_NAME_SPACE = re.compile(r"\s+")


def normalize_webhook_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValidationError("Webhook hedef adı metin olmalı.")
    name = _NAME_SPACE.sub(" ", value.strip())
    if not 2 <= len(name) <= 80 or not name.isprintable():
        raise ValidationError("Webhook hedef adı 2–80 yazdırılabilir karakter olmalı.")
    return name


def webhook_name_key(value: object) -> str:
    return normalize_webhook_name(value).casefold()


def normalize_webhook_url(value: object) -> tuple[str, str]:
    """Return a canonical private URL and a safe, non-secret display label."""
    if (
        not isinstance(value, str) or value != value.strip()
        or not 1 <= len(value) <= 2048 or not value.isascii()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ValidationError("Webhook adresi geçerli bir ASCII HTTPS adresi olmalı.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValidationError("Webhook adresi geçerli değil.") from error
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or parsed.fragment or port not in {None, 443}
    ):
        raise ValidationError(
            "Webhook adresi kimlik bilgisi/fragment içermeyen HTTPS ve 443 portunda olmalı."
        )
    try:
        host = parsed.hostname.encode("ascii").decode("idna").encode("idna").decode("ascii")
    except (UnicodeError, ValueError) as error:
        raise ValidationError("Webhook hedef adı desteklenen biçimde değil.") from error
    host = host.lower().removesuffix(".")
    if not host or len(host) > 253:
        raise ValidationError("Webhook hedef adı desteklenen biçimde değil.")
    if ":" in host:
        host_text = f"[{host}]"
    else:
        host_text = host
    path = parsed.path or "/"
    if not path.startswith("/") or len(path) > 1536 or len(parsed.query) > 1024:
        raise ValidationError("Webhook adresinin yol veya sorgu bölümü çok uzun.")
    canonical = urlunsplit(SplitResult("https", host_text, path, parsed.query, ""))
    if len(canonical) > 2048:
        raise ValidationError("Webhook adresi 2048 karakter sınırını aşıyor.")
    fingerprint = hashlib.sha256(canonical.encode("ascii")).hexdigest()[:12]
    return canonical, f"https://{host_text}/… [{fingerprint}]"


def canonical_webhook_payload(value: object) -> tuple[str, str]:
    try:
        payload = json.dumps(
            value, ensure_ascii=True, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError) as error:
        raise ValidationError("Webhook olay gövdesi güvenli JSON biçimine dönüştürülemedi.") from error
    encoded = payload.encode("ascii")
    if len(encoded) > MAX_WEBHOOK_PAYLOAD_BYTES:
        raise ValidationError("Webhook olay gövdesi 256 KiB güvenli sınırını aşıyor.")
    return payload, hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class WebhookDestination:
    id: str
    display_name: str
    endpoint: str
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class WebhookDestinationMutation:
    action: str
    destination: WebhookDestination


@dataclass(frozen=True, slots=True)
class WebhookDelivery:
    sequence: int
    id: str
    destination_id: str
    destination_name: str
    endpoint: str
    notification_id: str
    event_type: str
    status: str
    payload_sha256: str
    attempt_count: int
    created_at: str
    updated_at: str
    delivered_at: str | None
    last_http_status: int | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class WebhookDeliveryAttempt:
    sequence: int
    id: str
    delivery_id: str
    number: int
    outcome: str
    http_status: int | None
    error: str | None
    attempted_at: str


@dataclass(frozen=True, slots=True)
class WebhookDeliveryDetails:
    delivery: WebhookDelivery
    attempts: tuple[WebhookDeliveryAttempt, ...]


@dataclass(frozen=True, slots=True)
class WebhookDeliveryPage:
    deliveries: tuple[WebhookDelivery, ...]
    total_count: int


@dataclass(frozen=True, slots=True)
class WebhookTarget:
    delivery: WebhookDelivery
    url: str
    secret: bytes
    payload: bytes


@dataclass(frozen=True, slots=True)
class WebhookSendResult:
    outcome: str
    http_status: int | None
    error: str | None


@dataclass(frozen=True, slots=True)
class WebhookDeliveryResult:
    delivery: WebhookDelivery
    attempt: WebhookDeliveryAttempt


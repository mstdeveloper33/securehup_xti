"""Bounded TCP service evidence for an explicitly approved domain and IP."""

from dataclasses import dataclass, replace
from datetime import datetime
import ipaddress

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.surface import SurfaceScope


SERVICE_POLICY_VERSION = "bounded-tcp-connect-v1"
SERVICE_PORT_HINTS = {
    22: "SSH adayı",
    25: "SMTP adayı",
    53: "DNS adayı",
    80: "HTTP adayı",
    443: "HTTPS adayı",
    587: "E-posta gönderim adayı",
    993: "IMAPS adayı",
    3389: "Uzak masaüstü adayı",
    8080: "Alternatif HTTP adayı",
    8443: "Alternatif HTTPS adayı",
}
SERVICE_PORTS = tuple(SERVICE_PORT_HINTS)
SERVICE_PORT_STATES = frozenset({"open", "closed", "unknown"})
SERVICE_TRANSITION_STATES = SERVICE_PORT_STATES | {"not_checked"}
SERVICE_CHANGE_FIELDS = ("dns", "addresses", "checked_address", "ports")
SERVICE_DNS_STATUSES = frozenset({
    "resolved", "no_address", "nxdomain", "failed", "blocked", "address_mismatch",
})


@dataclass(frozen=True, slots=True)
class ServicePortResult:
    port: int
    state: str
    service_hint: str


@dataclass(frozen=True, slots=True)
class ServiceScanResult:
    domain: str
    requested_address: str
    started_at: str
    finished_at: str
    policy_version: str
    dns_status: str
    addresses: tuple[str, ...]
    checked_address: str | None
    ports: tuple[ServicePortResult, ...]
    errors: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ServicePortTransition:
    port: int
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class ServiceScanChange:
    kind: str
    changed_fields: tuple[str, ...]
    transitions: tuple[ServicePortTransition, ...]


@dataclass(frozen=True, slots=True)
class ServiceScanCheck:
    id: str
    asset_id: str
    asset_value: str
    authorization_reason: str
    result: ServiceScanResult
    state_sha256: str
    change: ServiceScanChange
    recorded_at: str


@dataclass(frozen=True, slots=True)
class ServiceScanDetails:
    scope: SurfaceScope
    checks: tuple[ServiceScanCheck, ...]
    total_check_count: int


def _timestamp(value: str) -> datetime:
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 64:
            raise ValueError("invalid timestamp")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("Servis kontrol zamanı geçersiz.") from error


def normalize_public_address(value: str) -> str:
    try:
        if not isinstance(value, str) or value != value.strip() or "%" in value:
            raise ValueError("invalid address")
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise ValidationError("Kontrol için geçerli bir genel IP adresi gerekli.") from error
    if not address.is_global or any((
        address.is_private, address.is_loopback, address.is_link_local,
        address.is_multicast, address.is_reserved, address.is_unspecified,
    )):
        raise ValidationError("Özel, yerel veya özel kullanım IP adresi kontrol edilemez.")
    return str(address)


def _texts(value: tuple[str, ...], *, maximum_items: int) -> tuple[str, ...]:
    if (
        not isinstance(value, tuple) or len(value) > maximum_items
        or any(
            not isinstance(item, str) or not 1 <= len(item) <= 1000
            or not item.isprintable() for item in value
        )
    ):
        raise ValidationError("Servis kontrol açıklamaları geçersiz.")
    return value


def validate_service_scan_result(result: ServiceScanResult) -> ServiceScanResult:
    if not isinstance(result, ServiceScanResult):
        raise ValidationError("Servis sağlayıcısı beklenen sonucu vermedi.")
    domain = normalize_domain(result.domain)
    if domain != result.domain:
        raise ValidationError("Servis sonucu kanonik domain ile eşleşmiyor.")
    requested = normalize_public_address(result.requested_address)
    started = _timestamp(result.started_at)
    finished = _timestamp(result.finished_at)
    if finished < started:
        raise ValidationError("Servis kontrol zamanları ters sırada.")
    if result.policy_version != SERVICE_POLICY_VERSION:
        raise ValidationError("Servis kontrol politikası desteklenmiyor.")
    if result.dns_status not in SERVICE_DNS_STATUSES:
        raise ValidationError("Servis DNS durumu geçersiz.")

    try:
        addresses = tuple(str(ipaddress.ip_address(item)) for item in result.addresses)
    except (TypeError, ValueError) as error:
        raise ValidationError("Servis DNS adresleri geçersiz.") from error
    expected_order = tuple(sorted(
        set(addresses), key=lambda item: (ipaddress.ip_address(item).version,
                                         int(ipaddress.ip_address(item))),
    ))
    if addresses != expected_order or len(addresses) > 16:
        raise ValidationError("Servis DNS adresleri tekil, sıralı ve sınırlı olmalı.")

    checked = result.checked_address
    if checked is not None:
        checked = normalize_public_address(checked)
    if result.dns_status == "resolved":
        if not addresses or requested not in addresses or checked != requested:
            raise ValidationError("Servis kontrol adresi DNS kanıtıyla uyuşmuyor.")
    elif checked is not None or result.ports:
        raise ValidationError("Tamamlanmayan DNS doğrulaması port sonucu taşıyamaz.")
    if result.dns_status in {"no_address", "nxdomain", "failed"} and addresses:
        raise ValidationError("Tamamlanmayan DNS sonucu adres kanıtı taşıyamaz.")
    if result.dns_status == "address_mismatch" and (
        not addresses or requested in addresses
    ):
        raise ValidationError("DNS adres uyuşmazlığı kanıtıyla çelişiyor.")

    ports: list[ServicePortResult] = []
    for item in result.ports:
        if (
            not isinstance(item, ServicePortResult)
            or item.port not in SERVICE_PORT_HINTS
            or item.state not in SERVICE_PORT_STATES
            or item.service_hint != SERVICE_PORT_HINTS[item.port]
        ):
            raise ValidationError("Servis port sonucu geçersiz.")
        ports.append(item)
    if result.dns_status == "resolved":
        if tuple(item.port for item in ports) != SERVICE_PORTS:
            raise ValidationError("Servis kontrolü sabit port planını tamamlamadı.")
    elif ports:
        raise ValidationError("DNS doğrulanmadan servis portu kaydedilemez.")

    errors = _texts(result.errors, maximum_items=len(SERVICE_PORTS) + 1)
    notes = _texts(result.notes, maximum_items=10)
    unknown_count = sum(item.state == "unknown" for item in ports)
    if result.dns_status == "resolved":
        if len(errors) != unknown_count:
            raise ValidationError("Belirsiz portlar ile hata kanıtları uyuşmuyor.")
    elif len(errors) != 1:
        raise ValidationError("Tamamlanmayan servis kontrolünün tek hata açıklaması olmalı.")
    return replace(
        result, domain=domain, requested_address=requested, addresses=addresses,
        checked_address=checked, ports=tuple(ports), errors=errors, notes=notes,
    )

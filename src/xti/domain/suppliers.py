"""Human-approved supplier inventory rules and immutable audit snapshots."""

from dataclasses import dataclass
import unicodedata
from uuid import UUID

from xti.domain.assets import ValidationError, normalize_domain


SUPPLIER_RELATIONSHIP_TYPES = {
    "software",
    "cloud",
    "payment",
    "communications",
    "professional_service",
    "other",
}
SUPPLIER_CRITICALITY_LEVELS = {"low", "medium", "high", "critical"}
SUPPLIER_EVENT_ACTIONS = {"added", "updated", "reactivated", "revoked"}


def normalize_supplier_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Geçerli bir tedarikçi kimliği gerekli.")
    try:
        normalized = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError("Geçerli bir tedarikçi kimliği gerekli.") from error
    if value != normalized:
        raise ValidationError("Tedarikçi kimliği kanonik UUID biçiminde olmalı.")
    return normalized


def normalize_supplier_name(value: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ValidationError("Tedarikçi adı gerekli.")
    display = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if (
        not 2 <= len(display) <= 200
        or any(not character.isprintable() for character in display)
    ):
        raise ValidationError("Tedarikçi adı 2–200 güvenli karakter olmalı.")
    key = display.casefold()
    if not key:
        raise ValidationError("Tedarikçi adı gerekli.")
    return key, display


def normalize_supplier_relationship(value: str) -> str:
    if not isinstance(value, str) or value not in SUPPLIER_RELATIONSHIP_TYPES:
        raise ValidationError(
            "Tedarikçi ilişkisi software, cloud, payment, communications, "
            "professional_service veya other olmalı."
        )
    return value


def normalize_supplier_criticality(value: str) -> str:
    if not isinstance(value, str) or value not in SUPPLIER_CRITICALITY_LEVELS:
        raise ValidationError("Tedarikçi önemi low, medium, high veya critical olmalı.")
    return value


def normalize_supplier_reason(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Tedarikçi ilişkisi için gerekçe gerekli.")
    normalized = " ".join(value.strip().split())
    if (
        not 5 <= len(normalized) <= 2000
        or any(not character.isprintable() for character in normalized)
    ):
        raise ValidationError("Tedarikçi gerekçesi 5–2000 güvenli karakter olmalı.")
    return normalized


@dataclass(frozen=True, slots=True)
class Supplier:
    id: str
    name_key: str
    display_name: str
    primary_domain: str
    relationship_type: str
    criticality: str
    active: bool
    reason: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class SupplierEvent:
    sequence: int
    id: str
    supplier_id: str
    action: str
    display_name: str
    primary_domain: str
    relationship_type: str
    criticality: str
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class SupplierMutation:
    action: str
    changed: bool
    supplier: Supplier


@dataclass(frozen=True, slots=True)
class SupplierDetails:
    supplier: Supplier
    events: tuple[SupplierEvent, ...]
    total_event_count: int


def validate_supplier(record: Supplier) -> Supplier:
    normalize_supplier_id(record.id)
    name_key, display_name = normalize_supplier_name(record.display_name)
    if record.name_key != name_key or record.display_name != display_name:
        raise ValidationError("Tedarikçi adı kanonik biçimde değil.")
    if normalize_domain(record.primary_domain) != record.primary_domain:
        raise ValidationError("Tedarikçi ana domaini kanonik biçimde değil.")
    normalize_supplier_relationship(record.relationship_type)
    normalize_supplier_criticality(record.criticality)
    if type(record.active) is not bool:
        raise ValidationError("Tedarikçi etkinlik durumu geçersiz.")
    normalize_supplier_reason(record.reason)
    return record

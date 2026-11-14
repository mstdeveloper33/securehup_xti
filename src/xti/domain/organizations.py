"""Explicit local grouping of existing records, without ownership inference."""

from dataclasses import dataclass
import unicodedata
from uuid import UUID

from xti.domain.assets import ValidationError, normalize_domain


ORGANIZATION_TARGET_KINDS = (
    "domain", "username-watch", "ransomware-watch", "ransomlook-watch",
)
ORGANIZATION_ACTIONS = frozenset({"added", "renamed", "reactivated", "revoked"})
ORGANIZATION_LINK_ACTIONS = frozenset({"linked", "updated", "reactivated", "revoked"})


def normalize_organization_id(value: str, *, field: str = "Kuruluş kimliği") -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} kanonik UUID biçiminde olmalı.")
    try:
        normalized = str(UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError(f"{field} kanonik UUID biçiminde olmalı.") from error
    if normalized != value:
        raise ValidationError(f"{field} kanonik UUID biçiminde olmalı.")
    return normalized


def _text(value: str, *, minimum: int, maximum: int, field: str) -> str:
    if not isinstance(value, str) or len(value) > maximum * 4:
        raise ValidationError(f"{field} {minimum}–{maximum} güvenli karakter olmalı.")
    normalized = unicodedata.normalize("NFKC", value)
    if any(not character.isprintable() for character in normalized):
        raise ValidationError(f"{field} kontrol karakteri içeremez.")
    normalized = " ".join(normalized.strip().split())
    if not minimum <= len(normalized) <= maximum:
        raise ValidationError(f"{field} {minimum}–{maximum} güvenli karakter olmalı.")
    return normalized


def normalize_organization_name(value: str) -> tuple[str, str]:
    display = _text(value, minimum=2, maximum=200, field="Kuruluş adı")
    return display.casefold(), display


def normalize_organization_reason(value: str) -> str:
    return _text(value, minimum=3, maximum=500, field="Kuruluş bağlantısı gerekçesi")


@dataclass(frozen=True, slots=True)
class OrganizationTargetReference:
    kind: str
    value: str


def normalize_organization_target(kind: str, value: str) -> OrganizationTargetReference:
    if not isinstance(kind, str) or kind not in ORGANIZATION_TARGET_KINDS:
        raise ValidationError("Bağlantı türü domain, username-watch, ransomware-watch veya ransomlook-watch olmalı.")
    normalized = normalize_domain(value) if kind == "domain" else normalize_organization_id(
        value, field="İzleme kimliği",
    )
    return OrganizationTargetReference(kind, normalized)


@dataclass(frozen=True, slots=True)
class Organization:
    id: str
    name_key: str
    display_name: str
    revision: int
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class OrganizationChange:
    action: str
    name_key: str
    display_name: str
    active: bool


def decide_organization_change(
    current: Organization | None, operation: str, *, name: str | None = None,
) -> OrganizationChange:
    if not isinstance(operation, str) or operation not in {"add", "rename", "revoke", "reactivate"}:
        raise ValidationError("Kuruluş işlemi desteklenmiyor.")
    if current is not None and (not isinstance(current, Organization) or type(current.active) is not bool):
        raise ValidationError("Kuruluş kaydı veya etkinlik durumu geçersiz.")
    if operation in {"add", "rename"}:
        name_key, display_name = normalize_organization_name(name)
    if current is None:
        if operation != "add":
            raise ValidationError("Kuruluş bulunamadı.")
        return OrganizationChange("added", name_key, display_name, True)
    if operation == "add":
        if current.name_key != name_key:
            raise ValidationError("Kuruluş adı mevcut kayıtla uyuşmuyor.")
        if not current.active:
            raise ValidationError("Kuruluş geri çekilmiş; açıkça yeniden etkinleştirin.")
        return OrganizationChange("unchanged", current.name_key, current.display_name, True)
    if operation == "rename":
        action = "unchanged" if current.display_name == display_name else "renamed"
        return OrganizationChange(action, name_key, display_name, current.active)
    active = operation == "reactivate"
    action = "unchanged" if current.active == active else "reactivated" if active else "revoked"
    return OrganizationChange(action, current.name_key, current.display_name, active)


@dataclass(frozen=True, slots=True)
class OrganizationEvent:
    sequence: int
    id: str
    organization_id: str
    action: str
    revision: int
    name_key: str
    display_name: str
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class OrganizationLink:
    id: str
    organization_id: str
    target: OrganizationTargetReference
    revision: int
    active: bool
    reason: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class OrganizationLinkChange:
    action: str
    active: bool
    reason: str


def decide_organization_link_change(
    current: OrganizationLink | None, *, link_requested: bool, reason: str,
    organization_active: bool, target_active: bool,
) -> OrganizationLinkChange:
    if any(type(value) is not bool for value in (link_requested, organization_active, target_active)):
        raise ValidationError("Kuruluş bağlantısı etkinlik seçimi geçersiz.")
    if current is not None and (not isinstance(current, OrganizationLink) or type(current.active) is not bool):
        raise ValidationError("Kuruluş bağlantı kaydı veya etkinlik durumu geçersiz.")
    reason = normalize_organization_reason(reason)
    if link_requested and not (organization_active and target_active):
        raise ValidationError("Bağlantı eklemek için kuruluş ve hedef kayıt etkin olmalı.")
    if current is None:
        if not link_requested:
            raise ValidationError("Kuruluş bağlantısı bulunamadı.")
        return OrganizationLinkChange("linked", True, reason)
    if not link_requested:
        return OrganizationLinkChange(
            "revoked" if current.active else "unchanged", False,
            reason if current.active else current.reason,
        )
    action = (
        "reactivated" if not current.active
        else "unchanged" if current.reason == reason else "updated"
    )
    return OrganizationLinkChange(action, True, reason)


@dataclass(frozen=True, slots=True)
class OrganizationLinkEvent:
    sequence: int
    id: str
    link_id: str
    organization_id: str
    action: str
    revision: int
    target: OrganizationTargetReference
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class OrganizationTargetSummary:
    reference: OrganizationTargetReference
    display_name: str
    source: str
    active: bool


@dataclass(frozen=True, slots=True)
class OrganizationLinkView:
    link: OrganizationLink
    target: OrganizationTargetSummary


def organization_link_effective(organization: Organization, view: OrganizationLinkView) -> bool:
    if (
        view.link.organization_id != organization.id
        or view.link.target != view.target.reference
        or any(type(value) is not bool for value in (
            organization.active, view.link.active, view.target.active,
        ))
    ):
        raise ValidationError("Kuruluş bağlantısı ile hedef görünümü uyuşmuyor.")
    return organization.active and view.link.active and view.target.active


@dataclass(frozen=True, slots=True)
class OrganizationMutation:
    action: str
    organization: Organization


@dataclass(frozen=True, slots=True)
class OrganizationLinkMutation:
    action: str
    link: OrganizationLink


@dataclass(frozen=True, slots=True)
class OrganizationPage:
    organizations: tuple[Organization, ...]
    total_count: int
    offset: int
    limit: int


@dataclass(frozen=True, slots=True)
class OrganizationDetails:
    organization: Organization
    events: tuple[OrganizationEvent, ...]
    total_event_count: int
    links: tuple[OrganizationLinkView, ...]
    total_link_count: int
    link_offset: int
    link_limit: int


@dataclass(frozen=True, slots=True)
class OrganizationLinkDetails:
    view: OrganizationLinkView
    events: tuple[OrganizationLinkEvent, ...]
    total_event_count: int

"""User-verified Ubuntu binary-to-source package inventory evidence."""

from dataclasses import dataclass
import re
from uuid import UUID

from xti.domain.assets import ValidationError
from xti.domain.debian_version import parse_debian_version
from xti.domain.ubuntu_package_match import (
    UbuntuPackageMatchReport,
    normalize_debian_source_package,
    normalize_ubuntu_ecosystem,
)


UBUNTU_PACKAGE_EVIDENCE_TYPES = {"user_verified"}
_BINARY_PACKAGE = re.compile(r"[a-z0-9][a-z0-9+.-]{0,254}", re.ASCII)
_ARCHITECTURE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}", re.ASCII)


def normalize_ubuntu_binary_package(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Ubuntu binary paket adı gerekli.")
    normalized = value.strip().lower()
    if _BINARY_PACKAGE.fullmatch(normalized) is None:
        raise ValidationError("Ubuntu binary paket adı kanonik Debian paket adı olmalı.")
    return normalized


def normalize_debian_architecture(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Debian paket mimarisi gerekli.")
    normalized = value.strip().lower()
    if _ARCHITECTURE.fullmatch(normalized) is None:
        raise ValidationError("Debian paket mimarisi küçük harf, sayı ve tire içermeli.")
    return normalized


def normalize_ubuntu_package_evidence(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Ubuntu paket doğrulama kanıtı gerekli.")
    normalized = " ".join(value.strip().split())
    if not 5 <= len(normalized) <= 1000 or any(
        not character.isprintable() for character in normalized
    ):
        raise ValidationError("Ubuntu paket doğrulama kanıtı 5–1000 güvenli karakter olmalı.")
    return normalized


def normalize_ubuntu_package_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Geçerli bir Ubuntu paket kanıtı kimliği gerekli.")
    try:
        normalized = str(UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError("Geçerli bir Ubuntu paket kanıtı kimliği gerekli.") from error
    if value != normalized:
        raise ValidationError("Ubuntu paket kanıtı kimliği kanonik UUID biçiminde olmalı.")
    return normalized


@dataclass(frozen=True, slots=True)
class UbuntuAssetPackageEvidence:
    id: str
    asset_id: str
    asset_value: str
    ecosystem: str
    binary_name: str
    binary_version: str
    architecture: str
    source_name: str
    source_version: str
    active: bool
    evidence_type: str
    evidence: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class UbuntuAssetPackageEvent:
    id: str
    ubuntu_package_id: str
    action: str
    evidence_type: str
    evidence: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class UbuntuAssetPackageMutation:
    action: str
    record: UbuntuAssetPackageEvidence


@dataclass(frozen=True, slots=True)
class UbuntuAssetPackageDetails:
    record: UbuntuAssetPackageEvidence
    events: tuple[UbuntuAssetPackageEvent, ...]
    total_event_count: int


@dataclass(frozen=True, slots=True)
class UbuntuInventoryMatchReport:
    package: UbuntuAssetPackageEvidence
    comparison: UbuntuPackageMatchReport
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UbuntuInventoryScanItem:
    package: UbuntuAssetPackageEvidence
    status: str
    fixed_version: str | None
    version_comparison: int | None
    affected_versions_count: int | None


@dataclass(frozen=True, slots=True)
class UbuntuInventoryScanReport:
    cve_id: str
    asset_value: str | None
    source: str | None
    source_url: str | None
    content_sha256: str | None
    record_id: str | None
    modified_at: str | None
    withdrawn_at: str | None
    total_active_package_count: int
    displayed_count: int
    record_withdrawn_count: int
    not_listed_count: int
    listed_without_fixed_boundary_count: int
    before_fixed_boundary_count: int
    at_fixed_boundary_count: int
    after_fixed_boundary_count: int
    total_advisory_reference_count: int
    advisory_references: tuple[str, ...]
    advisory_references_truncated: bool
    items: tuple[UbuntuInventoryScanItem, ...]
    truncated: bool
    source_requested: bool
    notes: tuple[str, ...]


def normalize_ubuntu_package_fields(
    *, ecosystem: str, binary_name: str, binary_version: str,
    architecture: str, source_name: str, source_version: str,
) -> tuple[str, str, str, str, str, str]:
    return (
        normalize_ubuntu_ecosystem(ecosystem),
        normalize_ubuntu_binary_package(binary_name),
        parse_debian_version(binary_version).value,
        normalize_debian_architecture(architecture),
        normalize_debian_source_package(source_name),
        parse_debian_version(source_version).value,
    )

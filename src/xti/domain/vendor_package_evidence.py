"""Structured, human-selected evidence from an exact RPM/VEX relationship."""

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from uuid import UUID

from xti.domain.assets import ValidationError
from xti.domain.packages import normalize_package_id, normalize_redhat_distribution_cpe
from xti.domain.vendor_advisory import redhat_vex_url
from xti.domain.vulnerability import normalize_cve_id
from xti.domain.vulnerability_exposure_evidence import normalize_exposure_evidence_summary
from xti.domain.vulnerability_exposures import normalize_exposure_id
from xti.domain.vendor_package_match import VendorPackageStatusMatch


VENDOR_STATUSES = {
    "fixed", "known_affected", "known_not_affected", "under_investigation",
    "first_affected", "first_fixed", "last_affected", "recommended",
}
MATCH_KINDS = {"exact_binary_package", "source_package_context"}
VENDOR_PACKAGE_EVIDENCE_ACTIONS = {"added", "updated", "reactivated", "revoked"}
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)


def normalize_vendor_package_evidence_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Geçerli bir kesin üretici kanıtı kimliği gerekli.")
    try:
        normalized = str(UUID(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError("Geçerli bir kesin üretici kanıtı kimliği gerekli.") from error
    if value != normalized:
        raise ValidationError("Kesin üretici kanıtı kimliği kanonik UUID biçiminde olmalı.")
    return normalized


def normalize_vendor_status(value: str) -> str:
    if not isinstance(value, str) or value not in VENDOR_STATUSES:
        raise ValidationError("Red Hat VEX ürün durumu geçersiz.")
    return value


def normalize_match_kind(value: str) -> str:
    if not isinstance(value, str) or value not in MATCH_KINDS:
        raise ValidationError("Kesin VEX eşleşme türü geçersiz.")
    return value


def normalize_vendor_identifier(value: str, *, field: str) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value) <= 2000
        or any(ord(character) < 33 or ord(character) > 126 for character in value)
    ):
        raise ValidationError(f"{field} 1–2000 güvenli ASCII karakter olmalı.")
    return value


def normalize_vendor_sha256(value: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValidationError("Red Hat VEX kaynak özeti geçersiz.")
    return value


def normalize_vendor_document_version(value: str) -> str:
    return normalize_vendor_identifier(value, field="Red Hat VEX belge sürümü")


def normalize_vendor_timestamp(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValidationError(f"{field} geçersiz.")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError(f"{field} geçersiz.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{field} saat dilimi içermeli.")
    return parsed.astimezone(timezone.utc).isoformat()


def validate_vendor_source_url(value: str, *, cve_id: str) -> str:
    expected = redhat_vex_url(normalize_cve_id(cve_id))
    if value != expected:
        raise ValidationError("Red Hat VEX kaynak adresi beklenen sabit CVE adresiyle uyuşmuyor.")
    return value


@dataclass(frozen=True, slots=True)
class VendorPackageEvidence:
    id: str
    exposure_id: str
    asset_package_id: str
    provider: str
    cve_id: str
    source_url: str
    source_sha256: str
    document_version: str
    current_release_at: str
    vendor_status: str
    match_kind: str
    vex_product_id: str
    component_product_id: str
    component_purl: str
    context_product_id: str
    context_cpe: str
    package_updated_at: str
    summary: str
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class VendorPackageEvidenceEvent:
    id: str
    evidence_id: str
    action: str
    summary: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class VendorPackageEvidenceMutation:
    action: str
    record: VendorPackageEvidence


@dataclass(frozen=True, slots=True)
class VendorPackageEvidenceDetails:
    record: VendorPackageEvidence
    events: tuple[VendorPackageEvidenceEvent, ...]
    total_event_count: int


@dataclass(frozen=True, slots=True)
class VendorPackageEvidenceSelection:
    mutation: VendorPackageEvidenceMutation
    selected_match: VendorPackageStatusMatch
    source_url: str
    source_sha256: str
    document_version: str
    current_release_at: str
    notes: tuple[str, ...]


def validate_vendor_evidence_keys(exposure_id: str, package_id: str, cve_id: str) -> tuple[str, str, str]:
    return (
        normalize_exposure_id(exposure_id), normalize_package_id(package_id),
        normalize_cve_id(cve_id),
    )


def normalize_vendor_evidence_summary(value: str) -> str:
    return normalize_exposure_evidence_summary(value)

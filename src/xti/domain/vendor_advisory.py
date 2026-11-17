"""Direct vendor advisory context without cross-vendor exposure claims."""

from dataclasses import dataclass

from xti.domain.assets import ValidationError
from xti.domain.vulnerability import normalize_cve_id


REDHAT_VEX_SOURCE = "redhat_csaf_vex"
REDHAT_VEX_BASE_URL = "https://security.access.redhat.com/data/csaf/v2/vex"
SUSE_VEX_SOURCE = "suse_csaf_vex"
SUSE_VEX_BASE_URL = "https://ftp.suse.com/pub/projects/security/csaf-vex"


def normalize_vendor_product_id(value: str, *, field: str) -> str:
    """Preserve opaque CSAF references exactly, within bounded printable ASCII."""
    if (
        not isinstance(value, str) or not 1 <= len(value) <= 2000
        or any(ord(character) < 32 or ord(character) > 126 for character in value)
    ):
        raise ValidationError(f"{field} 1–2000 yazdırılabilir ASCII karakter olmalı.")
    return value


def redhat_vex_url(cve_id: str) -> str:
    normalized = normalize_cve_id(cve_id)
    year = normalized.split("-", 2)[1]
    return f"{REDHAT_VEX_BASE_URL}/{year}/{normalized.lower()}.json"


def suse_vex_url(cve_id: str) -> str:
    """Return SUSE's deterministic per-CVE path; pre-2023 CVEs live in its 2023 backfill."""

    normalized = normalize_cve_id(cve_id)
    cve_year = int(normalized.split("-", 2)[1])
    directory_year = max(cve_year, 2023)
    return f"{SUSE_VEX_BASE_URL}/{directory_year}/{normalized.lower()}.json"


@dataclass(frozen=True, slots=True)
class VendorProduct:
    product_id: str
    name: str
    purl: str | None = None
    cpe: str | None = None
    relationship_category: str | None = None
    component_product_id: str | None = None
    component_purl: str | None = None
    context_product_id: str | None = None
    context_cpe: str | None = None


@dataclass(frozen=True, slots=True)
class VendorProductStatus:
    status: str
    products: tuple[VendorProduct, ...]


@dataclass(frozen=True, slots=True)
class VendorRemediation:
    category: str
    details: str
    date: str | None
    url: str | None
    target_count: int


@dataclass(frozen=True, slots=True)
class VendorAdvisory:
    provider: str
    cve_id: str
    record_id: str
    title: str
    document_status: str
    document_version: str
    initial_release_at: str
    current_release_at: str
    severity: str | None
    product_statuses: tuple[VendorProductStatus, ...]
    remediations: tuple[VendorRemediation, ...]


@dataclass(frozen=True, slots=True)
class VendorAdvisorySnapshot:
    source: str
    source_url: str
    format_version: str
    content_sha256: str
    advisory: VendorAdvisory


@dataclass(frozen=True, slots=True)
class VendorProductStatusPreview:
    status: str
    total_count: int
    examples: tuple[VendorProduct, ...]
    truncated: bool


@dataclass(frozen=True, slots=True)
class VendorAdvisoryPreview:
    source: str
    source_url: str
    format_version: str
    content_sha256: str
    provider: str
    cve_id: str
    record_id: str
    title: str
    document_status: str
    document_version: str
    initial_release_at: str
    current_release_at: str
    severity: str | None
    product_statuses: tuple[VendorProductStatusPreview, ...]
    total_remediation_count: int
    remediations: tuple[VendorRemediation, ...]
    remediations_truncated: bool
    notes: tuple[str, ...]

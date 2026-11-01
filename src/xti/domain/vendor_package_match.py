"""Read-only relation between exact local RPM evidence and vendor VEX context."""

from dataclasses import dataclass

from xti.domain.packages import AssetPackageEvidence


@dataclass(frozen=True, slots=True)
class VendorPackageStatusMatch:
    vendor_status: str
    match_kind: str
    vex_product_id: str
    vex_product_name: str
    component_product_id: str
    component_purl: str
    context_product_id: str
    context_cpe: str


@dataclass(frozen=True, slots=True)
class VendorPackageMatchReport:
    package: AssetPackageEvidence
    cve_id: str
    provider: str
    source_url: str
    content_sha256: str
    document_status: str
    document_version: str
    current_release_at: str
    match_state: str
    vendor_status: str | None
    matches: tuple[VendorPackageStatusMatch, ...]
    total_match_count: int
    matches_truncated: bool
    notes: tuple[str, ...]

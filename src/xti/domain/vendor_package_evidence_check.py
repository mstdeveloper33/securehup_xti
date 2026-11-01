"""Read-only currency report for one stored exact RPM/VEX evidence record."""

from dataclasses import dataclass

from xti.domain.vendor_package_evidence import VendorPackageEvidence
from xti.domain.vendor_package_match import VendorPackageStatusMatch


@dataclass(frozen=True, slots=True)
class VendorPackageEvidenceCheckReport:
    evidence: VendorPackageEvidence
    checked_at: str
    state: str
    package_active: bool
    package_snapshot_changed: bool
    source_checked: bool
    source_changed: bool | None
    current_source_sha256: str | None
    current_document_version: str | None
    current_release_at: str | None
    current_match_state: str | None
    current_vendor_status: str | None
    selected_relation_present: bool | None
    current_match: VendorPackageStatusMatch | None
    notes: tuple[str, ...]

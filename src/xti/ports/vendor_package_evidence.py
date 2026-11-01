"""Persistence boundary for selected exact RPM/VEX evidence."""

from typing import Protocol

from xti.domain.vendor_package_evidence import (
    VendorPackageEvidence,
    VendorPackageEvidenceDetails,
    VendorPackageEvidenceMutation,
)


class VendorPackageEvidenceRepository(Protocol):
    def add(
        self, *, exposure_id: str, asset_package_id: str, provider: str, cve_id: str,
        source_url: str, source_sha256: str, document_version: str,
        current_release_at: str, vendor_status: str, match_kind: str,
        vex_product_id: str, component_product_id: str, component_purl: str,
        context_product_id: str, context_cpe: str, package_updated_at: str,
        summary: str, recorded_at: str,
    ) -> VendorPackageEvidenceMutation:
        ...

    def revoke(
        self, evidence_id: str, *, reason: str, recorded_at: str,
    ) -> VendorPackageEvidenceMutation:
        ...

    def list(
        self, *, exposure_id: str, active_only: bool, limit: int,
    ) -> tuple[VendorPackageEvidence, ...]:
        ...

    def details(
        self, evidence_id: str, *, event_limit: int,
    ) -> VendorPackageEvidenceDetails:
        ...

"""Atomic persistence boundary for selected Ubuntu exposure evidence."""

from typing import Protocol

from xti.domain.vulnerability_exposure_evidence import (
    VulnerabilityExposureEvidence,
    VulnerabilityExposureEvidenceMutation,
)
from xti.ports.vulnerability_exposure_evidence import (
    VulnerabilityExposureEvidenceRepository,
)


class UbuntuExposureEvidenceRepository(
    VulnerabilityExposureEvidenceRepository, Protocol,
):
    def add_ubuntu_selection(
        self, *, exposure_id: str, ubuntu_package_id: str, cve_id: str,
        package_snapshot_sha256: str, source_sha256: str, match_status: str,
        summary: str, recorded_at: str,
    ) -> VulnerabilityExposureEvidenceMutation:
        ...

    def active_ubuntu_evidence(
        self, *, asset_value: str | None,
    ) -> tuple[VulnerabilityExposureEvidence, ...]:
        ...

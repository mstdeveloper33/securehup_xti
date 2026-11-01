"""Read-only currency result for selected Ubuntu exposure evidence."""

from dataclasses import dataclass

from xti.domain.ubuntu_evidence import UbuntuEvidencePlanReport, UbuntuEvidenceReference
from xti.domain.vulnerability_exposure_evidence import VulnerabilityExposureEvidence


@dataclass(frozen=True, slots=True)
class UbuntuEvidenceCheckReport:
    evidence: VulnerabilityExposureEvidence
    stored_reference: UbuntuEvidenceReference
    checked_at: str
    state: str
    evidence_active: bool
    package_active: bool
    package_snapshot_changed: bool
    source_checked: bool
    source_changed: bool | None
    current_package_snapshot_sha256: str
    current_source_sha256: str | None
    current_match_status: str | None
    current_fixed_version: str | None
    selected_relation_present: bool | None
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UbuntuEvidenceScanReport:
    plan: UbuntuEvidencePlanReport
    selected_count: int
    source_request_count: int
    current_count: int
    changed_count: int
    skipped_source_count: int
    results: tuple[UbuntuEvidenceCheckReport, ...]
    truncated: bool
    notes: tuple[str, ...]

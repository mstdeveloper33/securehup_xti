"""Human-selected Canonical Ubuntu package result as exposure support evidence."""

from dataclasses import asdict, dataclass
import hashlib
import json
import re

from xti.domain.assets import ValidationError
from xti.domain.ubuntu_package_match import (
    UBUNTU_MATCH_STATUSES,
    UbuntuPackageMatchReport,
)
from xti.domain.ubuntu_packages import (
    UbuntuAssetPackageEvidence,
    normalize_ubuntu_package_id,
)
from xti.domain.vulnerability import normalize_cve_id
from xti.domain.vulnerability_exposure_evidence import (
    VulnerabilityExposureEvidence,
    VulnerabilityExposureEvidenceMutation,
)


UBUNTU_SELECTABLE_EVIDENCE_STATUSES = {
    "listed_without_fixed_boundary",
    "before_fixed_boundary",
    "at_fixed_boundary",
    "after_fixed_boundary",
}
UBUNTU_EVIDENCE_REFERENCE_PREFIX = "ubuntu-osv-v1:"
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)


def normalize_ubuntu_evidence_status(value: str) -> str:
    if not isinstance(value, str) or value not in UBUNTU_MATCH_STATUSES:
        raise ValidationError("Canonical Ubuntu karşılaştırma durumu geçersiz.")
    if value not in UBUNTU_SELECTABLE_EVIDENCE_STATUSES:
        raise ValidationError(
            "Kalıcı Ubuntu kanıtı için güncel kayıtta tek bir affected paket bağı gerekli."
        )
    return value


def normalize_ubuntu_evidence_sha256(value: str, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValidationError(f"{field} SHA-256 özeti geçersiz.")
    return value


def ubuntu_package_snapshot_sha256(package: UbuntuAssetPackageEvidence) -> str:
    if not isinstance(package, UbuntuAssetPackageEvidence):
        raise ValidationError("Ubuntu paket anlık görüntüsü geçersiz.")
    payload = json.dumps(
        asdict(package), ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def ubuntu_evidence_reference(
    *, cve_id: str, package_id: str, package_snapshot_sha256: str,
    source_sha256: str, match_status: str,
) -> str:
    cve_id = normalize_cve_id(cve_id)
    package_id = normalize_ubuntu_package_id(package_id)
    package_snapshot_sha256 = normalize_ubuntu_evidence_sha256(
        package_snapshot_sha256, field="Ubuntu paket anlık görüntüsü",
    )
    source_sha256 = normalize_ubuntu_evidence_sha256(
        source_sha256, field="Canonical kaynak",
    )
    match_status = normalize_ubuntu_evidence_status(match_status)
    reference = (
        f"{UBUNTU_EVIDENCE_REFERENCE_PREFIX}{cve_id}:{package_id}:{package_snapshot_sha256}:"
        f"{source_sha256}:{match_status}"
    )
    if not 3 <= len(reference) <= 1000 or not reference.isascii():
        raise ValidationError("Ubuntu kanıt kaynak bağı geçersiz.")
    return reference


@dataclass(frozen=True, slots=True)
class UbuntuEvidenceReference:
    cve_id: str
    package_id: str
    package_snapshot_sha256: str
    source_sha256: str
    match_status: str


def parse_ubuntu_evidence_reference(value: str) -> UbuntuEvidenceReference:
    if not isinstance(value, str) or not value.startswith(UBUNTU_EVIDENCE_REFERENCE_PREFIX):
        raise ValidationError("Destek kanıtı seçilmiş Ubuntu OSV sonucu değil.")
    parts = value.split(":")
    if len(parts) != 6 or parts[0] != "ubuntu-osv-v1":
        raise ValidationError("Ubuntu kanıt kaynak bağı biçimi geçersiz.")
    parsed = UbuntuEvidenceReference(
        cve_id=normalize_cve_id(parts[1]),
        package_id=normalize_ubuntu_package_id(parts[2]),
        package_snapshot_sha256=normalize_ubuntu_evidence_sha256(
            parts[3], field="Ubuntu paket anlık görüntüsü",
        ),
        source_sha256=normalize_ubuntu_evidence_sha256(
            parts[4], field="Canonical kaynak",
        ),
        match_status=normalize_ubuntu_evidence_status(parts[5]),
    )
    if ubuntu_evidence_reference(
        cve_id=parsed.cve_id, package_id=parsed.package_id,
        package_snapshot_sha256=parsed.package_snapshot_sha256,
        source_sha256=parsed.source_sha256, match_status=parsed.match_status,
    ) != value:
        raise ValidationError("Ubuntu kanıt kaynak bağı kanonik değil.")
    return parsed


@dataclass(frozen=True, slots=True)
class UbuntuExposureEvidenceSelection:
    mutation: VulnerabilityExposureEvidenceMutation
    package: UbuntuAssetPackageEvidence
    comparison: UbuntuPackageMatchReport
    package_snapshot_sha256: str
    source_reference: str
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UbuntuEvidencePlanItem:
    evidence: VulnerabilityExposureEvidence
    stored_reference: UbuntuEvidenceReference
    package: UbuntuAssetPackageEvidence
    local_state: str


@dataclass(frozen=True, slots=True)
class UbuntuEvidencePlanReport:
    asset_value: str | None
    total_active_evidence_count: int
    displayed_count: int
    local_current_count: int
    package_snapshot_changed_count: int
    package_inactive_count: int
    items: tuple[UbuntuEvidencePlanItem, ...]
    truncated: bool
    notes: tuple[str, ...]

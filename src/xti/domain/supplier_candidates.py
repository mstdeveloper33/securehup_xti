"""Evidence-bound supplier candidates and reversible human resolutions."""

from dataclasses import dataclass
import re
from uuid import UUID

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.suppliers import Supplier, normalize_supplier_id


SUPPLIER_CANDIDATE_STATUSES = frozenset({
    "pending", "accepted", "uncertain", "rejected",
})
_SHA256 = re.compile(r"[0-9a-f]{64}")


def normalize_candidate_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Geçerli bir tedarikçi adayı kimliği gerekli.")
    try:
        normalized = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError("Geçerli bir tedarikçi adayı kimliği gerekli.") from error
    if normalized != value:
        raise ValidationError("Tedarikçi adayı kimliği kanonik UUID biçiminde olmalı.")
    return normalized


def normalize_candidate_status(value: str) -> str:
    if not isinstance(value, str) or value not in SUPPLIER_CANDIDATE_STATUSES:
        raise ValidationError(
            "Aday kararı pending, accepted, uncertain veya rejected olmalı."
        )
    return value


def normalize_resolution_reason(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Aday kararı için gerekçe gerekli.")
    normalized = " ".join(value.strip().split())
    if (
        not 5 <= len(normalized) <= 2000
        or any(not character.isprintable() for character in normalized)
    ):
        raise ValidationError("Aday kararı gerekçesi 5–2000 güvenli karakter olmalı.")
    return normalized


def normalize_sha256(value: str, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValidationError(f"{label} SHA-256 özeti geçersiz.")
    return value


def normalize_profile_text(value: str, *, label: str) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value) <= 200
        or value != value.strip() or not value.isprintable()
    ):
        raise ValidationError(f"{label} geçersiz.")
    return value


@dataclass(frozen=True, slots=True)
class SupplierDependencyObservation:
    source_evidence_id: str
    asset_id: str
    source_domain: str
    target_domain: str | None
    state_sha256: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class SupplierCandidateProposal:
    source_evidence_id: str
    asset_id: str
    asset_value: str
    target_domain: str
    candidate_domain: str
    state_sha256: str
    public_suffix_version: str
    public_suffix_sha256: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class SupplierCandidate:
    id: str
    asset_id: str
    asset_value: str
    candidate_domain: str
    status: str
    current: bool
    supplier_id: str | None
    resolution_reason: str | None
    first_seen_at: str
    last_seen_at: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class SupplierCandidateEvidence:
    sequence: int
    id: str
    candidate_id: str
    source_evidence_id: str
    source_domain: str
    target_domain: str
    state_sha256: str
    public_suffix_version: str
    public_suffix_sha256: str
    observed_at: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class SupplierCandidateResolution:
    sequence: int
    id: str
    candidate_id: str
    decision: str
    supplier_id: str | None
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class SupplierCandidateRefresh:
    observation_count: int
    external_dependency_count: int
    candidates_created: int
    candidates_existing: int
    evidence_created: int
    evidence_existing: int
    became_current: int
    became_historical: int


@dataclass(frozen=True, slots=True)
class SupplierCandidateMutation:
    action: str
    changed: bool
    candidate: SupplierCandidate
    supplier: Supplier | None


@dataclass(frozen=True, slots=True)
class SupplierCandidateDetails:
    candidate: SupplierCandidate
    supplier: Supplier | None
    evidence: tuple[SupplierCandidateEvidence, ...]
    resolutions: tuple[SupplierCandidateResolution, ...]
    total_evidence_count: int
    total_resolution_count: int


def validate_observation(record: SupplierDependencyObservation) -> SupplierDependencyObservation:
    normalize_profile_text(record.source_evidence_id, label="Kaynak kanıt kimliği")
    normalize_profile_text(record.asset_id, label="Varlık kimliği")
    if normalize_domain(record.source_domain) != record.source_domain:
        raise ValidationError("Bağımlılık kaynak domaini kanonik değil.")
    if record.target_domain is not None and normalize_domain(record.target_domain) != record.target_domain:
        raise ValidationError("Bağımlılık hedef domaini kanonik değil.")
    normalize_sha256(record.state_sha256, label="Kaynak kanıt")
    normalize_profile_text(record.observed_at, label="Gözlem zamanı")
    return record


def validate_proposal(record: SupplierCandidateProposal) -> SupplierCandidateProposal:
    normalize_profile_text(record.source_evidence_id, label="Kaynak kanıt kimliği")
    normalize_profile_text(record.asset_id, label="Varlık kimliği")
    for value in (record.asset_value, record.target_domain, record.candidate_domain):
        if normalize_domain(value) != value:
            raise ValidationError("Tedarikçi adayı domain kanıtı kanonik değil.")
    normalize_sha256(record.state_sha256, label="Kaynak kanıt")
    normalize_profile_text(record.public_suffix_version, label="Public Suffix List sürümü")
    normalize_sha256(record.public_suffix_sha256, label="Public Suffix List")
    normalize_profile_text(record.observed_at, label="Gözlem zamanı")
    return record


def validate_candidate(record: SupplierCandidate) -> SupplierCandidate:
    normalize_candidate_id(record.id)
    normalize_profile_text(record.asset_id, label="Varlık kimliği")
    if normalize_domain(record.asset_value) != record.asset_value:
        raise ValidationError("Tedarikçi adayı kaynak domaini kanonik değil.")
    if normalize_domain(record.candidate_domain) != record.candidate_domain:
        raise ValidationError("Tedarikçi adayı domaini kanonik değil.")
    normalize_candidate_status(record.status)
    if type(record.current) is not bool:
        raise ValidationError("Tedarikçi adayının güncellik durumu geçersiz.")
    if record.status == "accepted":
        if record.supplier_id is None or record.resolution_reason is None:
            raise ValidationError("Kabul edilen adayın tedarikçi bağlantısı eksik.")
        normalize_supplier_id(record.supplier_id)
    elif record.supplier_id is not None:
        raise ValidationError("Kabul edilmemiş aday tedarikçiye bağlanamaz.")
    if record.status == "pending":
        if record.resolution_reason is not None:
            raise ValidationError("Bekleyen aday karar gerekçesi taşıyamaz.")
    elif record.resolution_reason is None:
        raise ValidationError("İncelenmiş adayın karar gerekçesi eksik.")
    if record.resolution_reason is not None:
        normalize_resolution_reason(record.resolution_reason)
    return record

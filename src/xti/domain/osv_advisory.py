"""Bounded OSV advisory context without an exposure verdict."""

from dataclasses import dataclass
from urllib.parse import quote

from xti.domain.vulnerability_exposure_evidence import (
    VulnerabilityExposureEvidenceMutation,
)
from xti.domain.vulnerability import normalize_cve_id


OSV_SOURCE = "osv_dev"
OSV_VULNERABILITY_URL = "https://api.osv.dev/v1/vulns"


def osv_vulnerability_url(cve_id: str) -> str:
    normalized = normalize_cve_id(cve_id)
    return f"{OSV_VULNERABILITY_URL}/{quote(normalized, safe='')}"


@dataclass(frozen=True, slots=True)
class OsvAffectedPackage:
    ecosystem: str | None
    name: str | None
    purl: str | None
    versions_count: int
    range_count: int
    range_types: tuple[str, ...]
    single_range_event_order: tuple[str, ...] | None
    introduced_versions: tuple[str, ...]
    fixed_versions: tuple[str, ...]
    last_affected_versions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OsvAdvisory:
    queried_cve_id: str
    record_id: str
    schema_version: str | None
    modified_at: str
    published_at: str | None
    withdrawn_at: str | None
    summary: str | None
    details: str | None
    aliases: tuple[str, ...]
    upstream: tuple[str, ...]
    affected: tuple[OsvAffectedPackage, ...]
    advisory_references: tuple[str, ...]
    other_reference_count: int


@dataclass(frozen=True, slots=True)
class OsvAdvisorySnapshot:
    source: str
    source_url: str
    api_version: str
    content_sha256: str
    advisory: OsvAdvisory


@dataclass(frozen=True, slots=True)
class OsvAdvisoryPreview:
    source: str
    source_url: str
    api_version: str
    content_sha256: str
    queried_cve_id: str
    record_id: str
    schema_version: str | None
    modified_at: str
    published_at: str | None
    withdrawn_at: str | None
    summary: str | None
    details: str | None
    aliases: tuple[str, ...]
    upstream: tuple[str, ...]
    total_affected_count: int
    affected: tuple[OsvAffectedPackage, ...]
    affected_truncated: bool
    total_advisory_reference_count: int
    advisory_references: tuple[str, ...]
    advisory_references_truncated: bool
    other_reference_count: int
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OsvAdvisoryEvidenceSelection:
    source: str
    source_url: str
    content_sha256: str
    queried_cve_id: str
    record_id: str
    selected_reference: str
    mutation: VulnerabilityExposureEvidenceMutation
    notes: tuple[str, ...]

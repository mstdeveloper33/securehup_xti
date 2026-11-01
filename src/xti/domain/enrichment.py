"""Recorded network observations and explainable human review ordering."""

from dataclasses import dataclass

from xti.domain.findings import Finding, FindingDetails


@dataclass(frozen=True, slots=True)
class CertificateEvidence:
    sha256: str
    serial_number: str
    not_before: str
    not_after: str
    issuer: str
    subject: str
    dns_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    domain: str
    started_at: str
    finished_at: str
    policy_version: str
    dns_status: str
    addresses: tuple[str, ...]
    tls_status: str
    http_status: str
    http_status_code: int | None
    connected_address: str | None
    errors: tuple[str, ...]
    notes: tuple[str, ...]
    certificate: CertificateEvidence | None = None


@dataclass(frozen=True, slots=True)
class Assessment:
    id: str
    finding_id: str
    result: ProbeResult


@dataclass(frozen=True, slots=True)
class ReviewPriority:
    level: str
    reasons: tuple[str, ...]
    freshness: str
    calculated_at: str
    rule_version: str


@dataclass(frozen=True, slots=True)
class EnrichedFinding:
    details: FindingDetails
    assessments: tuple[Assessment, ...]


@dataclass(frozen=True, slots=True)
class QueueItem:
    finding: Finding
    latest_check: Assessment | None
    priority: ReviewPriority


@dataclass(frozen=True, slots=True)
class BatchCheckResult:
    assessments: tuple[Assessment, ...]
    skipped_fresh: int
    remaining: int

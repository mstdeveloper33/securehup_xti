"""Read-only relationship view assembled from stored surface evidence."""

from dataclasses import dataclass

from xti.domain.mail import MailDnsCheck
from xti.domain.services import ServiceScanCheck
from xti.domain.surface import (
    SurfaceCandidate,
    SurfaceCheck,
    SurfaceDiscoveryRun,
    SurfaceScope,
)


@dataclass(frozen=True, slots=True)
class SurfaceCandidateCounts:
    pending: int
    owned: int
    rejected: int
    total: int


@dataclass(frozen=True, slots=True)
class SurfaceOverviewSnapshot:
    asset_id: str
    asset_value: str
    scope: SurfaceScope | None
    latest_check: SurfaceCheck | None
    latest_mail_check: MailDnsCheck | None
    latest_service_check: ServiceScanCheck | None
    latest_discovery_run: SurfaceDiscoveryRun | None
    candidate_counts: SurfaceCandidateCounts
    candidates: tuple[SurfaceCandidate, ...]


@dataclass(frozen=True, slots=True)
class SurfaceRelation:
    kind: str
    source_type: str
    source_value: str
    target_type: str
    target_value: str
    evidence_type: str
    evidence_id: str
    observed_at: str
    detail: str | None


@dataclass(frozen=True, slots=True)
class SurfaceOverview:
    asset_id: str
    asset_value: str
    scope: SurfaceScope | None
    latest_check: SurfaceCheck | None
    latest_mail_check: MailDnsCheck | None
    latest_service_check: ServiceScanCheck | None
    latest_discovery_run: SurfaceDiscoveryRun | None
    candidate_counts: SurfaceCandidateCounts
    candidates: tuple[SurfaceCandidate, ...]
    relations: tuple[SurfaceRelation, ...]

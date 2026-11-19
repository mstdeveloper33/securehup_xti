"""Local finding notices; read state is independent of a threat review decision."""

from dataclasses import dataclass

from xti.domain.findings import Finding, FindingDetails
from xti.domain.surface import SurfaceCandidate, SurfaceCandidateDetails
from xti.domain.cti_saved_searches import CtiSavedSearchChangeEvidence
from xti.domain.global_saved_searches import GlobalSavedSearchRunReport
from xti.domain.ransomware_watches import RansomwareWatchChangeEvidence
from xti.domain.ransomlook_watches import RansomLookWatchChangeEvidence
from xti.domain.public_notice_watches import PublicNoticeWatchChangeEvidence
from xti.domain.supplier_watches import SupplierWatchRunReport
from xti.domain.brand_username_reviews import (
    BrandUsernameReviewNotificationEvidence,
)


@dataclass(frozen=True, slots=True)
class Notification:
    sequence: int
    id: str
    finding_id: str | None
    event_type: str
    origin: str
    created_at: str
    read_at: str | None
    candidate_id: str | None = None
    evidence_id: str | None = None
    evidence_type: str | None = None
    exposure_id: str | None = None
    cti_run_id: str | None = None
    ransomware_run_id: str | None = None
    brand_candidate_id: str | None = None
    ransomlook_run_id: str | None = None
    public_notice_watch_run_id: str | None = None
    supplier_watch_run_id: str | None = None
    global_search_run_id: str | None = None
    relationship_review_id: str | None = None
    social_change_id: str | None = None


@dataclass(frozen=True, slots=True)
class SurfacePortChange:
    port: int
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class SurfaceChangeEvidence:
    evidence_type: str
    check_id: str
    asset_id: str
    asset_value: str
    changed_fields: tuple[str, ...]
    recorded_at: str
    added_addresses: tuple[str, ...] = ()
    removed_addresses: tuple[str, ...] = ()
    port_changes: tuple[SurfacePortChange, ...] = ()


@dataclass(frozen=True, slots=True)
class VulnerabilityChangeEvidence:
    exposure_id: str
    asset_value: str
    cve_id: str
    decision_status: str
    triggers: tuple[str, ...]
    product_active: bool
    recheck_at: str | None
    nvd_source_record_sha256: str
    product_evidence_updated_at: str
    state_sha256: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class InboxItem:
    notification: Notification
    finding: Finding | None
    candidate: SurfaceCandidate | None = None
    change_evidence: SurfaceChangeEvidence | None = None
    vulnerability_change: VulnerabilityChangeEvidence | None = None
    cti_change: CtiSavedSearchChangeEvidence | None = None
    ransomware_change: RansomwareWatchChangeEvidence | None = None
    brand_profile_review: BrandUsernameReviewNotificationEvidence | None = None
    ransomlook_change: RansomLookWatchChangeEvidence | None = None
    public_notice_change: PublicNoticeWatchChangeEvidence | None = None
    supplier_change: SupplierWatchRunReport | None = None
    global_search_change: GlobalSavedSearchRunReport | None = None
    relationship_change: dict | None = None
    social_change: dict | None = None


@dataclass(frozen=True, slots=True)
class InboxPage:
    items: tuple[InboxItem, ...]
    next_before: int | None
    total_count: int
    unread_count: int
    matching_count: int


@dataclass(frozen=True, slots=True)
class InboxDetails:
    notification: Notification
    details: FindingDetails | None
    candidate_details: SurfaceCandidateDetails | None = None
    change_evidence: SurfaceChangeEvidence | None = None
    vulnerability_change: VulnerabilityChangeEvidence | None = None
    cti_change: CtiSavedSearchChangeEvidence | None = None
    ransomware_change: RansomwareWatchChangeEvidence | None = None
    brand_profile_review: BrandUsernameReviewNotificationEvidence | None = None
    ransomlook_change: RansomLookWatchChangeEvidence | None = None
    public_notice_change: PublicNoticeWatchChangeEvidence | None = None
    supplier_change: SupplierWatchRunReport | None = None
    global_search_change: GlobalSavedSearchRunReport | None = None
    relationship_change: dict | None = None
    social_change: dict | None = None


@dataclass(frozen=True, slots=True)
class MarkResult:
    notifications: tuple[Notification, ...]
    changed_count: int

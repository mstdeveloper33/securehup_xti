"""One bounded, read-only summary of stored external-risk evidence."""

from dataclasses import dataclass

from xti.domain.cti_feeds import CtiFeedRun
from xti.domain.overview import SurfaceOverview
from xti.domain.surface_discovery_status import SurfaceDiscoveryStatusReport
from xti.domain.surface_exposure import SurfaceExposureReport
from xti.domain.surface_freshness import SurfaceFreshnessReport


@dataclass(frozen=True, slots=True)
class AnalysisFindingSample:
    id: str
    domain: str
    status: str
    reasons: tuple[str, ...]
    last_seen_at: str


@dataclass(frozen=True, slots=True)
class AnalysisFindingSummary:
    total: int
    new: int
    suspicious: int
    uncertain: int
    dismissed: int
    samples: tuple[AnalysisFindingSample, ...]
    has_more: bool


@dataclass(frozen=True, slots=True)
class AnalysisIocMatch:
    indicator_id: str
    indicator_type: str
    value: str
    current_source_count: int
    maximum_confidence: int | None


@dataclass(frozen=True, slots=True)
class UnifiedAnalysisReport:
    asset_id: str
    asset_value: str
    observed_at: str
    stored_data_only: bool
    vulnerability_scope: str
    overview: SurfaceOverview
    freshness: SurfaceFreshnessReport
    discovery: SurfaceDiscoveryStatusReport
    exposures: SurfaceExposureReport
    findings: AnalysisFindingSummary
    ioc_catalog_status: str
    ioc_checked_values: tuple[str, ...]
    ioc_matches: tuple[AnalysisIocMatch, ...]
    next_steps: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnifiedAnalysisRefreshResult:
    """An explicit IOC refresh followed by a fresh stored-evidence report."""

    refresh_source: str
    refresh: CtiFeedRun
    report: UnifiedAnalysisReport

"""Read-only freshness view over stored approved surface evidence."""

from dataclasses import dataclass

from xti.domain.mail import MailDnsCheck
from xti.domain.cname import CnameDnsCheck
from xti.domain.services import ServiceScanCheck
from xti.domain.surface import SurfaceCheck, SurfaceDiscoveryRun, SurfaceScope


@dataclass(frozen=True, slots=True)
class SurfaceFreshnessSnapshot:
    asset_id: str
    asset_value: str
    scope: SurfaceScope | None
    latest_check: SurfaceCheck | None
    latest_mail_check: MailDnsCheck | None
    latest_service_check: ServiceScanCheck | None
    latest_cname_check: CnameDnsCheck | None = None
    latest_discovery_run: SurfaceDiscoveryRun | None = None


@dataclass(frozen=True, slots=True)
class SurfaceFreshnessItem:
    check_type: str
    freshness: str
    age_seconds: int | None
    evidence_id: str | None
    recorded_at: str | None
    result_status: str
    change_kind: str | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SurfaceFreshnessReport:
    asset_id: str
    asset_value: str
    observed_at: str
    freshness_hours: int
    scope_status: str
    current_count: int
    stale_count: int
    never_count: int
    clock_error_count: int
    items: tuple[SurfaceFreshnessItem, ...]
    notes: tuple[str, ...]

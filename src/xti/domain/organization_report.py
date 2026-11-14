"""Source-preserving, current-membership organization report models."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from xti.domain.assets import ValidationError
from xti.domain.cname import CnameDnsCheck
from xti.domain.mail import MailDnsCheck
from xti.domain.organization_scope import OrganizationScope
from xti.domain.organizations import OrganizationLinkView
from xti.domain.public_notices import PublicNotice
from xti.domain.public_notice_watches import PublicNoticeWatchDetails
from xti.domain.services import ServiceScanCheck
from xti.domain.surface import SurfaceCheck
from xti.domain.surface_freshness import SurfaceFreshnessSnapshot


@dataclass(frozen=True, slots=True)
class ReportNavigation:
    label: str
    arguments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OrganizationReportRecord:
    id: str
    kind: str
    value: str
    status: str
    recorded_at: str
    source: str
    details: tuple[str, ...] = ()
    run_id: str | None = None
    source_run_id: str | None = None
    definition_sha256: str | None = None
    navigation: tuple[ReportNavigation, ...] = ()
    public_notice: PublicNotice | None = None


@dataclass(frozen=True, slots=True)
class OrganizationReportPage:
    kind: str
    items: tuple[OrganizationReportRecord, ...]
    total_count: int
    offset: int
    limit: int
    has_more: bool


@dataclass(frozen=True, slots=True)
class OrganizationReportAttempt:
    id: str
    status: str
    recorded_at: str
    error: str | None = None
    source_run_id: str | None = None
    definition_sha256: str | None = None
    definition_matches_current: bool | None = None
    is_baseline: bool | None = None


@dataclass(frozen=True, slots=True)
class OrganizationReportCoverage:
    family: str
    source: str
    latest_attempt: OrganizationReportAttempt | None
    latest_success: OrganizationReportAttempt | None
    freshness: str
    notes: tuple[str, ...] = ()


def report_freshness(at: str | None, observed_at: str, stale_after_hours: int) -> str:
    if at is None:
        return "never"
    try:
        value, now = datetime.fromisoformat(at), datetime.fromisoformat(observed_at)
        if any(item.tzinfo is None or item.utcoffset() is None for item in (value, now)):
            raise ValueError("timezone required")
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("Kuruluş raporunda saat dilimli kayıt zamanı gerekli.") from error
    if value > now:
        return "clock_error"
    return "current" if now - value < timedelta(hours=stale_after_hours) else "stale"


def surface_result_status(check: SurfaceCheck | MailDnsCheck | ServiceScanCheck | CnameDnsCheck) -> str:
    """Describe collection completeness; this is never a safety verdict."""
    result = check.result
    if isinstance(check, SurfaceCheck):
        if result.dns_status in {"failed", "blocked"}:
            return "failed"
    elif isinstance(check, MailDnsCheck):
        if all(value == "failed" for value in (result.mx_status, result.spf_status, result.dmarc_status)):
            return "failed"
    elif isinstance(check, ServiceScanCheck):
        if result.dns_status != "resolved":
            return "failed"
        if any(port.state == "unknown" for port in result.ports):
            return "partial"
    elif isinstance(check, CnameDnsCheck):
        if result.alias_status == "failed":
            return "failed"
    else:
        raise ValidationError("Kuruluş raporunda yüzey kanıtı türü geçersiz.")
    return "partial" if result.errors else "complete"


@dataclass(frozen=True, slots=True)
class OrganizationReportTarget:
    membership: OrganizationLinkView
    current_definition: tuple[tuple[str, str], ...]
    coverage: tuple[OrganizationReportCoverage, ...]
    sections: tuple[OrganizationReportPage, ...]
    navigation: tuple[ReportNavigation, ...]
    notes: tuple[str, ...]
    surface: SurfaceFreshnessSnapshot | None = None


@dataclass(frozen=True, slots=True)
class OrganizationReport:
    scope: OrganizationScope
    observed_at: str
    stored_data_only: bool
    stale_after_hours: int
    targets: tuple[OrganizationReportTarget, ...]
    total_target_count: int
    target_offset: int
    target_limit: int
    item_offset: int
    item_limit: int
    has_more_targets: bool
    notes: tuple[str, ...]
    schema_version: int
    public_notice_watch: PublicNoticeWatchDetails | None = None

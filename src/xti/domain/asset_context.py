"""Human business criticality and read-only internet reachability context."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.services import ServiceScanCheck
from xti.domain.surface import SurfaceCheck, SurfaceScope


ASSET_CRITICALITY_LEVELS = {"low", "medium", "high", "critical"}
ASSET_CRITICALITY_ACTIONS = {"set", "updated", "reactivated", "cleared"}
INTERNET_REACHABILITY_STATUSES = {
    "confirmed", "dns_only", "not_confirmed", "unknown",
}
INTERNET_EVIDENCE_FRESHNESS = {
    "current", "stale", "clock_error", "never", "scope_inactive", "not_enabled",
}


def normalize_asset_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Geçerli bir varlık kimliği gerekli.")
    try:
        normalized = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError("Geçerli bir varlık kimliği gerekli.") from error
    if value != normalized:
        raise ValidationError("Varlık kimliği kanonik UUID biçiminde olmalı.")
    return normalized


def normalize_criticality_level(value: str) -> str:
    if not isinstance(value, str) or value not in ASSET_CRITICALITY_LEVELS:
        raise ValidationError("Varlık önemi low, medium, high veya critical olmalı.")
    return value


def normalize_criticality_reason(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Varlık önemi gerekçesi gerekli.")
    normalized = " ".join(value.strip().split())
    if (
        not 5 <= len(normalized) <= 2000
        or any(not character.isprintable() for character in normalized)
    ):
        raise ValidationError("Varlık önemi gerekçesi 5–2000 güvenli karakter olmalı.")
    return normalized


@dataclass(frozen=True, slots=True)
class AssetCriticality:
    asset_id: str
    asset_value: str
    level: str
    active: bool
    reason: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AssetCriticalityEvent:
    id: str
    asset_id: str
    action: str
    level: str
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class AssetCriticalityDetails:
    record: AssetCriticality
    events: tuple[AssetCriticalityEvent, ...]
    total_event_count: int


@dataclass(frozen=True, slots=True)
class AssetCriticalityMutation:
    action: str
    changed: bool
    record: AssetCriticality


@dataclass(frozen=True, slots=True)
class AssetInternetExposureContext:
    status: str
    freshness: str
    checked_at: str
    stale_after_hours: int
    current_sources: tuple[str, ...]
    latest_evidence_at: str | None
    web_http_status_code: int | None
    open_service_ports: tuple[int, ...]
    reasons: tuple[str, ...]


def _evidence_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("Dış yüzey kanıt zamanı geçersiz.") from error


def build_internet_exposure_context(
    scope: SurfaceScope | None, web: SurfaceCheck | None,
    services: ServiceScanCheck | None, *, checked_at: datetime,
    stale_after_hours: int,
) -> AssetInternetExposureContext:
    """Explain recorded reachability without turning absence into a safety claim."""

    if (
        not isinstance(checked_at, datetime) or checked_at.tzinfo is None
        or checked_at.utcoffset() is None
    ):
        raise ValidationError("Erişilebilirlik değerlendirme zamanı geçersiz.")
    if type(stale_after_hours) is not int or not 1 <= stale_after_hours <= 8760:
        raise ValidationError("Erişilebilirlik güncellik eşiği 1–8760 saat olmalı.")
    now = checked_at.astimezone(timezone.utc)
    checked_at_text = now.isoformat()
    if scope is None:
        return AssetInternetExposureContext(
            "unknown", "not_enabled", checked_at_text, stale_after_hours, (), None,
            None, (), ("no_surface_scope",),
        )
    if not scope.active:
        return AssetInternetExposureContext(
            "unknown", "scope_inactive", checked_at_text, stale_after_hours, (), None,
            None, (), ("surface_scope_inactive",),
        )
    evidence = tuple(item for item in (web, services) if item is not None)
    if not evidence:
        return AssetInternetExposureContext(
            "unknown", "never", checked_at_text, stale_after_hours, (), None,
            None, (), ("no_surface_evidence",),
        )
    times = tuple(_evidence_time(item.recorded_at) for item in evidence)
    latest = max(times)
    if any(value > now for value in times):
        return AssetInternetExposureContext(
            "unknown", "clock_error", checked_at_text, stale_after_hours, (),
            latest.isoformat(), None, (), ("surface_evidence_clock_error",),
        )
    threshold = timedelta(hours=stale_after_hours)
    current_web = web if web is not None and now - _evidence_time(web.recorded_at) < threshold else None
    current_services = (
        services if services is not None
        and now - _evidence_time(services.recorded_at) < threshold else None
    )
    if current_web is None and current_services is None:
        return AssetInternetExposureContext(
            "unknown", "stale", checked_at_text, stale_after_hours, (), latest.isoformat(),
            None, (), ("surface_evidence_stale",),
        )
    current_sources = tuple(
        name for name, item in (("web", current_web), ("services", current_services))
        if item is not None
    )
    web_code = None
    web_reachable = False
    dns_observed = False
    if current_web is not None:
        result = current_web.result
        dns_observed = result.dns_status == "resolved" and bool(result.addresses)
        web_reachable = (
            dns_observed and result.tls_status == "valid"
            and result.http_status == "responded"
            and type(result.http_status_code) is int
            and 100 <= result.http_status_code <= 599
        )
        if web_reachable:
            web_code = result.http_status_code
    open_ports: tuple[int, ...] = ()
    if current_services is not None:
        result = current_services.result
        dns_observed = dns_observed or (
            result.dns_status == "resolved" and bool(result.addresses)
        )
        open_ports = tuple(item.port for item in result.ports if item.state == "open")
    reasons: list[str] = []
    if web_reachable:
        reasons.append("https_response_observed")
    if open_ports:
        reasons.append("open_tcp_service_observed")
    if web_reachable or open_ports:
        status = "confirmed"
    elif dns_observed:
        status = "dns_only"
        reasons.append("dns_resolution_observed")
    else:
        status = "not_confirmed"
        reasons.append("reachability_not_confirmed")
    return AssetInternetExposureContext(
        status, "current", checked_at_text, stale_after_hours, current_sources,
        latest.isoformat(), web_code, open_ports, tuple(reasons),
    )


def validate_criticality_record(record: AssetCriticality) -> AssetCriticality:
    """Validate cross-layer records without importing persistence details."""

    normalize_asset_id(record.asset_id)
    if normalize_domain(record.asset_value) != record.asset_value:
        raise ValidationError("Varlık önemi kaydındaki adres kanonik değil.")
    normalize_criticality_level(record.level)
    if type(record.active) is not bool:
        raise ValidationError("Varlık önemi etkinlik durumu geçersiz.")
    normalize_criticality_reason(record.reason)
    return record

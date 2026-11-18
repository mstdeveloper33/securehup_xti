"""Source-bound supplier claim candidates without breach or risk conclusions."""

from dataclasses import dataclass
import re
import unicodedata
from uuid import NAMESPACE_URL, UUID, uuid5

from xti.domain.assets import ValidationError
from xti.domain.suppliers import Supplier, normalize_supplier_id
from xti.domain.ransomware_claims import RANSOMWARE_SOURCE_NAME, RANSOMWARE_SOURCE_URL, ransomware_claim_state_sha256
from xti.domain.ransomlook_ransomware import RANSOMLOOK_SOURCE_NAME, RANSOMLOOK_SOURCE_URL, ransomlook_claim_state_sha256
from xti.domain.ransomware_watches import ransomware_claim_website_host


SUPPLIER_THREAT_SOURCE_KEYS = frozenset({"threatcluster", "ransomlook"})
SUPPLIER_THREAT_SOURCE_FILTERS = frozenset({"all", *SUPPLIER_THREAT_SOURCE_KEYS})
SUPPLIER_THREAT_COVERAGE_STATES = frozenset({
    "available", "stale_after_failure", "not_collected", "unavailable",
})
_SHA256 = re.compile(r"[0-9a-f]{64}")


def normalize_supplier_threat_source(value: str) -> str:
    if not isinstance(value, str) or value not in SUPPLIER_THREAT_SOURCE_FILTERS:
        raise ValidationError(
            "Tedarikçi olay kaynağı all, threatcluster veya ransomlook olmalı."
        )
    return value


def normalize_supplier_threat_event_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Geçerli bir tedarikçi olay kimliği gerekli.")
    try:
        normalized = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError("Geçerli bir tedarikçi olay kimliği gerekli.") from error
    if normalized != value:
        raise ValidationError("Tedarikçi olay kimliği kanonik UUID biçiminde olmalı.")
    return normalized


def supplier_threat_event_id(
    *, supplier_id: str, source_key: str, claim_id: str,
) -> str:
    supplier_id = normalize_supplier_id(supplier_id)
    if source_key not in SUPPLIER_THREAT_SOURCE_KEYS:
        raise ValidationError("Tedarikçi olay kaynak kimliği geçersiz.")
    if not isinstance(claim_id, str) or _SHA256.fullmatch(claim_id) is None:
        raise ValidationError("Tedarikçi olay kaynak kayıt kimliği geçersiz.")
    return str(uuid5(
        NAMESPACE_URL,
        f"xti:supplier-threat-event:v1:{supplier_id}:{source_key}:{claim_id}",
    ))


@dataclass(frozen=True, slots=True)
class SupplierThreatMatchEvidence:
    field: str
    value: str
    match_type: str


@dataclass(frozen=True, slots=True)
class SupplierThreatSourceCoverage:
    source_key: str
    source_name: str
    state: str
    latest_attempt_id: str | None
    latest_attempt_status: str | None
    latest_attempt_finished_at: str | None
    latest_attempt_error: str | None
    snapshot_run_id: str | None
    snapshot_finished_at: str | None
    fetched_at: str | None
    window_days: int | None
    source_record_count: int
    claim_count: int


@dataclass(frozen=True, slots=True)
class SupplierThreatEvent:
    id: str
    supplier_id: str
    supplier_name: str
    supplier_domain: str
    supplier_criticality: str
    source_key: str
    source_name: str
    source_url: str
    source_run_id: str
    claim_id: str
    claim_state_sha256: str
    group: str
    victim: str
    website: str | None
    discovered_at: str
    claim_status: str | None
    match_evidence: tuple[SupplierThreatMatchEvidence, ...]
    same_name_supplier_count: int


@dataclass(frozen=True, slots=True)
class SupplierThreatEventReport:
    active_supplier_count: int
    selected_supplier_id: str | None
    source_filter: str
    coverage: tuple[SupplierThreatSourceCoverage, ...]
    total_event_count: int
    displayed_count: int
    has_more: bool
    events: tuple[SupplierThreatEvent, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SupplierThreatEventDetails:
    event: SupplierThreatEvent
    coverage: SupplierThreatSourceCoverage
    notes: tuple[str, ...]


def supplier_threat_coverage(
    *, source_key: str, source_name: str, latest, complete,
) -> SupplierThreatSourceCoverage:
    if complete is None:
        state = "not_collected" if latest is None else "unavailable"
    elif latest is not None and latest.id != complete.id and latest.status == "failed":
        state = "stale_after_failure"
    else:
        state = "available"
    return SupplierThreatSourceCoverage(
        source_key=source_key,
        source_name=source_name,
        state=state,
        latest_attempt_id=latest.id if latest is not None else None,
        latest_attempt_status=latest.status if latest is not None else None,
        latest_attempt_finished_at=latest.finished_at if latest is not None else None,
        latest_attempt_error=latest.error if latest is not None else None,
        snapshot_run_id=complete.id if complete is not None else None,
        snapshot_finished_at=complete.finished_at if complete is not None else None,
        fetched_at=complete.fetched_at if complete is not None else None,
        window_days=complete.window_days if complete is not None else None,
        source_record_count=complete.source_record_count if complete is not None else 0,
        claim_count=complete.claim_count if complete is not None else 0,
    )

def supplier_claim_name_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _domain_matches(host: str | None, domain: str) -> tuple[SupplierThreatMatchEvidence, ...]:
    if host is None:
        return ()
    if host == domain:
        return (SupplierThreatMatchEvidence("website", host, "exact"),)
    if host.endswith("." + domain):
        return (SupplierThreatMatchEvidence("website", host, "subdomain"),)
    return ()


def supplier_claim_event(supplier, claim, *, source_key, source_run_id, same_name_count):
    """The same exact-name/domain rule for standalone and composed readers."""
    if source_key not in SUPPLIER_THREAT_SOURCE_KEYS:
        raise ValidationError("Tedarikçi olay kaynak kimliği geçersiz.")
    threatcluster = source_key == "threatcluster"
    host = ransomware_claim_website_host(claim.website) if threatcluster else None
    matches = list(_domain_matches(host, supplier.primary_domain))
    if supplier_claim_name_key(claim.victim) == supplier.name_key:
        matches.append(SupplierThreatMatchEvidence("victim", claim.victim, "exact"))
    if not matches:
        return None
    return SupplierThreatEvent(
        id=supplier_threat_event_id(supplier_id=supplier.id, source_key=source_key, claim_id=claim.id),
        supplier_id=supplier.id, supplier_name=supplier.display_name,
        supplier_domain=supplier.primary_domain, supplier_criticality=supplier.criticality,
        source_key=source_key, source_name=RANSOMWARE_SOURCE_NAME if threatcluster else RANSOMLOOK_SOURCE_NAME,
        source_url=RANSOMWARE_SOURCE_URL if threatcluster else RANSOMLOOK_SOURCE_URL,
        source_run_id=source_run_id, claim_id=claim.id,
        claim_state_sha256=(ransomware_claim_state_sha256 if threatcluster else ransomlook_claim_state_sha256)(claim),
        group=claim.group, victim=claim.victim, website=host, discovered_at=claim.discovered_at,
        claim_status=claim.status if threatcluster else None, match_evidence=tuple(matches),
        same_name_supplier_count=same_name_count,
    )

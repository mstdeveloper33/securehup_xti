"""Source-bound supplier claim candidates without breach or risk conclusions."""

from dataclasses import dataclass
import re
from uuid import NAMESPACE_URL, UUID, uuid5

from xti.domain.assets import ValidationError
from xti.domain.suppliers import normalize_supplier_id


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

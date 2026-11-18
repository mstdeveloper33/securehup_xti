"""Explainable supplier review cards built only from explicit local evidence."""

from dataclasses import dataclass
from datetime import datetime

from xti.domain.supplier_candidates import SupplierCandidate
from xti.domain.supplier_threat_events import (
    SupplierThreatEvent,
    SupplierThreatSourceCoverage,
)
from xti.domain.suppliers import Supplier


SUPPLIER_ATTENTION_LEVELS = frozenset({
    "priority_review",
    "review",
    "identity_review",
    "insufficient_data",
    "no_current_match",
})


@dataclass(frozen=True, slots=True)
class SupplierRiskCard:
    supplier: Supplier
    attention: str
    current_dependency_count: int
    claim_candidate_count: int
    matched_source_count: int
    domain_evidence_count: int
    name_only_evidence_count: int
    ambiguous_name_count: int
    available_source_count: int
    degraded_source_count: int
    missing_source_count: int
    newest_claim_at: str | None
    newest_snapshot_at: str | None
    event_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    missing_data: tuple[str, ...]
    next_actions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SupplierRiskReport:
    total_supplier_count: int
    displayed_count: int
    has_more: bool
    priority_review_count: int
    review_count: int
    identity_review_count: int
    insufficient_data_count: int
    no_current_match_count: int
    coverage: tuple[SupplierThreatSourceCoverage, ...]
    cards: tuple[SupplierRiskCard, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SupplierRiskCardDetails:
    card: SupplierRiskCard
    coverage: tuple[SupplierThreatSourceCoverage, ...]
    dependencies: tuple[SupplierCandidate, ...]
    events: tuple[SupplierThreatEvent, ...]
    notes: tuple[str, ...]


def _latest(values: tuple[str, ...]) -> str | None:
    if not values:
        return None
    return max(values, key=lambda value: datetime.fromisoformat(value))


def _has_domain_evidence(event: SupplierThreatEvent) -> bool:
    return any(item.field == "website" for item in event.match_evidence)


def supplier_missing_data(
    coverage: tuple[SupplierThreatSourceCoverage, ...],
) -> tuple[str, ...]:
    missing = []
    for source in coverage:
        if source.state == "not_collected":
            missing.append(f"{source.source_key}: henüz yerel snapshot yok")
        elif source.state == "unavailable":
            missing.append(f"{source.source_key}: başarılı snapshot yok; son deneme hatalı")
        elif source.state == "stale_after_failure":
            missing.append(
                f"{source.source_key}: son deneme hatalı; önceki başarılı snapshot kullanılıyor"
            )
    missing.append("ransomlook: kaynak domain sağlamaz; yalnız tam kuruluş adı kullanılabilir")
    return tuple(missing)

def build_supplier_risk_card(
    supplier: Supplier,
    coverage: tuple[SupplierThreatSourceCoverage, ...],
    dependencies: tuple[SupplierCandidate, ...],
    events: tuple[SupplierThreatEvent, ...],
) -> SupplierRiskCard:
    domain_events = tuple(item for item in events if _has_domain_evidence(item))
    name_only = tuple(item for item in events if not _has_domain_evidence(item))
    ambiguous = tuple(
        item for item in name_only if item.same_name_supplier_count > 1
    )
    unambiguous = tuple(
        item for item in events
        if _has_domain_evidence(item) or item.same_name_supplier_count == 1
    )
    snapshots = tuple(
        item.snapshot_finished_at for item in coverage
        if item.snapshot_finished_at is not None
    )
    available = sum(item.snapshot_run_id is not None for item in coverage)
    degraded = sum(item.state in {"stale_after_failure", "unavailable"} for item in coverage)
    missing = sum(item.state in {"not_collected", "unavailable"} for item in coverage)

    reasons = []
    if events:
        reasons.append(
            f"Son yerel snapshot'larda {len(events)} kaynak iddiası adayı eşleşti."
        )
    if domain_events:
        reasons.append(
            f"{len(domain_events)} adayda kaynak web domaini tedarikçi domainiyle eşleşti."
        )
    if ambiguous:
        reasons.append(
            f"{len(ambiguous)} ad eşleşmesi aynı isimli birden fazla tedarikçiyi ayıramıyor."
        )
    if supplier.criticality in {"high", "critical"}:
        reasons.append(
            f"İnsan tarafından beyan edilen iş önemi {supplier.criticality}."
        )
    if dependencies:
        reasons.append(
            f"{len(dependencies)} güncel CNAME bağı insan kararıyla bu tedarikçiye bağlandı."
        )

    if unambiguous:
        attention = (
            "priority_review"
            if supplier.criticality in {"high", "critical"}
            else "review"
        )
    elif events:
        attention = "identity_review"
    elif available == 0:
        attention = "insufficient_data"
        reasons.append("Hiçbir ransomware kaynağında başarılı yerel snapshot yok.")
    else:
        attention = "no_current_match"
        reasons.append(
            "İncelenen son başarılı yerel snapshot'larda güncel eşleşme bulunmadı."
        )

    if attention == "priority_review":
        actions = (
            "Eşleşme dayanaklarını event-show ile incele.",
            "İddiayı bağımsız ve yetkili kaynaklarla doğrula; tedarikçi etkisini varsayma.",
            "Kritik ilişki için tedarikçi güvenlik irtibatıyla insan onaylı doğrulama yap.",
        )
    elif attention == "review":
        actions = (
            "Eşleşme dayanaklarını event-show ile incele.",
            "İddiayı bağımsız kaynaklarla doğrula; otomatik aksiyon alma.",
        )
    elif attention == "identity_review":
        actions = (
            "Aynı isimli kuruluşları ana domain ve sözleşme bilgisiyle ayır.",
            "Yalnız isim eşleşmesini ihlal kanıtı sayma.",
        )
    elif attention == "insufficient_data":
        actions = (
            "ThreatCluster ve RansomLook kaynaklarını açık yenileme komutlarıyla çalıştır.",
            "Veri olmadan güvenli veya risksiz sonucu çıkarma.",
        )
    else:
        actions = (
            "Kaynak güncelliğini koru ve sonraki snapshot değişimlerini izle.",
            "Eşleşme yokluğunu güvenli olma kanıtı sayma.",
        )

    return SupplierRiskCard(
        supplier=supplier,
        attention=attention,
        current_dependency_count=len(dependencies),
        claim_candidate_count=len(events),
        matched_source_count=len({item.source_key for item in events}),
        domain_evidence_count=len(domain_events),
        name_only_evidence_count=len(name_only),
        ambiguous_name_count=len(ambiguous),
        available_source_count=available,
        degraded_source_count=degraded,
        missing_source_count=missing,
        newest_claim_at=_latest(tuple(item.discovered_at for item in events)),
        newest_snapshot_at=_latest(snapshots),
        event_ids=tuple(item.id for item in events),
        reasons=tuple(reasons),
        missing_data=supplier_missing_data(coverage),
        next_actions=actions,
    )

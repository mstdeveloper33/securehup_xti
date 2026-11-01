"""Compose supplier inventory, dependency decisions and claim evidence locally."""

from datetime import datetime

from xti.domain.assets import ValidationError
from xti.domain.supplier_candidates import SupplierCandidate
from xti.domain.supplier_risk import (
    SupplierRiskCard,
    SupplierRiskCardDetails,
    SupplierRiskReport,
)
from xti.domain.supplier_threat_events import (
    SupplierThreatEvent,
    SupplierThreatSourceCoverage,
)
from xti.domain.suppliers import Supplier, normalize_supplier_id
from xti.application.supplier_threat_events import SupplierThreatEventService
from xti.ports.supplier_candidates import SupplierCandidateRepository
from xti.ports.suppliers import SupplierRepository


_ATTENTION_ORDER = {
    "priority_review": 0,
    "review": 1,
    "identity_review": 2,
    "insufficient_data": 3,
    "no_current_match": 4,
}
_MAX_SUPPLIERS = 500


def _latest(values: tuple[str, ...]) -> str | None:
    if not values:
        return None
    return max(values, key=lambda value: datetime.fromisoformat(value))


def _has_domain_evidence(event: SupplierThreatEvent) -> bool:
    return any(item.field == "website" for item in event.match_evidence)


class SupplierRiskService:
    """Build review priority cards; never assert a breach or a numeric risk."""

    def __init__(
        self,
        supplier_repository: SupplierRepository,
        candidate_repository: SupplierCandidateRepository,
        event_service: SupplierThreatEventService,
    ) -> None:
        self.suppliers = supplier_repository
        self.candidates = candidate_repository
        self.events = event_service

    @staticmethod
    def _limit(value: int) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError("Tedarikçi risk kartı sınırı 1–500 arasında olmalı.")
        return value

    def _inventory(self) -> tuple[Supplier, ...]:
        records = self.suppliers.list(active_only=True, limit=_MAX_SUPPLIERS)
        return tuple(
            self.suppliers.show(item.id, event_limit=1).supplier for item in records
        )

    @staticmethod
    def _missing_data(
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

    @staticmethod
    def _card(
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
            missing_data=SupplierRiskService._missing_data(coverage),
            next_actions=actions,
        )

    def _build(self):
        suppliers = self._inventory()
        event_report = self.events.evidence()
        dependencies = self.candidates.list(
            status="accepted", current_only=True, limit=500,
        )
        events_by_supplier: dict[str, list[SupplierThreatEvent]] = {
            item.id: [] for item in suppliers
        }
        dependencies_by_supplier: dict[str, list[SupplierCandidate]] = {
            item.id: [] for item in suppliers
        }
        for event in event_report.events:
            if event.supplier_id in events_by_supplier:
                events_by_supplier[event.supplier_id].append(event)
        for candidate in dependencies:
            if candidate.supplier_id in dependencies_by_supplier:
                dependencies_by_supplier[candidate.supplier_id].append(candidate)
        cards = tuple(
            self._card(
                supplier,
                event_report.coverage,
                tuple(dependencies_by_supplier[supplier.id]),
                tuple(events_by_supplier[supplier.id]),
            )
            for supplier in suppliers
        )
        cards = tuple(sorted(cards, key=lambda item: (
            _ATTENTION_ORDER[item.attention],
            item.supplier.display_name.casefold(),
            item.supplier.primary_domain,
            item.supplier.id,
        )))
        return cards, event_report.coverage, dependencies_by_supplier, events_by_supplier

    def list(self, *, limit: int = 100) -> SupplierRiskReport:
        limit = self._limit(limit)
        cards, coverage, _, _ = self._build()
        selected = cards[:limit]
        counts = {
            key: sum(card.attention == key for card in cards)
            for key in _ATTENTION_ORDER
        }
        return SupplierRiskReport(
            total_supplier_count=len(cards),
            displayed_count=len(selected),
            has_more=len(cards) > len(selected),
            priority_review_count=counts["priority_review"],
            review_count=counts["review"],
            identity_review_count=counts["identity_review"],
            insufficient_data_count=counts["insufficient_data"],
            no_current_match_count=counts["no_current_match"],
            coverage=coverage,
            cards=selected,
            notes=(
                "Kartlar yalnız yerel, kaynaklı kanıtı ve insan beyanlı iş önemini birleştirir.",
                "İnceleme önceliği sayısal risk skoru, doğrulanmış ihlal veya kullanıcı etkisi değildir.",
                "Eksik/eski kaynak verisi ve sıfır eşleşme ayrı gösterilir.",
                "Komut internet kullanmaz, veri yazmaz, alarm veya dış aksiyon üretmez.",
            ),
        )

    def show(self, supplier_id: str) -> SupplierRiskCardDetails:
        supplier_id = normalize_supplier_id(supplier_id)
        cards, coverage, dependencies, events = self._build()
        card = next(
            (item for item in cards if item.supplier.id == supplier_id), None,
        )
        if card is None:
            raise ValidationError("Etkin tedarikçi risk kartı bulunamadı.")
        return SupplierRiskCardDetails(
            card=card,
            coverage=coverage,
            dependencies=tuple(dependencies[supplier_id]),
            events=tuple(events[supplier_id]),
            notes=(
                "Bu kart karar desteğidir; doğrulanmış ihlal veya otomatik risk hükmü değildir.",
                "Kaynak iddiaları, CNAME bağları ve tedarikçi kaydı ayrı kanıt kimliklerini korur.",
            ),
        )

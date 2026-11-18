"""Compose supplier inventory, dependency decisions and claim evidence locally."""

from xti.domain.assets import ValidationError
from xti.domain.supplier_candidates import SupplierCandidate
from xti.domain.supplier_risk import (
    build_supplier_risk_card,
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
            build_supplier_risk_card(
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

"""Offline supplier views over independently stored public claim snapshots."""

from datetime import datetime

from xti.domain.assets import ValidationError
from xti.domain.ransomlook_ransomware import (
    RANSOMLOOK_SOURCE_NAME,
)
from xti.domain.ransomware_claims import (
    RANSOMWARE_SOURCE_NAME,
)
from xti.domain.supplier_threat_events import (
    SupplierThreatEvent,
    SupplierThreatEventDetails,
    SupplierThreatEventReport,
    SupplierThreatSourceCoverage,
    normalize_supplier_threat_event_id,
    normalize_supplier_threat_source,
    supplier_claim_event, supplier_threat_coverage, supplier_claim_name_key,
)
from xti.domain.suppliers import Supplier, normalize_supplier_id
from xti.ports.ransomlook_ransomware import RansomLookClaimRepository
from xti.ports.ransomware_claims import RansomwareClaimRepository
from xti.ports.suppliers import SupplierRepository


_MAX_ACTIVE_SUPPLIERS = 500
_MAX_EVENTS = 100_000
_SOURCE_ORDER = {"threatcluster": 0, "ransomlook": 1}


class SupplierThreatEventService:
    """Correlate local supplier records with claims; never refresh or persist."""

    def __init__(
        self,
        supplier_repository: SupplierRepository,
        threatcluster_repository: RansomwareClaimRepository,
        ransomlook_repository: RansomLookClaimRepository,
    ) -> None:
        self.suppliers = supplier_repository
        self.threatcluster = threatcluster_repository
        self.ransomlook = ransomlook_repository

    @staticmethod
    def _limit(value: int) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError("Tedarikçi olay görünüm sınırı 1–500 arasında olmalı.")
        return value

    @staticmethod
    def _notes() -> tuple[str, ...]:
        return (
            "Sonuçlar yalnız iki kaynağın son başarılı yerel snapshot'ından gelir; "
            "komut internet kullanmaz ve veri yazmaz.",
            "Kayıtlar ransomware gruplarının kamuya açık iddialarıdır; doğrulanmış "
            "ihlal, tedarikçi etkisi veya risk puanı değildir.",
            "Eşleşme yalnız tam normalleştirilmiş kuruluş adı veya ThreatCluster'ın "
            "sağladığı ilk-taraf web domainiyle yapılır; yaklaşık ad benzerliği yoktur.",
            "Aynı isimli birden fazla tedarikçi isim eşleşmesini belirsiz kılabilir; "
            "domain kanıtı ayrıca gösterilir.",
            "Eksik veya başarısız kaynak kapsamı eşleşme yokluğundan ayrı gösterilir.",
        )

    def _active_suppliers(self, selected: str | None) -> tuple[Supplier, ...]:
        records = self.suppliers.list(
            active_only=True, limit=_MAX_ACTIVE_SUPPLIERS,
        )
        # Validate every selected lifecycle, not just the materialized supplier row.
        records = tuple(
            self.suppliers.show(record.id, event_limit=1).supplier
            for record in records
        )
        if selected is None:
            return records
        selected = normalize_supplier_id(selected)
        match = next((record for record in records if record.id == selected), None)
        if match is None:
            raise ValidationError("Etkin tedarikçi kaydı bulunamadı.")
        return (match,)

    def _build(
        self, *, supplier_id: str | None, source: str,
    ) -> tuple[tuple[Supplier, ...], tuple[SupplierThreatSourceCoverage, ...], tuple[SupplierThreatEvent, ...]]:
        source = normalize_supplier_threat_source(source)
        inventory = self._active_suppliers(None)
        suppliers = inventory
        if supplier_id is not None:
            supplier_id = normalize_supplier_id(supplier_id)
            suppliers = tuple(record for record in inventory if record.id == supplier_id)
            if not suppliers:
                raise ValidationError("Etkin tedarikçi kaydı bulunamadı.")
        name_counts = {}
        for record in inventory:
            name_counts[record.name_key] = name_counts.get(record.name_key, 0) + 1
        coverage, events = [], []
        for key, name, repository in (
            ("threatcluster", RANSOMWARE_SOURCE_NAME, self.threatcluster),
            ("ransomlook", RANSOMLOOK_SOURCE_NAME, self.ransomlook),
        ):
            if source not in {"all", key}:
                continue
            status = repository.status(run_limit=1)
            coverage.append(supplier_threat_coverage(source_key=key, source_name=name,
                latest=status.latest_run, complete=status.latest_complete_run))
            if status.latest_complete_run is None:
                continue
            snapshot = repository.latest_snapshot()
            for claim in snapshot.claims:
                for record in suppliers:
                    event = supplier_claim_event(record, claim, source_key=key,
                        source_run_id=snapshot.run.id, same_name_count=name_counts.get(supplier_claim_name_key(claim.victim), 0))
                    if event is not None:
                        events.append(event)
                        if len(events) > _MAX_EVENTS:
                            raise ValidationError("Tedarikçi olay adayı güvenli sınırı aştı; tek tedarikçi veya kaynak seçin.")

        events.sort(key=lambda item: (
            -datetime.fromisoformat(item.discovered_at).timestamp(),
            _SOURCE_ORDER[item.source_key], item.supplier_name.casefold(), item.id,
        ))
        return suppliers, tuple(coverage), tuple(events)

    def list(
        self, *, supplier_id: str | None = None, source: str = "all",
        limit: int = 100,
    ) -> SupplierThreatEventReport:
        limit = self._limit(limit)
        normalized_supplier = (
            normalize_supplier_id(supplier_id) if supplier_id is not None else None
        )
        source = normalize_supplier_threat_source(source)
        complete = self.evidence(
            supplier_id=normalized_supplier, source=source,
        )
        selected = complete.events[:limit]
        return SupplierThreatEventReport(
            active_supplier_count=complete.active_supplier_count,
            selected_supplier_id=normalized_supplier,
            source_filter=source,
            coverage=complete.coverage,
            total_event_count=complete.total_event_count,
            displayed_count=len(selected),
            has_more=complete.total_event_count > len(selected),
            events=selected,
            notes=complete.notes,
        )

    def evidence(
        self, *, supplier_id: str | None = None, source: str = "all",
    ) -> SupplierThreatEventReport:
        """Return the complete bounded local evidence set for composed views."""
        normalized_supplier = (
            normalize_supplier_id(supplier_id) if supplier_id is not None else None
        )
        source = normalize_supplier_threat_source(source)
        suppliers, coverage, events = self._build(
            supplier_id=normalized_supplier, source=source,
        )
        return SupplierThreatEventReport(
            active_supplier_count=len(suppliers),
            selected_supplier_id=normalized_supplier,
            source_filter=source,
            coverage=coverage,
            total_event_count=len(events),
            displayed_count=len(events),
            has_more=False,
            events=events,
            notes=self._notes(),
        )

    def show(self, event_id: str) -> SupplierThreatEventDetails:
        event_id = normalize_supplier_threat_event_id(event_id)
        _, coverage, events = self._build(supplier_id=None, source="all")
        event = next((item for item in events if item.id == event_id), None)
        if event is None:
            raise ValidationError(
                "Tedarikçi olay adayı son başarılı yerel kaynak snapshot'larında bulunamadı."
            )
        source_coverage = next(
            item for item in coverage if item.source_key == event.source_key
        )
        return SupplierThreatEventDetails(
            event=event,
            coverage=source_coverage,
            notes=(
                "Bu kayıt kaynak iddiasının tedarikçi envanteriyle açıklanabilir "
                "eşleşmesidir; olayın gerçekleştiği doğrulanmamıştır.",
                "Kaynak kaydı ve tedarikçi kaydı birleştirilmez; kimlikleri ayrı kalır.",
            ),
        )

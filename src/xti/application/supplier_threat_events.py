"""Offline supplier views over independently stored public claim snapshots."""

from datetime import datetime
import unicodedata

from xti.domain.assets import ValidationError
from xti.domain.ransomlook_ransomware import (
    RANSOMLOOK_SOURCE_NAME,
    RANSOMLOOK_SOURCE_URL,
    ransomlook_claim_state_sha256,
)
from xti.domain.ransomware_claims import (
    RANSOMWARE_SOURCE_NAME,
    RANSOMWARE_SOURCE_URL,
    ransomware_claim_state_sha256,
)
from xti.domain.ransomware_watches import ransomware_claim_website_host
from xti.domain.supplier_threat_events import (
    SupplierThreatEvent,
    SupplierThreatEventDetails,
    SupplierThreatEventReport,
    SupplierThreatMatchEvidence,
    SupplierThreatSourceCoverage,
    normalize_supplier_threat_event_id,
    normalize_supplier_threat_source,
    supplier_threat_event_id,
)
from xti.domain.suppliers import Supplier, normalize_supplier_id
from xti.ports.ransomlook_ransomware import RansomLookClaimRepository
from xti.ports.ransomware_claims import RansomwareClaimRepository
from xti.ports.suppliers import SupplierRepository


_MAX_ACTIVE_SUPPLIERS = 500
_MAX_EVENTS = 100_000
_SOURCE_ORDER = {"threatcluster": 0, "ransomlook": 1}


def _text_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _domain_matches(host: str | None, domain: str) -> tuple[SupplierThreatMatchEvidence, ...]:
    if host is None:
        return ()
    if host == domain:
        return (SupplierThreatMatchEvidence("website", host, "exact"),)
    if host.endswith("." + domain):
        return (SupplierThreatMatchEvidence("website", host, "subdomain"),)
    return ()


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

    @staticmethod
    def _coverage(
        *, source_key: str, source_name: str, status,
    ) -> SupplierThreatSourceCoverage:
        latest, complete = status.latest_run, status.latest_complete_run
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

    @staticmethod
    def _name_index(records: tuple[Supplier, ...]) -> dict[str, tuple[Supplier, ...]]:
        temporary: dict[str, list[Supplier]] = {}
        for record in records:
            temporary.setdefault(record.name_key, []).append(record)
        return {key: tuple(values) for key, values in temporary.items()}

    @staticmethod
    def _event(
        supplier: Supplier, *, source_key: str, source_name: str, source_url: str,
        source_run_id: str, claim_id: str, claim_state: str, group: str,
        victim: str, website: str | None, discovered_at: str,
        claim_status: str | None, evidence: tuple[SupplierThreatMatchEvidence, ...],
        same_name_count: int,
    ) -> SupplierThreatEvent:
        return SupplierThreatEvent(
            id=supplier_threat_event_id(
                supplier_id=supplier.id, source_key=source_key, claim_id=claim_id,
            ),
            supplier_id=supplier.id,
            supplier_name=supplier.display_name,
            supplier_domain=supplier.primary_domain,
            supplier_criticality=supplier.criticality,
            source_key=source_key,
            source_name=source_name,
            source_url=source_url,
            source_run_id=source_run_id,
            claim_id=claim_id,
            claim_state_sha256=claim_state,
            group=group,
            victim=victim,
            website=website,
            discovered_at=discovered_at,
            claim_status=claim_status,
            match_evidence=evidence,
            same_name_supplier_count=same_name_count,
        )

    def _build(
        self, *, supplier_id: str | None, source: str,
    ) -> tuple[tuple[Supplier, ...], tuple[SupplierThreatSourceCoverage, ...], tuple[SupplierThreatEvent, ...]]:
        source = normalize_supplier_threat_source(source)
        suppliers = self._active_suppliers(supplier_id)
        by_name = self._name_index(suppliers)
        coverage: list[SupplierThreatSourceCoverage] = []
        events: list[SupplierThreatEvent] = []

        if source in {"all", "threatcluster"}:
            status = self.threatcluster.status(run_limit=1)
            source_coverage = self._coverage(
                source_key="threatcluster", source_name=RANSOMWARE_SOURCE_NAME,
                status=status,
            )
            coverage.append(source_coverage)
            if status.latest_complete_run is not None:
                snapshot = self.threatcluster.latest_snapshot()
                for claim in snapshot.claims:
                    name_matches = by_name.get(_text_key(claim.victim), ())
                    name_ids = {record.id for record in name_matches}
                    host = ransomware_claim_website_host(claim.website)
                    for record in suppliers:
                        evidence = list(_domain_matches(host, record.primary_domain))
                        if record.id in name_ids:
                            evidence.append(SupplierThreatMatchEvidence(
                                "victim", claim.victim, "exact",
                            ))
                        if not evidence:
                            continue
                        events.append(self._event(
                            record,
                            source_key="threatcluster",
                            source_name=RANSOMWARE_SOURCE_NAME,
                            source_url=RANSOMWARE_SOURCE_URL,
                            source_run_id=snapshot.run.id,
                            claim_id=claim.id,
                            claim_state=ransomware_claim_state_sha256(claim),
                            group=claim.group,
                            victim=claim.victim,
                            website=host,
                            discovered_at=claim.discovered_at,
                            claim_status=claim.status,
                            evidence=tuple(evidence),
                            same_name_count=len(name_matches),
                        ))
                        if len(events) > _MAX_EVENTS:
                            raise ValidationError(
                                "Tedarikçi olay adayı güvenli sınırı aştı; "
                                "tek tedarikçi veya kaynak seçin."
                            )

        if source in {"all", "ransomlook"}:
            status = self.ransomlook.status(run_limit=1)
            source_coverage = self._coverage(
                source_key="ransomlook", source_name=RANSOMLOOK_SOURCE_NAME,
                status=status,
            )
            coverage.append(source_coverage)
            if status.latest_complete_run is not None:
                snapshot = self.ransomlook.latest_snapshot()
                for claim in snapshot.claims:
                    name_matches = by_name.get(_text_key(claim.victim), ())
                    for record in name_matches:
                        events.append(self._event(
                            record,
                            source_key="ransomlook",
                            source_name=RANSOMLOOK_SOURCE_NAME,
                            source_url=RANSOMLOOK_SOURCE_URL,
                            source_run_id=snapshot.run.id,
                            claim_id=claim.id,
                            claim_state=ransomlook_claim_state_sha256(claim),
                            group=claim.group,
                            victim=claim.victim,
                            website=None,
                            discovered_at=claim.discovered_at,
                            claim_status=None,
                            evidence=(SupplierThreatMatchEvidence(
                                "victim", claim.victim, "exact",
                            ),),
                            same_name_count=len(name_matches),
                        ))
                        if len(events) > _MAX_EVENTS:
                            raise ValidationError(
                                "Tedarikçi olay adayı güvenli sınırı aştı; "
                                "tek tedarikçi veya kaynak seçin."
                            )

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

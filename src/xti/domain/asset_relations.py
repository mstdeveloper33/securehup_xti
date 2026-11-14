"""Historical, evidence-bound asset relationships without ownership inference."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from xti.domain.assets import ValidationError
from xti.domain.cname import CnameDnsCheck
from xti.domain.surface import SurfaceCheck, SurfaceScope


RELATION_KINDS = ("dns", "certificate", "cname", "supplier")
MAX_RELATION_OBSERVATIONS = 100_000


@dataclass(frozen=True, slots=True)
class SupplierRelationshipDecision:
    id: str
    sequence: int
    candidate_id: str
    source_domain: str
    candidate_domain: str
    decision: str
    supplier_id: str | None
    supplier_domain: str | None
    reason: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class AssetRelationsSnapshot:
    domain: str
    asset_id: str
    scope: SurfaceScope | None
    web_checks: tuple[SurfaceCheck, ...]
    cname_checks: tuple[CnameDnsCheck, ...]
    supplier_decisions: tuple[SupplierRelationshipDecision, ...]
    supplier_candidate_count: int


@dataclass(frozen=True, slots=True)
class AssetRelationObservation:
    id: str
    kind: str
    relation: str
    subject: str
    target: str | None
    target_type: str | None
    status: str
    observed_at: str
    recorded_at: str
    source: str
    evidence_id: str
    source_order: int
    state_sha256: str | None
    details: tuple[str, ...] = ()
    candidate_id: str | None = None
    target_label: str | None = None
    decision: str | None = None


@dataclass(frozen=True, slots=True)
class AssetRelationSummary:
    id: str
    kind: str
    relation: str
    subject: str
    target: str
    target_type: str
    first_observed_at: str
    last_observed_at: str
    observation_count: int
    latest_event_status: str
    latest_recorded_at: str
    latest_evidence_id: str
    latest_source: str
    target_label: str | None = None


@dataclass(frozen=True, slots=True)
class AssetRelationCoverage:
    kind: str
    check_count: int
    latest_status: str
    latest_evidence_id: str | None
    latest_observed_at: str | None
    latest_recorded_at: str | None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AssetRelationsReport:
    domain: str
    asset_id: str
    scope_active: bool | None
    kind: str | None
    history: bool
    offset: int
    limit: int
    items: tuple[AssetRelationObservation | AssetRelationSummary, ...]
    total_count: int
    total_relationship_count: int
    total_observation_count: int
    has_more: bool
    coverage: tuple[AssetRelationCoverage, ...]
    notes: tuple[str, ...]


def relation_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Timezone required")
        return parsed
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("Varlık ilişkisinin kayıt zamanı saat dilimi içermeli.") from error


def _identity(*values: object) -> str:
    return hashlib.sha256(json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("ascii")).hexdigest()


def _status_events(snapshot: AssetRelationsSnapshot):
    events: list[AssetRelationObservation] = []
    coverage = []

    def put(kind, relation, subject, target, target_type, status, check, order, details=()):
        events.append(AssetRelationObservation(
            _identity(kind, relation, subject, target, check.id, status), kind, relation,
            subject, target, target_type, status, check.result.finished_at,
            check.recorded_at, "surface-web" if kind in {"dns", "certificate"} else "surface-cname",
            check.id, order, check.state_sha256, tuple(details),
        ))
        if len(events) > MAX_RELATION_OBSERVATIONS:
            raise ValidationError("İlişki geçmişi 100.000 gözlem sınırını aşıyor; eksik sonuç üretilmedi.")

    for order, check in enumerate(snapshot.web_checks, 1):
        result = check.result
        dns_details = (f"Kontrol politikası: {result.policy_version}", f"DNS durumu: {result.dns_status}", *result.errors)
        if result.dns_status == "resolved" and result.addresses:
            for address in result.addresses:
                put("dns", "dns_address", snapshot.domain, address, "ip", "observed", check, order, dns_details)
        else:
            put("dns", "dns_observation", snapshot.domain, None, None,
                "failed" if result.dns_status in {"failed", "blocked"} else "no_address", check, order, dns_details)
        certificate = result.certificate
        if certificate is not None:
            details = (f"Kontrol politikası: {result.policy_version}", f"TLS durumu: {result.tls_status}", f"Seri: {certificate.serial_number}",
                       f"Düzenleyen: {certificate.issuer}", f"Konu: {certificate.subject}",
                       f"Sertifika tarihleri: {certificate.not_before} — {certificate.not_after}",
                       "Sertifikadaki DNS adları (sahiplik doğrulaması değil): " + ", ".join(certificate.dns_names))
            put("certificate", "certificate_presented", snapshot.domain, certificate.sha256,
                "certificate_sha256", "observed", check, order, details)
        else:
            put("certificate", "certificate_observation", snapshot.domain, None, None,
                result.tls_status if result.tls_status in {"not_checked", "failed"} else "no_certificate_evidence",
                check, order, (f"Kontrol politikası: {result.policy_version}", f"TLS durumu: {result.tls_status}", *result.errors,
                              "Sertifika kanıtı bulunmaması eski sertifika bağının silindiğini göstermez."))
    for order, check in enumerate(snapshot.cname_checks, 1):
        result = check.result
        details = (f"Kontrol politikası: {result.policy_version}", f"CNAME durumu: {result.alias_status}", f"Son hedef DNS durumu: {result.target_status}", *result.errors)
        if result.chain:
            for hop in result.chain:
                put("cname", "cname_alias", hop.owner, hop.target, "domain", "observed", check, order, details)
            for address in result.addresses:
                put("cname", "cname_target_address", result.target, address, "ip", "observed", check, order, details)
            if not result.addresses:
                put("cname", "cname_target_observation", result.target, None, None,
                    "failed" if result.target_status == "failed" else "no_address", check, order, details)
        else:
            put("cname", "cname_observation", snapshot.domain, None, None,
                "failed" if result.alias_status == "failed" else "no_alias", check, order, details)

    previous: dict[str, SupplierRelationshipDecision] = {}
    for event in snapshot.supplier_decisions:
        before = previous.get(event.candidate_id)
        changes = []
        if before is not None and before.decision == "accepted" and (
            event.decision != "accepted" or event.supplier_id != before.supplier_id
        ):
            changes.append((before.supplier_id, before.supplier_domain, "withdrawn"))
        if event.decision == "accepted":
            changes.append((event.supplier_id, event.supplier_domain, "accepted"))
        if not changes:
            changes.append((None, None, event.decision))
        for supplier_id, supplier_domain, status in changes:
            events.append(AssetRelationObservation(
                _identity("supplier", event.id, supplier_id, status), "supplier", "human_supplier_link",
                event.source_domain, supplier_id, "supplier" if supplier_id else None, status,
                event.recorded_at, event.recorded_at, "supplier-resolution", event.id, event.sequence,
                None, (f"Teknik aday kökü: {event.candidate_domain}",
                       f"Tedarikçi ana domaini: {supplier_domain or 'bağlı değil'}", f"Karar gerekçesi: {event.reason}",
                       f"Kaydedilen karar: {event.decision}",
                       "İnsan kararının tarihidir; teknik hizmetin başlangıç/bitiş tarihi değildir."),
                event.candidate_id, supplier_domain, event.decision,
            ))
        previous[event.candidate_id] = event
        if len(events) > MAX_RELATION_OBSERVATIONS:
            raise ValidationError("İlişki geçmişi 100.000 gözlem sınırını aşıyor; eksik sonuç üretilmedi.")

    for kind in RELATION_KINDS:
        selected = [event for event in events if event.kind == kind]
        latest = max(selected, key=lambda event: (event.source_order, event.id), default=None)
        checks = snapshot.web_checks if kind in {"dns", "certificate"} else snapshot.cname_checks
        count = len(snapshot.supplier_decisions) if kind == "supplier" else len(checks)
        if kind == "dns":
            status = checks[-1].result.dns_status if checks else "never"
        elif kind == "certificate":
            status = ("observed" if checks[-1].result.certificate else (
                checks[-1].result.tls_status if checks[-1].result.tls_status in {"not_checked", "failed"}
                else "no_certificate_evidence")) if checks else "never"
        elif kind == "cname":
            status = ("partial" if checks[-1].result.errors else checks[-1].result.alias_status) if checks else "never"
        else:
            status = "decisions_recorded" if count else "no_decision"
        notes = ((f"Kayıtlı teknik aday: {snapshot.supplier_candidate_count}",
                  "Kabul/geri çekme kararları tarihî olaydır; tedarikçinin bugünkü etkinliği veya kesintisiz bağımlılık sonucu değildir.")
                 if kind == "supplier" else ("Son kontrolün başarısız/boş olması önceki gözlemi silmez.",))
        coverage.append(AssetRelationCoverage(kind, count, status,
            latest.evidence_id if latest else None, latest.observed_at if latest else None,
            latest.recorded_at if latest else None, notes))
    return events, tuple(coverage)


def build_asset_relations(snapshot: AssetRelationsSnapshot, *, kind: str | None,
                          history: bool, offset: int, limit: int) -> AssetRelationsReport:
    events, coverage = _status_events(snapshot)
    if kind is not None:
        events = [event for event in events if event.kind == kind]
        coverage = tuple(item for item in coverage if item.kind == kind)
    grouped = defaultdict(list)
    for event in events:
        if event.target is not None:
            grouped[(event.kind, event.relation, event.subject, event.target, event.target_type)].append(event)
    summaries = []
    for key, entries in grouped.items():
        positive = [event for event in entries if event.status in {"observed", "accepted"}]
        if not positive:
            continue
        latest = max(entries, key=lambda event: (event.source_order, event.id))
        summaries.append(AssetRelationSummary(_identity(*key), *key,
            min((event.observed_at for event in positive), key=relation_time),
            max((event.observed_at for event in positive), key=relation_time), len(positive),
            latest.status, latest.recorded_at, latest.evidence_id, latest.source, latest.target_label))
    summaries.sort(key=lambda item: (relation_time(item.latest_recorded_at), item.kind, item.id), reverse=True)
    events.sort(key=lambda item: (relation_time(item.recorded_at), item.kind, item.source_order, item.id), reverse=True)
    items = events if history else summaries
    selected = tuple(items[offset:offset + limit])
    return AssetRelationsReport(snapshot.domain, snapshot.asset_id,
        snapshot.scope.active if snapshot.scope else None, kind, history, offset, limit, selected,
        len(items), len(summaries), len(events), offset + len(selected) < len(items), coverage,
        ("Yalnız kayıtlı tam domain kanıtları okunur; yeni DNS/TLS/HTTP isteği yapılmaz.",
         "İlk/son gözlem yalnız kaydedilmiş gözlem zamanlarını özetler; aradaki sürede kesintisiz bağ veya bugünkü durum kanıtı değildir.",
         "Ortak IP, sertifika veya CNAME hedefi sahiplik, aynı kuruluş ya da kötü niyet hükmü oluşturmaz.",
         "Sertifikadaki DNS adları sertifikanın iddiasıdır; ayrı varlık veya doğrulanmış sahiplik olarak eklenmez.",
         "Geçmiş yerel kayıt zamanına göre sıralanır; kaynak gözlem zamanı ayrıca gösterilir. Eşit zamanda kaynak içi sıra kullanılır.",
         "Tedarikçi karar olayları belirli bir tarihî CNAME kontrolünü dondurmaz; böyle bir eşleştirme tahmin edilmez."))

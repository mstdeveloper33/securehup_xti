"""Versioned, evidence-backed review order. No risk score or analyst mutation."""

from dataclasses import dataclass
from datetime import datetime

from xti.domain.indicator_enrichment import EnrichmentState, request_url
from xti.domain.research import (
    ResearchEvidence, ResearchReport, ResearchSnapshotChanged, freshness, identity, node_id,
)
from xti.domain.surface_discovery_status import StoredDiscoveryStatus


POLICY_VERSION = "research-priority-v8"
PRIORITIES = ("review_first", "verify", "context")

# Order is explicit and ordinal. Confidence, source popularity and duplicated
# observations do not vote, add points, or change an analyst's decision.
RULES = {
    'open_case': ('verify', 'İlgili açık vaka var; karar gerekçesini ve özgün vaka kanıtını inceleyin.'),
    'closed_case': ('context', 'İlgili vaka kapatılmış; bu karar kaynak iddiasını geri çekmez.'),
    'social_impersonation_review': ('review_first', 'Bu profil kesiti insan tarafından olası taklit olarak işaretlenmiş; özgün incelemeyi doğrulayın.'),
    'content_candidate': ('verify', 'Saklı firma aramasında içerik adayı var; kaynak metnini ve arama kapsamını inceleyin.'),
    'investigation_pending': ('verify', 'Kimlik veya metin adayı insan incelemesi bekliyor; özgün kanıtı ve önceki kararları inceleyin.'),
    'report_text_context': ('context', 'Saklı rapor metninde geçiyor; metin ve kaynak sürümünü inceleyin. Zararlılık veya bağımsız doğrulama değildir.'),
    'report_document_historical': ('context', 'Bu kanıt önceki belge sürümüne bağlı; yeni metin eski bağlantıları kendiliğinden devralmaz.'),
    'report_linked': ('context', 'İnsan bu rapor sürümünü hedef kayda bağlamış; bu doğrudan aktör–IOC saldırı ilişkisi oluşturmaz.'),
    'report_link_withdrawn': ('context', 'Bu belge bağlantısı insan tarafından geri çekilmiş; önceki karar yalnız geçmiş olarak korunur.'),
    "supplier_priority_review": ("review_first", "İnsan tarafından önemli tanımlanan tedarikçide kaynak iddiası adayı var; kimliği ve iddiayı doğrulayın. Müşteri etkisi kanıtlanmış değildir."),
    "supplier_claim_review": ("verify", "Tedarikçiyle eşleşen kaynak iddiası var; özgün kaydı ve eşleşme dayanağını inceleyin."),
    "supplier_identity_ambiguous": ("verify", "Kaynak adı birden fazla etkin tedarikçiyle eşleşiyor; kuruluş kimliği belirsiz."),
    "supplier_source_degraded": ("verify", "Tedarikçi kaynağının son denemesi başarısız; varsa önceki başarılı yanıt korunuyor, güncel boş sonuç değildir."),
    "supplier_watch_historical": ("verify", "Son izleme karşılaştırması bugünkü etkin kimlik/izleme kapsamında değil; tarihî kaynak ve karar korunuyor."),
    "supplier_watch_changes": ("verify", "Son yerel tedarikçi karşılaştırmasında yeni, değişen veya çıkarılan kaynak eşleşmesi var; çıkarılma çözülmüş ihlal değildir."),
    "supplier_source_missing": ("context", "Tedarikçi kaynağı henüz toplanmamış; veri yokluğu eşleşme yokluğu veya güvenli olduğu anlamına gelmez."),
    "supplier_no_current_match": ("context", "İncelenen son başarılı kaynak yanıtlarında tedarikçiyle eşleşme yok; kaynak kapsamı ve tarihini ayrıca kontrol edin."),
    "future_evidence_time": ("review_first", "Kanıtın gözlem veya kayıt zamanı gelecekte; zaman bilgisini doğrulayın."),
    "source_status_difference": ("review_first", "Aynı kayıt için farklı kaynakların etkin ve geri çekilmiş iddiaları var; gerekçelerini karşılaştırın. Bu tek başına mantıksal çelişki değildir."),
    "indicator_with_list_context": ("review_first", "Etkin IOC iddiasına liste bağlamı eşlik ediyor; kaynak iddiasını ve altyapı bağlamını birlikte inceleyin. Liste eşleşmesi iddiayı geçersiz kılmaz."),
    "active_indicator_claim": ("review_first", "Güncel ve etkin IOC kaynak iddiası var; özgün iddiayı inceleyin. Bu doğrulanmış tehdit kararı değildir."),
    "latest_check_failed": ("verify", "Son kayıtlı DNS kontrolü başarısız; önceki gözlemler bugünkü durumu doğrulamaz."),
    "latest_cname_check_failed": ("verify", "Son kayıtlı CNAME veya son hedef sorgusu başarısız; eski bağlantılar güncel doğrulama değildir."),
    "latest_tls_check_failed": ("verify", "Son kayıtlı web kontrolünde TLS başarısız; eski sertifika gözlemi bugünkü durumu doğrulamaz."),
    "certificate_expired": ("verify", "Gözlenmiş sertifikanın geçerlilik süresi dolmuş; bugün hâlâ sunulduğu veya bir zafiyet bulunduğu sonucu çıkarılamaz."),
    "certificate_not_yet_valid": ("verify", "Gözlenmiş sertifikanın geçerlilik başlangıcı henüz gelmemiş; tarihleri ve gözlemi doğrulayın."),
    "supplier_review_pending": ("verify", "Tedarikçi adayı inceleme bekliyor veya belirsiz; kaynak bağı insan onayı değildir."),
    "supplier_dependency_historical": ("verify", "Aday son yenilemede tarihî işaretlenmiş; bu teknik durum insan onayının geri çekildiği anlamına gelmez."),
    "supplier_inventory_inactive": ("verify", "Tedarikçi envanter kaydı pasif; tarihî onay ve kaynak kanıtı korunuyor."),
    "surface_candidate_pending": ("verify", "Pasif alt alan adayı inceleme bekliyor; arşiv kaydı sahiplik veya aktif kontrol onayı değildir."),
    "discovery_query_failed": ("verify", "Son pasif keşif sorgusu başarısız; kayıtlı adaylar ve önceki tamamlanmış yanıt korunuyor."),
    "discovery_query_partial": ("verify", "Son pasif keşif yanıtı kısmi; aday görülmese de tamamlanmış boş sonuç değildir."),
    "discovery_status_limited": ("verify", "Kaynak durumu okuma sınırına sığmadı; hiç sorgulanmadı veya boş sonuç olarak yorumlanamaz."),
    "source_lookup_failed": ("verify", "Son URL/dosya kaynak sorgusu başarısız; varsa önceki geçerli yanıt korunuyor."),
    "evidence_truncated": ("verify", "Bu kaydın kanıtlarının tamamı okuma sınırına sığmadı; özgün kayıt ayrıntısını inceleyin."),
    "stale_active_indicator": ("verify", "Etkin IOC iddiasının son gözlemi güncellik eşiğini aşıyor; iddianın güncel dayanağını kontrol edin."),
    "stale_evidence": ("verify", "Gösterilen son gözlem veya kaynak yanıtı güncellik eşiğini aşıyor; yeni durum doğrulanmış değil."),
    "evidence_missing": ("verify", "Bu kapsamda kayıtlı kanıt yok; veri yokluğu güvenli olduğu anlamına gelmez."),
    "source_no_match": ("context", "Son geçerli kaynak yanıtında eşleşme yok; bu yalnız o sorgunun sonucudur."),
    "discovery_never_checked": ("context", "Bu kök için bir pasif keşif sağlayıcısı henüz sorgulanmamış; kaynak kapsamı eksik."),
    "discovery_complete_empty": ("context", "Son tamamlanmış pasif sorguda aday görülmedi; tarihî adaylar silinmez ve bütün internetin boş olduğu sonucu çıkarılmaz."),
    "inactive_claims_only": ("context", "Bu kaydın gösterilen kaynak iddiaları etkin değil; tarihî kanıtı güncel tehdit olarak yorumlamayın."),
    "supplier_link_withdrawn": ("context", "Bu tedarikçi bağlantısı sonraki insan kararıyla kaldırılmış veya değiştirilmiş; eski kabul güncel onay değildir."),
    "surface_candidate_rejected": ("context", "Alt alan adayı insan kararıyla reddedilmiş; tarihî kaynak kanıtı korunur."),
    "surface_candidate_owned": ("context", "Alt alan adı insan tarafından kendine ait sınıflandırılmış; aktif kontrol kapsamı ve teknik doğrulama ayrıdır."),
    "listed_context": ("context", "Kaynak listesiyle eşleşme var; altyapı bağlamı sağlar, güvenli veya zararlı hükmü vermez."),
    "recorded_context": ("context", "Kayıtlı gözlem veya kaynak bağlamı var; bu kurallar ek inceleme önceliği üretmedi."),
    "relationship_context_only": ("context", "Bu düğüm ilişkili kanıtta geçiyor; düğüme ait ayrı bir iddia kaydı yok."),
}
RULE_ORDER = {code: index for index, code in enumerate(RULES)}


def evidence_id(item: ResearchEvidence) -> str:
    """A locator for this evidence, not a new persisted assertion or record."""
    return "evidence:" + identity(item.record_type, item.record_id, item.assertion_id,
        item.event_id, item.source, item.source_reference, item.source_run_id, item.state_sha256)


@dataclass(frozen=True, slots=True)
class ReviewReason:
    code: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReviewItem:
    id: str
    subject_kind: str
    label: str
    record_type: str
    value: str | None
    source_id: str | None
    target_id: str | None
    references: tuple[dict, ...]
    related_item_ids: tuple[str, ...]
    priority: str
    evidence_basis: tuple[str, ...]
    reasons: tuple[ReviewReason, ...]
    evidence: tuple[ResearchEvidence, ...]
    evidence_total_count: int
    warninglist_matches: tuple[dict, ...]
    enrichment: EnrichmentState | None = None
    discovery: tuple[StoredDiscoveryStatus, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchPriorities:
    research: ResearchReport
    snapshot_id: str
    items: tuple[ReviewItem, ...]
    total_items: int
    priority_counts: dict[str, int]
    has_more: bool


def _recent_evidence(rows):
    """Older observations remain visible, but a fresh repeat clears stale priority.

    CTI assertions are already the latest state of their own source claim.
    DNS observations on one edge are historical repeats of the same binding.
    """
    latest, others = {}, []
    for item in rows:
        if (item.record_type in {'supplier_risk_context', 'supplier_watch_pending'} or
            item.record_type == 'supplier_source_coverage' and item.status in {'not_collected', 'unavailable'}):
            # Configuration/missing-source clocks are not network observations.
            continue
        if item.kind == "human_decision":
            # Decision age is exposed, but isn't a new network observation
            # or grounds to stale every superseded decision in a long history.
            continue
        if item.kind in {"observation", "candidate_context"}:
            key = (item.record_type, item.source)
            if key not in latest or (
                datetime.fromisoformat(item.observed_at), item.record_id
            ) > (datetime.fromisoformat(latest[key].observed_at), latest[key].record_id):
                latest[key] = item
        elif item.kind != "source_claim" or item.current:
            others.append(item)
    return (*latest.values(), *others)


def _reasons(rows, total, matches, related, checked_at, hours, discovery=()):
    reasons = []

    def add(code, evidence=()):
        reasons.append(ReviewReason(code, tuple(sorted({evidence_id(row) for row in evidence}))))

    now = datetime.fromisoformat(checked_at)
    for code, selected in (
        ('open_case', [row for row in rows if row.record_type == 'case_activity' and row.current and row.status in {'open', 'investigating', 'monitoring'}]),
        ('closed_case', [row for row in rows if row.record_type == 'case_activity' and row.current and row.status in {'closed', 'resolved'}]),
        ('social_impersonation_review', [row for row in rows if row.record_type == 'social_decision' and row.current and row.status == 'possible_impersonation']),
        ('content_candidate', [row for row in rows if row.record_type == 'company_content']),
        ('investigation_pending', [row for row in rows if row.record_type in {'identity_proposal', 'report_candidate'} and row.status in {'pending', 'uncertain'}]),
        ('report_text_context', [row for row in rows if row.record_type == 'report_text_mention']),
        ('report_document_historical', [row for row in rows if row.record_type in {'report_document', 'report_text_mention', 'report_search_scope'} and row.status == 'historical_document']),
        ('report_linked', [row for row in rows if row.record_type == 'report_link_decision' and row.current and row.status == 'linked']),
        ('report_link_withdrawn', [row for row in rows if row.record_type == 'report_link_decision' and row.current and row.status == 'withdrawn']),
    ):
        if selected:
            add(code, selected)
    future = [row for row in rows if any(datetime.fromisoformat(value) > now
              for value in (row.observed_at, row.recorded_at))]
    if future:
        add("future_evidence_time", future)
    for record_type, states, code in (
        ('supplier_risk_context', {'priority_review'}, 'supplier_priority_review'),
        ('supplier_risk_context', {'review'}, 'supplier_claim_review'),
        ('supplier_threat_match', {'domain_match', 'name_match'}, 'supplier_claim_review'),
        ('supplier_threat_match', {'ambiguous_name'}, 'supplier_identity_ambiguous'),
        ('supplier_risk_context', {'identity_review'}, 'supplier_identity_ambiguous'),
        ('supplier_source_coverage', {'stale_after_failure', 'unavailable'}, 'supplier_source_degraded'),
        ('supplier_source_coverage', {'not_collected'}, 'supplier_source_missing'),
        ('supplier_risk_context', {'no_current_match'}, 'supplier_no_current_match'),
        ('supplier_watch_run', {'historical_scope'}, 'supplier_watch_historical'),
        ('supplier_watch_run', {'changes'}, 'supplier_watch_changes'),
    ):
        selected = [row for row in rows if row.record_type == record_type and row.status in states]
        if selected:
            add(code, selected)
    claims = [row for row in rows if row.kind == "source_claim"]
    active = [row for row in claims if row.current]
    revoked = [row for row in claims if row.status == "revoked"]
    if any(left.source != right.source for left in active for right in revoked):
        add("source_status_difference", (*active, *revoked))
    indicators = [row for row in active if row.record_type == "cti_indicator"]
    if indicators and matches:
        add("indicator_with_list_context", indicators)
    fresh = [row for row in indicators if freshness(row.observed_at, checked_at, hours) == "fresh"]
    if fresh:
        add("active_indicator_claim", fresh)
    failed_dns = [row for row in rows if row.record_type == "surface_check" and row.status == "failed"]
    if failed_dns:
        add("latest_check_failed", failed_dns)
    for record_type, code in (("surface_cname_check", "latest_cname_check_failed"),
                              ("surface_tls_check", "latest_tls_check_failed")):
        failed = [row for row in rows if row.record_type == record_type and row.status == "failed"]
        if failed:
            add(code, failed)
    certificates = [row for row in rows if row.record_type == "surface_certificate"]
    expired = [row for row in certificates if row.valid_until and datetime.fromisoformat(row.valid_until) < now]
    pending = [row for row in certificates if row.valid_from and datetime.fromisoformat(row.valid_from) > now]
    if expired:
        add("certificate_expired", expired)
    if pending:
        add("certificate_not_yet_valid", pending)
    for code, selected in (
        ("supplier_review_pending", [row for row in rows if row.record_type == "supplier_candidate" and row.status in {"pending", "uncertain"}]),
        ("supplier_dependency_historical", [row for row in rows if row.record_type == "supplier_candidate" and row.current is False]),
        ("supplier_inventory_inactive", [row for row in rows if row.record_type == "supplier_inventory" and row.current and row.status == "revoked"]),
        ("supplier_link_withdrawn", [row for row in rows if row.record_type == "supplier_resolution" and row.current and row.status == "withdrawn"]),
    ):
        if selected:
            add(code, selected)
    failed_source = [row for row in rows if row.record_type in {"enrichment_run", 'social_watch_run', 'company_search_run'} and row.status == "failed"]
    classifications = [row for row in rows if row.record_type == "surface_candidate" or
                       (row.record_type == "surface_candidate_decision" and row.current)]
    for status in ("pending", "rejected", "owned"):
        selected = [row for row in classifications if row.status == status]
        if selected:
            add("surface_candidate_" + status, selected)
    if failed_source:
        add("source_lookup_failed", failed_source)
    for code, condition in (
        ('discovery_query_failed', lambda state: state.latest_run and state.latest_run.status == 'failed'),
        ('discovery_query_partial', lambda state: state.latest_run and state.latest_run.status == 'partial'),
        ('discovery_complete_empty', lambda state: state.latest_run and state.latest_run.status == 'complete' and not state.latest_run.candidate_count),
    ):
        runs = {state.latest_run.id for state in discovery if state.read_complete and condition(state)}
        if runs:
            add(code, [row for row in rows if row.record_type == 'surface_discovery_run' and row.record_id in runs])
    if any(state.read_complete and not state.latest_run for state in discovery):
        add('discovery_never_checked')
    if any(not state.read_complete for state in discovery):
        add('discovery_status_limited')
    if total > len(rows):
        add("evidence_truncated")
    old_indicators = [row for row in indicators if freshness(row.observed_at, checked_at, hours) == "stale"]
    if old_indicators:
        add("stale_active_indicator", old_indicators)
    # Failed requests are not observations. Their age is still exposed on the
    # evidence, while preserved successful context has its own age/reason.
    stale = [row for row in _recent_evidence(rows) if row.status != "failed" and
             row not in old_indicators and freshness(row.observed_at, checked_at, hours) == "stale"]
    if stale:
        add("stale_evidence", stale)
    if not rows and not total:
        add("relationship_context_only" if related else "evidence_missing")
    absent = [row for row in rows if row.kind == "source_context" and row.status == "no_match"]
    if absent:
        add("source_no_match", absent)
    if claims and not active:
        add("inactive_claims_only", claims)
    if matches:
        add("listed_context")
    if not reasons:
        add("recorded_context", rows)
    return tuple(sorted(reasons, key=lambda item: RULE_ORDER[item.code]))


def _node_evidence(node):
    rows, total = node.evidence, node.evidence_total_count
    state = node.enrichment
    if state and state.successful_run and state.latest_run.id != state.successful_run.id:
        good = state.successful_run
        # A failed latest lookup cannot hide the last valid response, even
        # when that response had no relationships (e.g. a known absence).
        rows += (ResearchEvidence("enrichment_run", good.id, good.provider, request_url(state.query),
            "source_context", good.status, good.finished_at, good.finished_at,
            "Son geçerli kaynak yanıtı; daha sonraki başarısız sorgudan ayrı korunur.",
            state_sha256=good.snapshot_sha256, source_run_id=good.id, time_basis="response_received_at"),)
        total += 1
    return rows, total


def _review_item(report, *, identifier, kind, label, record_type, rows, total,
                 value=None, source=None, target=None, references=(), related=(),
                 matches=(), enrichment=None, discovery=()):
    reasons = _reasons(rows, total, matches, related, report.checked_at, report.query.stale_after_hours, discovery)
    priority = min((RULES[row.code][0] for row in reasons), key=PRIORITIES.index)
    return ReviewItem(
        id=identifier, subject_kind=kind, label=label, record_type=record_type,
        value=value, source_id=source, target_id=target, references=references,
        related_item_ids=related, priority=priority,
        evidence_basis=tuple(sorted({row.kind for row in rows})), reasons=reasons,
        evidence=rows, evidence_total_count=total, warninglist_matches=matches,
        enrichment=enrichment, discovery=discovery,
    )


def prioritize_research(report: ResearchReport, *, paginate=True) -> ResearchPriorities:
    """Rank ALL collected nodes/edges before paging, within the existing bounds."""
    nodes = {node_id(item.key): item for item in report.nodes}
    adjacency = {key: [] for key in nodes}
    for edge in report.edges:
        adjacency[node_id(edge.source)].append(edge.id)
        adjacency[node_id(edge.target)].append(edge.id)
    items = []
    for key, node in nodes.items():
        rows, total = _node_evidence(node)
        items.append(_review_item(report, identifier=key, kind="node", label=node.label,
            record_type=node.record_type, value=node.key[1], rows=rows, total=total,
            references=node.references, related=tuple(sorted(set(adjacency[key]))),
            matches=node.warninglist_matches, enrichment=node.enrichment, discovery=node.discovery))
    for edge in report.edges:
        source, target = node_id(edge.source), node_id(edge.target)
        items.append(_review_item(report, identifier=edge.id, kind="relationship",
            label=nodes[source].label + " → " + nodes[target].label,
            record_type=edge.relationship_type, source=source, target=target,
            rows=edge.evidence, total=edge.evidence_total_count))
    items.sort(key=lambda item: (PRIORITIES.index(item.priority),
        min(RULE_ORDER[row.code] for row in item.reasons), item.id))
    counts = {priority: sum(item.priority == priority for item in items) for priority in PRIORITIES}
    snapshot = identity(POLICY_VERSION, report.snapshot_id, report.query.stale_after_hours,
        [(item.id, item.priority, [(reason.code, reason.evidence_ids) for reason in item.reasons],
          [(evidence_id(row), freshness(row.observed_at, report.checked_at, report.query.stale_after_hours))
           for row in item.evidence]) for item in items])
    expected = report.query.expected_snapshot
    if expected is not None and expected != snapshot:
        raise ResearchSnapshotChanged("İnceleme sırası, kanıt veya güncellik değişti; ilk sayfadan yeniden başlayın.")
    query = report.query
    selected = tuple(items[query.offset:query.offset + query.limit] if paginate else items)
    return ResearchPriorities(report, snapshot, selected, len(items), counts,
                              paginate and query.offset + len(selected) < len(items))

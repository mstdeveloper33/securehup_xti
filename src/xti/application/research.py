"""Related evidence investigation independent of storage, CLI and transport."""

from dataclasses import replace
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.research import RESEARCH_MODEL_VERSION, build_research, freshness, node_id, research_query
from xti.ports.research import ResearchRepository
from xti.domain.warninglists import catalog_data
from xti.application.indicator_enrichment import state_data
from xti.domain.research_priority import POLICY_VERSION, RULES, evidence_id, prioritize_research
from xti.domain.research_discovery_status import status_data


class ResearchService:
    def __init__(self, repository: ResearchRepository, *, clock=None):
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self):
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Araştırma zamanı saat dilimi içermeli.")
        return now.astimezone(timezone.utc).isoformat()

    def show(self, **parameters):
        query = research_query(**parameters)
        checked_at = self._now()
        with self.repository.open(query, checked_at) as reader:
            return build_research(reader, query, checked_at)

    def priorities(self, **parameters):
        return self._priorities(parameters, paginate=True)

    def full_priorities(self, **parameters):
        """Internal capture input; public read results retain their page limits."""
        return self._priorities(parameters, paginate=False)

    def _priorities(self, parameters, *, paginate):
        query = research_query(**parameters)
        checked_at = self._now()
        with self.repository.open(query, checked_at) as reader:
            graph = build_research(reader, replace(query, expected_snapshot=None), checked_at, paginate=False)
            return prioritize_research(replace(graph, query=query), paginate=paginate)


def research_evidence_data(item, checked_at, stale_after_hours):
    return {
        "record_type": item.record_type, "record_id": item.record_id,
        "source": item.source, "source_reference": item.source_reference,
        "kind": item.kind, "status": item.status, "current": item.current,
        "observed_at": item.observed_at, "recorded_at": item.recorded_at,
        "freshness": freshness(item.observed_at, checked_at, stale_after_hours),
        "description": item.description, "assertion_id": item.assertion_id,
        "event_id": item.event_id, "confidence": item.confidence,
        "valid_from": item.valid_from, "valid_until": item.valid_until,
        "state_sha256": item.state_sha256,
        "first_observed_at": item.first_observed_at, "source_run_id": item.source_run_id,
        "time_basis": item.time_basis,
    }


def priority_data(review) -> dict:
    report, query = review.research, review.research.query
    warninglists = catalog_data(report.warninglists, checked_at=report.checked_at)
    return {
        "model_version": RESEARCH_MODEL_VERSION, "policy_version": POLICY_VERSION,
        "checked_at": report.checked_at, "snapshot_id": review.snapshot_id,
        "evidence_snapshot_id": report.snapshot_id, "consistency": "single_read_snapshot",
        "stored_data_only": True, "scope": "bounded_research_neighborhood",
        "status": report.status, "root_id": report.root_id,
        "query": {"indicator_type": query.indicator_type, "value": query.value,
            "max_hops": query.max_hops, "node_limit": query.node_limit,
            "edge_limit": query.edge_limit, "stale_after_hours": query.stale_after_hours},
        "offset": query.offset, "limit": query.limit, "has_more": review.has_more,
        "next_offset": query.offset + len(review.items) if review.has_more else None,
        "collected_item_count": review.total_items, "priority_counts": dict(review.priority_counts),
        "coverage_complete": not report.limitations, "limitations": list(report.limitations),
        "coverage": [{key: item[key] for key in (
            "kind", "scope", "examined_count", "window_limit", "complete", "order")}
            for item in report.coverage],
        "warninglists": {"lists": warninglists,
            "coverage_complete": all(row["latest_status"] == "complete" and row["freshness"] == "fresh" for row in warninglists)},
        "items": [{
            "id": item.id, "subject_kind": item.subject_kind, "label": item.label,
            "record_type": item.record_type, "value": item.value,
            "source_id": item.source_id, "target_id": item.target_id,
            "references": [{key: ref[key] for key in ("kind", "record_type", "namespace", "record_id")}
                           for ref in item.references],
            "related_item_ids": list(item.related_item_ids), "priority": item.priority,
            "evidence_basis": list(item.evidence_basis),
            "reasons": [{"code": reason.code, "priority": RULES[reason.code][0],
                         "message": RULES[reason.code][1], "evidence_ids": list(reason.evidence_ids)}
                        for reason in item.reasons],
            "evidence": [{"id": evidence_id(row),
                          **research_evidence_data(row, report.checked_at, query.stale_after_hours)}
                         for row in item.evidence],
            "evidence_total_count": item.evidence_total_count,
            "enrichment": state_data(item.enrichment, report.checked_at, query.stale_after_hours) if item.enrichment else None,
            "discovery": status_data(item.discovery, report.checked_at, query.stale_after_hours),
            "warninglist_matches": [{key: match[key] for key in (
                "list_id", "run_id", "snapshot_sha256", "matched_entries", "matching_type", "category")}
                for match in item.warninglist_matches],
        } for item in review.items],
        "notes": [
            "Öncelik analistin inceleme sırasıdır; risk skoru, ihlal veya güvenli kararı değildir.",
            "Kaynak güveni, kanıt türü, güncellik ve etkinlik ayrı kalır; kaynak sayısı veya güven puanı sıralamayı oylamaz.",
            "Kaynak durumları farklı olabilir; metinlerden anlamsal çelişki veya aynı aktör sonucu çıkarılmaz.",
            "Sıra yalnız seçilen kökün sınırlı araştırmasını kapsar; bütün firma veya internet envanteri değildir.",
            "Kaynaklar sorgulanmaz; alarm, vaka ve insan kararları değiştirilmez. Eksik kanıt sıfır risk değildir.",
            "Yol sayfalarından önce bütün toplanan düğüm ve ilişkiler sıralanır; sayfa öğe sayfasıdır.",
            "Sonraki sayfada bu cevabın snapshot_id değerini kullanın; kanıt veya güncellik değişirse ilk sayfaya dönün.",
        ],
    }


def research_data(report) -> dict:
    """Explicit research-model fields shared by CLI and v1 engine/platform envelopes."""
    query = report.query
    warninglists = catalog_data(report.warninglists, checked_at=report.checked_at)

    def evidence(item):
        return research_evidence_data(item, report.checked_at, query.stale_after_hours)

    return {
        "model_version": RESEARCH_MODEL_VERSION, "status": report.status, "checked_at": report.checked_at,
        "snapshot_id": report.snapshot_id, "consistency": "single_read_snapshot",
        "root_id": report.root_id, "stored_data_only": True,
        "query": {"indicator_type": query.indicator_type, "value": query.value,
                  "max_hops": query.max_hops, "node_limit": query.node_limit,
                  "edge_limit": query.edge_limit, "stale_after_hours": query.stale_after_hours},
        "offset": query.offset, "limit": query.limit, "has_more": report.has_more,
        "next_offset": query.offset + len(report.paths) if report.has_more else None,
        "collected_node_count": report.collected_node_count,
        "collected_edge_count": report.collected_edge_count,
        "collected_path_count": report.collected_path_count,
        "coverage_complete": not report.limitations, "limitations": list(report.limitations),
        "warninglists": {"lists": warninglists,
            "coverage_complete": all(row["latest_status"] == "complete" and row["freshness"] == "fresh" for row in warninglists)},
        "coverage": [{key: item[key] for key in (
            "kind", "scope", "examined_count", "window_limit", "complete", "order")}
            for item in report.coverage],
        "nodes": [{"id": node_id(item.key), "kind": item.key[0], "value": item.key[1],
                   "label": item.label, "record_type": item.record_type,
                   "references": [{key: ref[key] for key in ("kind", "record_type", "namespace", "record_id")}
                                  for ref in item.references],
                   "evidence": [evidence(row) for row in item.evidence],
                   "evidence_total_count": item.evidence_total_count,
                   "enrichment": state_data(item.enrichment, report.checked_at, query.stale_after_hours) if item.enrichment else None,
                   "discovery": status_data(item.discovery, report.checked_at, query.stale_after_hours),
                   "warninglist_matches": [{key: match[key] for key in (
                       "list_id", "run_id", "snapshot_sha256", "matched_entries", "matching_type", "category")}
                       for match in item.warninglist_matches]}
                  for item in report.nodes],
        "edges": [{"id": item.id, "source_id": node_id(item.source), "target_id": node_id(item.target),
                   "relationship_type": item.relationship_type, "kind": item.kind,
                   "evidence": [evidence(row) for row in item.evidence],
                   "evidence_total_count": item.evidence_total_count} for item in report.edges],
        "paths": [{"node_ids": list(nodes), "edge_ids": list(edges), "hops": len(edges)}
                  for nodes, edges in report.paths],
        "notes": [
            "Yalnız seçili çalışma alanının kayıtlı DNS, CNAME, TLS, pasif aday, IOC, CTI, tedarikçi ve URL/dosya kanıtları okunur; kaynaklar yeniden sorgulanmaz.",
            "Yollar iki yönde araştırılabilir; ilişkinin özgün yönü source_id/target_id alanlarında korunur.",
            "Ortak IP, CNAME hedefi, aynı sertifika veya kaynak iddiası sahiplik, aynı saldırgan, kötü niyet veya doğrulanmış ihlal sonucu değildir.",
            "Eski DNS ve geri çekilmiş/geçersiz IOC/CTI iddiaları tarihî kanıt olarak görünür; geçerlilik ile güncellik ayrıdır.",
            "Sayım yalnız toplanan alt grafı kapsar; kısmi sonuç bütün kayıtların tarandığı anlamına gelmez.",
            "Sonraki sayfada expected_snapshot kullanın; değişen kayıtlar snapshot_changed ile reddedilir. Bu tarihî kesit deposu değildir.",
            "Sertifika bağlantısı yalnız kayıtlı web kontrolünde gerçekten sunulmuş sertifikadır; SAN/wildcard adları gözlenmiş domain sayılmaz. certificate düğümü dosya hash IOC'sinden ayrıdır.",
            "CNAME zincirinin her adımı ve yalnız son hedefin IP'si ayrıdır. Tarihî bağlantılar korunur; son başarısız kontrol ve sertifikanın geçerlilik tarihleri bugünkü durumu doğrulamaz.",
            "Ters CNAME, sertifika ve pasif aday bağlantıları sınırlı kayıt kapsamından gelir; bütün arşiv taranmış sayılmaz.",
            "Pasif alt alan adayının arşiv kanıtı ve insan sahiplik sınıflandırması ayrıdır; owned aktif tarama yetkisi veya teknik sahiplik doğrulaması değildir. Keşif çalışmasının hata/boş sonucu eski adayı silmez; bu görünüm yeni sorgu değildir.",
            "Tedarikçi adayı candidate_context, insan kararı human_decision olarak ayrıdır. İnsan kararında current son ilgili kararı belirtir; accepted/withdrawn/rejected ve envanter etkinliği ayrıca okunmalıdır.",
            "Tedarikçi adayının current değeri son aday yenilemesinin durumudur; yeni DNS kontrolü değildir. Teknik kanıtın kaybolması insan onayını kendiliğinden kaldırmaz. Envantere girilmiş domain bağı sahiplik doğrulaması değildir.",
            "Warninglist eşleşmeleri kaynak bağlamıdır; otomatik güvenli kararı, alarm kapatma veya aktör ilişkisi oluşturmaz.",
            "Kaynak araştırması yalnız sorgulanmış URL/hash için saklanan yanıtlardan genişler; ters yönde bütün arşivi taramaz. Yanıt alınma tarihi ile sağlayıcının gözlem tarihi ayrıdır.",
        ],
    }

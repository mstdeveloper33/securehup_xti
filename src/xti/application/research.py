"""Related evidence investigation independent of storage, CLI and transport."""

from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.research import build_research, freshness, node_id, research_query
from xti.ports.research import ResearchRepository
from xti.domain.warninglists import catalog_data
from xti.application.indicator_enrichment import state_data


class ResearchService:
    def __init__(self, repository: ResearchRepository, *, clock=None):
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def show(self, **parameters):
        query = research_query(**parameters)
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("Araştırma zamanı saat dilimi içermeli.")
        checked_at = now.astimezone(timezone.utc).isoformat()
        with self.repository.open(query, checked_at) as reader:
            return build_research(reader, query, checked_at)


def research_data(report) -> dict:
    """Explicit v1 fields shared by CLI, local engine and company platform."""
    query = report.query
    warninglists = catalog_data(report.warninglists, checked_at=report.checked_at)

    def evidence(item):
        return {
            "record_type": item.record_type, "record_id": item.record_id,
            "source": item.source, "source_reference": item.source_reference,
            "kind": item.kind, "status": item.status, "current": item.current,
            "observed_at": item.observed_at, "recorded_at": item.recorded_at,
            "freshness": freshness(item.observed_at, report.checked_at, query.stale_after_hours),
            "description": item.description, "assertion_id": item.assertion_id,
            "event_id": item.event_id, "confidence": item.confidence,
            "valid_from": item.valid_from, "valid_until": item.valid_until,
            "state_sha256": item.state_sha256,
            "first_observed_at": item.first_observed_at, "source_run_id": item.source_run_id,
            "time_basis": item.time_basis,
        }

    return {
        "model_version": 1, "status": report.status, "checked_at": report.checked_at,
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
            "Yalnız seçili çalışma alanının kayıtlı DNS, IOC, CTI ve URL/dosya kaynak yanıtları okunur; kaynaklar yeniden sorgulanmaz.",
            "Yollar iki yönde araştırılabilir; ilişkinin özgün yönü source_id/target_id alanlarında korunur.",
            "Ortak IP veya kaynak iddiası sahiplik, aynı saldırgan, kötü niyet veya doğrulanmış ihlal sonucu değildir.",
            "Eski DNS ve geri çekilmiş/geçersiz IOC/CTI iddiaları tarihî kanıt olarak görünür; geçerlilik ile güncellik ayrıdır.",
            "Sayım yalnız toplanan alt grafı kapsar; kısmi sonuç bütün kayıtların tarandığı anlamına gelmez.",
            "Sonraki sayfada expected_snapshot kullanın; değişen kayıtlar snapshot_changed ile reddedilir. Bu tarihî kesit deposu değildir.",
            "İlk kapsam surface web kontrollerindeki DNS adresleridir; pasif aday, CNAME, sertifika ve diğer modüller mevcut ayrıntı komutlarında kalır.",
            "Warninglist eşleşmeleri kaynak bağlamıdır; otomatik güvenli kararı, alarm kapatma veya aktör ilişkisi oluşturmaz.",
            "Kaynak araştırması yalnız sorgulanmış URL/hash için saklanan yanıtlardan genişler; ters yönde bütün arşivi taramaz. Yanıt alınma tarihi ile sağlayıcının gözlem tarihi ayrıdır.",
        ],
    }

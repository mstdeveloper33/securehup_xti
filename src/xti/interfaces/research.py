"""Terminal investigation and composition; no collector or network client."""

from xti.application.research import ResearchService, research_data, priority_data
from xti.interfaces.text import safe_text, xti_command


def _discovery_lines(states, value, data_dir):
    labels = {'never': 'henüz sorgulanmadı', 'complete_found': 'tamamlandı, aday bulundu',
              'complete_empty': 'tamamlandı, bu yanıtta aday yok', 'partial_found': 'kısmi yanıt, aday var',
              'partial_empty': 'kısmi yanıt, aday görülmedi; sonuç eksik', 'failed': 'son sorgu başarısız',
              'read_limited': 'kaynak durumu okuma sınırına sığmadı'}
    ages = {'fresh': 'güncel kayıt', 'stale': 'eski kayıt', 'future': 'gelecek tarihli kayıt'}
    lines = []
    for state in states:
        lines.append('   Pasif kaynak ' + safe_text(state['provider']) + ': ' + labels[state['outcome']])
        latest, good = state['latest_run'], state['successful_run']
        if latest:
            lines.append('   Sorgu bitişi: ' + safe_text(latest['finished_at']) + ' | ' + ages[latest['freshness']])
            if latest['error']:
                lines.append('   Kaynak hatası: ' + safe_text(latest['error']))
        if state['previous_success_preserved']:
            lines.append('   Önceki tamamlanmış yanıt korunuyor: ' + safe_text(good['finished_at']) +
                         ' | ' + ages[good['freshness']] + ' | ' + safe_text(good['id']))
    if states:
        lines.append('   Kaynak durumu adayların arşiv kanıtını veya insan kararını güncellemez.')
        lines.append('   Ayrıntı: ' + xti_command('surface', 'discovery-health', value, data_dir=data_dir))
    return lines


def _surface_detail_commands(rows, data_dir):
    commands = set()
    for row in rows:
        if row['record_type'] in {'investigation_decision', 'identity_proposal', 'report_candidate'}:
            commands.add(xti_command('investigate', 'show', row['record_id'], data_dir=data_dir))
        if row['record_type'] in {'case_activity', 'case_evidence'}:
            commands.add(xti_command('cases', 'show', row['source_reference'], data_dir=data_dir))
        elif row['record_type'] in {'social_observation', 'social_watch_run'}:
            commands.add(xti_command('brand', 'watch-run-show', row['source_run_id'], data_dir=data_dir))
        elif row['record_type'] == 'social_decision':
            commands.add(xti_command('brand', 'watch-review-show', row['record_id'], data_dir=data_dir))
        elif row['record_type'] == 'organization_social_link':
            commands.add(xti_command('organizations', 'show', row['source_reference'], data_dir=data_dir))
        elif row['record_type'] in {'company_content', 'company_search_run'}:
            commands.add(xti_command('mentions', 'run-show', row['source_run_id'], data_dir=data_dir))
        if row['record_type'] == 'surface_discovery_run':
            commands.add(xti_command('surface', 'run', row['record_id'], data_dir=data_dir))
        if row["record_type"] in {"surface_candidate", "surface_candidate_source", "surface_candidate_decision"}:
            identifier = row["source_reference"] if row["record_type"] == "surface_candidate_decision" else row["record_id"]
            commands.add(xti_command("surface", "candidate", "show", identifier, data_dir=data_dir))
        kind = ("cname" if row["record_type"] in {"surface_cname_check", "surface_cname_observation"} else
                "certificate" if row["record_type"] in {"surface_tls_check", "surface_certificate"} else None)
        if kind:
            commands.add(xti_command("surface", "relations", row["source_reference"],
                "--kind", kind, "--history", data_dir=data_dir))
        if row["record_type"] in {"supplier_candidate", "supplier_candidate_evidence"}:
            commands.add(xti_command("suppliers", "candidate-show", row["record_id"], data_dir=data_dir))
        elif row["record_type"] == "supplier_resolution":
            commands.add(xti_command("suppliers", "candidate-show", row["source_reference"], data_dir=data_dir))
        elif row["record_type"] == "supplier_inventory":
            commands.add(xti_command("suppliers", "show", row["source_reference"], data_dir=data_dir))
        elif row['record_type'] == 'supplier_risk_context':
            commands.add(xti_command('suppliers', 'risk-show', row['record_id'], data_dir=data_dir))
        elif row['record_type'] == 'supplier_threat_match':
            commands.add(xti_command('suppliers', 'event-show', row['record_id'], data_dir=data_dir))
        elif row['record_type'] == 'supplier_watch':
            commands.add(xti_command('suppliers', 'watch', 'show', row['record_id'], data_dir=data_dir))
        elif row['record_type'] in {'supplier_watch_run', 'supplier_watch_item'}:
            identifier = row['record_id'] if row['record_type'] == 'supplier_watch_run' else row['source_reference']
            commands.add(xti_command('suppliers', 'watch-run-show', identifier, data_dir=data_dir))
        elif row['record_type'] == 'supplier_source_run':
            command = ('notices', 'run-show', row['record_id']) if row['source'] == 'hibp' else (
                'ransomware', 'status', '--source', row['source'])
            commands.add(xti_command(*command, data_dir=data_dir))
    return commands


def _record_detail_command(ref, value, data_dir):
    if ref["record_type"] == "surface_candidate":
        return xti_command("surface", "candidate", "show", ref["record_id"], data_dir=data_dir)
    args = (("ioc", "show", ref["record_id"]) if ref["kind"] == "indicator" else
            ("cti", "entity-show", ref["record_id"]) if ref["kind"] == "cti" else
            ("suppliers", "show", ref["record_id"]) if ref["kind"] == "supplier" else
            ("surface", "relations", value, "--kind", "dns", "--history"))
    return xti_command(*args, data_dir=data_dir)


def make_research_service(database):
    from xti.adapters.sqlite_research import SQLiteResearchRepository
    return ResearchService(SQLiteResearchRepository(database))


def register_research_parser(commands):
    parser = commands.add_parser("research", help="Domain/IP/URL/dosya için kayıtlı kaynak kanıt yollarını araştır.")
    parser.add_argument("value")
    parser.add_argument("--type", choices=("domain", "ip", "ipv4", "ipv6", "url", "md5", "sha1", "sha256"), required=True, dest="indicator_type")
    for flag, default in (("max-hops", 2), ("node-limit", 100), ("edge-limit", 200),
                          ("offset", 0), ("limit", 50), ("stale-after-hours", 24)):
        parser.add_argument("--" + flag, type=int, default=default)
    parser.add_argument("--expected-snapshot", help="Önceki sayfanın snapshot_id değeri; kayıtlar değişirse durur.")
    parser.add_argument("--priorities", action="store_true", help="Kayıt ve ilişkileri gerekçeli inceleme sırasıyla göster; --limit öğe sayısıdır.")


def priority_lines(data, *, data_dir=None):
    labels = {"review_first": "Önce incele", "verify": "Doğrula", "context": "Bağlam"}
    lines = ["İnceleme önceliği: " + safe_text(data["query"]["value"]),
             "Öncelik inceleme sırasıdır; risk veya tehdit kararı değildir.",
             f"Bu sayfada {len(data['items'])} / {data['collected_item_count']} kayıt ve ilişki; "
             "yalnız seçili araştırmanın kapsamı."]
    if not data["priority_counts"]["review_first"] and not data["priority_counts"]["verify"]:
        lines.append("Bu sınırlı araştırmada ek inceleme gerekçesi çıkmadı; listelenen öğeler kaynak bağlamıdır.")
    limits = {
        "node_limit": "Kayıt sayısı sınırına ulaşıldı.",
        "edge_limit": "Bağlantı sayısı sınırına ulaşıldı.",
        "path_limit": "İlişki yollarının sayısı sınırına ulaşıldı.",
        "dns_history_window": "DNS/TLS geçmişinin yalnız en son web kontrol penceresi okundu.",
        "dns_read_budget": "DNS/TLS kanıtlarının bir bölümü ortak okuma sınırına sığmadı.",
        "dns_adjacency_limit": "Bazı kayıtların DNS bağlantıları gösterim sınırını aşıyor.",
        "cname_history_window": "CNAME geçmişinin yalnız en son kontrol penceresi okundu.",
        "cname_read_budget": "CNAME kanıtlarının bir bölümü okuma sınırına sığmadı.",
        "cname_adjacency_limit": "Bazı kayıtların CNAME bağlantıları gösterim sınırını aşıyor.",
        "certificate_adjacency_limit": "Bazı sertifikaların domain bağlantıları gösterim sınırını aşıyor.",
        "supplier_adjacency_limit": "Bazı tedarikçi veya aday bağlantıları gösterim sınırını aşıyor.",
        "supplier_read_budget": "Bazı tedarikçi geçmişleri bu isteğin doğrulama sınırına sığmadı; doğrulanmayan kayıt gösterilmedi.",
        "supplier_context_read_budget": "Tedarikçi izleme/risk kanıtının bir bölümü doğrulama sınırına sığmadı; eksik kart üretilmedi.",
        "supplier_context_event_limit": "Tedarikçi iddia adaylarının bir bölümü gösterim sınırına sığmadı; kartın toplamı korunuyor.",
        "discovery_candidate_limit": "Bazı pasif alt alan adayları bu görünümün kayıt sınırına sığmadı.",
        "discovery_read_budget": "Bazı pasif adayların kaynak/karar geçmişi okuma sınırını aştı; doğrulanmayan kayıt gösterilmedi.",
        "discovery_status_read_budget": "Bazı pasif kaynak durumları okuma sınırını aştı; boş sonuç sayılmadı.",
        "cti_adjacency_limit": "Bazı kayıtların CTI bağlantıları gösterim sınırını aşıyor.",
        "source_evidence_limit": "Bazı kayıtların kaynak kanıtları bu görünüme sığmadı.",
        "enrichment_result_window": "URL kaynağının sonuç penceresi sınırlı; bütün arşiv kapsanmıyor.",
    }
    for limitation in data["limitations"]:
        lines.append("Kapsam eksik: " + limits.get(limitation, safe_text(limitation)))
    incomplete_lists = [row["list_id"] for row in data["warninglists"]["lists"]
                        if row["latest_status"] != "complete" or row["freshness"] != "fresh"]
    if incomplete_lists:
        lines.append("Eksik, eski veya başarısız liste bağlamı: " + ", ".join(incomplete_lists))
    for number, item in enumerate(data["items"], data["offset"] + 1):
        lines.append(f"{number}. {labels[item['priority']]} — {safe_text(item['label'])}")
        for reason in item["reasons"]:
            lines.append("   " + reason["message"])
        lines.extend(_discovery_lines(item.get('discovery', []), item['value'], data_dir))
        # Full identities remain in JSON and in the original detail commands;
        # source names here make a short list useful without only counters.
        if item["evidence"]:
            lines.append("   Kaynak: " + ", ".join(sorted({safe_text(row["source"]) for row in item["evidence"]})))
        commands = _surface_detail_commands(item["evidence"], data_dir)
        for ref in item["references"]:
            commands.add(_record_detail_command(ref, item["value"], data_dir))
        if item["subject_kind"] == "relationship" and item["id"].startswith("cti:"):
            commands.add(xti_command("cti", "relation-show", item["id"].removeprefix("cti:"), data_dir=data_dir))
        for row in item["evidence"]:
            if row["record_type"] == "enrichment_run":
                commands.add(xti_command("enrich", "run-show", row["record_id"], data_dir=data_dir))
        for match in item["warninglist_matches"]:
            lines.append("   Liste: " + safe_text(match["list_id"]) + " | " +
                         ", ".join(safe_text(entry) for entry in match["matched_entries"]))
            commands.add(xti_command("warninglists", "run-show", match["run_id"], data_dir=data_dir))
        for command in sorted(commands):
            lines.append("   Ayrıntı: " + command)
    query = data["query"]
    args = ["research", query["value"], "--type", query["indicator_type"]]
    for field in ("max_hops", "node_limit", "edge_limit", "stale_after_hours"):
        args.extend(("--" + field.replace("_", "-"), str(query[field])))
    lines.append("Kanıt yolları: " + xti_command(*args, data_dir=data_dir))
    if data["has_more"]:
        args.extend(("--priorities", "--offset", str(data["next_offset"]), "--limit", str(data["limit"]),
                     "--expected-snapshot", data["snapshot_id"]))
        lines.append("Sonraki sayfa: " + xti_command(*args, data_dir=data_dir))
    return lines


def research_lines(data, *, data_dir=None):
    labels = {"related_records": "İlişkili kanıt var", "partial": "Kısmi araştırma",
              "no_relationships": "Kayıt var, bu kapsamda ilişki yok", "not_recorded": "Bu kapsamda kayıt bulunamadı"}
    states = {"active": "etkin iddia", "revoked": "geri çekilmiş", "expired": "süresi dolmuş",
              "not_yet_valid": "geçerliliği başlamamış", "resolved": "DNS adresi gözlenmiş",
              "failed": "başarısız", "fresh": "güncel", "stale": "eski", "future": "gelecek tarihli",
              "presented": "sertifika gözlenmiş", "valid": "kontrol sırasında TLS geçerli",
              "present": "CNAME gözlenmiş", "absent": "CNAME yok", "nxdomain": "DNS'te ad yok",
              "accepted": "insan onayı", "rejected": "reddedilmiş aday", "uncertain": "belirsiz aday",
              "pending": "inceleme bekleyen aday", "derived": "kayıtlı kanıttan aday",
              "withdrawn": "insan kararıyla kaldırılmış bağlantı", "owned": "insan tarafından bana ait sınıflandırılmış",
              "recorded": "arşivde kayıtlı ad", "enabled": "izleme açık", "disabled": "izleme kapalı",
              "priority_review": "öncelikli insan incelemesi", "review": "iddia incelemesi",
              "identity_review": "kuruluş kimliği belirsiz", "insufficient_data": "veri yetersiz",
              "no_current_match": "son başarılı yanıtlarda eşleşme yok", "not_collected": "kaynak henüz toplanmadı",
              "unavailable": "başarılı kaynak yanıtı yok", "stale_after_failure": "son deneme hatalı, eski yanıt korunuyor",
              "available": "başarılı kaynak yanıtı kayıtlı", "not_evaluated": "henüz karşılaştırılmadı",
              "historical_scope": "önceki kimlik veya izleme kapsamı", "baseline": "sessiz başlangıç",
              "changes": "yerel karşılaştırmada değişim", "domain_match": "domain dayanaklı aday",
              "name_match": "yalnız tam adla aday", "ambiguous_name": "aynı ad nedeniyle belirsiz aday"}
    relations = {"cname_alias": "CNAME yönlendirmesi", "cname_target_address": "CNAME son hedefi → IP",
                 "certificate_presented": "Domain → gözlenmiş TLS sertifikası",
                 "supplier_candidate": "Domain → teknik tedarikçi adayı",
                 "supplier_candidate_domain": "Aday → olası hizmet domaini",
                 "human_supplier_link": "İnsan kararıyla tedarikçi bağlantısı (geçmiş dahil)",
                 "supplier_registered_domain": "Tedarikçi → envantere girilmiş domain",
                 "supplier_risk": "Tedarikçi → hesaplanan inceleme kartı",
                 "supplier_event": "Tedarikçi → kaynak iddiası adayı",
                 "supplier_watch": "Tedarikçi → kaynak bağlı izleme karşılaştırması",
                 "passive_subdomain": "Kök domain → pasif alt alan adayı",
                 "subdomain_classification": "Alt alan sahiplik incelemesi (insan kararı; geçmiş dahil)"}
    lines = [f"İlişkili kanıt araştırması: {safe_text(data['query']['value'])}",
             labels[data["status"]],
             f"Toplanan: {data['collected_node_count']} düğüm, {data['collected_edge_count']} bağlantı, "
             f"{data['collected_path_count']} yol | Bu sayfada: {len(data['paths'])} yol"]
    if data["limitations"]:
        lines.append("Kapsam eksik; ulaşılan sınırlar: " + ", ".join(data["limitations"]))
    nodes = {item["id"]: item for item in data["nodes"]}
    for number, path in enumerate(data["paths"], data["offset"] + 1):
        lines.append(f"{number}. " + " — ".join(safe_text(nodes[key]["label"]) for key in path["node_ids"]))
        lines.append("   Bağlantılar: " + ", ".join(path["edge_ids"]))

    def show_evidence(rows):
        for row in rows:
            when = {"response_received_at": "Yanıt alınma", "decision_recorded_at": "Karar",
                    "stored_seen_range": "Arşivde son görülme", "source_response_received_at": "Kaynak yanıtı",
                    "stored_context_updated_at": "Dayanak kayıt zamanı", "inventory_recorded_at": "Envanter kaydı",
                    "watch_configured_at": "İzleme tanımı"}.get(row["time_basis"], "Gözlem")
            status = states.get(row['status'], safe_text(row['status']))
            if row["kind"] == "human_decision":
                status = ("envanter etkin" if row["status"] == "active" else
                          "envanter pasif" if row["status"] == "revoked" else status)
                status += " | " + ("son karar" if row["current"] else "önceki karar")
            lines.append(f"    {safe_text(row['source'])} | {status} | "
                         f"{states[row['freshness']]} | {when}: {safe_text(row['observed_at'])} | Kayıt: {safe_text(row['recorded_at'])}")
            lines.append(f"    Kanıt: {safe_text(row['record_id'])} | Kaynak: {safe_text(row['source_reference'])}")
            if row["first_observed_at"] != row["observed_at"]:
                lines.append("    İlk gözlem: " + safe_text(row["first_observed_at"]))
            if row["valid_from"] or row["valid_until"]:
                lines.append(f"    Geçerlilik: {safe_text(row['valid_from'] or 'belirtilmemiş')} — {safe_text(row['valid_until'] or 'belirtilmemiş')}")
            if row["assertion_id"]:
                lines.append(f"    İddia: {safe_text(row['assertion_id'])} | Son olay: {safe_text(row['event_id'])} | Kaynak güveni: {row['confidence']}")
            elif row["event_id"]:
                lines.append("    Özgün karar/kanıt olayı: " + safe_text(row["event_id"]))
            if row["source_run_id"]:
                lines.append("    Kaynak çalışması: " + safe_text(row["source_run_id"]))
            lines.append("    " + safe_text(row["description"]))

    for edge in data["edges"]:
        lines.append(f"Bağlantı {edge['id']}: {safe_text(nodes[edge['source_id']]['label'])} → "
                     f"{safe_text(nodes[edge['target_id']]['label'])} | " +
                     relations.get(edge['relationship_type'], safe_text(edge['relationship_type'])))
        show_evidence(edge["evidence"])
        for command in sorted(_surface_detail_commands(edge["evidence"], data_dir)):
            lines.append("  Ayrıntı: " + command)
        if edge["evidence_total_count"] > len(edge["evidence"]):
            lines.append(f"    Bu görünümde gösterilmeyen kanıt: {edge['evidence_total_count'] - len(edge['evidence'])}; ayrıntıyı açın.")
        if edge["kind"] == "source_claim":
            lines.append("  Ayrıntı: " + xti_command("cti", "relation-show", edge["id"].removeprefix("cti:"), data_dir=data_dir))
    for node in data["nodes"]:
        lines.append("Kayıt: " + safe_text(node["label"]))
        lines.extend(_discovery_lines(node.get('discovery', []), node['value'], data_dir))
        show_evidence(node["evidence"])
        for command in sorted(_surface_detail_commands(node["evidence"], data_dir)):
            lines.append("  Ayrıntı: " + command)
        if node.get("enrichment") and node["enrichment"]["latest_run"]:
            from xti.interfaces.indicator_enrichment import enrichment_lines
            lines.extend(enrichment_lines(node["enrichment"], data_dir=data_dir))
        for match in node["warninglist_matches"]:
            lines.append("  Liste bağlamı: " + safe_text(match["list_id"]) + " | " +
                         ", ".join(safe_text(entry) for entry in match["matched_entries"]))
            lines.append("  Liste kanıtı: " + xti_command("warninglists", "run-show", match["run_id"], data_dir=data_dir))
        if node["evidence_total_count"] > len(node["evidence"]):
            lines.append(f"    Bu görünümde gösterilmeyen kanıt: {node['evidence_total_count'] - len(node['evidence'])}; ayrıntıyı açın.")
        for ref in node["references"]:
            lines.append("  Ayrıntı: " + _record_detail_command(ref, node["value"], data_dir))
    if data["has_more"]:
        query = data["query"]
        args = ["research", query["value"], "--type", query["indicator_type"]]
        for field in ("max_hops", "node_limit", "edge_limit", "stale_after_hours"):
            args.extend(("--" + field.replace("_", "-"), str(query[field])))
        args.extend(("--offset", str(data["next_offset"]), "--limit", str(data["limit"]),
                     "--expected-snapshot", data["snapshot_id"]))
        lines.append("Sonraki sayfa: " + xti_command(*args, data_dir=data_dir))
    from xti.interfaces.warninglists import warninglist_lines
    lines.extend(warninglist_lines(data["warninglists"], data_dir=data_dir))
    lines.extend("Not: " + note for note in data["notes"])
    return lines


def execute_research(database, args):
    parameters = {key: getattr(args, key) for key in (
        "indicator_type", "value", "max_hops", "node_limit", "edge_limit", "offset",
        "limit", "stale_after_hours", "expected_snapshot")}
    service = make_research_service(database)
    if args.priorities:
        data = priority_data(service.priorities(**parameters))
        return data, priority_lines(data, data_dir=args.data_dir)
    data = research_data(service.show(**parameters))
    return data, research_lines(data, data_dir=args.data_dir)

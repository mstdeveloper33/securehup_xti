"""Terminal investigation and composition; no collector or network client."""

from xti.application.research import ResearchService, research_data, priority_data
from xti.interfaces.text import safe_text, xti_command


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
        "dns_history_window": "DNS geçmişinin yalnız en son kontrol penceresi okundu.",
        "dns_read_budget": "DNS kanıtlarının bir bölümü okuma boyutu sınırına sığmadı.",
        "dns_adjacency_limit": "Bazı kayıtların DNS bağlantıları gösterim sınırını aşıyor.",
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
        # Full identities remain in JSON and in the original detail commands;
        # source names here make a short list useful without only counters.
        if item["evidence"]:
            lines.append("   Kaynak: " + ", ".join(sorted({safe_text(row["source"]) for row in item["evidence"]})))
        commands = set()
        for ref in item["references"]:
            args = (("ioc", "show", ref["record_id"]) if ref["kind"] == "indicator" else
                    ("cti", "entity-show", ref["record_id"]) if ref["kind"] == "cti" else
                    ("surface", "relations", item["value"], "--kind", "dns", "--history"))
            commands.add(xti_command(*args, data_dir=data_dir))
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
              "failed": "başarısız", "fresh": "güncel", "stale": "eski", "future": "gelecek tarihli"}
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
            lines.append(f"    {safe_text(row['source'])} | {states.get(row['status'], safe_text(row['status']))} | "
                         f"{states[row['freshness']]} | {'Yanıt alınma' if row['time_basis'] == 'response_received_at' else 'Gözlem'}: {safe_text(row['observed_at'])} | Kayıt: {safe_text(row['recorded_at'])}")
            lines.append(f"    Kanıt: {safe_text(row['record_id'])} | Kaynak: {safe_text(row['source_reference'])}")
            if row["first_observed_at"] != row["observed_at"]:
                lines.append("    İlk gözlem: " + safe_text(row["first_observed_at"]))
            if row["valid_from"] or row["valid_until"]:
                lines.append(f"    Geçerlilik: {safe_text(row['valid_from'] or 'belirtilmemiş')} — {safe_text(row['valid_until'] or 'belirtilmemiş')}")
            if row["assertion_id"]:
                lines.append(f"    İddia: {safe_text(row['assertion_id'])} | Son olay: {safe_text(row['event_id'])} | Kaynak güveni: {row['confidence']}")
            if row["source_run_id"]:
                lines.append("    Kaynak çalışması: " + safe_text(row["source_run_id"]))
            lines.append("    " + safe_text(row["description"]))

    for edge in data["edges"]:
        lines.append(f"Bağlantı {edge['id']}: {safe_text(nodes[edge['source_id']]['label'])} → "
                     f"{safe_text(nodes[edge['target_id']]['label'])} | {safe_text(edge['relationship_type'])}")
        show_evidence(edge["evidence"])
        if edge["evidence_total_count"] > len(edge["evidence"]):
            lines.append(f"    Bu görünümde gösterilmeyen kanıt: {edge['evidence_total_count'] - len(edge['evidence'])}; ayrıntıyı açın.")
        if edge["kind"] == "source_claim":
            lines.append("  Ayrıntı: " + xti_command("cti", "relation-show", edge["id"].removeprefix("cti:"), data_dir=data_dir))
    for node in data["nodes"]:
        lines.append("Kayıt: " + safe_text(node["label"]))
        show_evidence(node["evidence"])
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
            args = (("ioc", "show", ref["record_id"]) if ref["kind"] == "indicator" else
                    ("cti", "entity-show", ref["record_id"]) if ref["kind"] == "cti" else
                    ("surface", "relations", node["value"], "--kind", "dns", "--history"))
            lines.append("  Ayrıntı: " + xti_command(*args, data_dir=data_dir))
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

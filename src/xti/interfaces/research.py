"""Terminal investigation and composition; no collector or network client."""

from xti.application.research import ResearchService, research_data
from xti.interfaces.text import safe_text, xti_command


def make_research_service(database):
    from xti.adapters.sqlite_research import SQLiteResearchRepository
    return ResearchService(SQLiteResearchRepository(database))


def register_research_parser(commands):
    parser = commands.add_parser("research", help="Domain/IP için kayıtlı DNS, IOC ve CTI kanıt yollarını araştır.")
    parser.add_argument("value")
    parser.add_argument("--type", choices=("domain", "ip", "ipv4", "ipv6"), required=True, dest="indicator_type")
    for flag, default in (("max-hops", 2), ("node-limit", 100), ("edge-limit", 200),
                          ("offset", 0), ("limit", 50), ("stale-after-hours", 24)):
        parser.add_argument("--" + flag, type=int, default=default)
    parser.add_argument("--expected-snapshot", help="Önceki sayfanın snapshot_id değeri; kayıtlar değişirse durur.")


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
                         f"{states[row['freshness']]} | Gözlem: {safe_text(row['observed_at'])} | Kayıt: {safe_text(row['recorded_at'])}")
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
    data = research_data(make_research_service(database).show(**parameters))
    return data, research_lines(data, data_dir=args.data_dir)

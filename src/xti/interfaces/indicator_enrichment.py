"""Operator acquisition and shared offline context views."""
from xti.application.indicator_enrichment import EnrichmentService
from xti.interfaces.text import safe_text, xti_command


def make_enrichment_service(database, *, refresh=False, request_usage=None):
    from xti.adapters.sqlite_enrichment import SQLiteEnrichmentRepository
    from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
    from xti.adapters.enrichment_sources import PublicEnrichmentSource
    return EnrichmentService(SQLiteEnrichmentRepository(database),
        PublicEnrichmentSource(SQLiteCooldownRepository(database), request_usage=request_usage) if refresh else None)


def register_enrichment_parser(commands):
    parser = commands.add_parser("enrich", help="URL ve dosya kimliği için kaynaklı bağlam araştırması.")
    actions = parser.add_subparsers(dest="enrichment_action", required=True)
    for name, help_text in (("fetch", "URL/hash değerini resmî kaynağa sorgula ve yanıtı sakla."),
                            ("lookup", "Kayıtlı yanıtı ağ kullanmadan göster."),
                            ("history", "Kaynak sorgulama geçmişini göster.")):
        sub = actions.add_parser(name, help=help_text)
        sub.add_argument("value")
        sub.add_argument("--type", dest="indicator_type", choices=("url", "md5", "sha1", "sha256", "ipv4", "ipv6"), required=True)
        sub.add_argument("--provider", choices=("circl", "urlscan", "ripestat"))
        if name == "lookup":
            sub.add_argument("--stale-after-hours", type=int, default=24)
        if name == "history":
            sub.add_argument("--offset", type=int, default=0)
            sub.add_argument("--limit", type=int, default=20)
    show = actions.add_parser("run-show", help="Kaynak çalışmasının değişmez ayrıntısını aç.")
    show.add_argument("run_id")


def enrichment_lines(data, *, data_dir=None):
    states = {"never": "henüz sorgulanmadı", "matched": "kaynak kaydı var", "no_match": "bu yanıtta eşleşme yok",
        "failed": "son deneme başarısız", "fresh": "yakın zamanda alındı", "stale": "eski yanıt", "future": "saat tutarsızlığı"}
    lines = ["Kaynak araştırması: " + safe_text(data["source"]["label"])]
    if "query" in data:
        lines.append("Değer: " + safe_text(data["query"]["value"]))
    if "status" in data:
        lines.append("Durum: " + states[data["status"]] + " | " + states[data["freshness"]])
        if data["latest_run"] and data["latest_run"]["error"]:
            lines.append("Hata: " + safe_text(data["latest_run"]["error"]))
        if data["successful_run"]:
            good = data["successful_run"]
            lines.append("Son geçerli yanıt: " + safe_text(good["finished_at"]) + " | " + states[good["status"]])
            lines.append("Kanıt: " + xti_command("enrich", "run-show", good["id"], data_dir=data_dir))
    for run in data.get("runs", []) or ([data["run"]] if "run" in data else []):
        lines.append(f"{safe_text(run['id'])} | {states[run['status']]} | {safe_text(run['finished_at'])}")
        if run["error"]:
            lines.append("  " + safe_text(run["error"]))
        if run["snapshot_sha256"]:
            lines.append("  Yanıt SHA-256: " + run["snapshot_sha256"])
    for row in data.get("records", []):
        lines.append("Kayıt: " + safe_text(row["reference"]))
        if row["observed_at"]:
            lines.append("  Kaynak gözlem tarihi: " + safe_text(row["observed_at"]))
        for key, value in row["attributes"].items():
            lines.append("  " + safe_text(key) + ": " + safe_text(str(value)))
    if data.get("has_more"):
        if "runs" in data:
            query = data["query"]
            lines.append("Sonraki sayfa: " + xti_command("enrich", "history", query["value"], "--type", query["indicator_type"],
                "--provider", query["provider"], "--offset", str(data["offset"] + data["limit"]), "--limit", str(data["limit"]), data_dir=data_dir))
        else:
            lines.append("Kaynakta ek sonuç var; bu sorgu ilk 20 arşiv kaydıyla sınırlıdır.")
    if data.get("excluded_count"):
        lines.append(f"Tam URL eşleşmesi olmadığı için dışarıda kalan kayıt: {data['excluded_count']}")
    if data.get("search_date_limit_days"):
        lines.append(f"Kaynağın arama penceresi: son {data['search_date_limit_days']} gün.")
    lines.append("Kaynak / kullanım koşulları: " + data["source"]["terms_url"])
    lines.extend("Not: " + safe_text(note) for note in data.get("notes", []))
    return lines


def execute_enrichment(database, args):
    action = args.enrichment_action
    service = make_enrichment_service(database, refresh=action == "fetch")
    if action == "run-show":
        data = service.show(args.run_id)
    else:
        query = {key: getattr(args, key) for key in ("provider", "indicator_type", "value")}
        if action == "fetch":
            from xti.adapters.worker_lock import LocalExecutionLock
            with LocalExecutionLock(database).acquire():
                data = service.refresh(**query)
        elif action == "history":
            data = service.history(**query, offset=args.offset, limit=args.limit)
        else:
            data = service.lookup(**query, stale_after_hours=args.stale_after_hours)
    return data, enrichment_lines(data, data_dir=args.data_dir)

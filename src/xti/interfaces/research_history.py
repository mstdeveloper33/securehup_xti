"""Terminal and company request composition for frozen research reviews."""

from xti.application.research_history import ResearchHistoryService
from xti.domain.engine import EngineContractError
from xti.domain.research_history import ResearchHistoryError, SCOPE_FIELDS
from xti.interfaces.research import make_research_service
from xti.interfaces.text import safe_text, xti_command


def make_history_service(database):
    from xti.adapters.sqlite_research_history import SQLiteResearchHistoryRepository
    return ResearchHistoryService(SQLiteResearchHistoryRepository(database), make_research_service(database))


def register_history_parser(commands):
    parser = commands.add_parser("research-history", help="İncelemeyi açıkça kaydet; önceki kayıtla değişimini gör.")
    actions = parser.add_subparsers(dest="history_action", required=True)
    for name, label in (("record", "Yeni inceleme kaydet ve aynı kapsamın önceki kaydıyla karşılaştır."),
                        ("list", "Seçili domain/IP/URL/dosyanın kayıtlı incelemelerini listele.")):
        action = actions.add_parser(name, help=label)
        action.add_argument("value")
        action.add_argument("--type", dest="indicator_type", required=True,
                            choices=("domain", "ip", "ipv4", "ipv6", "url", "md5", "sha1", "sha256"))
        if name == "record":
            for flag, default in (("max-hops", 2), ("node-limit", 100), ("edge-limit", 200), ("stale-after-hours", 24)):
                action.add_argument("--" + flag, type=int, default=default)
            action.add_argument("--idempotency-key", help="Aynı anahtar/kapsam mevcut kaydı döndürür; ikinci kayıt oluşturmaz.")
        else:
            action.add_argument("--offset", type=int, default=0)
            action.add_argument("--limit", type=int, default=20)
            action.add_argument("--expected-snapshot")
    show = actions.add_parser("show", help="Saklanan değişim veya inceleme öğelerini özgün tarihleriyle göster.")
    show.add_argument("review_id")
    show.add_argument("--view", choices=("changes", "items"), default="changes")
    show.add_argument("--offset", type=int, default=0)
    show.add_argument("--limit", type=int, default=20)


def history_lines(data, *, data_dir=None):
    states = {"baseline": "İlk kayıt; karşılaştırma için başlangıç oluşturuldu.",
              "policy_baseline": "Kural sürümü değişti; yeni başlangıç oluşturuldu.",
              "unchanged": "Önceki aynı kapsamlı incelemeye göre değişiklik yok.",
              "changed": "Önceki aynı kapsamlı incelemeye göre değişiklik var."}
    priority = {"review_first": "Önce incele", "verify": "Doğrula", "context": "Bağlam"}
    kinds = {"entered_view": "İnceleme görünümüne eklendi", "not_in_current_view": "Bu incelemede görünmüyor",
             "changed": "Kayıt değişti"}
    origins = {"visibility": "Görünüm değişimi; tehdit kararı değil.",
               "time_only": "Kayıtlı kanıt aynı; yalnız zaman değerlendirmesi değişti.",
               "evidence_or_mixed": "Kanıt veya kaynak bağlamı değişti; zamanın etkisi de bulunabilir."}
    if "records" in data:
        lines = ["İnceleme geçmişi: " + safe_text(data["query"]["value"]),
                 f"Bu sayfada {len(data['records'])} / {data['total_count']} kayıt"]
        for row in data["records"]:
            lines.extend((f"{row['id']} | {row['checked_at']} | {states[row['comparison']['state']]}",
                f"  Kapsam: {row['query']['max_hops']} ilişki adımı, {row['query']['stale_after_hours']} saat güncellik; "
                f"en çok {row['query']['node_limit']} kayıt / {row['query']['edge_limit']} ilişki.",
                "  Ayrıntı: " + xti_command("research-history", "show", row["id"], data_dir=data_dir)))
        if data["has_more"]:
            lines.append("Sonraki sayfa: " + xti_command("research-history", "list", data["query"]["value"],
                "--type", data["query"]["indicator_type"], "--offset", str(data["next_offset"]),
                "--limit", str(data["limit"]), "--expected-snapshot", data["snapshot_id"], data_dir=data_dir))
        return lines
    row = data["review"]
    lines = ["Kayıtlı inceleme: " + row["id"], "Hedef: " + safe_text(row["query"]["value"]),
             "Değerlendirme tarihi: " + row["checked_at"], states[row["comparison"]["state"]]]
    if data.get("replayed"):
        lines.append("Aynı istek için mevcut kayıt döndürüldü.")
    if row["comparison"]["coverage_limited"]:
        lines.append("Araştırma kapsamı kısmi; görünmeyen kayıtların kaldırıldığı sonucu çıkarılmaz.")
    if row["comparison"]["context_changed"]:
        lines.append("Kaynak listesi durumu veya araştırmanın kapsam bilgisi değişti.")
        lines.append("  " + origins[row["comparison"]["context_origin"]])
    for change in data.get("changes", []):
        before, after = change["before"], change["after"]
        lines.append(kinds[change["kind"]] + ": " + safe_text((after or before)["label"]))
        if before and after:
            lines.append("  Öncelik: " + priority[before["priority"]] + " → " + priority[after["priority"]])
        lines.append("  " + origins[change["origin"]])
        if change["withdrawn_assertion_ids"]:
            lines.append("  Açıkça geri çekilen kaynak iddiaları: " + ", ".join(change["withdrawn_assertion_ids"]))
    if data.get("evaluation"):
        for item in data["evaluation"]["items"]:
            lines.append(priority[item["priority"]] + ": " + safe_text(item["label"]))
            lines.extend("  " + safe_text(reason["message"]) for reason in item["reasons"])
            for evidence in item["evidence"]:
                lines.append("  Kaynak: " + safe_text(evidence["source"]) + " | Kanıt: " + safe_text(evidence["record_id"]))
    lines.append("Kaydedilen öğeler: " + xti_command("research-history", "show", row["id"], "--view", "items", data_dir=data_dir))
    lines.append("Değişim ayrıntısı: " + xti_command("research-history", "show", row["id"], data_dir=data_dir))
    if row["previous_id"]:
        lines.append("Önceki inceleme: " + xti_command("research-history", "show", row["previous_id"], data_dir=data_dir))
    if data.get("has_more"):
        lines.append("Sonraki sayfa: " + xti_command("research-history", "show", row["id"], "--view", data["view"],
            "--offset", str(data["next_offset"]), "--limit", str(data["limit"]), data_dir=data_dir))
    return lines


def execute_history(database, args):
    service = make_history_service(database)
    if args.history_action == "record":
        data = service.record(**{key: getattr(args, key) for key in SCOPE_FIELDS}, idempotency_key=args.idempotency_key)
    elif args.history_action == "list":
        data = service.history(indicator_type=args.indicator_type, value=args.value, offset=args.offset,
                               limit=args.limit, expected_snapshot=args.expected_snapshot)
    else:
        data = service.show(args.review_id, view=args.view, offset=args.offset, limit=args.limit)
    return data, history_lines(data, data_dir=args.data_dir)


def execute_platform_record(context, parameters):
    parameters = dict(parameters)
    if parameters.pop("expected_workspace_id") != context.workspace_id:
        raise EngineContractError("scope_mismatch", "İstek güncel firma veri alanına ait değil; kapsamı yeniden alın.")
    try:
        return make_history_service(context.database).record(**parameters)
    except ResearchHistoryError as error:
        raise EngineContractError(error.code, str(error)) from error

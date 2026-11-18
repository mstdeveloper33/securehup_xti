"""Operator refresh and identical read-only context for CLI/engine/platform."""

from xti.application.warninglists import WarninglistService
from xti.domain.warninglists import POLICIES
from xti.interfaces.text import safe_text, xti_command


def make_warninglist_service(database, *, refresh=False, request_usage=None):
    from xti.adapters.sqlite_warninglists import SQLiteWarninglistRepository
    from xti.adapters.misp_warninglists import MispWarninglistSource
    return WarninglistService(SQLiteWarninglistRepository(database),
        MispWarninglistSource(request_usage=request_usage) if refresh else None)


def register_warninglist_parser(commands):
    parser = commands.add_parser("warninglists", help="MISP kaynak listelerini güncelle ve domain/IP bağlamını incele.")
    actions = parser.add_subparsers(dest="warninglist_action", required=True)
    sync = actions.add_parser("sync", help="Seçili resmî listeleri internetten al; hata olursa önceki listeyi koru.")
    sync.add_argument("--list", dest="list_ids", action="append", choices=tuple(POLICIES))
    status = actions.add_parser("status", help="Kayıtlı liste, güncellik ve kaynak hataları.")
    status.add_argument("--stale-after-hours", type=int, default=168)
    lookup = actions.add_parser("lookup", help="Kayıtlı listelerden domain/IP bağlamı; internete sorgu göndermez.")
    lookup.add_argument("value")
    lookup.add_argument("--type", dest="indicator_type", choices=("domain", "ip", "ipv4", "ipv6"), required=True)
    lookup.add_argument("--stale-after-hours", type=int, default=168)
    history = actions.add_parser("history", help="Liste güncelleme geçmişi.")
    history.add_argument("list_id", choices=tuple(POLICIES))
    show = actions.add_parser("run-show", help="Özgün kaynak çalışmasını ve liste kayıtlarını aç.")
    show.add_argument("run_id")
    for action, limit in ((history, 20), (show, 100)):
        action.add_argument("--offset", type=int, default=0)
        action.add_argument("--limit", type=int, default=limit)


def warninglist_lines(data, *, data_dir=None):
    statuses = {"never": "henüz alınmadı", "failed": "son deneme başarısız", "complete": "tamamlandı",
                "fresh": "yakın zamanda alındı", "stale": "eski indirme", "future": "saat tutarsızlığı"}
    lines = ["MISP warninglists — kaynak bağlamı"]
    for row in data.get("lists", []):
        lines.append(f"{safe_text(row['label'])}: {statuses[row['latest_status']]} | {statuses[row['freshness']]}")
        if row["fetched_at"]:
            lines.append(f"  Son geçerli indirme: {safe_text(row['fetched_at'])} | Liste sürümü: {row['source_version']} | Kayıt: {row['entry_count']}")
            lines.append("  Kaynak: " + safe_text(row["source_url"]))
            lines.append("  Ayrıntı: " + xti_command("warninglists", "run-show", row["success_run_id"], data_dir=data_dir))
        if row["error"]:
            lines.append("  Hata: " + safe_text(row["error"]))
    for match in data.get("matches", []):
        lines.append(f"Eşleşme: {safe_text(match['list_id'])} | " + ", ".join(safe_text(value) for value in match["matched_entries"]))
    if "matches" in data and not data["matches"]:
        lines.append("Eldeki listelerde eşleşme yok." if data["coverage_complete"] else "Eldeki listelerde eşleşme yok; kaynak kapsamı eksik/eski veya son deneme başarısız.")
    runs = data.get("runs", []) or ([data["run"]] if "run" in data else [])
    for run in runs:
        lines.append(f"{safe_text(run['list_id'])} | {statuses[run['status']]} | {safe_text(run['finished_at'])} | {safe_text(run['id'])}")
        if run["error"]:
            lines.append("  " + safe_text(run["error"]))
        lines.append("  Ayrıntı: " + xti_command("warninglists", "run-show", run["id"], data_dir=data_dir))
    if "entries" in data:
        if data.get("name"):
            lines.append("Liste: " + safe_text(data["name"]))
            lines.append(f"Kaynak liste sürümü: {data['source_version']} | Tür: {safe_text(data['matching_type'])}")
        if data.get("source_url"):
            lines.append("Kaynak: " + safe_text(data["source_url"]))
            lines.append("Kaynak commit: " + safe_text(data["run"]["revision"]))
        if data["run"]["snapshot_sha256"]:
            lines.append("İçerik SHA-256: " + safe_text(data["run"]["snapshot_sha256"]))
        lines.append("Veri lisansı: " + safe_text(data["license"]) + " | " + safe_text(data["license_reference"]))
        lines.append(f"Liste kayıtları: {len(data['entries'])}/{data['entry_count'] or 0} | Başlangıç: {data['offset']}")
        lines.extend("  " + safe_text(value) for value in data["entries"])
    if data.get("has_more"):
        action, identifier = ("run-show", data["run"]["id"]) if "run" in data else ("history", data["list_id"])
        lines.append("Sonraki sayfa: " + xti_command("warninglists", action, identifier,
            "--offset", str(data["offset"] + data["limit"]), "--limit", str(data["limit"]), data_dir=data_dir))
    lines.extend("Not: " + safe_text(note) for note in data.get("notes", []))
    return lines


def execute_warninglists(database, args):
    service = make_warninglist_service(database, refresh=args.warninglist_action == "sync")
    if args.warninglist_action == "sync":
        from xti.adapters.worker_lock import LocalExecutionLock
        with LocalExecutionLock(database).acquire():
            data = service.sync(args.list_ids)
    elif args.warninglist_action == "status":
        data = service.status(args.stale_after_hours)
    elif args.warninglist_action == "lookup":
        data = service.lookup(indicator_type=args.indicator_type, value=args.value, stale_after_hours=args.stale_after_hours)
    elif args.warninglist_action == "history":
        data = service.history(args.list_id, offset=args.offset, limit=args.limit)
    else:
        data = service.show(args.run_id, offset=args.offset, limit=args.limit)
    return data, warninglist_lines(data, data_dir=args.data_dir)

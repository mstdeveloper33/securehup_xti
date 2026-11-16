"""CLI/JSON composition for the same managed scan service used by platform hosts."""

from xti.adapters.managed_nmap import ManagedNmapRuntime, NmapWorkerLock
from xti.adapters.sqlite import SQLiteAssetRepository
from xti.adapters.sqlite_nmap_jobs import SQLiteNmapWorkRepository
from xti.adapters.sqlite_nmap_management import SQLiteNmapManagementRepository
from xti.adapters.sqlite_surface import SQLiteSurfaceRepository
from xti.application.nmap_execution import NmapExecutionService
from xti.application.nmap_management import NmapManagementService
from xti.domain.nmap_options import nmap_capabilities
from xti.interfaces.text import safe_text


def make_nmap_service(database):
    lock = NmapWorkerLock(database)
    management = NmapManagementService(SQLiteAssetRepository(database), SQLiteSurfaceRepository(database),
                                      SQLiteNmapManagementRepository(database), lock)
    return NmapExecutionService(management, SQLiteNmapWorkRepository(database), lock, ManagedNmapRuntime())


def register_nmap_execution_parsers(actions):
    actions.add_parser("capabilities", help="Arayüz için seçenek kataloğu; ağ veya kayıt alanı gerektirmez.")
    jobs = actions.add_parser("jobs", help="Nmap işlerini kuyruğa al, çalıştır, iptal et ve sonuçları oku.")
    commands = jobs.add_subparsers(dest="nmap_job_action", required=True)
    for name, help_text in (
        ("submit", "Planı kalıcı kuyruğa al; tarama başlatmaz."),
        ("list", "Domain işlerini ve ilerlemesini göster."),
        ("show", "Hedef başına kanıtı sayfalı göster."),
        ("worker", "Seçilen kuyruk işini çalıştır."),
        ("cancel", "Kuyruktaki veya çalışan işin iptalini iste."),
        ("recover", "Kesilmiş işi kayda geçir; otomatik tarama yapmaz."),
        ("resume", "Kesilmiş işte hiç başlanmamış hedefleri yeniden kuyruğa al."),
    ):
        parser = commands.add_parser(name, help=help_text)
        parser.add_argument("domain")
        if name == "submit":
            parser.add_argument("plan_id")
            parser.add_argument("--request-key", required=True)
        elif name != "list":
            parser.add_argument("job_id")
        if name in {"list", "show"}:
            parser.add_argument("--limit", type=int, default=20)
            parser.add_argument("--offset", type=int, default=0)


def work_lines(work):
    data = work.summary()
    return [f"Nmap işi: {work.id} | {safe_text(work.status)}",
            f"Hedefler: {data['target_count']} | sonuç: {data['finished_count']} | başlanmamış: {data['pending_count']}",
            f"İptal isteği: {'var' if data['cancel_requested'] else 'yok'}"]


def result_page(work, offset, limit):
    if type(offset) is not int or not 0 <= offset <= 4096 or type(limit) is not int or not 1 <= limit <= 100:
        from xti.domain.assets import ValidationError
        raise ValidationError("Nmap sonuç sayfalaması geçersiz.")
    items = list(work.results[offset:offset + limit])
    more = offset + len(items) < len(work.results)
    return {"job": work.summary(), "results": items, "offset": offset, "limit": limit,
            "total_results": len(work.results), "next_offset": offset + len(items) if more else None}


def execute_nmap_work_command(service, args):
    action = args.nmap_job_action
    if action == "submit":
        work = service.submit(args.domain, args.plan_id, args.request_key)
    elif action == "list":
        jobs = service.list(args.domain, limit=args.limit, offset=args.offset)
        return {"jobs": [w.summary() for w in jobs], "offset": args.offset, "limit": args.limit}, [
            line for work in jobs for line in work_lines(work)]
    elif action == "show":
        work = service.show(args.domain, args.job_id)
        data = result_page(work, args.offset, args.limit)
        lines = work_lines(work)
        for item in data["results"]:
            lines.append(f"  {safe_text(item['address'])} | {safe_text(item['status'])} | {safe_text(item['reason'])}")
            lines.append("    Port durumları: " + safe_text(str(item["port_states"])))
            for port in item["ports"]:
                lines.append(f"    {port['port']}/{port['protocol']} {safe_text(port['state'])} | {safe_text(str(port['service']))}")
            for match in item["os_matches"]:
                lines.append(f"    OS tahmini: {safe_text(match['name'])} | Nmap eşleşmesi %{match['accuracy']}")
            for script in item["scripts"]:
                lines.append(f"    NSE {script['id']} ({script['port']}): {safe_text(script['output'])}")
            if item["scripts_without_output"]:
                lines.append("    Saklanan çıktısı olmayan kontroller (temiz sonuç anlamına gelmez): " + ", ".join(item["scripts_without_output"]))
        if data["next_offset"] is not None:
            lines.append(f"Devam: --offset {data['next_offset']} --limit {args.limit}")
        return data, lines
    else:
        method = "work" if action == "worker" else action
        work = getattr(service, method)(args.domain, args.job_id)
    return {"job": work.summary()}, work_lines(work)

"""Company/supplier monitoring commands and escaped, evidence-linked output."""

from pathlib import Path

from xti.domain.mention_groups import MentionGroupDefinition
from xti.domain.mentions import build_query
from xti.interfaces.mentions import _wire, mentions_command, run_lines
from xti.interfaces.scheduling import generated_lines
from xti.interfaces.text import safe_text


def register_mention_groups(actions):
    groups = actions.add_parser("groups", help="Firmanı ve seçtiğin tedarikçileri bütçeli olarak birlikte izle.")
    commands = groups.add_subparsers(dest="mention_group_action", required=True)
    save = commands.add_parser("save", help="İzleme grubunu oluştur veya aynı adla sürümlü güncelle; arama yapmaz.")
    save.add_argument("name")
    save.add_argument("--organization", required=True)
    save.add_argument("--supplier", action="append", default=[])
    save.add_argument("--topic", choices=("general", "news"), default="news")
    save.add_argument("--max-results", type=int, default=10)
    save.add_argument("--interval-hours", type=int, default=23)
    save.add_argument("--run-queries", type=int, default=20)
    save.add_argument("--daily-queries", type=int, default=20)
    listing = commands.add_parser("list", help="Kaydedilen izleme gruplarını göster.")
    listing.add_argument("--all", action="store_true")
    for name in ("show", "plan", "runs", "run", "monitor", "disable", "schedule", "prepare"):
        item = commands.add_parser(name, help={
            "show": "Grup tanımını ve günlük kullanımını göster.",
            "plan": "Bütün hedef sorgularını ve bütçeyi ağsız göster.",
            "runs": "Grubun değişmez çalışma geçmişini göster.",
            "run": "Zamanı ve bütçesi uygunsa tek tur topla ve yerel bildirimleri işle.",
            "monitor": "Sınırlı süre terminalde tekrarla; kayıtlı aralık ve bütçeyi koru.",
            "disable": "Yeni toplamalara grubu kapat; geçmişi koru.",
            "schedule": "Linux hizmet/zamanlayıcı dosyalarını yeni klasöre üret.",
            "prepare": "Zamanlama öncesi plan ve doğrulanmış yedek kontrolü yap.",
        }[name])
        item.add_argument("group_id")
        if name in {"run", "monitor", "schedule"}:
            item.add_argument("--api-key-file", type=Path)
        if name == "run":
            item.add_argument("--request-id", help="Aynı UUID ile tekrar çağrı yeni internet araması yapmaz.")
        if name == "runs":
            item.add_argument("--offset", type=int, default=0)
            item.add_argument("--limit", type=int, default=20)
        if name == "monitor":
            item.add_argument("--cycles", type=int, default=2)
            item.add_argument("--interval-seconds", type=int, default=60)
            item.add_argument("--duration-seconds", type=int, default=600)
        if name == "disable":
            item.add_argument("--reason", required=True)
        if name in {"schedule", "prepare"}:
            item.add_argument("--keep", type=int, default=7)
        if name == "prepare":
            item.add_argument("--calendar-hours", type=int, choices=(24, 168))
        if name == "schedule":
            item.add_argument("--output", required=True)
            item.add_argument("--at", required=True)
            item.add_argument("--timezone", default="UTC")
            item.add_argument("--weekday", choices=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--limit", type=int, default=20)
    for name in ("run-show", "resume"):
        item = commands.add_parser(name, help="Çalışma kanıtını görüntüle." if name == "run-show" else
                                   "Kesilmiş işi devam ettir; sonucu belirsiz sorguları tekrarlama.")
        item.add_argument("run_id")
        if name == "run-show":
            item.add_argument("--details", action="store_true", help="Her hedefin bütün kaynak sonuçlarını da göster.")
        else:
            item.add_argument("--api-key-file", type=Path)


def group_lines(group):
    definition = group.definition
    return [f"İzleme grubu: {safe_text(group.name)} | {'etkin' if group.active else 'kapalı'} | sürüm {group.revision}",
            f"  Kimlik: {group.id}", f"  Kuruluş: {definition.organization_id}",
            "  Tedarikçiler: " + (", ".join(definition.supplier_ids) or "Seçilmedi"),
            f"  Konu: {definition.topic} | hedef başına en çok {definition.max_results} sonuç",
            f"  En az aralık: {definition.interval_hours} saat | çalışma sınırı: {definition.per_run_queries} sorgu",
            f"  Grup günlük sınırı: {definition.daily_queries} sorgu (UTC günü)"]


def budget_lines(budget):
    return [f"UTC {budget.utc_day}: kullanılan/ayrılan {budget.used_queries}, kalan {budget.remaining_queries} sorgu.",
            "Bu sınır bu veri alanındaki gruba aittir; Tavily hesap bakiyesi veya bütün hesabın harcama sınırı değildir."]


_REASONS = {
    "not_due": "Tanımlanan aralık henüz dolmadı; internet araması yapılmadı.",
    "daily_budget": "Günlük sorgu bütçesi yeterli değil; yeni sorgu yapılmadı.",
    "unfinished_run": "Kesilmiş çalışma var; yeni tur başlatılmadı.",
    "replayed": "Önceki çalışma döndürüldü; internet araması tekrarlanmadı.",
}


def group_run_lines(result, *, data_dir=None):
    lines = ["İzleme grubu çalışma durumu: " + safe_text(result["status"])]
    if result.get("reason"):
        lines.append(_REASONS.get(result["reason"], safe_text(result["reason"])))
    if result.get("budget") is not None:
        lines.extend(budget_lines(result["budget"]))
    if result.get("next_due_at"):
        lines.append("Sonraki en erken çalışma: " + safe_text(result["next_due_at"]))
    if result.get("unfinished_run_id"):
        lines.append("Devam: " + mentions_command("groups", "resume", result["unfinished_run_id"], data_dir=data_dir))
    run = result.get("run")
    if run is None:
        return lines
    lines.append(f"Çalışma: {run.id} | grup sürümü {run.group_revision} | {run.started_at}")
    for attempt in run.attempts:
        lines.extend(("", f"{attempt.index + 1}. {safe_text(attempt.request.target.name)} | {safe_text(attempt.status)}",
                      "  Sorgu: " + safe_text(build_query(attempt.request.target))))
        if attempt.error_code:
            lines.append("  Açıklama: " + safe_text(attempt.error_code))
        if attempt.result_run_id and attempt.status in {"complete", "failed"}:
            lines.append("  Kaynak sonuçları: " + mentions_command("run-show", attempt.result_run_id, data_dir=data_dir))
        if attempt.notification_run_id:
            from xti.interfaces.global_saved_searches import search_watch_command
            lines.append("  Değişiklik karşılaştırması: " + search_watch_command("run-show", attempt.notification_run_id, data_dir=data_dir))
        if attempt.status == "unknown":
            lines.append("  Kaynağın yanıtı kesinleşmedi; sorgu bütçede tutuldu ve tekrar edilmedi.")
    if run.status == "running":
        lines.append("Devam: " + mentions_command("groups", "resume", run.id, data_dir=data_dir))
    lines.append("Bütün içerikler: " + mentions_command("groups", "run-show", run.id, "--details", data_dir=data_dir))
    lines.append("İlk başarılı sorgu kapsamı sessiz başlangıçtır; sonraki yeni/değişen içerikler mevcut inbox'a düşer.")
    return lines


def make_mention_group_service(database, *, api_key_file=None):
    from xti.adapters.sqlite_mention_groups import SQLiteMentionGroupRepository
    from xti.adapters.sqlite_mentions import SQLiteMentionRepository
    from xti.adapters.sqlite_mention_targets import SQLiteMentionTargetRepository
    from xti.adapters.sqlite_mention_notifications import SQLiteMentionNotificationBridge
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.adapters.scheduled_backups import ScheduledBackupMaintenance
    from xti.adapters.systemd_mentions_schedule import SystemdMentionScheduleWriter
    from xti.adapters.tavily_search import TavilySearchSource, load_tavily_api_key
    from xti.application.mention_groups import MentionGroupService
    return MentionGroupService(SQLiteMentionGroupRepository(database), SQLiteMentionRepository(database),
        SQLiteMentionTargetRepository(database), LocalExecutionLock(database),
        notifications=SQLiteMentionNotificationBridge(database),
        source_factory=lambda: TavilySearchSource(load_tavily_api_key(api_key_file)),
        files=SystemdMentionScheduleWriter(Path(__file__).resolve().parents[3] / "xti", database),
        backups=ScheduledBackupMaintenance(database))


def execute_mention_group_command(service, args, *, progress=None):
    action = args.mention_group_action
    if action == "save":
        definition = MentionGroupDefinition(args.organization, tuple(args.supplier), args.topic,
            args.max_results, args.interval_hours, args.run_queries, args.daily_queries)
        group = service.save(args.name, definition)
        return _wire(group), group_lines(group) + ["Tanım kaydedildi; internet araması yapılmadı."], 0
    if action == "disable":
        group = service.disable(args.group_id, reason=args.reason)
        return _wire(group), group_lines(group), 0
    if action in {"run", "resume", "run-show"}:
        result = (service.run(args.group_id, request_id=args.request_id) if action == "run" else
                  service.resume(args.run_id) if action == "resume" else service.run_show(args.run_id))
        lines = group_run_lines(result, data_dir=args.data_dir)
        if action == "run-show" and args.details:
            from xti.application.mentions import MentionService
            reader = MentionService(service.mentions, service.targets)
            details = []
            for attempt in result["run"].attempts:
                if attempt.result_run_id and attempt.status in {"complete", "failed"}:
                    evidence = reader.run_show(attempt.result_run_id)
                    details.append(evidence)
                    lines.extend(("", *run_lines(evidence, data_dir=args.data_dir)))
            result = {**result, "source_details": tuple(details)}
        status = 0 if action == "run-show" or result["status"] in {"complete", "skipped"} else 3
        if result.get("reason") == "unfinished_run":
            status = 3
        return _wire(result), lines, status
    if action == "monitor":
        from xti.application.mention_group_monitor import MentionGroupMonitor
        report = MentionGroupMonitor(service).run(args.group_id, cycles=args.cycles,
            interval_seconds=args.interval_seconds, duration_seconds=args.duration_seconds, progress=progress)
        data = _wire(report)
        lines = [f"Grup ön plan izlemesi: {report.completed_cycles}/{report.planned_cycles} tur | "
                 f"durma nedeni: {safe_text(report.stop_reason)}"]
        for cycle in report.cycles:
            lines.append(f"  Tur {cycle.cycle}: {safe_text(cycle.status)} | günlük sorgu {cycle.daily_queries_used}")
            if cycle.reason:
                lines.append("    " + _REASONS.get(cycle.reason, safe_text(cycle.reason)))
            if cycle.run_id:
                lines.append("    " + mentions_command("groups", "run-show", cycle.run_id, data_dir=args.data_dir))
        status = 130 if report.stop_reason == "interrupted" else 3 if any(
            cycle.status not in {"complete", "skipped"} or cycle.reason == "unfinished_run"
            for cycle in report.cycles) else 0
        return data, lines, status
    if action == "schedule":
        report = service.generate(args.group_id, output=args.output, at=args.at, timezone=args.timezone,
            weekday=args.weekday, keep=args.keep, api_key_file=args.api_key_file)
        return _wire(report), generated_lines(report), 0
    if action == "prepare":
        report = service.prepare(args.group_id, keep=args.keep, calendar_hours=args.calendar_hours)
        return _wire(report), ["Zamanlama hazırlığı ve yedekten kurtarma doğrulaması tamamlandı.",
            "Yedek: " + safe_text(report["backup"].path)], 0
    if action == "plan":
        plan = service.plan(args.group_id)
        lines = group_lines(plan["group"]) + budget_lines(plan["budget"])
        for request in plan["requests"]:
            lines.extend(("", "Hedef: " + safe_text(request.target.name),
                          "Sorgu: " + safe_text(build_query(request.target))))
        lines.append(f"Bu tur en çok {plan['planned_queries']} temel sorgu gönderecek.")
        if plan["reason"]:
            lines.append(_REASONS[plan["reason"]])
        lines.append("Bu plan internete çıkmaz, kredi kullanmaz ve kayıt yazmaz.")
        return _wire(plan), lines, 0
    if action == "show":
        report = service.show(args.group_id)
        return _wire(report), group_lines(report["group"]) + budget_lines(report["budget"]) + [
            f"Geçmiş çalışma: {report['run_count']}"], 0
    if action == "list":
        page = service.list(active_only=not args.all, offset=args.offset, limit=args.limit)
        lines = [f"İzleme grupları: toplam {page['total_count']} | gösterilen {len(page['groups'])}"]
        for group in page["groups"]:
            lines.extend(("", *group_lines(group)))
    else:
        page = service.runs(args.group_id, offset=args.offset, limit=args.limit)
        lines = [f"Grup çalışmaları: toplam {page['total_count']} | gösterilen {len(page['runs'])}"]
        for run in page["runs"]:
            lines.extend((f"{run.started_at} | {run.status} | sürüm {run.group_revision}",
                "  " + mentions_command("groups", "run-show", run.id, data_dir=args.data_dir)))
    if page["has_more"]:
        tail = (["--all"] if args.all else []) if action == "list" else [args.group_id]
        lines.append("Sonraki sayfa: " + mentions_command("groups", action, *tail,
            "--offset", args.offset + args.limit, "--limit", args.limit, data_dir=args.data_dir))
    return _wire(page), lines, 0

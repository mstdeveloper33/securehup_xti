"""Explicit local search watches and escaped historical evidence views."""

from dataclasses import asdict
import json
import shlex

from xti.domain.global_search import GLOBAL_SEARCH_KINDS
from xti.interfaces.text import safe_text


_ACTIONS = {
    "added": "eklendi", "updated": "değişti", "reactivated": "yeniden etkinleştirildi",
    "disabled": "devre dışı bırakıldı", "unchanged": "değişmedi", "removed": "artık eşleşmiyor",
}


def register_global_saved_search_parser(commands):
    parser = commands.add_parser("search-watch", help="Kayıtlı genel aramaları ve yerel değişiklik bildirimlerini yönet.")
    actions = parser.add_subparsers(dest="search_watch_action", required=True)
    add = actions.add_parser("add", help="Arama tanımı ekle; aynı ad varsa güncelle veya yeniden etkinleştir.")
    add.add_argument("name")
    add.add_argument("query")
    add.add_argument("--kind", choices=GLOBAL_SEARCH_KINDS, action="append", dest="kinds")
    add.add_argument("--all", action="store_true", dest="include_inactive",
                     help="Etkin olmayan kayıtların son bilinen durumlarını da ara; tüm sürüm arşivi değildir.")
    listing = actions.add_parser("list", help="Kayıtlı aramaları ve son çalışma özetini oku.")
    listing.add_argument("--all", action="store_true", dest="include_disabled")
    _window(listing)
    show = actions.add_parser("show", help="Tanımı ve eklemeli çalışma/tanım geçmişini oku.")
    show.add_argument("search_id")
    show.add_argument("--event-offset", type=int, default=0)
    show.add_argument("--event-limit", type=int, default=50)
    show.add_argument("--run-offset", type=int, default=0)
    show.add_argument("--run-limit", type=int, default=20)
    disable = actions.add_parser("disable", help="Aramayı gerekçesiyle durdur; geçmiş ve bildirimler korunur.")
    disable.add_argument("search_id")
    disable.add_argument("--reason", required=True)
    run = actions.add_parser("run", help="Yerel kayıtların tam karşılaştırmasını kaydet; yalnız görünümü sayfala.")
    run.add_argument("search_id")
    _window(run)
    run_show = actions.add_parser("run-show", help="Kaydedilmiş çalışmanın değişmez kanıtını oku.")
    run_show.add_argument("run_id")
    _window(run_show)
    monitor = actions.add_parser("monitor", help="Terminal açıkken aramayı sınırlı sayıda tekrarla; kaynak toplamaz.")
    monitor.add_argument("search_id")
    monitor.add_argument("--cycles", type=int, default=2)
    monitor.add_argument("--interval", type=int, default=60)
    monitor.add_argument("--duration", type=int, default=600)
    monitor.add_argument("--limit", type=int, default=50)


def _window(parser):
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=50)


def _launcher(data_dir=None):
    return ("./xti", "--data-dir", str(data_dir)) if data_dir is not None else ("./xti",)


def search_watch_command(*arguments, data_dir=None):
    return safe_text(shlex.join((*_launcher(data_dir), "search-watch", *(str(value) for value in arguments))))


def _definition_lines(search):
    if search.mention_request_key is not None:
        return [
            f"İçerik izlemesi: {safe_text(search.display_name)} | {safe_text(search.id)} | sürüm {search.revision}",
            "Kapsam: yalnız seçilen firma/tedarikçinin aynı arama tanımındaki Tavily sonuçları",
            "Durum: " + ("etkin" if search.active else "devre dışı"),
        ]
    return [
        f"Arama: {safe_text(search.display_name)} | {safe_text(search.id)} | sürüm {search.revision}",
        f"Sorgu: {safe_text(search.query)} | türler: " + ", ".join(safe_text(kind) for kind in search.kinds),
        "Kapsam: " + ("etkin olmayan kayıtların son bilinen durumu dahil" if search.include_inactive else "varsayılan güncel kayıtlar"),
        "Durum: " + ("etkin" if search.active else "devre dışı"),
    ]


def mutation_lines(result):
    return [f"Kayıtlı genel arama {_ACTIONS.get(result.action, safe_text(result.action))}.",
            *_definition_lines(result.saved_search),
            "Tanımı kaydetmek kaynak toplamaz veya aramayı kendiliğinden çalıştırmaz."]


def list_lines(page, *, include_disabled=False, data_dir=None):
    lines = [f"Kayıtlı genel aramalar: {page.total_count} | gösterilen {len(page.items)} | başlangıç {page.offset}",
             "Görünüm: " + ("etkin ve devre dışı" if include_disabled else "yalnız etkin")]
    for item in page.items:
        lines.extend(_definition_lines(item.saved_search))
        lines.append(f"  Çalışma: {item.run_count} | son çalışma: {safe_text(item.last_run.executed_at) if item.last_run else 'henüz yok'}")
    if not page.items:
        lines.append("Kayıtlı arama yok." if page.total_count == 0 else "Bu sayfa toplam arama sayısının dışında.")
    if page.has_more:
        args = ["list", "--offset", page.offset + len(page.items), "--limit", page.limit]
        if include_disabled:
            args.append("--all")
        lines.append("Sonraki sayfa: " + search_watch_command(*args, data_dir=data_dir))
    return lines


def detail_lines(details, *, data_dir=None):
    lines = _definition_lines(details.saved_search)
    lines.append(f"Tanım geçmişi: {details.total_event_count}; gösterilen {len(details.events)}; başlangıç {details.event_offset}")
    for event in details.events:
        lines.append(f"  {safe_text(event.recorded_at)} | {_ACTIONS.get(event.action, safe_text(event.action))} | sürüm {event.revision}")
        lines.extend("    " + line for line in _definition_lines(event.search))
        lines.append("    Gerekçe: " + safe_text(event.reason))
    lines.append(f"Çalışma geçmişi: {details.total_run_count}; gösterilen {len(details.runs)}; başlangıç {details.run_offset}")
    for run in details.runs:
        lines.extend((f"  {safe_text(run.executed_at)} | toplam {run.total_count} | yeni {run.added_count} | değişen {run.updated_count} | aynı {run.unchanged_count} | artık eşleşmeyen {run.removed_count}",
                      "    Kanıt: " + search_watch_command("run-show", run.id, data_dir=data_dir)))
    if details.total_event_count and not details.events:
        lines.append("Tanım geçmişinin bu sayfası toplam kayıt sayısının dışında.")
    if details.total_run_count and not details.runs:
        lines.append("Çalışma geçmişinin bu sayfası toplam kayıt sayısının dışında.")
    for kind in ("events", "runs"):
        if getattr(details, "has_more_" + kind):
            event_offset = details.event_offset + len(details.events) if kind == "events" else details.event_offset
            run_offset = details.run_offset + len(details.runs) if kind == "runs" else details.run_offset
            lines.append(("Sonraki tanım sayfası: " if kind == "events" else "Sonraki çalışma sayfası: ") + search_watch_command(
                "show", details.saved_search.id, "--event-offset", event_offset, "--event-limit", details.event_limit,
                "--run-offset", run_offset, "--run-limit", details.run_limit, data_dir=data_dir))
    return lines


def _match_lines(match, label, *, data_dir=None):
    if match is None:
        return [f"    {label}: bu karşılaştırma kapsamında yok"]
    result = match.result
    matching = ("kayıtlı hedef ve arama kapsamı" if result.matched_field == 'mention_request_key'
                else f"{safe_text(result.match_type)} | {safe_text(result.matched_field)}={safe_text(result.matched_value)}")
    lines = [
        f"    {label}: {safe_text(result.display_value)}",
        "      Kayıt kimliği: " + safe_text(json.dumps(match.identity, ensure_ascii=False)),
        f"      Tür: {safe_text(result.kind)} / {safe_text(result.record_type)} | kaynak: {safe_text(result.source)}",
        f"      Durum: {safe_text(result.status)} | " + ("güncel yerel kayıt" if result.current else "tarihî / etkin değil"),
        f"      Eşleşme: {matching}",
        f"      Kayıt zamanı: {safe_text(result.recorded_at)} | kaynak çalışması: {safe_text(result.source_run_id or 'yok')}",
        f"      Karşılaştırma özeti: {safe_text(match.state_sha256)}",
    ]
    lines.extend("      " + safe_text(value) for value in result.details)
    # The stored semantic object is verified by the repository. It explains
    # changes that the short search result would otherwise hide.
    semantic = json.loads(match.semantic_json)["semantic"]
    lines.append("      Karşılaştırılan kaynak alanları: " + safe_text(json.dumps(semantic, ensure_ascii=False, sort_keys=True)))
    for nav in result.navigation:
        lines.append("      Güncel " + safe_text(nav.label) + ": " + safe_text(shlex.join((*_launcher(data_dir), *nav.arguments))))
    return lines


def run_lines(report, *, data_dir=None):
    run = report.run
    lines = ["Kayıtlı genel arama çalışması — çalışma anındaki değişmez tanım ve kanıt", *_definition_lines(report.saved_search),
             f"Çalışma: {safe_text(run.id)} | zaman: {safe_text(run.executed_at)}",
             "Önceki karşılaştırma: " + safe_text(run.previous_run_id or "yok; sessiz başlangıç"),
             f"Toplam eşleşme {run.total_count} | yeni {run.added_count} | değişen {run.updated_count} | aynı {run.unchanged_count} | artık eşleşmeyen {run.removed_count}",
             f"Kanıt satırları: {report.total_item_count} | gösterilen {len(report.items)} | başlangıç {report.offset} | sınır {report.limit}",
             "Kaynak kapsamı (çalışma anında):"]
    for scope in report.coverage:
        lines.extend((f"  {safe_text(scope.kind)} / {safe_text(scope.source)}: {scope.examined_count} incelenen; {scope.matched_count} eşleşen",
                      f"    Son deneme: {safe_text(scope.latest_run_status or 'kayıt yok')} | {safe_text(scope.latest_run_at or 'yok')} | {safe_text(scope.latest_run_id or 'yok')}",
                      f"    Son başarılı kaynak: {safe_text(scope.latest_success_at or 'yok')} | {safe_text(scope.latest_success_run_id or 'yok')}"))
        lines.extend("    " + safe_text(note) for note in scope.notes)
    for item in report.items:
        lines.append(f"  {_ACTIONS.get(item.action, safe_text(item.action))} | {safe_text(item.key)}")
        lines.extend(_match_lines(item.before, "Önce", data_dir=data_dir))
        lines.extend(_match_lines(item.after, "Sonra", data_dir=data_dir))
    if not report.items:
        lines.append("Bu çalışmada eşleşme veya fark yok." if report.total_item_count == 0 else "Bu sayfa toplam kanıt satırı sayısının dışında.")
    if report.notification_id:
        lines.append("Yerel bildirim: " + safe_text(report.notification_id))
    if report.has_more:
        lines.append("Sonraki kanıt sayfası: " + search_watch_command("run-show", run.id, "--offset", report.offset + len(report.items), "--limit", report.limit, data_dir=data_dir))
    source_note = ("Kaydedilmiş Tavily çalışmasının kanıtı karşılaştırıldı; içerik değişmesi doğrulanmış ihlal anlamına gelmez."
                   if report.saved_search.mention_request_key is not None else
                   "Kaynak toplama yapılmadı; kayıtların değişmesi yeni veya doğrulanmış ihlal anlamına gelmez.")
    lines.extend((source_note,
                  "Artık eşleşmeyen kayıt silinmiş tehdit veya giderilmiş risk demek değildir; yalnız çıkarılma bildirim oluşturmaz.",
                  "İlk çalışma ve yeni tanım sessiz başlangıçtır. Yalnız sonraki yeni/değişen eşleşmeler yerel bildirim üretir.",
                  "Güncel kayıt komutları bugünkü durumu açar; yukarıdaki önce/sonra kanıtı çalışma anına aittir."))
    return lines


def monitor_lines(report, *, data_dir=None):
    lines = [f"Genel arama izleme: {safe_text(report.search_id)} | tamamlanan tur {report.completed_cycles}/{report.planned_cycles}",
             f"Süre: {report.elapsed_seconds:.1f} saniye | bitiş nedeni: {safe_text(report.stop_reason)} | yerel bildirim {report.notification_count}"]
    for result in report.runs:
        run = result.run
        lines.append(f"  {safe_text(run.executed_at)} | yeni {run.added_count} | değişen {run.updated_count} | artık eşleşmeyen {run.removed_count}")
        lines.append("    Kanıt: " + search_watch_command("run-show", run.id, data_dir=data_dir))
    lines.extend(("Her tamamlanan tur ayrı kaydedildi; turlar arasında kaynak toplama komutları çalışabilir.",
                  "Bu komut kaynak toplamaz veya arka plan servisi kurmaz. Bildirimler: ./xti inbox"))
    return lines


def make_global_saved_search_service(database):
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.application.global_saved_searches import GlobalSavedSearchService
    # Validate an explicitly initialized current schema before a write can
    # create the persistent worker lock. This does not initialize or migrate.
    with SQLiteAssetRepository(database)._connection(readonly=True):
        pass
    return GlobalSavedSearchService(SQLiteGlobalSavedSearchRepository(database), LocalExecutionLock(database))


def execute_global_saved_search_command(service, args, *, progress=None):
    action = args.search_watch_action
    data_dir = args.data_dir
    if action == "add":
        report = service.add(args.name, args.query, kinds=args.kinds, include_inactive=args.include_inactive)
        lines = mutation_lines(report)
    elif action == "disable":
        report = service.disable(args.search_id, reason=args.reason)
        lines = mutation_lines(report)
    elif action == "list":
        report = service.list(active_only=not args.include_disabled, offset=args.offset, limit=args.limit)
        lines = list_lines(report, include_disabled=args.include_disabled, data_dir=data_dir)
    elif action == "show":
        report = service.show(args.search_id, event_offset=args.event_offset, event_limit=args.event_limit,
                              run_offset=args.run_offset, run_limit=args.run_limit)
        lines = detail_lines(report, data_dir=data_dir)
    elif action == "run":
        report = service.run(args.search_id, offset=args.offset, limit=args.limit)
        lines = run_lines(report, data_dir=data_dir)
    elif action == "run-show":
        report = service.show_run(args.run_id, offset=args.offset, limit=args.limit)
        lines = run_lines(report, data_dir=data_dir)
    else:
        from xti.application.global_saved_search_monitor import GlobalSavedSearchMonitor
        report = GlobalSavedSearchMonitor(service).run(
            args.search_id, cycles=args.cycles, interval_seconds=args.interval,
            duration_seconds=args.duration, limit=args.limit, progress=progress,
        )
        lines = monitor_lines(report, data_dir=data_dir)
    return asdict(report), lines

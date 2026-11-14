"""Explicit watch configuration and source-preserving historical views."""

from dataclasses import asdict

from xti.interfaces.public_notices import _notice_lines
from xti.interfaces.text import safe_text


_ACTIONS = {"baseline": "Sessiz başlangıç", "added": "Yeni eşleşen kayıt",
            "updated": "Değişen kayıt", "removed": "Eşleşmeden çıkan kayıt",
            "unchanged": "Değişmeyen kayıt"}


def register_public_notice_watch_parsers(actions) -> None:
    parser = actions.add_parser("watch", help="Kuruluş için kamu olay bildirimlerini açıkça aç/kapat; ağa çıkmaz.")
    watches = parser.add_subparsers(dest="notice_watch_action", required=True)
    for action, label in (("enable", "Kuruluşun etkin domainleri için yerel izlemeyi aç."),
                          ("disable", "İzlemeyi geçmişini silmeden kapat.")):
        command = watches.add_parser(action, help=label)
        command.add_argument("organization_id")
        if action == "enable":
            command.add_argument("--reason", default="Kullanıcı kuruluş kamu olay izlemesini açtı.")
        else:
            command.add_argument("--reason", required=True)
    listing = watches.add_parser("list", help="Kamu olay izlemelerinin durumunu göster.")
    listing.add_argument("--all", action="store_true", dest="all_entries")
    listing.add_argument("--limit", type=int, default=50)
    listing.add_argument("--offset", type=int, default=0)
    show = watches.add_parser("show", help="Kuruluş izlemesinin kapsamını ve geçmişini göster.")
    show.add_argument("organization_id")
    show.add_argument("--event-limit", type=int, default=20)
    show.add_argument("--run-limit", type=int, default=20)
    show.add_argument("--event-offset", type=int, default=0)
    show.add_argument("--run-offset", type=int, default=0)
    run = actions.add_parser("watch-run-show", help="İzlemenin tarihî kapsam ve önce/sonra kayıtlarını göster.")
    run.add_argument("run_id")
    run.add_argument("--limit", type=int, default=20)
    run.add_argument("--offset", type=int, default=0)


def _header(report) -> list[str]:
    return ["Kaynak: " + safe_text(report.attribution), "Lisans: " + safe_text(report.license)]


def _source_lines(report) -> list[str]:
    latest, complete = report.latest_source_run, report.latest_complete_source_run
    lines = ["Son katalog denemesi: " + (
        f"{safe_text(latest.status)} | {safe_text(latest.finished_at)} | {safe_text(latest.id)}"
        if latest else "henüz yok; kapsam bilinmiyor")]
    if latest and latest.error:
        lines.append("Kaynak hatası: " + safe_text(latest.error))
    lines.append("Son başarılı katalog: " + (
        f"{safe_text(complete.finished_at)} | {safe_text(complete.id)}"
        if complete else "henüz yok; sıfır eşleşme sonucu değildir"))
    return lines


def change_lines(change) -> list[str]:
    lines = [f"  {_ACTIONS[change.action]} | {safe_text(change.notice_id)} | {safe_text(change.domain)}"]
    if change.before is not None:
        lines.append("    Önceki kaynak kaydı:")
        lines.extend("    " + line for line in _notice_lines(change.before, detailed=True))
    if change.after is not None:
        lines.append("    Bu çalışmadaki kaynak kaydı:")
        lines.extend("    " + line for line in _notice_lines(change.after, detailed=True))
    if change.before is not None and change.after is not None:
        fields = [name for name in change.before.__dataclass_fields__
                  if getattr(change.before, name) != getattr(change.after, name)]
        if fields:
            lines.append("    Değişen metadata alanları: " + safe_text(", ".join(fields)))
    if change.action == "removed":
        lines.append("    Katalog veya kapsam eşleşmesinden çıktı; çözülmüş ihlal kararı değildir.")
    return lines


def _run_lines(run) -> list[str]:
    return [
        f"  Çalışma: {safe_text(run.id)} | {safe_text(run.recorded_at)}",
        f"    Eşleşen {run.matched_count} | başlangıç {run.baseline_count} | yeni {run.added_count} | "
        f"değişen {run.updated_count} | çıkan {run.removed_count} | aynı {run.unchanged_count}",
        "    Kaynak çalışma: " + safe_text(run.source_run_id),
        "    Ayrıntı: ./xti notices watch-run-show " + safe_text(run.id),
    ]


def watch_page_lines(report) -> list[str]:
    lines = _header(report) + _source_lines(report)
    lines.append(f"Kuruluş izlemesi: toplam {report.total_count} | bu sayfada {len(report.watches)}")
    for item in report.watches:
        lines.extend([
            f"  {safe_text(item.organization_name)} | {safe_text(item.watch.organization_id)}",
            f"    İzleme {'açık' if item.watch.active else 'kapalı'} | kuruluş "
            f"{'etkin' if item.organization_active else 'kapalı'} | etkin domain {item.effective_domain_count}",
            "    Kapsam ve geçmiş: ./xti notices watch show " + safe_text(item.watch.organization_id),
        ])
        if item.latest_run is not None:
            lines.extend(_run_lines(item.latest_run))
        elif item.watch.active and item.organization_active and item.effective_domain_count:
            lines.append("    Henüz değerlendirme yok; sonraki başarılı yenileme sessiz başlangıçtır.")
        else:
            lines.append("    Henüz değerlendirme yok; izleme ve kuruluş açık, domain kapsamı etkin olmalı.")
    if report.offset + len(report.watches) < report.total_count:
        lines.append(f"Sonraki sayfa: --offset {report.offset + len(report.watches)}")
    return lines + [safe_text(note) for note in report.notes]


def watch_detail_lines(report) -> list[str]:
    lines = _header(report) + [
        f"Kuruluş kamu olay izlemesi: {safe_text(report.organization.display_name)} | {safe_text(report.organization.id)}",
        f"İzleme: {'açık' if report.watch.active else 'kapalı'} | {safe_text(report.watch.id)} | sürüm {report.watch.revision}",
        f"Kuruluş: {'etkin' if report.organization.active else 'kapalı'}",
        f"Güncel etkin domain kapsamı: {len(report.effective_domains)}",
    ]
    lines.extend("  " + safe_text(domain) for domain in report.effective_domains)
    if not report.effective_domains:
        lines.append("Etkin domain kapsamı yok; bu durum kaynakta olay bulunmadığı anlamına gelmez.")
    lines.extend(_source_lines(report))
    lines.append(f"İzleme geçmişi: toplam {report.total_run_count}; gösterilen {len(report.runs)}; başlangıç {report.run_offset}")
    for run in report.runs:
        lines.extend(_run_lines(run))
    if not report.total_run_count:
        if report.watch.active and report.organization.active and report.effective_domains:
            lines.append("Henüz değerlendirme yok; sonraki başarılı katalog yenilemesi ilk ölçümü oluşturur.")
        else:
            lines.append("Henüz değerlendirme yok; izleme ve kuruluş açık, domain kapsamı etkin olmalı.")
    elif report.run_offset == 0 and report.runs and report.latest_complete_source_run and report.runs[0].source_run_id != report.latest_complete_source_run.id:
        lines.append("Bu izlemenin son değerlendirmesi en yeni başarılı kataloğa ait değil; tarihî sonuç gösteriliyor.")
    if report.total_run_count > report.run_offset + len(report.runs):
        lines.append(f"Daha eski çalışmalar: ./xti notices watch show {safe_text(report.organization.id)} --run-offset {report.run_offset + len(report.runs)}")
    lines.append(f"Açma/kapatma geçmişi: toplam {report.total_event_count}; gösterilen {len(report.events)}; başlangıç {report.event_offset}")
    for event in report.events:
        lines.append(f"  {safe_text(event.action)} | {safe_text(event.recorded_at)} | {safe_text(event.reason)}")
    if report.total_event_count > report.event_offset + len(report.events):
        lines.append(f"Daha eski tanım olayları: ./xti notices watch show {safe_text(report.organization.id)} --event-offset {report.event_offset + len(report.events)}")
    lines.append("Geçmiş çalışmalar o anki kapsamı gösterir; güncel alan adı bağlantılarıyla yeniden yazılmaz.")
    return lines + [safe_text(note) for note in report.notes]


def watch_run_lines(report) -> list[str]:
    lines = _header(report) + [
        f"Tarihî kuruluş: {safe_text(report.scope.organization_name)} | {safe_text(report.scope.organization_id)}",
        "Tarihî izleme kapsamı:",
    ]
    for member in report.scope.members:
        label = "sessiz başlangıç" if member.domain in report.baseline_domains else "devam eden kapsam"
        lines.append(f"  {safe_text(member.domain)} | {label} | bağlantı {safe_text(member.link_id)}")
    if not report.scope.members:
        lines.append("  Bu çalışmada etkin domain kapsamı yoktu; bu durum kaynakta olay olmadığı anlamına gelmez.")
    lines.extend(_run_lines(report.run))
    if report.previous_source_run_id:
        lines.append("Karşılaştırılan önceki kaynak çalışma: " + safe_text(report.previous_source_run_id))
    if report.notification_id:
        lines.append("Yerel bildirim: ./xti inbox show " + safe_text(report.notification_id))
    else:
        lines.append("Bu çalışma bildirim üretmedi; başlangıç, tekrar veya yalnız çıkarılma olabilir.")
    lines.append(f"Kayıtlar: toplam {report.total_item_count} | bu sayfada {len(report.items)} | başlangıç {report.offset}")
    for change in report.items:
        lines.extend(change_lines(change))
    if report.offset + len(report.items) < report.total_item_count:
        lines.append(f"Devamı: ./xti notices watch-run-show {safe_text(report.run.id)} --offset {report.offset + len(report.items)}")
    return lines + [safe_text(note) for note in report.notes]


def execute_public_notice_watch_command(service, args) -> tuple[dict, list[str]]:
    if args.notice_action == "watch-run-show":
        result = service.run_show(args.run_id, item_limit=args.limit, offset=args.offset)
        lines = watch_run_lines(result)
    elif args.notice_watch_action == "list":
        result = service.list(active_only=not args.all_entries, offset=args.offset, limit=args.limit)
        lines = watch_page_lines(result)
    elif args.notice_watch_action == "show":
        result = service.show(args.organization_id, event_limit=args.event_limit, run_limit=args.run_limit,
                              event_offset=args.event_offset, run_offset=args.run_offset)
        lines = watch_detail_lines(result)
    else:
        result = service.configure(args.organization_id, enabled=args.notice_watch_action == "enable", reason=args.reason)
        lines = [f"Kamu olay izlemesi: {'açık' if result.watch.active else 'kapalı'} | {safe_text(result.action)}",
                 "Kuruluş: " + safe_text(result.watch.organization_id), "İzleme: " + safe_text(result.watch.id),
                 "Bu komut kaynak sorgulamadı. Açılan izlemenin ilk başarılı değerlendirmesi sessiz başlangıçtır.",
                 "Kapsam ve geçmiş: ./xti notices watch show " + safe_text(result.watch.organization_id)]
    return asdict(result), lines

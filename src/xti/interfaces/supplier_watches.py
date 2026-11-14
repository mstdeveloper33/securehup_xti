"""Plain terminal views preserve each supplier source and historical record."""
from dataclasses import asdict
import json
from xti.domain.supplier_watches import SUPPLIER_WATCH_SOURCES
from xti.interfaces.text import safe_text

_ACTIONS = {'baseline': 'Sessiz başlangıç', 'added': 'Yeni eşleşme', 'updated': 'Değişen kayıt',
            'removed': 'Eşleşmeden çıkan kayıt', 'unchanged': 'Değişmeyen kayıt'}


def register_supplier_watch_parser(actions):
    watch = actions.add_parser('watch', help='Tedarikçi için kaynağa özel yerel bildirim izlemesi.')
    commands = watch.add_subparsers(dest='watch_action', required=True)
    for action in ('enable', 'disable'):
        command = commands.add_parser(action, help='İzlemeyi aç.' if action == 'enable' else 'Geçmişi silmeden izlemeyi kapat.')
        command.add_argument('supplier_id')
        command.add_argument('--source', required=True, choices=SUPPLIER_WATCH_SOURCES)
        if action == 'enable':
            command.add_argument('--reason', default='Kullanıcı tedarikçi kaynak izlemesini açtı.')
        else:
            command.add_argument('--reason', required=True)
    listing = commands.add_parser('list', help='Yerel tedarikçi izlemelerini göster.')
    listing.add_argument('--all', action='store_true', dest='all_entries')
    listing.add_argument('--limit', type=int, default=50)
    listing.add_argument('--offset', type=int, default=0)
    show = commands.add_parser('show', help='İzlemenin tanımını, kaynak durumunu ve geçmişini göster.')
    show.add_argument('watch_id')
    for kind in ('event', 'run'):
        show.add_argument('--' + kind + '-limit', type=int, default=20)
        show.add_argument('--' + kind + '-offset', type=int, default=0)
    run = actions.add_parser('watch-run-show', help='Tarihî tedarikçi ve kaynak kanıtlarını göster.')
    run.add_argument('run_id')
    run.add_argument('--limit', type=int, default=20)
    run.add_argument('--offset', type=int, default=0)


def _header(source):
    return ['Kaynak: ' + safe_text(source.name), 'Kaynak adresi: ' + safe_text(source.url),
            'Atıf: ' + safe_text(source.attribution), 'Lisans: ' + safe_text(source.license)]


def _run_lines(run):
    return [f'  Çalışma: {safe_text(run.id)} | {safe_text(run.recorded_at)}',
        f'    Eşleşen {run.matched_count} | başlangıç {run.baseline_count} | yeni {run.added_count} | '
        f'değişen {run.updated_count} | çıkan {run.removed_count} | aynı {run.unchanged_count}',
        '    Kaynak çalışma: ' + safe_text(run.source_run_id),
        '    Ayrıntı: ./xti suppliers watch-run-show ' + safe_text(run.id)]


def watch_page_lines(report):
    lines = [f'Tedarikçi izlemesi: toplam {report.total_count} | bu sayfada {len(report.watches)}']
    for item in report.watches:
        lines.extend([f'  {safe_text(item.supplier.display_name)} | {safe_text(item.supplier.primary_domain)} | {safe_text(item.watch.source_key)}',
            f"    İzleme {'açık' if item.watch.active else 'kapalı'} | tedarikçi {'etkin' if item.supplier.active else 'geri çekilmiş'}",
            '    Ayrıntı: ./xti suppliers watch show ' + safe_text(item.watch.id)])
        if item.latest_run:
            lines.extend(_run_lines(item.latest_run))
        else:
            lines.append('    Henüz değerlendirilmedi; ilk başarılı kaynak yenilemesi sessiz başlangıçtır.')
    if report.offset + len(report.watches) < report.total_count:
        lines.append(f'Sonraki sayfa: --offset {report.offset + len(report.watches)}')
    return lines + [safe_text(note) for note in report.notes]


def watch_detail_lines(report):
    lines = _header(report.source.source) + [
        f'Tedarikçi: {safe_text(report.supplier.display_name)} | {safe_text(report.supplier.id)}',
        'Domain: ' + safe_text(report.supplier.primary_domain),
        f"İzleme: {'açık' if report.watch.active else 'kapalı'} | {safe_text(report.watch.id)} | sürüm {report.watch.revision}",
        f"Tedarikçi durumu: {'etkin' if report.supplier.active else 'geri çekilmiş; yeni karşılaştırma yapılmaz'}"]
    latest, complete = report.source.latest_run, report.source.latest_complete_run
    lines.append('Son kaynak denemesi: ' + (f"{safe_text(latest['status'])} | {safe_text(latest['finished_at'])} | {safe_text(latest['id'])}" if latest else 'henüz yok; kapsam bilinmiyor'))
    if latest and latest['error']:
        lines.append('Kaynak hatası: ' + safe_text(latest['error']))
    lines.append('Son başarılı kaynak: ' + (safe_text(complete['id']) if complete else 'henüz yok; sıfır eşleşme değildir'))
    lines.append(f'Çalışmalar: toplam {report.total_run_count} | bu sayfada {len(report.runs)} | başlangıç {report.run_offset}')
    for run in report.runs:
        lines.extend(_run_lines(run))
    if report.runs and complete and report.run_offset == 0 and report.runs[0].source_run_id != complete['id']:
        lines.append('Son izleme değerlendirmesi en yeni başarılı kaynağa ait değil; tarihî sonuç gösteriliyor.')
    if report.run_offset + len(report.runs) < report.total_run_count:
        lines.append(f'Daha eski çalışmalar: --run-offset {report.run_offset + len(report.runs)}')
    lines.append(f'Açma/kapatma geçmişi: toplam {report.total_event_count} | bu sayfada {len(report.events)}')
    for event in report.events:
        lines.append(f'  {safe_text(event.action)} | {safe_text(event.recorded_at)} | {safe_text(event.reason)}')
    if report.event_offset + len(report.events) < report.total_event_count:
        lines.append(f'Daha eski tanım olayları: --event-offset {report.event_offset + len(report.events)}')
    return lines + [safe_text(note) for note in report.notes]


def change_lines(item):
    lines = [f'  {_ACTIONS[item.action]} | {safe_text(item.record_id)}']
    for label, record, matched in (('Önceki kaynak kaydı', item.before, item.match_before),
                                    ('Bu çalışmadaki kaynak kaydı', item.after, item.match_after)):
        if record is not None:
            lines.append('    ' + label + ' | eşleşme: ' + safe_text(', '.join(matched) or 'eşleşmiyor'))
            for key, value in record.items():
                lines.append('      ' + safe_text(key) + ': ' + safe_text(json.dumps(value, ensure_ascii=False)))
    if item.before is not None and item.after is not None:
        fields = sorted(key for key in set(item.before) | set(item.after) if item.before.get(key) != item.after.get(key))
        if fields:
            lines.append('    Değişen kaynak alanları: ' + safe_text(', '.join(fields)))
    if item.action == 'removed':
        lines.append('    Kaynak/kapsam eşleşmesinden çıktı; çözülmüş olay kararı değildir.')
    return lines


def watch_run_lines(report):
    supplier = report.scope['supplier']
    lines = _header(report.source) + [
        f"Tarihî tedarikçi: {safe_text(supplier['display_name'])} | {safe_text(supplier['id'])}",
        'Tarihî domain: ' + safe_text(supplier['primary_domain']),
        f"Aynı adlı etkin tedarikçi: {report.scope['same_name_supplier_count']}",
        'Kaynak kayıtları doğrulanmış ihlal veya müşteriye etki kararı değildir.']
    if report.scope['same_name_supplier_count'] > 1:
        lines.append('Ad eşleşmesi belirsiz: aynı isim birden fazla tedarikçide var; domain kanıtını ayrıca inceleyin.')
    lines.extend(_run_lines(report.run))
    if report.previous_source_run is not None:
        lines.append('Karşılaştırılan önceki kaynak: ' + safe_text(report.previous_source_run['id']))
    lines.append('Yerel bildirim: ./xti inbox show ' + safe_text(report.notification_id) if report.notification_id else 'Bu çalışma bildirim üretmedi; başlangıç, tekrar veya yalnız çıkarılma olabilir.')
    lines.append(f'Kayıtlar: toplam {report.total_item_count} | bu sayfada {len(report.items)} | başlangıç {report.offset}')
    for item in report.items:
        lines.extend(change_lines(item))
    if report.offset + len(report.items) < report.total_item_count:
        lines.append(f'Devamı: ./xti suppliers watch-run-show {safe_text(report.run.id)} --offset {report.offset + len(report.items)}')
    return lines + [safe_text(note) for note in report.notes]


def execute_supplier_watch(args, service):
    if args.supplier_action == 'watch-run-show':
        result = service.run_show(args.run_id, item_limit=args.limit, offset=args.offset)
        lines = watch_run_lines(result)
    elif args.watch_action == 'list':
        result = service.list(active_only=not args.all_entries, offset=args.offset, limit=args.limit)
        lines = watch_page_lines(result)
    elif args.watch_action == 'show':
        result = service.show(args.watch_id, event_limit=args.event_limit, run_limit=args.run_limit,
            event_offset=args.event_offset, run_offset=args.run_offset)
        lines = watch_detail_lines(result)
    else:
        result = service.configure(args.supplier_id, source=args.source, enabled=args.watch_action == 'enable', reason=args.reason)
        lines = [f"Tedarikçi izlemesi: {'açık' if result.watch.active else 'kapalı'} | {safe_text(result.action)}",
            'Kaynak: ' + safe_text(result.watch.source_key), 'Tedarikçi: ' + safe_text(result.watch.supplier_id),
            'Bu komut kaynak sorgulamadı; açılan izlemenin ilk başarılı değerlendirmesi sessiz başlangıçtır.',
            'Ayrıntı: ./xti suppliers watch show ' + safe_text(result.watch.id)]
    return asdict(result), lines

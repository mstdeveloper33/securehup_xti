"""Safe Turkish terminal rendering of cross-module local search."""
from dataclasses import asdict
import shlex
from xti.domain.global_search import GLOBAL_SEARCH_KINDS
from xti.interfaces.text import safe_text


_LABELS = {'domain': 'Domain / alt alan', 'finding': 'Marka bulgusu', 'social': 'Sosyal kayıt',
           'ransomware': 'Ransomware kaynak iddiası', 'public-notice': 'Kamu olayı',
           'case': 'Vaka', 'supplier': 'Tedarikçi', 'organization': 'Kuruluş',
           'cti': 'CTI varlığı', 'indicator': 'IOC'}
_MATCH = {'exact': 'tam metin', 'prefix': 'başlangıç', 'contains': 'içerme'}


def register_global_search_parser(commands):
    parser = commands.add_parser('search', help='Kayıtlı domain, bulgu, sosyal kayıt, olay, vaka ve CTI/IOC içinde tek yerel arama.')
    parser.add_argument('query')
    parser.add_argument('--kind', choices=GLOBAL_SEARCH_KINDS, action='append', dest='kinds', help='Tekrarlanabilir kayıt türü filtresi.')
    parser.add_argument('--all', action='store_true', dest='include_inactive', help='Geri çekilmiş kayıtları ve eski izleme tanımlarının son bilinen sonuçlarını da göster; tüm sürüm arşivi değildir.')
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--limit', type=int, default=50)


def global_search_lines(report):
    lines = [f'Platform genelinde yerel arama: {safe_text(report.query)}',
             f'Toplam eşleşme: {report.total_match_count} | gösterilen: {len(report.results)} | başlangıç: {report.offset}',
             'Kapsam: ' + ', '.join(_LABELS[kind] for kind in report.kinds),
             'Kaynak kapsamı:']
    for scope in report.coverage:
        line = f'  {_LABELS[scope.kind]} / {safe_text(scope.source)}: {scope.examined_count} kayıt, {scope.matched_count} eşleşme'
        if scope.latest_run_status is not None:
            line += f' | son deneme: {safe_text(scope.latest_run_status)} / {safe_text(scope.latest_run_at)} ({safe_text(scope.latest_run_id)})'
        if scope.latest_success_run_id is not None:
            line += f' | son başarı: {safe_text(scope.latest_success_at)} ({safe_text(scope.latest_success_run_id)})'
        lines.append(line)
        lines.extend('    ' + safe_text(note) for note in scope.notes)
    if not report.results:
        lines.append('Seçilen kayıtlarda eşleşme yok; kaynak kapsamını yukarıdan kontrol et.' if report.total_match_count == 0
                     else 'Bu sayfada kayıt yok; başlangıç değeri toplam eşleşme sayısının dışında.')
    for record in report.results:
        lines.extend(('', f'{_LABELS[record.kind]} | {safe_text(record.display_value)}',
            f'  Kimlik: {safe_text(record.record_id)} | tür: {safe_text(record.record_type)}',
            f'  Durum: {safe_text(record.status)} | {"güncel yerel kayıt" if record.current else "tarihî / etkin değil"}',
            f'  Eşleşme: {_MATCH[record.match_type]} / {safe_text(record.matched_field)} = {safe_text(record.matched_value)}',
            f'  Kaynak: {safe_text(record.source)} | kayıt zamanı: {safe_text(record.recorded_at)}'))
        if record.source_run_id:
            lines.append('  Kaynak çalışma: ' + safe_text(record.source_run_id))
        lines.extend('  ' + safe_text(value) for value in record.details)
        for nav in record.navigation:
            lines.append('  ' + safe_text(nav.label) + ': ' + safe_text(shlex.join(('./xti', *nav.arguments))))
    if report.has_more:
        args = ['./xti', 'search', report.query, '--offset', str(report.offset + len(report.results)), '--limit', str(report.limit)]
        for kind in report.kinds: args.extend(('--kind', kind))
        if report.include_inactive: args.append('--all')
        lines.append('Sonraki sayfa: ' + safe_text(shlex.join(args)))
    lines.extend(safe_text(note) for note in report.notes)
    return lines


def execute_global_search_command(service, args):
    result = service.search(args.query, kinds=args.kinds, include_inactive=args.include_inactive,
                            offset=args.offset, limit=args.limit)
    return asdict(result), global_search_lines(result)

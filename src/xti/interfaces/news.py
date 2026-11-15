"""Explicit publisher-feed collection and escaped local news views."""

from dataclasses import asdict
import shlex

from xti.domain.news import NEWS_SOURCES, news_source
from xti.interfaces.text import safe_text


def register_news_parser(commands):
    parser = commands.add_parser('news', help='RSS/Atom haberlerini internetten al, kaynaklı yerel kayıtlarını araştır.')
    actions = parser.add_subparsers(dest='news_action', required=True)
    actions.add_parser('sources', help='Desteklenen yayıncıları ve atıfları veri alanı açmadan göster.')
    refresh = actions.add_parser('refresh', help='Seçilen yayıncının akışını bir kez al; haber sayfalarını açma.')
    refresh.add_argument('--source', choices=tuple(source.key for source in NEWS_SOURCES), required=True)
    refresh.add_argument('--limit', type=int, default=20, help='Yalnız gösterilen kanıt sayısı; toplama kapsamını kesmez.')
    listing = actions.add_parser('list', help='Saklanan haberlerin başlık, özet veya bağlantısında yerel arama.')
    listing.add_argument('query', nargs='?')
    listing.add_argument('--source', choices=tuple(source.key for source in NEWS_SOURCES))
    _window(listing)
    show = actions.add_parser('show', help='Bir haberin son bilinen halini ve kaynak bağlarını göster.')
    show.add_argument('article_id')
    status = actions.add_parser('status', help='Kaynak son deneme/son başarı ve geçmişini ağsız göster.')
    status.add_argument('--source', choices=tuple(source.key for source in NEWS_SOURCES))
    _window(status)
    run = actions.add_parser('run-show', help='Belirli bir toplamanın değişmez önce/sonra kanıtını oku.')
    run.add_argument('run_id')
    _window(run)


def _window(parser):
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--limit', type=int, default=20)


def news_command(*arguments, data_dir=None):
    prefix = ('./xti', '--data-dir', str(data_dir)) if data_dir is not None else ('./xti',)
    return safe_text(shlex.join((*prefix, 'news', *(str(value) for value in arguments))))


def source_lines(sources):
    lines = ['Desteklenen RSS/Atom haber kaynakları:']
    for source in sources:
        lines.extend((f'  {safe_text(source.key)} | {safe_text(source.name)}',
                      '    Akış: ' + safe_text(source.url), '    Atıf: ' + safe_text(source.attribution)))
    lines.append('Bu liste internet erişimini denemez; kaynakların canlı durumunu yenileme belirler.')
    return lines


def _source_status(status, *, data_dir=None):
    source, latest, success = status.source, status.latest_run, status.latest_complete_run
    lines = [f'Kaynak: {safe_text(source.name)} ({safe_text(source.key)})',
             '  Atıf: ' + safe_text(source.attribution), '  Akış: ' + safe_text(source.url)]
    if latest is None:
        lines.append('  Henüz toplanmadı; haber kapsamı bilinmiyor.')
    else:
        lines.append(f'  Son deneme: {safe_text(latest.status)} | {safe_text(latest.finished_at)} | {safe_text(latest.id)}')
        if latest.error:
            lines.append('  Kaynak hatası: ' + safe_text(latest.error))
    if success is None:
        lines.append('  Başarılı toplama yok; sıfır haber sonucu değildir.')
    else:
        lines.append(f'  Son başarı: {safe_text(success.finished_at)} | {safe_text(success.id)} | akışta {success.article_count} haber')
        lines.append(f'  Saklanan son bilinen haber: {status.article_count}')
        if latest and latest.id != success.id:
            lines.append('  Son deneme başarısız; önceki başarılı kanıt korunuyor.')
    lines.append('  Yenile: ' + news_command('refresh', '--source', source.key, data_dir=data_dir))
    return lines


def _article_lines(article, *, label=None, data_dir=None):
    lines = [f'{label + ": " if label else ""}{safe_text(article.title)}',
             f'  Kimlik: {safe_text(article.id)} | kaynak: {safe_text(article.source_key)}',
             '  Özgün haber: ' + safe_text(article.url),
             '  Özet: ' + safe_text(article.summary or 'Kaynak özet sunmuyor.'),
             '  Kaynak yayın zamanı: ' + safe_text(article.published_at or 'Ayrıştırılmış tarih yok'),
             '  Kaynak güncelleme zamanı: ' + safe_text(article.updated_at or 'Ayrıştırılmış tarih yok')]
    if article.published_raw:
        lines.append('  Kaynak yayın tarih metni: ' + safe_text(article.published_raw))
    if article.updated_raw:
        lines.append('  Kaynak güncelleme tarih metni: ' + safe_text(article.updated_raw))
    if article.summary_truncated:
        lines.append('  Özet gösterim/saklama sınırına kısaltıldı; tam makale indirilmedi.')
    lines.append('  Güncel ayrıntı: ' + news_command('show', article.id, data_dir=data_dir))
    return lines


def _record_lines(record, *, data_dir=None):
    return [*_article_lines(record.article, data_dir=data_dir),
            f'  İlk toplama: {safe_text(record.first_seen_at)} | son görülme: {safe_text(record.last_seen_at)}',
            '  Son içerik değişimi: ' + safe_text(record.last_changed_at),
            '  İçerik özeti: ' + safe_text(record.state_sha256),
            '  İlk toplama kanıtı: ' + news_command('run-show', record.first_run_id, data_dir=data_dir),
            '  Son değişim kanıtı: ' + news_command('run-show', record.last_change_run_id, data_dir=data_dir),
            '  Son görülme kanıtı: ' + news_command('run-show', record.last_seen_run_id, data_dir=data_dir)]


def search_lines(report, *, limit, data_dir=None):
    lines = [f'Yerel haberler: {safe_text(report.query or "bütün kayıtlar")} | kaynak {safe_text(report.source_key or "tümü")}',
             f'Toplam {report.total_count} | gösterilen {len(report.articles)} | başlangıç {report.offset}']
    for status in report.sources:
        lines.extend(_source_status(status, data_dir=data_dir))
    for record in report.articles:
        lines.extend(('', *_record_lines(record, data_dir=data_dir)))
    if not report.articles:
        lines.append('Seçilen kapsamda eşleşme yok; kaynak durumlarını kontrol et.' if report.total_count == 0
                     else 'Bu sayfa toplam haber sayısının dışında.')
    if report.has_more:
        arguments = ['list']
        if report.query is not None:
            arguments.append(report.query)
        if report.source_key is not None:
            arguments.extend(('--source', report.source_key))
        arguments.extend(('--offset', report.offset + len(report.articles), '--limit', limit))
        lines.append('Sonraki haber sayfası: ' + news_command(*arguments, data_dir=data_dir))
    return lines + [safe_text(note) for note in report.notes]


def status_lines(report, *, source_key=None, limit, data_dir=None):
    lines = ['Haber kaynaklarının saklanan durumu:']
    for status in report.sources:
        lines.extend(_source_status(status, data_dir=data_dir))
    lines.append(f'Çalışma geçmişi: toplam {report.total_run_count} | gösterilen {len(report.recent_runs)} | başlangıç {report.offset}')
    for run in report.recent_runs:
        lines.extend((f'  {safe_text(run.source_key)} | {safe_text(run.status)} | {safe_text(run.finished_at)}',
                      '    Kanıt: ' + news_command('run-show', run.id, data_dir=data_dir)))
    if report.offset + len(report.recent_runs) < report.total_run_count:
        arguments = ['status', '--offset', report.offset + len(report.recent_runs), '--limit', limit]
        if source_key is not None:
            arguments.extend(('--source', source_key))
        lines.append('Sonraki çalışma sayfası: ' + news_command(*arguments, data_dir=data_dir))
    return lines + [safe_text(note) for note in report.notes]


def detail_lines(report, *, data_dir=None):
    return [*_source_status(report.source, data_dir=data_dir),
            *_record_lines(report.record, data_dir=data_dir), *(safe_text(note) for note in report.notes)]


def refresh_lines(report, *, limit, data_dir=None):
    run = report.run
    source = news_source(run.source_key)
    lines = [f'Haber toplama: {safe_text(run.status)} | {safe_text(run.id)}',
             f'Kaynak: {safe_text(source.name)} | {safe_text(source.attribution)}',
             f'Başlangıç: {safe_text(run.started_at)} | bitiş: {safe_text(run.finished_at)}',
             f'Akışta {run.article_count} haber | yeni {run.added_count} | değişen {run.updated_count} | aynı {run.unchanged_count}']
    if run.error:
        lines.extend(('Kaynak hatası: ' + safe_text(run.error),
                      'Varsa önceki başarılı kanıt korunur; bu durum boş başarılı sonuç değildir.'))
    lines.append(f'Kanıt satırları: toplam {report.total_change_count} | gösterilen {len(report.changes)} | başlangıç {report.offset}')
    for change in report.changes:
        lines.append('  İşlem: ' + safe_text(change.action))
        if change.before is not None:
            lines.extend(_article_lines(change.before, label='Önce', data_dir=data_dir))
        else:
            lines.append('Önce: yerel haber kaydı yoktu.')
        lines.extend(_article_lines(change.after, label='Sonra', data_dir=data_dir))
    lines.append('Çalışma kanıtı: ' + news_command('run-show', run.id, data_dir=data_dir))
    if report.offset + len(report.changes) < report.total_change_count:
        lines.append('Sonraki kanıt sayfası: ' + news_command(
            'run-show', run.id, '--offset', report.offset + len(report.changes), '--limit', limit, data_dir=data_dir))
    lines.append('Kayıtlı aramalar ayrıca search-watch run ile karşılaştırılır; bu toplama otomatik bildirim üretmez.')
    return lines + [safe_text(note) for note in report.notes]


def make_news_service(database, *, refresh=False):
    from xti.adapters.sqlite import SQLiteAssetRepository
    from xti.adapters.sqlite_news import SQLiteNewsRepository
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.application.news import NewsService
    source = None
    if refresh:
        with SQLiteAssetRepository(database)._connection(readonly=True):
            pass
        from xti.adapters.rss_atom_news import RssAtomNewsSource
        source = RssAtomNewsSource()
    return NewsService(SQLiteNewsRepository(database), source=source,
                       lock=LocalExecutionLock(database) if refresh else None)


def execute_news_command(service, args):
    action, data_dir = args.news_action, args.data_dir
    if action == 'sources':
        return {'sources': [asdict(source) for source in NEWS_SOURCES]}, source_lines(NEWS_SOURCES), 0
    if action == 'refresh':
        report = service.refresh(args.source, limit=args.limit)
        return asdict(report), refresh_lines(report, limit=args.limit, data_dir=data_dir), 0 if report.run.status == 'complete' else 3
    if action == 'list':
        report = service.list(query=args.query, source_key=args.source, offset=args.offset, limit=args.limit)
        lines = search_lines(report, limit=args.limit, data_dir=data_dir)
    elif action == 'show':
        report = service.show(args.article_id)
        lines = detail_lines(report, data_dir=data_dir)
    elif action == 'status':
        report = service.status(source_key=args.source, offset=args.offset, limit=args.limit)
        lines = status_lines(report, source_key=args.source, limit=args.limit, data_dir=data_dir)
    else:
        report = service.run_show(args.run_id, offset=args.offset, limit=args.limit)
        lines = refresh_lines(report, limit=args.limit, data_dir=data_dir)
    return asdict(report), lines, 0

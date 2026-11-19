"""Shared report service composition and safe terminal rendering."""

from contextlib import nullcontext
from xti.domain.report_contract import WRITE_OPERATIONS
from xti.interfaces.text import safe_text


def make_report_service(database, *, allow_fetch=False):
    from xti.adapters.sqlite_reports import SQLiteReportRepository
    from xti.application.reports import ReportService
    publisher = None
    if allow_fetch:
        from xti.adapters.publisher_documents import PublisherDocumentSource
        publisher = PublisherDocumentSource()
    return ReportService(SQLiteReportRepository(database), publisher=publisher)


def _page(parser):
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--expected-snapshot')


def register_report_parser(commands):
    parser = commands.add_parser('reports', help='Saklı haber/firma metnini sürümlü rapor ve insan bağlantılarıyla incele.')
    actions = parser.add_subparsers(dest='report_action', required=True)
    actions.add_parser('publishers', help='İzinli yayıncı, lisans ve HTML/PDF sınırlarını göster.')
    fetch = actions.add_parser('fetch', help='İzinli yayıncıdan HTML/PDF ana metnini ve özgün kanıtını al.')
    fetch.add_argument('url')
    fetch.add_argument('--provider', choices=('cert-fr', 'ncsc'), required=True)
    fetch.add_argument('--idempotency-key', required=True)
    _page(actions.add_parser('fetches', help='Başarılı ve başarısız yayıncı denemelerini ayrı göster.'))
    fetch_show = actions.add_parser('fetch-show', help='Yayıncı denemesinin saklı makbuzunu göster.')
    fetch_show.add_argument('identifier')
    capture = actions.add_parser('capture', help='Toplanmış kaynak kaydını rapora al; değişmişse yeni belge sürümü koru.')
    capture.add_argument('--source', choices=('news', 'mentions'), required=True)
    capture.add_argument('identifier')
    capture.add_argument('--idempotency-key', required=True)
    capture.add_argument('--expected-content-sha256')
    show = actions.add_parser('show', help='Seçilen belge sürümünü, metni ve bağlantı geçmişini göster.')
    show.add_argument('identifier')
    show.add_argument('--document-revision', type=int)
    listing = actions.add_parser('list', help='Raporların son belge sürümlerini listele.')
    listing.add_argument('--source', choices=('news', 'mentions', 'publisher'))
    _page(listing)
    link = actions.add_parser('link', help='Belirli rapor sürümüne gerekçeli CTI bağlantısı ekle/geri çek.')
    link.add_argument('identifier')
    link.add_argument('--target-kind', choices=('entity', 'indicator'), required=True)
    link.add_argument('--target-id', required=True)
    link.add_argument('--state', choices=('linked', 'withdrawn'), required=True)
    link.add_argument('--reason', required=True)
    link.add_argument('--expected-revision', type=int, required=True)
    link.add_argument('--document-revision', type=int, help='İsteğe bağlı belge sürümü; varsayılan son belge.')
    link.add_argument('--idempotency-key', required=True)
    obs = commands.add_parser('observations', help='Metinde geçme, liste üyeliği ve sağlayıcı gözlemini ayrı göster.')
    obs.add_argument('indicator_type', choices=('domain', 'ipv4', 'ipv6', 'url', 'md5', 'sha1', 'sha256'))
    obs.add_argument('value')
    _page(obs)


def report_lines(data):
    lines = []
    for key, value in data.get('publishers', {}).items():
        lines.append(f"{key} | {value['label']} | {value['license']} | {value['terms_url']}")
    if 'limits' in data:
        lines.append('HTML/PDF: 8 MiB yanıt, 64 KiB ana metin, 80 PDF sayfası. PDF: ' + data['pdf_dependency'] + '; OCR yok.')
    if 'run' in data:
        run = data['run']
        lines.append(f"Yayıncı çalışması: {run['id']} | {run['status']} | {run['recorded_at']}")
        if run['error']:
            lines.append(safe_text(run['error']))
    if 'record' in data:
        record = data['record']
        doc = record['document']
        lines.extend([f"Rapor: {record['id']} | kayıt sürümü {record['revision']} | belge {record['document_revision']}",
            safe_text(doc['title']), 'Kaynak: ' + safe_text(doc['source_reference']),
            'Yayın: ' + safe_text(doc['publication']['at'] or doc['publication']['date'] or 'bilinmiyor'),
            'Kaynakta alınma: ' + doc['collected_at'], 'Rapora kayıt: ' + record['recorded_at'],
            ('Yayıncı ana metni: ' + safe_text(doc['text']) if doc['model_version'] == 2 else 'Saklı özet: ' + safe_text(doc['summary']))])
        if doc['model_version'] == 2:
            lines.append('Atıf/lisans: ' + doc['acquisition']['attribution'] + ' | ' + doc['acquisition']['license_url'])
            lines.append('Özgün belge SHA-256: ' + doc['source_sha256'])
        elif doc['summary_truncated']:
            lines.append('Kaynak özeti kısaltılmış; tam makale değildir.')
        for row in doc['candidates']:
            lines.append(f"Metinde geçiyor: {row['indicator_type']} | {safe_text(row['value'])} | [{row['start']}:{row['end']}]")
        for row in record['links']:
            lines.append(f"İnsan bağlantısı: {safe_text(row['target']['label'])} | {row['state']} | {safe_text(row['reason'])}")
        for row in record['history']:
            lines.append(f"Geçmiş: {row['recorded_at']} | {row['action']} | belge {row['document_revision']} | kayıt {row['revision']}")
        if data.get('action') == 'unchanged':
            lines.append('İçerik/karar değişmedi; yeni belge veya gözlem oluşturulmadı.')
        if data.get('replayed'):
            lines.append('Tekrar anahtarının ilk sonucu gösteriliyor.')
    for row in data.get('records', []):
        if 'request' in row:
            lines.append(f"{row['id']} | {row['status']} | {row['recorded_at']} | {safe_text(row['request']['url'])}")
            if row['error']:
                lines.append('  ' + safe_text(row['error']))
            continue
        if 'kind' not in row:
            lines.append(f"{row['id']} | belge {row['document_revision']} | {safe_text(row['title'])}")
            continue
        label = {'text_mention': 'Metinde geçme', 'feed_membership': 'Liste üyeliği',
                 'provider_observation': 'Sağlayıcı gözlemi', 'source_assertion': 'Kaynak iddiası'}[row['kind']]
        lines.append(f"{label} | {safe_text(row['source'])} | {safe_text(row['value'])} | {safe_text(row['source_reference'])}")
        lines.append('  Olay zamanı: ' + (row['observed_at'] or 'bilinmiyor') + ' | kayıt: ' + row['recorded_at'])
        if row.get('report_id'):
            lines.append(f"  Rapor: {row['report_id']} | belge {row['document_revision']} | güncel belge: {row['current_document']}")
    if 'total_count' in data:
        lines.append(f"Gösterilen: {len(data['records'])} / {data['total_count']}")
    if data.get('has_more'):
        lines.append(f"Devam: --offset {data['next_offset']} --expected-snapshot {data['snapshot_id']}")
    lines.extend(data.get('notes', []))
    return lines


def execute_report(database, args):
    from xti.adapters.worker_lock import LocalExecutionLock
    operation = 'observations.list' if args.command == 'observations' else 'reports.' + args.report_action
    fields = {'reports.list': ('source', 'offset', 'limit', 'expected_snapshot'),
        'reports.publishers': (), 'reports.fetch': ('provider', 'url', 'idempotency_key'),
        'reports.fetches': ('offset', 'limit', 'expected_snapshot'), 'reports.fetch-show': ('identifier',),
        'reports.show': ('identifier', 'document_revision'),
        'reports.capture': ('source', 'identifier', 'idempotency_key', 'expected_content_sha256'),
        'reports.link': ('identifier', 'target_kind', 'target_id', 'state', 'reason', 'expected_revision', 'idempotency_key', 'document_revision'),
        'observations.list': ('indicator_type', 'value', 'offset', 'limit', 'expected_snapshot')}
    options = {key: getattr(args, key) for key in fields[operation] if getattr(args, key) is not None}
    with LocalExecutionLock(database).acquire() if operation in WRITE_OPERATIONS else nullcontext():
        data = make_report_service(database, allow_fetch=operation == 'reports.fetch').execute(operation, **options)
    return data, report_lines(data)


def execute_platform_report(context, request):
    from xti.adapters.worker_lock import LocalExecutionLock
    from xti.domain.engine import EngineContractError
    options = dict(request.parameters)
    if options.pop('expected_workspace_id') != context.workspace_id:
        raise EngineContractError('scope_mismatch', 'İstek güncel firma veri alanına ait değil.')
    with LocalExecutionLock(context.database).acquire():
        return make_report_service(context.database, allow_fetch=request.operation == 'reports.fetch').execute(request.operation, **options)

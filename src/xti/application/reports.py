"""Shared terminal and company operations over source-preserving records."""

from datetime import datetime, timezone

from xti.domain.report_contract import parameters, WRITE_OPERATIONS
from xti.domain.reports import report_view, ReportError
from xti.domain.observations import observations
from xti.domain.research import identity
from xti.ports.reports import ReportRepository
from xti.ports.publisher_documents import PublisherDocumentSource
from xti.ports.discovery import SourceError


def page(rows, options, scope):
    snapshot = identity('report-observations-v1', scope, rows)
    if options.get('expected_snapshot') is not None and options['expected_snapshot'] != snapshot:
        raise ReportError('snapshot_changed', 'Kayıtlar değişmiş; ilk sayfayı yeniden alın.')
    start, limit = options['offset'], options['limit']
    return {'model_version': 1, 'records': rows[start:start + limit], 'total_count': len(rows),
            'offset': start, 'limit': limit, 'has_more': start + limit < len(rows),
            'next_offset': start + limit if start + limit < len(rows) else None, 'snapshot_id': snapshot}


class ReportService:
    def __init__(self, repository: ReportRepository, *, clock=None, publisher: PublisherDocumentSource | None = None):
        self.repository = repository
        self.publisher = publisher
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, operation, **options):
        options = parameters(operation, options, scoped=False)
        if operation == 'reports.publishers':
            from xti.domain.publisher_documents import PUBLISHERS, POLICY_VERSION, MAX_BODY_BYTES, MAX_TEXT_BYTES, MAX_PAGES, PDF_VERSION
            return {'model_version': 1, 'policy': POLICY_VERSION, 'publishers': PUBLISHERS,
                'limits': {'body_bytes': MAX_BODY_BYTES, 'text_bytes': MAX_TEXT_BYTES, 'pdf_pages': MAX_PAGES},
                'pdf_dependency': 'pypdf==' + PDF_VERSION, 'ocr': False}
        if operation == 'reports.fetch':
            receipt = self.repository.fetch_replay(options)
            if receipt is None:
                if self.publisher is None:
                    raise SourceError('Yayıncı kaynağı bu girişte yapılandırılmadı.')
                try:
                    fetched = self.publisher.fetch(options['provider'], options['url'])
                except SourceError as error:
                    receipt = self.repository.record_fetch(options, None, str(error), self.clock().isoformat())
                else:
                    receipt = self.repository.record_fetch(options, fetched, None, self.clock().isoformat())
            if receipt['run']['status'] != 'complete':
                raise SourceError(receipt['run']['error'] + ' Çalışma: ' + receipt['run']['id'] + '; yeniden denemek için yeni tekrar anahtarı kullanın.')
            return receipt
        if operation in ('reports.fetches', 'reports.fetch-show'):
            rows = self.repository.fetches()
            if operation == 'reports.fetch-show':
                row = next((r for r in rows if r['id'] == options['identifier']), None)
                if row is None:
                    raise ReportError('not_found', 'Yayıncı çalışma kaydı bulunamadı.')
                return {'run': row}
            return page(list(reversed(rows)), options, 'publisher-fetches')
        if operation in WRITE_OPERATIONS:
            return self.repository.mutate(operation, options, self.clock().isoformat())
        if operation == 'observations.list':
            records, source = self.repository.evidence(options['indicator_type'], options['value'])
            rows = observations(records, source, options['indicator_type'], options['value'])
            return {**page(rows, options, [options['indicator_type'], options['value']]),
                'notes': ['Metinde geçme, liste üyeliği ve sağlayıcı gözlemi ayrı kanıtlardır.',
                          'Bu kayıtlar müşteri ağında saldırı görüldüğünü veya zararlılığı kanıtlamaz.',
                          'Görünüm yalnız bu çalışma alanında saklı ve rapora alınmış kanıtı kapsar.']}
        records = self.repository.read()
        if operation == 'reports.show':
            return {'record': report_view(records.get(options['identifier']), options.get('document_revision'))}
        rows = []
        for record in records.values():
            doc = record['documents'][-1]['document']
            if options.get('source') is not None and doc['source'] != options['source']:
                continue
            rows.append({'id': record['id'], 'revision': record['revision'], 'document_revision': len(record['documents']),
                'title': doc['title'], 'source': doc['source'], 'provider': doc['provider'],
                'source_reference': doc['source_reference'], 'publication': doc['publication'],
                'recorded_at': record['documents'][-1]['recorded_at'], 'state_sha256': identity(record)})
        rows.sort(key=lambda row: (row['recorded_at'], row['id']), reverse=True)
        return page(rows, options, options.get('source'))

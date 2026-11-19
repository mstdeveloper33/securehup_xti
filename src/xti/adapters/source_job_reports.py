"""Bounded report capture from already stored sources while the worker holds its lock."""

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_reports import SQLiteReportRepository, resolve_document
from xti.adapters.research_read_budget import ResearchReadBudget
from xti.application.reports import ReportService
from xti.domain.research import identity


class VersionedReportStep:
    def __init__(self, database):
        self.storage = SQLiteAssetRepository(database)
        self.service = ReportService(SQLiteReportRepository(database))

    def execute(self, plan, job_id):
        source, limit = plan['capture_source'], plan['capture_limit']
        with self.storage._connection(readonly=True) as connection:
            connection.execute('BEGIN')
            prefix = 'news_' if source == 'news' else 'mentions_'
            tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'") if row[0].startswith(prefix)]
            if not ResearchReadBudget(connection, set()).admit(tables, 'capture_budget'):
                raise StorageError('Otomatik rapor kaynak geçmişi okuma sınırını aşıyor.')
            if source == 'news':
                from xti.adapters.sqlite_news import read_news_catalog
                providers = {key[5:] for key in plan['sources'] if key.startswith('news:')}
                items = [(row.last_changed_at, row.article.id) for row in read_news_catalog(connection).articles
                         if not providers or row.article.source_key in providers]
            else:
                from xti.adapters.sqlite_mentions import read_mentions_catalog
                items = [(row.last_changed_at, row.id) for row in read_mentions_catalog(connection).records]
            items.sort(reverse=True)
            documents = [resolve_document(connection, source, identifier) for _, identifier in items[:limit]]
        rows = []
        for document in documents:
            result = self.service.execute('reports.capture', source=source, identifier=document['source_record_id'],
                expected_content_sha256=document['content_sha256'],
                idempotency_key='capture-job:' + identity(job_id, source, document['source_record_id'], document['content_sha256']))
            record = result['record']
            rows.append(dict(id=record['id'], document_revision=record['document_revision'],
                             content_sha256=record['document']['content_sha256']))
        return dict(kind='report_documents', source=source, records=rows, has_more=len(items) > limit)

    def verify(self, receipt, plan):
        providers = {key[5:] for key in plan['sources'] if key.startswith('news:')}
        for row in receipt['records']:
            record = self.service.execute('reports.show', identifier=row['id'], document_revision=row['document_revision'])['record']
            if record['document']['source'] != receipt['source'] or record['document']['content_sha256'] != row['content_sha256']:
                raise StorageError('Rapor işi özgün belge sürümüyle uyuşmuyor.')
            if receipt['source'] == 'news' and providers and record['document']['provider'] not in providers:
                raise StorageError('Rapor işi seçilen haber sağlayıcısına ait değil.')

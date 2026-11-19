"""Publisher fetches with durable receipts across queue/core commit boundaries."""

from xti.adapters.sqlite import StorageError
from xti.application.reports import ReportService
from xti.ports.discovery import SourceError
from xti.domain.publisher_jobs import document_for
from xti.domain.research import identity


class PublisherDocumentStep:
    def __init__(self, reports, jobs, source=None):
        self.reports, self.jobs, self.source = reports, jobs, source

    @staticmethod
    def request(selected, job_id, key):
        return {**selected, 'idempotency_key': 'publisher-job:' + identity(job_id, key)}

    @staticmethod
    def reference(receipt):
        run, record = receipt['run'], receipt.get('record')
        return {'kind': 'publisher_document', 'provider': run['request']['provider'],
            'url': run['request']['url'], 'run_id': run['id'], 'source_status': run['status'],
            'document': None if record is None else {'id': record['id'],
                'document_revision': record['document_revision'],
                'content_sha256': record['document']['content_sha256']}}

    def execute(self, key, plan, job_id):
        selected = document_for(key, plan)
        job = self.jobs.get(job_id)
        # Queue replay validates ancestry, immutable plan and completed-step reuse.
        # An interrupted parent may have committed the core receipt before progress.
        while job.payload.retry_of is not None:
            job = self.jobs.get(job.payload.retry_of)
            prior = self.reports.fetch_replay(self.request(selected, job.id, key))
            if prior is not None:
                if prior['run']['status'] == 'complete':
                    return self.reference(prior)
                break  # A failed attempt gets a fresh key in this retry job.
        request = self.request(selected, job_id, key)
        service = ReportService(self.reports, publisher=self.source)
        try:
            receipt = service.execute('reports.fetch', **request)
        except SourceError:
            receipt = self.reports.fetch_replay(request)
            if receipt is None:
                raise  # No durable outcome: retain uncertainty, never manufacture failure.
        return self.reference(receipt)

    def verify(self, receipt, plan):
        row = next((row for row in self.reports.fetches() if row['id'] == receipt['run_id']), None)
        if row is None:
            raise StorageError('Yayıncı işi makbuzu bulunamadı.')
        actual = self.reports.fetch_replay(row['request'])
        if actual is None or self.reference(actual) != receipt:
            raise StorageError('Yayıncı işi makbuzu veya belge sürümü özgün kanıtla uyuşmuyor.')

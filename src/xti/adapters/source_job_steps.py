"""Compose established source services; retain their original immutable run IDs."""

from xti.adapters.sqlite import StorageError
from xti.domain.research_history import SCOPE_FIELDS
from xti.domain.source_jobs import validate_receipt
from xti.domain.source_job_usage import RequestUsageMeter, request_ceiling


class ExistingSourceJobOperations:
    def __init__(self, enrichment, warninglists, research):
        self.enrichment, self.warninglists, self.research = enrichment, warninglists, research

    @staticmethod
    def _enrichment_receipt(data):
        run = data['run']
        return {'kind': 'enrichment_run', 'run_id': run['id'], 'provider': run['provider'],
            'indicator_type': run['indicator_type'], 'value': run['value'], 'source_status': run['status'],
            'snapshot_sha256': run['snapshot_sha256'], 'has_more': data['has_more']}

    def execute(self, key, plan, job_id, *, measure=False):
        meter = RequestUsageMeter(request_ceiling(key, plan)) if measure else None
        receipt = self._execute(key, plan, job_id, meter)
        if meter is not None:
            receipt = {**receipt, 'usage': meter.snapshot()}
        return receipt

    def _execute(self, key, plan, job_id, meter):
        options = {'refresh': True, **({'request_usage': meter} if meter is not None else {})}
        if key in {'circl', 'urlscan'}:
            service = self.enrichment(**options)
            data = service.refresh(provider=key, indicator_type=plan['indicator_type'], value=plan['value'])
            return self._enrichment_receipt(service.show(data['run']['id']))
        if key == 'misp':
            data = self.warninglists(**options).sync(plan['warninglist_ids'])
            return {'kind': 'warninglist_runs', 'runs': [
                {'list_id': row['list_id'], 'run_id': row['id'], 'status': row['status']} for row in data['runs']]}
        data = self.research().record(**{name: plan[name] for name in SCOPE_FIELDS},
                                     idempotency_key='source-job-review:' + job_id)
        return {'kind': 'research_review', 'review_id': data['review']['id']}

    def verify(self, key, receipt, plan):
        validate_receipt(key, receipt, plan)
        receipt = {name: value for name, value in receipt.items() if name != 'usage'}
        if key in {'circl', 'urlscan'}:
            actual = self._enrichment_receipt(self.enrichment().show(receipt['run_id']))
            if receipt != actual:
                raise StorageError('İş başvurusu özgün kaynak kanıtıyla uyuşmuyor.')
        elif key == 'misp':
            for row in receipt['runs']:
                run = self.warninglists().show(row['run_id'], limit=1)['run']
                if any(row[key] != run[field] for key, field in (('run_id', 'id'), ('list_id', 'list_id'), ('status', 'status'))):
                    raise StorageError('İş başvurusu özgün liste kanıtıyla uyuşmuyor.')
        else:
            data = self.research().show(receipt['review_id'], limit=1)
            if data['review']['query'] != {name: plan[name] for name in SCOPE_FIELDS}:
                raise StorageError('İnceleme kaydı kaynak işi kapsamına ait değil.')

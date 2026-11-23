"""Compose established source services; retain their original immutable run IDs."""

from xti.adapters.sqlite import StorageError
from xti.domain.research_history import SCOPE_FIELDS
from xti.domain.source_jobs import validate_receipt
from xti.domain.source_job_usage import RequestUsageMeter, request_ceiling


class ExistingSourceJobOperations:
    def __init__(self, enrichment, warninglists, research, *, news=None, investigations=None, reports=None, publishers=None, relationship_notifications=None, social_tracking=None, groups=None, code_exposure=None, content_monitoring=None, brand_protection=None, cti_analysis=None, darkweb_monitoring=None):
        self.enrichment, self.warninglists, self.research = enrichment, warninglists, research
        self.news, self.investigations = news, investigations
        self.reports = reports
        self.publishers, self.relationship_notifications = publishers, relationship_notifications
        self.social_tracking, self.groups = social_tracking, groups
        self.code_exposure = code_exposure
        self.content_monitoring = content_monitoring
        self.brand_protection=brand_protection
        self.cti_analysis = cti_analysis
        self.darkweb_monitoring = darkweb_monitoring

    @staticmethod
    def _enrichment_receipt(data):
        run = data['run']
        return {'kind': 'enrichment_run', 'run_id': run['id'], 'provider': run['provider'],
            'indicator_type': run['indicator_type'], 'value': run['value'], 'source_status': run['status'],
            'snapshot_sha256': run['snapshot_sha256'], 'has_more': data['has_more']}

    def execute(self, key, plan, job_id, *, measure=False):
        if key == 'darkweb-monitor':
            return self.darkweb_monitoring().execute(plan, job_id)
        if key == 'cti-analysis':
            return self.cti_analysis().execute(plan, job_id)
        if key == 'brand-protection':
            return self.brand_protection().execute(plan,job_id)
        if key == 'content-monitor':
            return self.content_monitoring().execute(plan, job_id)
        if key == 'code-monitor':
            return self.code_exposure().execute(plan, job_id)
        if key == 'social-tracking':
            return self.social_tracking(network=True).execute(plan, job_id)
        meter = RequestUsageMeter(request_ceiling(key, plan)) if measure else None
        receipt = self._execute(key, plan, job_id, meter)
        if meter is not None:
            receipt = {**receipt, 'usage': meter.snapshot()}
        return receipt

    def _execute(self, key, plan, job_id, meter):
        options = {'refresh': True, **({'request_usage': meter} if meter is not None else {})}
        if key in {'circl', 'urlscan', 'ripestat', 'ripestat-whois'}:
            service = self.enrichment(**options)
            data = service.refresh(provider=key, indicator_type=plan['indicator_type'], value=plan['value'])
            return self._enrichment_receipt(service.show(data['run']['id']))
        if key == 'misp':
            data = self.warninglists(**options).sync(plan['warninglist_ids'])
            return {'kind': 'warninglist_runs', 'runs': [
                {'list_id': row['list_id'], 'run_id': row['id'], 'status': row['status']} for row in data['runs']]}
        if key.startswith('news:'):
            report = self.news(request_usage=meter).refresh(key[5:], limit=1)
            return {'kind': 'news_run', 'run_id': report.run.id, 'source': key[5:], 'source_status': report.run.status}
        if key == 'reports':
            from xti.domain.research import identity
            service = self.investigations()
            page = self.news().list(limit=20)
            records = []
            for stored in page.articles:
                result = service.extract('news', stored.article.id,
                    'report-job:' + identity(stored.article.id, stored.state_sha256))
                record = result['record']
                records.append({'id': record['id'], 'proposal_sha256': identity(record['proposal'])})
            return {'kind': 'report_extractions', 'records': records, 'has_more': page.has_more}
        if key.startswith('publisher:'):
            return self.publishers(request_usage=meter).execute(key, plan, job_id)
        if key == 'group-refresh':
            return self.groups().execute(plan, job_id)
        if key == 'relationship-notify':
            return self.relationship_notifications().execute(plan)
        if key == 'report-capture':
            return self.reports().execute(plan, job_id)
        data = self.research().record(**{name: plan[name] for name in SCOPE_FIELDS},
                                     idempotency_key='source-job-review:' + job_id)
        return {'kind': 'research_review', 'review_id': data['review']['id']}

    def verify(self, key, receipt, plan):
        validate_receipt(key, receipt, plan)
        if key == 'darkweb-monitor':
            self.darkweb_monitoring().verify(receipt, plan)
            return
        if key == 'cti-analysis':
            self.cti_analysis().verify(receipt, plan)
            return
        if key == 'brand-protection':
            self.brand_protection().verify(receipt,plan)
            return
        if key == 'content-monitor':
            self.content_monitoring().verify(receipt, plan)
            return
        if key == 'code-monitor':
            self.code_exposure().verify(receipt, plan)
            return
        if key == 'social-tracking':
            self.social_tracking().verify(receipt, plan)
            return
        receipt = {name: value for name, value in receipt.items() if name != 'usage'}
        if key in {'circl', 'urlscan', 'ripestat', 'ripestat-whois'}:
            actual = self._enrichment_receipt(self.enrichment().show(receipt['run_id']))
            if receipt != actual:
                raise StorageError('İş başvurusu özgün kaynak kanıtıyla uyuşmuyor.')
        elif key.startswith('news:'):
            run = self.news().run_show(receipt['run_id'], limit=1).run
            if run.source_key != receipt['source'] or run.status != receipt['source_status']:
                raise StorageError('Haber iş başvurusu özgün kaynakla uyuşmuyor.')
        elif key.startswith('publisher:'):
            self.publishers().verify(receipt, plan)
        elif key == 'group-refresh':
            self.groups().verify(receipt, plan)
        elif key == 'relationship-notify':
            self.relationship_notifications().verify(receipt, plan)
        elif key == 'report-capture':
            self.reports().verify(receipt, plan)
        elif key == 'reports':
            from xti.domain.research import identity
            for row in receipt['records']:
                record = self.investigations().show(row['id'])['record']
                if record['kind'] != 'report' or identity(record['proposal']) != row['proposal_sha256']:
                    raise StorageError('Rapor iş başvurusu özgün metinle uyuşmuyor.')
        elif key == 'misp':
            for row in receipt['runs']:
                run = self.warninglists().show(row['run_id'], limit=1)['run']
                if any(row[key] != run[field] for key, field in (('run_id', 'id'), ('list_id', 'list_id'), ('status', 'status'))):
                    raise StorageError('İş başvurusu özgün liste kanıtıyla uyuşmuyor.')
        else:
            data = self.research().show(receipt['review_id'], limit=1)
            if data['review']['query'] != {name: plan[name] for name in SCOPE_FIELDS}:
                raise StorageError('İnceleme kaydı kaynak işi kapsamına ait değil.')

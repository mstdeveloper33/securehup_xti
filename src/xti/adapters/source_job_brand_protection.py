"""Core receipt survives queue interruption; completed source work is not silently reissued."""
from xti.adapters.sqlite import StorageError
from xti.domain.brand_protection import BrandProtectionError, digest
from xti.domain.brand_protection_jobs import guard, scope_matches, SOURCE
from xti.domain.engine_jobs import EngineJobError


class BrandProtectionStep:
    def __init__(self, service, jobs): self.service, self.jobs = service, jobs

    @staticmethod
    def key(identifier): return 'brand-protection-job:' + identifier

    @staticmethod
    def reference(run, *, reused=False):
        report=run['report']
        attempts=[] if reused else report.get('http_attempts',[])
        unknown=not reused and report.get('external_social_tool_http_requests') is None
        usage={'version':1,'unit':'brand_source_operations','operations':len(attempts),
            'http_requests':None if unknown else len(attempts),
            'http_usage':{'version':1,'unit':'http_open_attempt','attempts':len(attempts),
                'responses':sum(a.get('http_status') is not None for a in attempts),
                'transport_errors':sum(a.get('http_status') is None for a in attempts),
                'rate_limited':sum(a.get('http_status')==429 for a in attempts),'budget_rejections':0},
            'unmeasured_transports':['social'] if unknown else [],'receipt_reused':reused}
        return {'kind': 'brand_protection_run', 'run_id': run['id'], 'watch_id': run['watch_id'],
                'watch_revision': run['snapshot']['watch_revision'], 'source_status': run['status'],
                'report_sha256': digest(run['report']), 'reused_receipt': reused, 'usage': usage}

    def execute(self, plan, job_id):
        key = self.key(job_id); keys = [(key, False)]
        job = self.jobs.get(job_id); ancestor = job
        while ancestor.payload.retry_of is not None:
            ancestor = self.jobs.get(ancestor.payload.retry_of)
            step = next(step for step in ancestor.steps if step['key'] == SOURCE)
            if step['receipt'] is not None: break
            keys.append((self.key(ancestor.id), True))
        for previous_key, reused in keys:
            with self.service.repository.storage._connection(readonly=True) as connection:
                row = connection.execute('SELECT id FROM brand_protection_runs WHERE request_key=?', (previous_key,)).fetchone()
            if row is None: continue
            run = self.service.execute('brand.protection.run.show', identifier=row[0])
            if (run['watch_id'] != plan['protection_watch_id'] or run['snapshot']['watch_revision'] != plan['protection_watch_revision']
                    or not scope_matches(run['snapshot'], plan)):
                raise StorageError('Marka iş makbuzu başka kapsama bağlı.')
            if run['status'] == 'running': raise EngineJobError('execution_uncertain', 'Marka toplama kesilmiş; brand protection recover sonrası açık iş tekrarı gerekli.')
            if run['status'] == 'interrupted':
                if reused: continue
                raise EngineJobError('execution_uncertain', 'Marka makbuzu kesilmiş; yeni iş tekrarı gerekli.')
            return self.reference(run, reused=reused)
        bundle = self.service.execute('brand.protection.plan', identifier=plan['protection_watch_id'])
        if not guard(bundle, plan): raise EngineJobError('plan_changed', 'Marka izleme kapsamı, sürümü veya bütçesi değişti.')
        watch=bundle['watch']
        self.service.cancelled = lambda: self.jobs.get(job_id).cancel_requested
        try:
            run = self.service.execute('brand.protection.run', identifier=watch['id'], expected_revision=watch['revision'],
                force=plan['protection_force'] or job.payload.retry_of is not None, idempotency_key=key)
        except BrandProtectionError as error: raise EngineJobError(error.code, error.message) from error
        return self.reference(run)

    def verify(self, receipt, plan):
        run = self.service.execute('brand.protection.run.show', identifier=receipt['run_id'])
        if receipt != self.reference(run, reused=receipt['reused_receipt']) or not scope_matches(run['snapshot'], plan):
            raise StorageError('Marka iş sonucu özgün firma makbuzuyla uyuşmuyor.')

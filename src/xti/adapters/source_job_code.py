"""Queue/core receipt recovery; never reissue a completed code collection silently."""
from xti.adapters.sqlite import StorageError
from xti.domain.code_exposure import CodeExposureError
from xti.domain.code_jobs import guard, SOURCE
from xti.domain.engine_jobs import EngineJobError


class CodeMonitorStep:
    def __init__(self, service, jobs): self.service, self.jobs = service, jobs

    @staticmethod
    def key(identifier): return 'code-job:' + identifier

    @staticmethod
    def reference(run, *, reused=False):
        counts = run['report']['http_usage'] if not reused else dict.fromkeys(
            ('attempts', 'responses', 'transport_errors', 'rate_limited', 'budget_rejections'), 0)
        return {'kind': 'code_exposure_run', 'run_id': run['id'], 'watch_id': run['watch_id'],
                'watch_revision': run['watch_revision'], 'source_status': run['status'],
                'report_sha256': run['report_sha256'], 'reused_receipt': reused,
                'usage': {'version': 1, 'unit': 'http_open_attempt', **counts}}

    def execute(self, plan, job_id):
        # Same job's deterministic key is checked before current watch guards.
        key = self.key(job_id)
        keys = [(key, False)]
        job = self.jobs.get(job_id)
        ancestor = job
        while ancestor.payload.retry_of is not None:
            ancestor = self.jobs.get(ancestor.payload.retry_of)
            step = next(step for step in ancestor.steps if step['key'] == SOURCE)
            if step['receipt'] is not None: break
            keys.append((self.key(ancestor.id), True))
        repo = self.service.repository
        for previous_key, reused in keys:
            with repo.storage._connection(readonly=True) as connection:
                row = connection.execute('SELECT id FROM code_runs WHERE request_key=?', (previous_key,)).fetchone()
            if row is None: continue
            run = self.service.execute('code.run.show', identifier=row[0])
            if run['watch_id'] != plan['code_watch_id'] or run['watch_revision'] != plan['code_watch_revision'] or run['scope']['domain'] != plan['value']:
                raise StorageError('Kod iş makbuzu başka kapsama bağlı.')
            if run['status'] == 'running':
                raise EngineJobError('execution_uncertain', 'Kod toplama kesilmiş; code recover sonrası açık iş tekrarı gerekli.')
            if run['status'] == 'interrupted':
                if reused: continue  # An explicit queue retry may start a new bounded read after core recovery.
                raise EngineJobError('execution_uncertain', 'Kod makbuzu kesilmiş; yeni iş tekrarı gerekli.')
            return self.reference(run, reused=reused)
        watch = self.service.execute('code.watch.show', identifier=plan['code_watch_id'])
        if not guard(watch, plan): raise EngineJobError('plan_changed', 'Kod izleme kapsamı, sürümü veya bütçesi değişti.')
        self.service.sources.cancelled = lambda: self.jobs.get(job_id).cancel_requested
        try:
            run = self.service.execute('code.run', identifier=watch['id'], expected_revision=watch['revision'],
                                       force=plan['code_force'] or job.payload.retry_of is not None, idempotency_key=key)
        except CodeExposureError as error:
            raise EngineJobError(error.code, error.message) from error
        return self.reference(run)

    def verify(self, receipt, plan):
        run = self.service.execute('code.run.show', identifier=receipt['run_id'])
        expected = self.reference(run, reused=receipt['reused_receipt'])
        if receipt != expected or run['scope']['domain'] != plan['value']:
            raise StorageError('Kod iş sonucu özgün firma makbuzuyla uyuşmuyor.')

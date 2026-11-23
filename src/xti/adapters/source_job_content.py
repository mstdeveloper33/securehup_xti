"""Core receipt survives queue interruption; completed source work is not silently reissued."""
from xti.adapters.sqlite import StorageError
from xti.domain.content_monitoring import ContentError, digest
from xti.domain.content_jobs import guard, scope_matches, SOURCE
from xti.domain.engine_jobs import EngineJobError


class ContentMonitorStep:
    def __init__(self, service, jobs): self.service, self.jobs = service, jobs

    @staticmethod
    def key(identifier): return 'content-job:' + identifier

    @staticmethod
    def reference(run, *, reused=False):
        sources = run['report'].get('sources', [])
        unmeasured = sorted({s['provider'] for s in sources if s.get('operations', 0) and s['provider'] in ('telegram', 'irc')})
        if any(s.get('usage_complete') is False for s in sources): unmeasured = sorted(set(unmeasured) | {'unknown'})
        http = sum(len(s.get('attempts', [])) for s in sources)
        attempts = [a for s in sources for a in s.get('attempts', [])] if not reused else []
        http_usage = {'version': 1, 'unit': 'http_open_attempt', 'attempts': len(attempts),
                      'responses': sum(a.get('http_status') is not None for a in attempts),
                      'transport_errors': sum(a.get('http_status') is None for a in attempts),
                      'rate_limited': sum(a.get('http_status') == 429 for a in attempts), 'budget_rejections': 0}
        usage = {'version': 1, 'unit': 'content_source_operations',
                 'operations': 0 if reused else sum(s.get('operations', 0) for s in sources),
                 'http_requests': 0 if reused else None if unmeasured else http,
                 'http_usage': http_usage,
                 'unmeasured_transports': [] if reused else unmeasured, 'receipt_reused': reused}
        return {'kind': 'content_monitor_run', 'run_id': run['id'], 'watch_id': run['watch_id'],
                'watch_revision': run['watch_revision'], 'source_status': run['status'],
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
                row = connection.execute('SELECT id FROM content_runs WHERE request_key=?', (previous_key,)).fetchone()
            if row is None: continue
            run = self.service.execute('content.run.show', identifier=row[0])
            if (run['watch_id'] != plan['content_watch_id'] or run['watch_revision'] != plan['content_watch_revision']
                    or not scope_matches(run['snapshot'], plan)):
                raise StorageError('İçerik iş makbuzu başka kapsama bağlı.')
            if run['status'] == 'running': raise EngineJobError('execution_uncertain', 'İçerik toplama kesilmiş; content recover sonrası açık iş tekrarı gerekli.')
            if run['status'] == 'interrupted':
                if reused: continue
                raise EngineJobError('execution_uncertain', 'İçerik makbuzu kesilmiş; yeni iş tekrarı gerekli.')
            return self.reference(run, reused=reused)
        watch = self.service.execute('content.watch.show', identifier=plan['content_watch_id'])
        if not guard(watch, plan): raise EngineJobError('plan_changed', 'İçerik izleme kapsamı, sürümü veya bütçesi değişti.')
        self.service.cancelled = lambda: self.jobs.get(job_id).cancel_requested
        try:
            run = self.service.execute('content.run', identifier=watch['id'], expected_revision=watch['revision'],
                force=plan['content_force'] or job.payload.retry_of is not None, idempotency_key=key)
        except ContentError as error: raise EngineJobError(error.code, error.message) from error
        return self.reference(run)

    def verify(self, receipt, plan):
        run = self.service.execute('content.run.show', identifier=receipt['run_id'])
        if receipt != self.reference(run, reused=receipt['reused_receipt']) or not scope_matches(run['snapshot'], plan):
            raise StorageError('İçerik iş sonucu özgün firma makbuzuyla uyuşmuyor.')

"""Use existing social receipts across queue/core transaction boundaries."""
from xti.adapters.sqlite import StorageError
from xti.domain.social_discovery import SocialDiscoveryError
from xti.domain.social_jobs import SOURCE, blocked, reference, usage, watch_guard


class SocialTrackingStep:
    def __init__(self, tracking, discoveries, jobs):
        self.tracking, self.discoveries, self.jobs = tracking, discoveries, jobs

    @staticmethod
    def key(job_id):
        return 'social-job-' + job_id

    def _guard(self, plan):
        try: watch = self.tracking.execute('brand.tracking.show', identifier=plan['social_watch_id'])['record']
        except SocialDiscoveryError as error:
            if error.code == 'not_found': return 'not_found'
            raise
        return watch_guard(watch, plan)

    def _reference(self, result, plan):
        run = result['record']
        if (run['watch_id'] != plan['social_watch_id'] or run['scope']['domain'] != plan['value']
                or run.get('watch_revision') != plan['social_watch_revision']):
            raise StorageError('Sosyal iş turu dondurulmuş izleme kapsamına ait değil.')
        discovery = self.discoveries.show(run['discovery_id'])['record']
        reused = result.get('discovery_replayed', result.get('replayed', False))
        pages = discovery['report']['metrics']['page_http_requests'] if discovery['report'] is not None else None
        return {**reference(run, plan), 'usage': usage(attempted=not reused, pages=pages, reused=reused)}

    def _run(self, plan, key):
        try:
            result = self.tracking.execute('brand.tracking.run', identifier=plan['social_watch_id'],
                force=plan['social_force'], idempotency_key=key)
        except SocialDiscoveryError as error:
            if error.code in ('not_due', 'busy'): return blocked(error.code, plan)
            raise
        return self._reference(result, plan)

    def _recover(self, plan, job_id):
        key = self.key(job_id)
        run = self.tracking.find_run(key)
        if run is None: return None
        if run['status'] != 'running':
            return self._reference({'record': run, 'replayed': True}, plan)
        # A durable discovery reservation guarantees that replay cannot send again.
        # Without it, current pause/revision/domain guards still apply before network.
        if self.discoveries.find_key(run['discovery_key']) is None:
            guard = self._guard(plan)
            if guard:
                self.tracking.interrupt_run(key)
                return blocked(guard, plan)
        return self._run(plan, key)

    def execute(self, plan, job_id):
        own = self._recover(plan, job_id)
        if own is not None: return own
        job = self.jobs.get(job_id)
        while job.payload.retry_of is not None:
            job = self.jobs.get(job.payload.retry_of)
            step = next(s for s in job.steps if s['key'] == SOURCE)
            if step['receipt'] is not None:
                break  # Explicit retry of a recorded partial/failure gets a new round.
            previous = self._recover(plan, job.id)
            if previous is not None:
                if previous['source_status'] != 'interrupted': return previous
                break  # Parent uncertainty was explicitly accepted by queue admission.
        guard = self._guard(plan)
        if guard: return blocked(guard, plan)
        return self._run(plan, self.key(job_id))

    def verify(self, receipt, plan):
        if receipt['source_status'] == 'blocked':
            # Admission facts belong to the immutable job event. Rechecking a later
            # pause/due state would rewrite history, and there is no provider evidence.
            return
        run = self.tracking.execute('brand.tracking.run.show', identifier=receipt['run_id'])['record']
        if (reference(run, plan) != {key: value for key, value in receipt.items() if key != 'usage'}
                or run['watch_id'] != plan['social_watch_id'] or run['scope']['domain'] != plan['value']
                or run.get('watch_revision') != plan['social_watch_revision']):
            raise StorageError('Sosyal iş başvurusu özgün tur kanıtıyla uyuşmuyor.')
        if receipt['usage']['attempted']:
            report = self.discoveries.show(run['discovery_id'])['record']['report']
            expected = report['metrics']['page_http_requests'] if report is not None else None
            if receipt['usage']['page_http_requests'] != expected:
                raise StorageError('Sosyal iş sayfa ölçümü özgün keşifle uyuşmuyor.')

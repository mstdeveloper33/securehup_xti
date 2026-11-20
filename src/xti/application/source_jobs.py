"""Admission and cooperative execution in the existing durable engine queue."""

from datetime import datetime, timezone
import time

from xti.domain.assets import ValidationError
from xti.domain.collection_history import history_uuid
from xti.domain.engine_jobs import EngineJobError, ENGINE_JOB_TERMINAL, digest, request_key
from xti.domain.source_jobs import SourceJobPayload, source_plan, plan_data, result_for, validate_receipt
from xti.ports.engine_jobs import EngineJobRepository, SourceJobOperations
from xti.ports.jobs import ExecutionLock


class SourceJobService:
    def __init__(self, repository: EngineJobRepository, *, clock=None, social_tracking=None, groups=None):
        self.repository = repository
        self.social_tracking, self.groups = social_tracking, groups
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _social_guard(self, plan):
        from xti.domain.social_jobs import SOURCE, watch_guard
        if SOURCE not in plan['sources']: return
        if self.social_tracking is None:
            raise EngineJobError('invalid_parameters', 'Sosyal iş için çalışma alanı izleme servisi gerekli.')
        watch = self.social_tracking.execute('brand.tracking.show', identifier=plan['social_watch_id'])['record']
        reason = watch_guard(watch, plan)
        if reason: raise EngineJobError('plan_changed', 'Sosyal izleme domaini, sürümü veya etkinliği değişti; planı yenileyin.')
        return watch

    def _group_guard(self, plan):
        from xti.domain.group_jobs import SOURCE, scope_matches
        if SOURCE not in plan['sources']:
            return
        if self.groups is None:
            raise EngineJobError('invalid_parameters', 'Grup işi için çalışma alanı kanıt servisi gerekli.')
        record = self.groups.execute('groups.show', identifier=plan['group_id'])['record']
        if not scope_matches(record, plan):
            raise EngineJobError('plan_changed', 'Kayıtlı grup farklı araştırma köküne bağlı.')
        return record

    def plan(self, **parameters):
        plan = source_plan(**parameters)
        watch = self._social_guard(plan)
        group = self._group_guard(plan)
        data = plan_data(plan)
        if group is not None:
            data["group"] = {"id": group["id"], "scope": group["group"]["scope"], "current_revision": group["revision"]}
        if watch is not None:
            data['social_watch'] = {'id': watch['id'], 'revision': watch['revision'], 'scope': watch['scope'],
                                    'interval_seconds': watch['interval_seconds']}
        return data

    def _now(self):
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError('Motor işi zamanı saat dilimi bilgili olmalı.')
        return value.astimezone(timezone.utc).isoformat()

    def _submit(self, payload, key):
        key = request_key(key)
        request = payload.request_json()
        previous = self.repository.find_request(key)
        if previous:
            if previous.request_sha256 != digest(request):
                raise EngineJobError('idempotency_conflict', 'Bu anahtar başka bir motor işine bağlı.')
            return previous
        return self.repository.create(key, request, payload, recorded_at=self._now())

    def submit(self, *, idempotency_key, plan_sha256, **parameters):
        plan = source_plan(**parameters)
        if plan_data(plan)['plan_sha256'] != plan_sha256:
            raise EngineJobError('plan_changed', 'Kaynak planı özeti uyuşmuyor; güncel planı inceleyin.')
        if self.repository.find_request(request_key(idempotency_key)) is None:
            self._social_guard(plan)
            self._group_guard(plan)
        return self._submit(SourceJobPayload(plan), idempotency_key)

    def status(self, job_id):
        job = self.repository.get(history_uuid(job_id))
        if not isinstance(job.payload, SourceJobPayload):
            raise EngineJobError('not_found', 'Bu kimlikte kaynak işi bulunamadı.')
        return job

    def results(self, job_id):
        job = self.status(job_id)
        return {'job': job.to_dict(), 'result': job.result}

    def cancel(self, job_id):
        self.status(job_id)
        return self.repository.cancel(job_id, recorded_at=self._now())

    def retry(self, job_id, *, idempotency_key, allow_uncertain=False):
        if type(allow_uncertain) is not bool:
            raise ValidationError('Belirsiz tekrar seçimi boolean olmalı.')
        parent = self.status(job_id)
        if parent.status not in ENGINE_JOB_TERMINAL - {'complete'}:
            raise EngineJobError('invalid_job_state', 'Yalnız tamamlanamamış ve sona ermiş kaynak işi yeniden denenebilir.')
        if parent.status == 'interrupted' and not allow_uncertain:
            raise EngineJobError('uncertain_outcome', 'Kesilen isteğin dış sonucu belirsiz; yeniden gönderme için allow_uncertain açıkça seçilmeli.')
        from xti.domain.source_jobs import reusable_steps
        reused = reusable_steps(parent)
        return self._submit(SourceJobPayload(parent.payload.plan, parent.id, allow_uncertain, reused), idempotency_key)

    def list(self, *, offset=0, limit=20):
        rows, more = self.repository.list_sources(offset=offset, limit=limit)
        return {'jobs': [job.to_dict() for job in rows], 'offset': offset, 'limit': limit, 'has_more': more}


class CooperativeSourceJobRunner:
    def __init__(self, operations: SourceJobOperations, lock: ExecutionLock, *, monotonic=None):
        self.operations, self.lock = operations, lock
        self.monotonic = monotonic or time.monotonic

    def run(self, job, *, started, current, progress):
        with self.lock.acquire():
            # Queue lock is already held; same queue→core order as platform backup.
            for step in job.steps:
                if step['receipt'] is not None:
                    self.operations.verify(step['key'], step['receipt'], job.payload.plan)
            started()
            deadline = self.monotonic() + job.payload.plan['max_seconds']
            for initial in job.steps:
                if initial['status'] == 'complete':
                    continue
                key = initial['key']
                latest = current()
                if job.payload.plan.get('failure_policy') == 'stop' and any(s['status'] in {'failed', 'partial'} for s in latest.steps):
                    progress(key, action='skip', reason='dependency_failed')
                    continue
                if latest.cancel_requested or self.monotonic() >= deadline:
                    progress(key, action='skip', reason='cancelled' if latest.cancel_requested else 'budget_exhausted')
                    continue
                latest = progress(key, action='start')
                if latest.cancel_requested:
                    progress(key, action='skip', reason='cancelled')
                    continue
                # Durable start precedes all external activity. Exceptions leave an
                # uncertain step, never an implicitly retried request.
                receipt = self.operations.execute(key, job.payload.plan, job.id,
                                                  **({'measure': True} if job.payload.version >= 2 else {}))
                validate_receipt(key, receipt, job.payload.plan)
                self.operations.verify(key, receipt, job.payload.plan)
                progress(key, action='finish', receipt=receipt)
            return result_for(current())

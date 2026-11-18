"""At-most-once dispatch with durable identity and explicit uncertain-outcome recovery."""

from collections.abc import Callable
from datetime import datetime, timezone

from xti.domain.assets import ValidationError
from xti.domain.collection_history import history_uuid
from xti.domain.engine_jobs import (
    EngineJob, EngineJobError, digest, request_key, request_json, result_json, job_result_status,
)
from xti.domain.source_jobs import SourceJobPayload
from xti.ports.engine_jobs import EngineJobRepository, EngineJobRunner, SourceJobRunner
from xti.ports.jobs import ExecutionLock


class EngineJobService:
    def __init__(self, repository: EngineJobRepository, runner: EngineJobRunner | None,
                 lock: ExecutionLock, *, clock: Callable[[], datetime] | None = None,
                 source_runner: SourceJobRunner | None = None):
        self.repository, self.runner, self.lock = repository, runner, lock
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.source_runner = source_runner

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError('Motor işi zamanı saat dilimi bilgili olmalı.')
        return value.astimezone(timezone.utc).isoformat()

    def submit(self, key: str, profile_name: str, profile_revision: int) -> EngineJob:
        key, request = request_key(key), request_json(profile_name, profile_revision)
        previous = self.repository.find_request(key)
        if previous is not None:
            if previous.request_sha256 != digest(request):
                raise EngineJobError('idempotency_conflict', 'Bu tekrar önleme anahtarı başka bir isteğe bağlı.')
            return previous
        if self.runner is None:
            raise EngineJobError('execution_unavailable', 'Motor işi çalıştırıcısı yapılandırılmamış.')
        payload = self.runner.prepare(profile_name, profile_revision)
        return self.repository.create(key, request, payload, recorded_at=self._now())

    def status(self, job_id: str) -> EngineJob:
        return self.repository.get(history_uuid(job_id))

    def results(self, job_id: str) -> dict:
        job = self.status(job_id)
        return {'job': job.to_dict(), 'result': job.result}

    def cancel(self, job_id: str) -> EngineJob:
        return self.repository.cancel(history_uuid(job_id), recorded_at=self._now())

    def work_one(self, job_id: str | None = None) -> EngineJob | None:
        if job_id is not None:
            history_uuid(job_id)
        if self.runner is None and self.source_runner is None:
            raise EngineJobError('execution_unavailable', 'Motor işi çalıştırıcısı yapılandırılmamış.')
        with self.lock.acquire():
            claim = self.repository.claim(job_id, recorded_at=self._now())
            if claim is None:
                return None
            try:
                if isinstance(claim.job.payload, SourceJobPayload):
                    if self.source_runner is None:
                        raise EngineJobError('execution_unavailable', 'Kaynak işi çalıştırıcısı yapılandırılmamış.')
                    result = self.source_runner.run(claim.job,
                        started=lambda: self.repository.link_session(claim, claim.job.id, recorded_at=self._now()),
                        current=lambda: self.repository.get(claim.job.id),
                        progress=lambda key, **kwargs: self.repository.source_step(claim, key,
                            recorded_at=self._now(), **kwargs))
                else:
                    if self.runner is None:
                        raise EngineJobError('execution_unavailable', 'Profil çalıştırıcısı yapılandırılmamış.')
                    result = self.runner.run(claim.job.payload, session_started=lambda session_id:
                        self.repository.link_session(claim, session_id, recorded_at=self._now()))
                result_json(result)
                return self.repository.finish(
                    claim, status=job_result_status(result), result=result,
                    error_code=None, recorded_at=self._now(),
                )
            except BaseException:
                # A source may have accepted a request before the process failed.
                # Never turn an exception or expired lease into permission to repeat it.
                try:
                    self.repository.finish(claim, status='interrupted', result=None,
                                           error_code='execution_uncertain', recorded_at=self._now())
                except Exception:
                    pass  # Durable running state is resolved only by explicit locked recovery.
                raise

    def recover(self) -> tuple[EngineJob, ...]:
        with self.lock.acquire():
            return self.repository.recover_interrupted(recorded_at=self._now())

"""Persist scan intent and attempts without keeping a database transaction during HTTP."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from xti.application.discovery import DiscoveryService
from xti.domain.collection_history import CollectionOperationToken
from xti.domain.assets import ValidationError
from xti.domain.discovery import QueryResult
from xti.domain.jobs import JOB_STATUSES, JobDetails, ScanAttempt, ScanJob
from xti.ports.jobs import ExecutionLock, JobRepository


RECOVERY_REASON = "Önceki çalıştırma tamamlanmadan kapandı. Yeniden deneme ayrı bir kayıt oluşturur."


class JobService:
    def __init__(
        self, jobs: JobRepository, discovery: DiscoveryService,
        lock: ExecutionLock, *, provider: str = "crt.sh",
        discoveries: Mapping[str, DiscoveryService] | None = None,
    ) -> None:
        self.jobs = jobs
        self.discovery = discovery
        self.lock = lock
        self.provider = provider
        self.discoveries = dict(discoveries or {})
        self.discoveries.setdefault(provider, discovery)

    @staticmethod
    def _validate_id(job_id: str) -> None:
        if not isinstance(job_id, str) or not job_id or len(job_id) > 64 or not job_id.isprintable():
            raise ValidationError("Geçerli bir iş kimliği gerekli.")

    def enqueue(
        self, domains: Sequence[str] | None = None, *, typos: bool = False,
        provider: str | None = None,
        operation: CollectionOperationToken | None = None,
    ) -> ScanJob:
        provider = provider or self.provider
        discovery = self.discoveries.get(provider)
        if discovery is None:
            raise ValidationError("Bu internet kaynağı desteklenmiyor.")
        targets = discovery.validate_targets(domains, typos=typos)
        return self.jobs.create(
            targets, typos, provider, discovery.matcher.rule_version,
            **({"operation": operation} if operation is not None else {}),
        )

    def list(self, status: str | None = None, limit: int = 20) -> list[ScanJob]:
        if status is not None and status not in JOB_STATUSES:
            raise ValidationError("Geçersiz iş durumu.")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Liste sınırı 1–100 arasında olmalı.")
        return self.jobs.list(status, limit)

    def show(self, job_id: str) -> JobDetails:
        self._validate_id(job_id)
        return self.jobs.get(job_id)

    def recover(self) -> int:
        with self.lock.acquire():
            return self.jobs.recover_interrupted(RECOVERY_REASON)

    def source_status(self) -> list[dict]:
        """Last recorded query outcomes, never a claim of current availability."""
        statuses = []
        for details in self.jobs.latest_by_provider():
            attempt = details.attempts[-1]
            queries = attempt.queries
            source_state = "unknown"
            if queries:
                succeeded = sum(query.status != "failed" for query in queries)
                source_state = "failed" if not succeeded else (
                    "partial" if succeeded != len(queries) or any(q.status == "partial" for q in queries)
                    else "responded"
                )
            statuses.append({
                "provider": details.job.provider, "job_id": details.job.id,
                "attempt_id": attempt.id, "attempt_status": attempt.status,
                "started_at": attempt.started_at, "finished_at": attempt.finished_at,
                "source_status": source_state, "queries": queries, "error": attempt.error,
            })
        return statuses

    def run(
        self, job_id: str | None = None, *, progress: Callable[[str], None] | None = None,
    ) -> ScanAttempt | None:
        if job_id is not None:
            self._validate_id(job_id)
            self.jobs.get(job_id)
        with self.lock.acquire():
            return self.run_owned(job_id, progress=progress)

    def run_owned(
        self, job_id: str | None = None, *, monitor_id: str | None = None,
        progress: Callable[[str], None] | None = None,
        operation: CollectionOperationToken | None = None,
    ) -> ScanAttempt | None:
        """Run work while the caller holds this service's execution lock.

        Monitoring holds that same lock over its entire session, including gaps.
        Ordinary callers must use run(), which acquires it before entering here.
        """
        if job_id is not None:
            self._validate_id(job_id)
        if monitor_id is not None:
            self._validate_id(monitor_id)
            if job_id is None:
                raise ValidationError("İzleme çalıştırması için açık iş kimliği gerekli.")
        if operation is not None and (job_id is None or monitor_id is not None):
            raise ValidationError("Toplama çalıştırması için yalnız açık toplama işi gerekli.")
        self.jobs.recover_interrupted(RECOVERY_REASON)
        operation_options = {"operation": operation} if operation is not None else {}
        attempt = (
            self.jobs.start(job_id, **operation_options) if monitor_id is None
            else self.jobs.start(job_id, monitor_id=monitor_id)
        )
        if attempt is None:
            return None
        try:
            job = self.jobs.get(attempt.job_id).job
            discovery = self.discoveries.get(job.provider)
            if discovery is None or job.rule_version != discovery.matcher.rule_version:
                raise ValidationError(
                    "Bu işin kaynak veya karşılaştırma sürümü değişmiş. "
                    "Güncel kurallarla yeni bir 'scan' başlat."
                )

            def update(message: str) -> None:
                self.jobs.progress(attempt.id, message)
                if progress:
                    progress(message)

            def record_query(query: QueryResult) -> None:
                self.jobs.progress(attempt.id, f"Sorgu tamamlandı: {query.pattern}", query)

            if progress:
                progress(f"İş: {job.id} | Deneme: {attempt.number}")
            result = discovery.scan(
                job.targets, typos=job.typos, progress=update, on_query=record_query,
            )
            return self.jobs.finish(
                attempt.id, result.status, result=result, **operation_options,
            )
        except BaseException as exc:
            interrupted = isinstance(exc, (KeyboardInterrupt, SystemExit))
            # Do not put arbitrary exception text (which may carry secrets) in history.
            message = (
                "İşlem kullanıcı veya süreç tarafından durduruldu."
                if interrupted else (
                    str(exc) if isinstance(exc, ValidationError)
                    else "İşlem tamamlanamadı. Kayıt alanını ve uygulama hatasını kontrol et."
                )
            )
            try:
                self.jobs.finish(
                    attempt.id, "interrupted" if interrupted else "failed", error=message,
                    **operation_options,
                )
            except Exception:
                # If storage itself is unavailable, the running record remains recoverable.
                pass
            raise

    def retry(self, job_id: str, *, progress: Callable[[str], None] | None = None) -> ScanAttempt:
        result = self.run(job_id, progress=progress)
        assert result is not None
        return result

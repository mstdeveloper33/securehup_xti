"""Persistence and exclusive local execution boundaries for scan jobs."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from xti.domain.collection_history import CollectionOperationToken
from xti.domain.discovery import QueryResult, ScanResult
from xti.domain.jobs import JobDetails, ScanAttempt, ScanJob


class WorkerBusyError(RuntimeError):
    """Another local worker holds the execution lock."""


class ExecutionLock(Protocol):
    def acquire(self) -> AbstractContextManager[None]:
        ...


class JobRepository(Protocol):
    def create(
        self, targets: tuple[str, ...], typos: bool, provider: str, rule_version: str, *,
        operation: CollectionOperationToken | None = None,
    ) -> ScanJob:
        ...

    def list(self, status: str | None = None, limit: int = 20) -> list[ScanJob]:
        ...

    def get(self, job_id: str) -> JobDetails:
        ...

    def latest_by_provider(self) -> list[JobDetails]:
        """Latest attempted job per provider, in insertion order rather than wall clock."""
        ...

    def recover_interrupted(self, reason: str) -> int:
        """Caller MUST hold the exclusive execution lock before recovering work."""
        ...

    def start(
        self, job_id: str | None = None, *, monitor_id: str | None = None,
        operation: CollectionOperationToken | None = None,
    ) -> ScanAttempt | None:
        """Claim a queued job, or explicitly retry a failed/partial/interrupted job.

        Caller holds execution lock. No id selects the oldest ordinary queued job.
        Monitoring work requires its owning live session and cannot be retried.
        """
        ...

    def progress(self, attempt_id: str, message: str, query: QueryResult | None = None) -> None:
        ...

    def finish(
        self, attempt_id: str, status: str, *, result: ScanResult | None = None,
        error: str | None = None,
        operation: CollectionOperationToken | None = None,
    ) -> ScanAttempt:
        ...

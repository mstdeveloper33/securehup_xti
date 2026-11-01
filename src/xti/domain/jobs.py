"""Durable scan requests and append-only execution attempts."""

from dataclasses import dataclass

from xti.domain.discovery import QueryResult, ScanResult


JOB_STATUSES = frozenset({"queued", "running", "complete", "partial", "failed", "interrupted"})
RETRYABLE_STATUSES = frozenset({"failed", "partial", "interrupted"})


@dataclass(frozen=True, slots=True)
class ScanJob:
    id: str
    targets: tuple[str, ...]
    typos: bool
    provider: str
    rule_version: str
    status: str
    created_at: str
    updated_at: str
    attempt_count: int


@dataclass(frozen=True, slots=True)
class ScanAttempt:
    id: str
    job_id: str
    number: int
    status: str
    started_at: str
    finished_at: str | None
    progress: str | None
    error: str | None
    queries: tuple[QueryResult, ...]
    result: ScanResult | None


@dataclass(frozen=True, slots=True)
class JobDetails:
    job: ScanJob
    attempts: tuple[ScanAttempt, ...]

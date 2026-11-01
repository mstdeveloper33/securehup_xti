"""Bounded monitoring sessions and their attributed first execution attempts."""

from dataclasses import dataclass

from xti.domain.jobs import ScanJob
from xti.domain.findings import ImportSummary


@dataclass(frozen=True, slots=True)
class MonitorSpec:
    targets: tuple[str, ...]
    providers: tuple[str, ...]
    typos: bool
    rule_version: str
    max_cycles: int
    interval_seconds: int
    max_duration_seconds: int


@dataclass(frozen=True, slots=True)
class MonitorRun:
    id: str
    spec: MonitorSpec
    status: str
    started_at: str
    finished_at: str | None
    elapsed_seconds: float | None
    stop_reason: str | None


@dataclass(frozen=True, slots=True)
class MonitorAttempt:
    id: str
    number: int
    status: str
    started_at: str
    finished_at: str | None
    error: str | None
    query_count: int
    failed_queries: int
    partial_queries: int
    summary: ImportSummary | None


@dataclass(frozen=True, slots=True)
class MonitorEntry:
    cycle: int
    provider: str
    job: ScanJob
    attempt: MonitorAttempt | None


@dataclass(frozen=True, slots=True)
class MonitorDetails:
    run: MonitorRun
    entries: tuple[MonitorEntry, ...]


@dataclass(frozen=True, slots=True)
class MonitorSourceSummary:
    provider: str
    planned_runs: int
    scheduled_jobs: int
    started_attempts: int
    complete: int
    partial: int
    failed: int
    interrupted: int
    running: int
    not_started: int
    query_count: int
    failed_queries: int
    partial_queries: int
    observations_created: int
    findings_created: int
    unknown_result_count: int
    findings_suppressed: int = 0


@dataclass(frozen=True, slots=True)
class MonitorReport:
    run: MonitorRun
    sources: tuple[MonitorSourceSummary, ...]
    completed_cycles: int
    outcome: str
    notes: tuple[str, ...]

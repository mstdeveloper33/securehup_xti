"""Results from external domain discovery, independent of transport and storage."""

from dataclasses import dataclass

from xti.domain.findings import ImportDocument, ImportSummary


@dataclass(frozen=True, slots=True)
class SourceBatch:
    documents: tuple[ImportDocument, ...]
    skipped_names: int
    record_count: int
    warnings: tuple[str, ...] = ()
    coverage_notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QueryResult:
    pattern: str
    source_url: str
    status: str
    record_count: int
    skipped_names: int
    error: str | None
    warnings: tuple[str, ...]
    coverage_notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScanResult:
    targets: tuple[str, ...]
    started_at: str
    finished_at: str
    status: str
    queries: tuple[QueryResult, ...]
    summary: ImportSummary
    candidate_domains: tuple[str, ...]


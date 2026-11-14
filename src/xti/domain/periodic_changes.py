"""Local daily/weekly evidence windows; families never imply a unique threat total."""
from dataclasses import dataclass
from datetime import datetime, timezone
from xti.domain.assets import ValidationError
from xti.domain.organization_scope import OrganizationScope
FAMILIES = ('brand', 'surface', 'username', 'threatcluster', 'ransomlook', 'collection', 'notices')


@dataclass(frozen=True, slots=True)
class PeriodicWindow:
    start_at: str
    end_at: str
    days: int


@dataclass(frozen=True, slots=True)
class PeriodicScope:
    domain: str | None =  None
    organization_id: str | None = None


@dataclass(frozen=True, slots=True)
class PeriodicValueChange:
    """Stored before/after values; None means no corresponding observation."""

    field: str
    before: str | int | bool | tuple[str, ...] | None
    after: str | int | bool | tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class PeriodicChangeEvidence:
    family: str
    source: str
    record_id: str
    action: str
    recorded_at: str
    value: str
    status: str =  'complete'
    asset_value: str | None =  None
    watch_id: str | None =  None
    run_id: str | None =  None
    reference: str | None =  None
    source_run_id: str | None =  None
    previous_run_id: str | None =  None
    definition_sha256: str | None =  None
    source_observed_at: str | None =  None
    is_baseline: bool =  False
    rule_version: str | None =  None
    target_record_id: str | None =  None
    previous_record_id: str | None = None
    evidence_type: str | None = None
    value_changes: tuple[PeriodicValueChange, ...] = ()
    commands: tuple[tuple[str, ...], ...] = ()
    shared_scope: bool = False
    evidence_note: str | None = None
    source_classification: tuple[tuple[str, bool], ...] = ()
    source_attribution: str | None = None
    source_license: str | None = None


@dataclass(frozen=True, slots=True)
class PeriodicSection:
    family: str
    changes: tuple[PeriodicChangeEvidence, ...]
    baselines: tuple[PeriodicChangeEvidence, ...]
    failures: tuple[PeriodicChangeEvidence, ...]
    total_change_count: int
    total_baseline_count: int
    total_failure_count: int
    omitted_count: int
    offset: int = 0


@dataclass(frozen=True, slots=True)
class PeriodicSourceCoverage:
    family: str
    source: str
    scope_kind: str
    scope_id: str
    last_run_id: str | None
    last_status: str | None
    last_recorded_at: str | None
    last_complete_run_id: str | None
    last_complete_recorded_at: str | None
    window_run_count: int
    complete_count: int
    partial_count: int
    failed_count: int
    interrupted_count: int
    coverage_state: str


@dataclass(frozen=True, slots=True)
class PeriodicChangesSnapshot:
    sections: tuple[PeriodicSection, ...]
    coverage: tuple[PeriodicSourceCoverage, ...]
    schema_version: int
    notes: tuple[str, ...] =  ()
    coverage_total_count: int =  0
    coverage_omitted_count: int =  0
    organization_scope: OrganizationScope | None = None
    offset: int = 0


@dataclass(frozen=True, slots=True)
class PeriodicChangesReport:
    window: PeriodicWindow
    scope: PeriodicScope
    sections: tuple[PeriodicSection, ...]
    coverage: tuple[PeriodicSourceCoverage, ...]
    generated_at: str
    notes: tuple[str, ...]
    schema_version: int
    coverage_total_count: int =  0
    coverage_omitted_count: int =  0
    organization_scope: OrganizationScope | None = None
    offset: int = 0


def periodic_time(value: str) -> datetime:
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 64:
            raise ValueError('invalid timestamp')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('timezone required')
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError('Dönem raporu zamanı saat dilimi bilgili olmalı.') from error


def in_period(value: str, window: PeriodicWindow) -> bool:
    return periodic_time(window.start_at) <= periodic_time(value) < periodic_time(window.end_at)

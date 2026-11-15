"""Summary of bounded foreground group execution; persistent runs stay separate."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MentionGroupMonitorCycle:
    cycle: int
    status: str
    reason: str | None
    run_id: str | None
    daily_queries_used: int
    next_due_at: str | None


@dataclass(frozen=True, slots=True)
class MentionGroupMonitorReport:
    group_id: str
    planned_cycles: int
    completed_cycles: int
    started_at: str
    finished_at: str
    elapsed_seconds: float
    stop_reason: str
    cycles: tuple[MentionGroupMonitorCycle, ...]

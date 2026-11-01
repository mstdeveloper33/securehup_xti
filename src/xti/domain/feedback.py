"""Read-only summaries of human review activity, never ground-truth labels."""

from dataclasses import dataclass


class FeedbackError(RuntimeError):
    """A repository returned a contradictory feedback snapshot."""


@dataclass(frozen=True, slots=True)
class RuleFeedback:
    rule_version: str
    total_findings: int
    reviewed_findings: int
    unreviewed_findings: int
    suspicious: int
    dismissed: int
    uncertain: int


@dataclass(frozen=True, slots=True)
class FeedbackSnapshot:
    finding_counts: dict[str, int]
    review_event_count: int
    revisited_finding_count: int
    rules: tuple[RuleFeedback, ...]


@dataclass(frozen=True, slots=True)
class FeedbackReport:
    total_findings: int
    reviewed_findings: int
    unreviewed_findings: int
    review_coverage_percent: float
    decision_counts: dict[str, int]
    review_event_count: int
    revisited_finding_count: int
    rules: tuple[RuleFeedback, ...]
    notes: tuple[str, ...]

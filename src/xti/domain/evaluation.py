"""Immutable records for transparent, offline matching-quality evaluation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    id: str
    category: str
    asset: str
    domain: str
    expected: str
    baseline: str
    note: str


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    version: str
    sha256: str
    description: str
    cases: tuple[EvaluationCase, ...]


@dataclass(frozen=True, slots=True)
class EvaluationGap:
    case_id: str
    category: str
    asset: str
    input_domain: str
    canonical_domain: str
    expected: str
    predicted: str
    baseline: str
    note: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvaluationCategory:
    category: str
    total: int
    correct: int
    false_positive: int
    false_negative: int


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    dataset_version: str
    dataset_sha256: str
    rule_version: str
    total: int
    expected_review: int
    expected_ignore: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    precision_percent: float
    recall_percent: float
    false_positive_rate_percent: float
    accuracy_percent: float
    known_gap_count: int
    baseline_change_count: int
    categories: tuple[EvaluationCategory, ...]
    quality_gaps: tuple[EvaluationGap, ...]
    baseline_changes: tuple[EvaluationGap, ...]
    notes: tuple[str, ...]

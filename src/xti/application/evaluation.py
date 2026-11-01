"""Measure candidate rules on a pinned labelled set without storage or network access."""

from collections import defaultdict

from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.evaluation import (
    EvaluationCategory,
    EvaluationDataset,
    EvaluationGap,
    EvaluationReport,
)
from xti.domain.matching import DomainMatcher


_LABELS = frozenset({"review", "ignore"})


def _text(value: str, name: str, maximum: int) -> str:
    if (
        not isinstance(value, str) or value != value.strip() or not value
        or len(value) > maximum or not value.isprintable()
    ):
        raise ValidationError(f"Değerlendirme örneğinin {name} alanı geçersiz.")
    return value


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        raise ValidationError("Değerlendirme kümesi iki etiketi de içermeli.")
    return round(100 * numerator / denominator, 2)


class EvaluationService:
    def __init__(self, matcher: DomainMatcher) -> None:
        self.matcher = matcher

    def run(self, dataset: EvaluationDataset) -> EvaluationReport:
        if not dataset.cases:
            raise ValidationError("Değerlendirme kümesi boş olamaz.")
        _text(dataset.version, "sürüm", 64)
        _text(dataset.description, "açıklama", 1000)
        if (
            not isinstance(dataset.sha256, str) or len(dataset.sha256) != 64
            or any(character not in "0123456789abcdef" for character in dataset.sha256)
        ):
            raise ValidationError("Değerlendirme kümesinin özeti geçersiz.")
        seen: set[str] = set()
        outcomes = []
        counts = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
        category_counts = defaultdict(lambda: {"total": 0, "correct": 0, "fp": 0, "fn": 0})

        for case in dataset.cases:
            _text(case.id, "kimlik", 64)
            _text(case.category, "kategori", 64)
            _text(case.note, "not", 1000)
            if case.id in seen:
                raise ValidationError("Değerlendirme kümesinde tekrarlı örnek kimliği var.")
            seen.add(case.id)
            if case.expected not in _LABELS or case.baseline not in _LABELS:
                raise ValidationError("Değerlendirme örneğinin etiketi geçersiz.")
            asset_value = normalize_domain(case.asset)
            if self.matcher.unicode_security is not None:
                candidate = self.matcher.unicode_security.to_ascii(case.domain)
            else:
                candidate = normalize_domain(case.domain)
            result = self.matcher.match(
                Asset(f"evaluation:{case.id}", asset_value, "1970-01-01T00:00:00+00:00"),
                candidate,
            )
            predicted = "review" if result is not None else "ignore"
            correct = predicted == case.expected
            if case.expected == "review":
                key = "tp" if predicted == "review" else "fn"
            else:
                key = "tn" if predicted == "ignore" else "fp"
            counts[key] += 1
            group = category_counts[case.category]
            group["total"] += 1
            group["correct"] += int(correct)
            group["fp"] += int(key == "fp")
            group["fn"] += int(key == "fn")
            outcomes.append(EvaluationGap(
                case_id=case.id,
                category=case.category,
                asset=asset_value,
                input_domain=case.domain,
                canonical_domain=candidate,
                expected=case.expected,
                predicted=predicted,
                baseline=case.baseline,
                note=case.note,
                reasons=result.reasons if result is not None else (),
            ))

        positives = counts["tp"] + counts["fn"]
        negatives = counts["tn"] + counts["fp"]
        predicted_positives = counts["tp"] + counts["fp"]
        if not positives or not negatives or not predicted_positives:
            raise ValidationError(
                "Değerlendirme kümesi review/ignore ve üretilen aday örneklerini içermeli."
            )
        quality_gaps = tuple(item for item in outcomes if item.predicted != item.expected)
        baseline_changes = tuple(item for item in outcomes if item.predicted != item.baseline)
        categories = tuple(
            EvaluationCategory(
                category=name,
                total=value["total"],
                correct=value["correct"],
                false_positive=value["fp"],
                false_negative=value["fn"],
            )
            for name, value in sorted(category_counts.items())
        )
        return EvaluationReport(
            dataset_version=dataset.version,
            dataset_sha256=dataset.sha256,
            rule_version=self.matcher.rule_version,
            total=len(outcomes),
            expected_review=positives,
            expected_ignore=negatives,
            true_positive=counts["tp"],
            true_negative=counts["tn"],
            false_positive=counts["fp"],
            false_negative=counts["fn"],
            precision_percent=_percent(counts["tp"], predicted_positives),
            recall_percent=_percent(counts["tp"], positives),
            false_positive_rate_percent=_percent(counts["fp"], negatives),
            accuracy_percent=_percent(counts["tp"] + counts["tn"], len(outcomes)),
            known_gap_count=sum(
                item.predicted != item.expected and item.predicted == item.baseline
                for item in outcomes
            ),
            baseline_change_count=len(baseline_changes),
            categories=categories,
            quality_gaps=quality_gaps,
            baseline_changes=baseline_changes,
            notes=(
                "Bu sonuç sürümlü sentetik örnek kümesine aittir; gerçek internet doğruluğu değildir.",
                "review etiketi insan incelemesi beklentisidir; phishing veya kötü niyet kararı değildir.",
                "Bilinen açıklar görünür tutulur; baseline değişimi kural davranışının ayrıca incelenmesini gerektirir.",
            ),
        )

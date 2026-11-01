"""Human review lifecycle for current cross-source ransomware comparisons."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from xti.application.ransomware_source_comparison import (
    RansomwareSourceComparisonService,
)
from xti.domain.assets import ValidationError
from xti.domain.ransomware_source_comparison import (
    RansomwareSourceComparisonReport,
    RansomwareSourceReviewDetails,
    RansomwareSourceReviewMutation,
    normalize_ransomware_source_comparison_id,
    normalize_ransomware_source_review_decision,
    normalize_ransomware_source_review_reason,
)
from xti.ports.ransomware_source_reviews import RansomwareSourceReviewRepository


class RansomwareSourceReviewService:
    def __init__(
        self,
        repository: RansomwareSourceReviewRepository,
        comparison_service: RansomwareSourceComparisonService,
        *, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.comparison_service = comparison_service
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValidationError("Kaynak karşılaştırma karar zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError(
                "Kaynak karşılaştırma karar olayı sınırı 1–500 arasında olmalı."
            )
        return value

    def decide(
        self, comparison_id: str, *, decision: str, reason: str,
    ) -> RansomwareSourceReviewMutation:
        comparison_id = normalize_ransomware_source_comparison_id(comparison_id)
        decision = normalize_ransomware_source_review_decision(decision)
        reason = normalize_ransomware_source_review_reason(reason)
        recorded_at = self._now()
        evidence = self.comparison_service.find(comparison_id)
        return self.repository.record(
            evidence, decision=decision, reason=reason, recorded_at=recorded_at,
        )

    def show(
        self, comparison_id: str, *, event_limit: int = 100,
    ) -> RansomwareSourceReviewDetails:
        comparison_id = normalize_ransomware_source_comparison_id(comparison_id)
        return self.repository.details(
            comparison_id, event_limit=self._limit(event_limit),
        )

    def decorate(
        self, report: RansomwareSourceComparisonReport,
    ) -> RansomwareSourceComparisonReport:
        states = {state.comparison_id: state for state in self.repository.states()}
        return replace(
            report,
            comparisons=tuple(
                replace(value, current_review=states.get(value.id))
                for value in report.comparisons
            ),
        )

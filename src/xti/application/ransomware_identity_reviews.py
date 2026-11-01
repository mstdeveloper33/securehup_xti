"""Validated human decisions for ransomware identity-change candidates."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from xti.application.ransomware_watch_identity_candidates import (
    RansomwareWatchIdentityCandidateService,
)
from xti.domain.assets import ValidationError
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.ransomware_watches import (
    RansomwareIdentityReviewDetails,
    RansomwareIdentityReviewMutation,
    RansomwareWatchIdentityCandidateReport,
    normalize_ransomware_identity_review_decision,
    normalize_ransomware_identity_review_reason,
)
from xti.ports.ransomware_identity_reviews import RansomwareIdentityReviewRepository


class RansomwareIdentityReviewService:
    def __init__(
        self,
        repository: RansomwareIdentityReviewRepository,
        candidate_service: RansomwareWatchIdentityCandidateService,
        *, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.candidate_service = candidate_service
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Kimlik adayı karar zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _limit(value: int) -> int:
        if type(value) is not int or not 1 <= value <= 500:
            raise ValidationError("Kimlik adayı karar olayı sınırı 1–500 arasında olmalı.")
        return value

    def decide(
        self, watch_id: str, candidate_id: str, *, decision: str, reason: str,
    ) -> RansomwareIdentityReviewMutation:
        watch_id = normalize_knowledge_id(watch_id, field="ransomware izleme kimliği")
        candidate_id = normalize_knowledge_id(
            candidate_id, field="ransomware kimlik adayı kimliği",
        )
        candidate = self.candidate_service.find(watch_id, candidate_id)
        return self.repository.record(
            candidate,
            decision=normalize_ransomware_identity_review_decision(decision),
            reason=normalize_ransomware_identity_review_reason(reason),
            recorded_at=self._now(),
        )

    def show(
        self, candidate_id: str, *, event_limit: int = 100,
    ) -> RansomwareIdentityReviewDetails:
        return self.repository.details(
            normalize_knowledge_id(
                candidate_id, field="ransomware kimlik adayı kimliği",
            ),
            event_limit=self._limit(event_limit),
        )

    def decorate(
        self, report: RansomwareWatchIdentityCandidateReport,
    ) -> RansomwareWatchIdentityCandidateReport:
        states = {
            state.candidate_id: state
            for state in self.repository.states(report.watch.id)
        }
        return replace(
            report,
            candidates=tuple(
                replace(candidate, current_review=states.get(candidate.id))
                for candidate in report.candidates
            ),
        )

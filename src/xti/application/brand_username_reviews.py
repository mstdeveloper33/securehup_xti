"""Validated human review of exact social profile observations."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

from xti.application.brand_username import (
    SHERLOCK_SUPPORTED_PLATFORMS,
    SUPPORTED_PLATFORMS,
)
from xti.domain.assets import ValidationError
from xti.domain.brand_username_reviews import (
    BrandUsernameReviewDetails,
    BrandUsernameReviewMutation,
    brand_username_review_candidate_id,
    normalize_brand_username_review_decision,
    normalize_brand_username_review_reason,
)
from xti.domain.brand_username_watches import BrandUsernameWatchRunReport
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.ports.brand_username_reviews import BrandUsernameReviewRepository


class BrandUsernameReviewService:
    def __init__(
        self,
        repository: BrandUsernameReviewRepository,
        *, clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Profil kararı zamanı geçersiz.")
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _watch_id(value: str) -> str:
        return normalize_knowledge_id(value, field="Sosyal kullanıcı adı izleme kimliği")

    @staticmethod
    def _platform(value: str) -> str:
        if (
            not isinstance(value, str)
            or value not in SUPPORTED_PLATFORMS + SHERLOCK_SUPPORTED_PLATFORMS
        ):
            raise ValidationError("Desteklenen tam platform adı gerekli.")
        return value

    def decide(
        self, watch_id: str, platform: str, *, decision: str, reason: str,
    ) -> BrandUsernameReviewMutation:
        candidate = self.repository.current_candidate(
            self._watch_id(watch_id), self._platform(platform),
        )
        return self.repository.record(
            candidate,
            decision=normalize_brand_username_review_decision(decision),
            reason=normalize_brand_username_review_reason(reason),
            recorded_at=self._now(),
        )

    def show(
        self, candidate_id: str, *, event_limit: int = 100,
    ) -> BrandUsernameReviewDetails:
        if type(event_limit) is not int or not 1 <= event_limit <= 500:
            raise ValidationError("Profil kararı olay sınırı 1–500 arasında olmalı.")
        return self.repository.details(
            normalize_knowledge_id(candidate_id, field="Profil inceleme adayı kimliği"),
            event_limit=event_limit,
        )

    def decorate(
        self, report: BrandUsernameWatchRunReport,
    ) -> BrandUsernameWatchRunReport:
        states = {
            state.candidate_id: state for state in self.repository.states(report.watch.id)
        }
        items = []
        for item in report.items:
            candidate_id = None
            if item.status == "found_unverified":
                candidate_id = brand_username_review_candidate_id(
                    watch_id=report.watch.id,
                    definition_sha256=report.run.definition_sha256,
                    platform=item.platform,
                    state_sha256=item.state_sha256,
                )
            items.append(replace(item, current_review=states.get(candidate_id)))
        return replace(report, items=tuple(items))

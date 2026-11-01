"""Human decisions bound to an exact observed social profile state."""

from dataclasses import dataclass
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from xti.domain.assets import ValidationError


BRAND_USERNAME_REVIEW_DECISIONS = frozenset({
    "known_official",
    "possible_impersonation",
    "uncertain",
})


def normalize_brand_username_review_decision(value: str) -> str:
    if not isinstance(value, str) or value not in BRAND_USERNAME_REVIEW_DECISIONS:
        raise ValidationError(
            "Profil kararı known_official, possible_impersonation veya uncertain olmalı."
        )
    return value


def normalize_brand_username_review_reason(value: str) -> str:
    if not isinstance(value, str):
        raise ValidationError("Profil kararı gerekçesi gerekli.")
    normalized = " ".join(value.strip().split())
    if (
        not 2 <= len(normalized) <= 500
        or any(not character.isprintable() for character in normalized)
    ):
        raise ValidationError("Profil kararı gerekçesi 2–500 görünür karakter olmalı.")
    return normalized


def brand_username_review_candidate_id(
    *, watch_id: str, definition_sha256: str, platform: str, state_sha256: str,
) -> str:
    canonical = json.dumps(
        [watch_id, definition_sha256, platform, state_sha256],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return str(uuid5(NAMESPACE_URL, "xti:brand-username-review:" + canonical))


@dataclass(frozen=True, slots=True)
class BrandUsernameReviewState:
    candidate_id: str
    decision: str
    reason: str
    reviewed_at: str
    event_count: int
    state_sha256: str


@dataclass(frozen=True, slots=True)
class BrandUsernameReviewCandidate:
    id: str
    watch_id: str
    run_id: str
    run_sequence: int
    definition_sha256: str
    username: str
    platform: str
    profile_url: str
    state_sha256: str
    observed_at: str
    current_review: BrandUsernameReviewState | None = None


def brand_username_review_candidate_json(
    candidate: BrandUsernameReviewCandidate,
) -> str:
    payload = {
        "definition_sha256": candidate.definition_sha256,
        "id": candidate.id,
        "observed_at": candidate.observed_at,
        "platform": candidate.platform,
        "profile_url": candidate.profile_url,
        "run_id": candidate.run_id,
        "run_sequence": candidate.run_sequence,
        "state_sha256": candidate.state_sha256,
        "username": candidate.username,
        "watch_id": candidate.watch_id,
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def brand_username_review_candidate_sha256(
    candidate: BrandUsernameReviewCandidate,
) -> str:
    return hashlib.sha256(
        brand_username_review_candidate_json(candidate).encode("ascii")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class BrandUsernameReviewEvent:
    sequence: int
    id: str
    candidate_id: str
    watch_id: str
    run_id: str
    decision: str
    reason: str
    recorded_at: str
    previous_event_id: str | None
    candidate_sha256: str


@dataclass(frozen=True, slots=True)
class BrandUsernameReviewDetails:
    candidate: BrandUsernameReviewCandidate
    current: BrandUsernameReviewState
    events: tuple[BrandUsernameReviewEvent, ...]
    total_event_count: int


@dataclass(frozen=True, slots=True)
class BrandUsernameReviewMutation:
    action: str
    details: BrandUsernameReviewDetails
    notification_id: str | None = None
    notification_created: bool = False


@dataclass(frozen=True, slots=True)
class BrandUsernameReviewNotificationEvidence:
    notification_id: str
    watch_name: str
    candidate: BrandUsernameReviewCandidate
    trigger: BrandUsernameReviewEvent
    current: BrandUsernameReviewState

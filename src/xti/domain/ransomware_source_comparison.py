"""Explainable comparisons and human review state across ransomware sources."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import unicodedata

from xti.domain.assets import ValidationError
from xti.domain.ransomlook_ransomware import RansomLookClaim, RansomLookClaimRun
from xti.domain.ransomware_claims import RansomwareClaim, RansomwareClaimRun


RANSOMWARE_SOURCE_COMPARISON_BASES = frozenset({
    "organization_group_time",
    "organization_group",
    "organization_time",
})
RANSOMWARE_SOURCE_REVIEW_DECISIONS = frozenset({
    "possible_same", "different", "uncertain",
})


def _visible_text(value: str, *, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} gerekli.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if (
        not minimum <= len(normalized) <= maximum
        or any(not character.isprintable() for character in normalized)
    ):
        raise ValidationError(
            f"{field} {minimum}–{maximum} görünür karakter arasında olmalı."
        )
    return normalized


def normalize_ransomware_source_review_decision(value: str) -> str:
    if not isinstance(value, str) or value not in RANSOMWARE_SOURCE_REVIEW_DECISIONS:
        raise ValidationError(
            "Kaynak karşılaştırma kararı possible_same, different veya uncertain olmalı."
        )
    return value


def normalize_ransomware_source_review_reason(value: str) -> str:
    return _visible_text(
        value, field="Kaynak karşılaştırma karar gerekçesi", minimum=2, maximum=500,
    )


def ransomware_source_text_key(value: str) -> str:
    """Return a deterministic comparison key without fuzzy inference."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def ransomware_source_comparison_id(
    *, threatcluster_claim_id: str, ransomlook_claim_id: str,
) -> str:
    canonical = json.dumps(
        {
            "ransomlook_claim_id": ransomlook_claim_id,
            "threatcluster_claim_id": threatcluster_claim_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def normalize_ransomware_source_comparison_id(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValidationError("Kaynak karşılaştırma kimliği geçersiz.")
    return value


@dataclass(frozen=True, slots=True)
class RansomwareSourceReviewState:
    comparison_id: str
    decision: str
    reason: str
    reviewed_at: str
    event_count: int


@dataclass(frozen=True, slots=True)
class RansomwareSourceComparison:
    id: str
    basis: str
    common_evidence: tuple[str, ...]
    different_evidence: tuple[str, ...]
    threatcluster_claim: RansomwareClaim
    ransomlook_claim: RansomLookClaim
    current_review: RansomwareSourceReviewState | None = None


def compare_ransomware_source_claims(
    threatcluster_claim: RansomwareClaim,
    ransomlook_claim: RansomLookClaim,
) -> RansomwareSourceComparison | None:
    """Compare shared source fields; never infer identity from approximate text."""
    same_organization = (
        ransomware_source_text_key(threatcluster_claim.victim)
        == ransomware_source_text_key(ransomlook_claim.victim)
    )
    if not same_organization:
        return None
    same_group = (
        ransomware_source_text_key(threatcluster_claim.group)
        == ransomware_source_text_key(ransomlook_claim.group)
    )
    same_time = threatcluster_claim.discovered_at == ransomlook_claim.discovered_at
    if not (same_group or same_time):
        return None

    common = ["organization"]
    different = []
    if same_group:
        common.append("group")
    else:
        different.append("group")
    if same_time:
        common.append("discovered_at")
    else:
        different.append("discovered_at")
    basis = (
        "organization_group_time" if same_group and same_time
        else "organization_group" if same_group
        else "organization_time"
    )
    return RansomwareSourceComparison(
        id=ransomware_source_comparison_id(
            threatcluster_claim_id=threatcluster_claim.id,
            ransomlook_claim_id=ransomlook_claim.id,
        ),
        basis=basis,
        common_evidence=tuple(common),
        different_evidence=tuple(different),
        threatcluster_claim=threatcluster_claim,
        ransomlook_claim=ransomlook_claim,
    )


@dataclass(frozen=True, slots=True)
class RansomwareSourceComparisonEvidence:
    comparison: RansomwareSourceComparison
    threatcluster_run_id: str
    ransomlook_run_id: str


def ransomware_source_comparison_evidence_json(
    evidence: RansomwareSourceComparisonEvidence,
) -> str:
    comparison = evidence.comparison
    threatcluster = comparison.threatcluster_claim
    ransomlook = comparison.ransomlook_claim
    payload = {
        "comparison": {
            "basis": comparison.basis,
            "common_evidence": comparison.common_evidence,
            "different_evidence": comparison.different_evidence,
            "id": comparison.id,
            "ransomlook_claim": {
                "discovered_at": ransomlook.discovered_at,
                "group": ransomlook.group,
                "id": ransomlook.id,
                "victim": ransomlook.victim,
            },
            "threatcluster_claim": {
                "country": threatcluster.country,
                "delisted_at": threatcluster.delisted_at,
                "discovered_at": threatcluster.discovered_at,
                "first_party": threatcluster.first_party,
                "group": threatcluster.group,
                "id": threatcluster.id,
                "last_seen_at": threatcluster.last_seen_at,
                "sector": threatcluster.sector,
                "source_post_available": threatcluster.source_post_available,
                "status": threatcluster.status,
                "victim": threatcluster.victim,
                "website": threatcluster.website,
            },
        },
        "ransomlook_run_id": evidence.ransomlook_run_id,
        "threatcluster_run_id": evidence.threatcluster_run_id,
    }
    return json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    )


def ransomware_source_comparison_evidence_sha256(
    evidence: RansomwareSourceComparisonEvidence,
) -> str:
    return hashlib.sha256(
        ransomware_source_comparison_evidence_json(evidence).encode("ascii")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class RansomwareSourceReviewEvent:
    sequence: int
    id: str
    comparison_id: str
    decision: str
    reason: str
    recorded_at: str
    previous_event_id: str | None
    evidence_sha256: str


@dataclass(frozen=True, slots=True)
class RansomwareSourceReviewDetails:
    evidence: RansomwareSourceComparisonEvidence
    threatcluster_run: RansomwareClaimRun
    ransomlook_run: RansomLookClaimRun
    current: RansomwareSourceReviewState
    events: tuple[RansomwareSourceReviewEvent, ...]
    total_event_count: int


@dataclass(frozen=True, slots=True)
class RansomwareSourceReviewMutation:
    action: str
    details: RansomwareSourceReviewDetails


@dataclass(frozen=True, slots=True)
class RansomwareSourceComparisonReport:
    threatcluster_run: RansomwareClaimRun
    ransomlook_run: RansomLookClaimRun
    threatcluster_claim_count: int
    ransomlook_claim_count: int
    total_comparison_count: int
    displayed_count: int
    has_more: bool
    comparisons: tuple[RansomwareSourceComparison, ...]
    notes: tuple[str, ...]

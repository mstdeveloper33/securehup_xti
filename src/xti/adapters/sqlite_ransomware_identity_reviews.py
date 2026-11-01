"""Append-only SQLite decisions for ransomware identity-change candidates."""

from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import unicodedata
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.ransomware_claims import RansomwareClaim
from xti.domain.ransomware_watches import (
    RansomwareIdentityReviewDetails,
    RansomwareIdentityReviewEvent,
    RansomwareIdentityReviewMutation,
    RansomwareIdentityReviewState,
    RansomwareWatchIdentityCandidate,
    match_ransomware_claim,
    normalize_ransomware_identity_review_decision,
    normalize_ransomware_identity_review_reason,
    ransomware_claim_website_host,
    ransomware_identity_candidate_id,
    ransomware_identity_candidate_json,
    ransomware_identity_candidate_sha256,
)


_SELECT = (
    "sequence, id, candidate_id, watch_id, transition_source_run_id, "
    "older_claim_id, newer_claim_id, candidate_json, candidate_sha256, "
    "decision, reason, recorded_at, previous_event_id"
)
_MAX_EVENTS = 100_000
_CLAIM_FIELDS = {
    "id", "group", "victim", "country", "sector", "discovered_at", "status",
    "website", "last_seen_at", "delisted_at", "first_party",
    "source_post_available",
}
_CANDIDATE_FIELDS = {
    "id", "older_claim", "newer_claim", "transition_source_sequence",
    "transition_source_run_id", "transition_observed_at",
    "successful_snapshot_gap", "older_matches_watch", "newer_matches_watch",
    "common_evidence", "changed_identity_fields",
}
_EVIDENCE_ORDER = ("group", "victim", "discovered_at", "website")
_IDENTITY_ORDER = ("group", "victim", "discovered_at")


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid UUID")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("Non-canonical UUID")
    return normalized


def _sha256(value: object) -> str:
    if (
        not isinstance(value, str) or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("Invalid SHA-256")
    return value


def _timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    normalized = normalize_cti_timestamp(value, field="kimlik adayı zamanı")
    if normalized != value:
        raise ValueError("Non-canonical timestamp")
    return normalized


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON number")


def _text_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _comparison(
    older: RansomwareClaim, newer: RansomwareClaim,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    old = {
        "group": _text_key(older.group), "victim": _text_key(older.victim),
        "discovered_at": older.discovered_at,
        "website": ransomware_claim_website_host(older.website),
    }
    new = {
        "group": _text_key(newer.group), "victim": _text_key(newer.victim),
        "discovered_at": newer.discovered_at,
        "website": ransomware_claim_website_host(newer.website),
    }
    common = tuple(
        field for field in _EVIDENCE_ORDER
        if old[field] is not None and old[field] == new[field]
    )
    changed = tuple(field for field in _IDENTITY_ORDER if old[field] != new[field])
    return common, changed


class SQLiteRansomwareIdentityReviewRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _claim(value: object) -> RansomwareClaim:
        if not isinstance(value, dict) or set(value) != _CLAIM_FIELDS:
            raise ValueError("Invalid candidate claim")
        claim = RansomwareClaim(**value)
        return SQLiteRansomwareClaimRepository._claim(claim)

    @classmethod
    def _candidate_json(cls, value: object) -> RansomwareWatchIdentityCandidate:
        if not isinstance(value, str) or len(value.encode("utf-8")) > 20_000:
            raise ValueError("Invalid candidate JSON")
        payload = json.loads(
            value, object_pairs_hook=_object, parse_constant=_constant,
        )
        if not isinstance(payload, dict) or set(payload) != _CANDIDATE_FIELDS:
            raise ValueError("Invalid candidate fields")
        common = payload["common_evidence"]
        changed = payload["changed_identity_fields"]
        if not isinstance(common, list) or not isinstance(changed, list):
            raise ValueError("Invalid candidate evidence")
        candidate = RansomwareWatchIdentityCandidate(
            id=_uuid(payload["id"]),
            older_claim=cls._claim(payload["older_claim"]),
            newer_claim=cls._claim(payload["newer_claim"]),
            transition_source_sequence=payload["transition_source_sequence"],
            transition_source_run_id=_uuid(payload["transition_source_run_id"]),
            transition_observed_at=_timestamp(payload["transition_observed_at"]),
            successful_snapshot_gap=payload["successful_snapshot_gap"],
            older_matches_watch=payload["older_matches_watch"],
            newer_matches_watch=payload["newer_matches_watch"],
            common_evidence=tuple(common), changed_identity_fields=tuple(changed),
        )
        if (
            type(candidate.transition_source_sequence) is not int
            or candidate.transition_source_sequence < 1
            or type(candidate.successful_snapshot_gap) is not int
            or candidate.successful_snapshot_gap not in {0, 1}
            or type(candidate.older_matches_watch) is not bool
            or type(candidate.newer_matches_watch) is not bool
            or candidate.common_evidence != tuple(
                field for field in _EVIDENCE_ORDER if field in candidate.common_evidence
            )
            or len(candidate.common_evidence) < 2
            or candidate.changed_identity_fields != tuple(
                field for field in _IDENTITY_ORDER
                if field in candidate.changed_identity_fields
            )
            or not candidate.changed_identity_fields
            or ransomware_identity_candidate_json(candidate) != value
        ):
            raise ValueError("Invalid canonical candidate")
        return candidate

    @classmethod
    def _validate_candidate(
        cls, candidate: RansomwareWatchIdentityCandidate, *, watch, runs, items,
        complete_ordinals,
    ) -> RansomwareWatchIdentityCandidate:
        if not isinstance(candidate, RansomwareWatchIdentityCandidate):
            raise ValueError("Invalid candidate")
        candidate = replace(candidate, current_review=None)
        run = runs.get(candidate.transition_source_run_id)
        if (
            run is None or run.status != "complete"
            or run.sequence != candidate.transition_source_sequence
            or run.finished_at != candidate.transition_observed_at
            or candidate.id != ransomware_identity_candidate_id(
                watch_id=watch.id,
                older_claim_id=candidate.older_claim.id,
                newer_claim_id=candidate.newer_claim.id,
                transition_source_run_id=run.id,
            )
            or candidate.older_claim.id == candidate.newer_claim.id
        ):
            raise ValueError("Invalid candidate identity")
        common, changed = _comparison(candidate.older_claim, candidate.newer_claim)
        if (
            common != candidate.common_evidence
            or changed != candidate.changed_identity_fields
            or len(common) < 2 or not changed
        ):
            raise ValueError("Invalid candidate comparison")
        old_match = match_ransomware_claim(
            candidate.older_claim, kind=watch.kind, query_key=watch.query_key,
            match_mode=watch.match_mode,
        ) is not None
        new_match = match_ransomware_claim(
            candidate.newer_claim, kind=watch.kind, query_key=watch.query_key,
            match_mode=watch.match_mode,
        ) is not None
        if (
            (old_match, new_match) != (
                candidate.older_matches_watch, candidate.newer_matches_watch,
            )
            or not (old_match or new_match)
        ):
            raise ValueError("Invalid candidate watch relevance")
        new_items = [
            item for item in items
            if item.run_id == run.id and item.action == "added"
            and item.claim == candidate.newer_claim
        ]
        old_items = [
            item for item in items
            if item.action == "removed" and item.claim == candidate.older_claim
            and item.run_id in complete_ordinals
            and complete_ordinals[run.id] - complete_ordinals[item.run_id]
            == candidate.successful_snapshot_gap
        ]
        if len(new_items) != 1 or len(old_items) != 1:
            raise ValueError("Missing candidate source transition")
        return candidate

    @classmethod
    def _audit(cls, connection):
        runs_tuple, items = SQLiteRansomwareClaimRepository._audit(connection)
        watches, _, _, _, _ = SQLiteRansomwareWatchRepository._audit(connection)
        runs = {run.id: run for run in runs_tuple}
        complete_ordinals = {
            run.id: ordinal for ordinal, run in enumerate(
                (run for run in runs_tuple if run.status == "complete"), start=1,
            )
        }
        rows = connection.execute(
            f"SELECT {_SELECT} FROM ransomware_identity_review_events "
            "ORDER BY sequence LIMIT ?", (_MAX_EVENTS + 1,),
        ).fetchall()
        if len(rows) > _MAX_EVENTS:
            raise StorageError("Kimlik adayı karar geçmişi güvenli sınırı aşıyor.")
        records = []
        candidates: dict[str, RansomwareWatchIdentityCandidate] = {}
        watch_ids: dict[str, str] = {}
        try:
            for row in rows:
                if type(row[0]) is not int or row[0] < 1:
                    raise ValueError("Invalid sequence")
                event_id, candidate_id = _uuid(row[1]), _uuid(row[2])
                watch_id, run_id = _uuid(row[3]), _uuid(row[4])
                watch = watches.get(watch_id)
                if watch is None:
                    raise ValueError("Missing watch")
                candidate = cls._candidate_json(row[7])
                candidate = cls._validate_candidate(
                    candidate, watch=watch, runs=runs, items=items,
                    complete_ordinals=complete_ordinals,
                )
                candidate_sha = _sha256(row[8])
                if (
                    candidate.id != candidate_id
                    or candidate.transition_source_run_id != run_id
                    or candidate.older_claim.id != _sha256(row[5])
                    or candidate.newer_claim.id != _sha256(row[6])
                    or ransomware_identity_candidate_sha256(candidate) != candidate_sha
                ):
                    raise ValueError("Candidate columns mismatch")
                event = RansomwareIdentityReviewEvent(
                    sequence=row[0], id=event_id, candidate_id=candidate_id,
                    decision=normalize_ransomware_identity_review_decision(row[9]),
                    reason=normalize_ransomware_identity_review_reason(row[10]),
                    recorded_at=_timestamp(row[11]),
                    previous_event_id=(
                        _uuid(row[12]) if row[12] is not None else None
                    ),
                    candidate_sha256=candidate_sha,
                )
                if datetime.fromisoformat(event.recorded_at) < datetime.fromisoformat(
                    candidate.transition_observed_at
                ):
                    raise ValueError("Decision predates candidate")
                existing = candidates.get(candidate_id)
                if existing is not None and ransomware_identity_candidate_json(
                    existing
                ) != ransomware_identity_candidate_json(candidate):
                    raise ValueError("Candidate snapshot changed")
                candidates[candidate_id] = candidate
                watch_ids[candidate_id] = watch_id
                records.append(event)
        except (TypeError, ValueError, ValidationError, OverflowError, json.JSONDecodeError) as error:
            raise StorageError(
                "Kimlik adayı karar geçmişi bozuk; işlem durduruldu."
            ) from error
        if len({event.sequence for event in records}) != len(records):
            raise StorageError("Kimlik adayı karar sırası bozuk; işlem durduruldu.")
        by_candidate: dict[str, list[RansomwareIdentityReviewEvent]] = {
            candidate_id: [] for candidate_id in candidates
        }
        for event in records:
            by_candidate[event.candidate_id].append(event)
        for candidate_id, history in by_candidate.items():
            for index, event in enumerate(history):
                expected_previous = history[index - 1].id if index else None
                if event.previous_event_id != expected_previous:
                    raise StorageError(
                        "Kimlik adayı karar zinciri bozuk; işlem durduruldu."
                    )
                if index and datetime.fromisoformat(
                    history[index - 1].recorded_at
                ) > datetime.fromisoformat(event.recorded_at):
                    raise StorageError(
                        "Kimlik adayı karar zamanı bozuk; işlem durduruldu."
                    )
                if event.candidate_sha256 != history[0].candidate_sha256:
                    raise StorageError(
                        "Kimlik adayı karar kanıtı değişmiş; işlem durduruldu."
                    )
        return watches, runs, items, candidates, watch_ids, tuple(records), by_candidate

    @staticmethod
    def _state(
        candidate_id: str, history: list[RansomwareIdentityReviewEvent],
    ) -> RansomwareIdentityReviewState:
        latest = history[-1]
        return RansomwareIdentityReviewState(
            candidate_id=candidate_id, decision=latest.decision,
            reason=latest.reason, reviewed_at=latest.recorded_at,
            event_count=len(history),
        )

    @classmethod
    def _details(
        cls, candidate_id: str, candidates, by_candidate, *, event_limit: int,
    ) -> RansomwareIdentityReviewDetails:
        candidate = candidates.get(candidate_id)
        history = by_candidate.get(candidate_id)
        if candidate is None or not history:
            raise ValidationError("Kayıtlı kimlik adayı kararı bulunamadı.")
        current = cls._state(candidate_id, history)
        return RansomwareIdentityReviewDetails(
            candidate=replace(candidate, current_review=current), current=current,
            events=tuple(history[-event_limit:]), total_event_count=len(history),
        )

    def record(self, candidate, *, decision, reason, recorded_at):
        decision = normalize_ransomware_identity_review_decision(decision)
        reason = normalize_ransomware_identity_review_reason(reason)
        try:
            recorded_at = _timestamp(recorded_at)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("Kimlik adayı karar zamanı geçersiz.") from error
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                watches, runs, items, candidates, _, _, by_candidate = self._audit(
                    connection
                )
                if not isinstance(candidate, RansomwareWatchIdentityCandidate):
                    raise ValidationError("Geçerli bir kimlik adayı gerekli.")
                candidate = replace(candidate, current_review=None)
                matching_watch_ids = [
                    watch.id for watch in watches.values()
                    if candidate.id == ransomware_identity_candidate_id(
                            watch_id=watch.id,
                            older_claim_id=candidate.older_claim.id,
                            newer_claim_id=candidate.newer_claim.id,
                            transition_source_run_id=candidate.transition_source_run_id,
                        )
                ]
                if len(matching_watch_ids) != 1:
                    raise ValidationError("Kimlik adayına bağlı izleme bulunamadı.")
                watch_id = matching_watch_ids[0]
                complete_ordinals = {
                    run.id: ordinal for ordinal, run in enumerate(
                        sorted(
                            (run for run in runs.values() if run.status == "complete"),
                            key=lambda value: value.sequence,
                        ), start=1,
                    )
                }
                candidate = self._validate_candidate(
                    candidate, watch=watches[watch_id], runs=runs, items=items,
                    complete_ordinals=complete_ordinals,
                )
                history = by_candidate.get(candidate.id, [])
                if history:
                    stored = candidates[candidate.id]
                    if ransomware_identity_candidate_json(stored) != ransomware_identity_candidate_json(
                        candidate
                    ):
                        raise StorageError(
                            "Kimlik adayının kayıtlı kanıtı güncel adayla uyuşmuyor."
                        )
                    latest = history[-1]
                    if datetime.fromisoformat(recorded_at) < datetime.fromisoformat(
                        latest.recorded_at
                    ):
                        raise ValidationError("Kimlik adayı karar zamanı önceki karardan eski.")
                    if latest.decision == decision and latest.reason == reason:
                        connection.commit()
                        return RansomwareIdentityReviewMutation(
                            "unchanged",
                            self._details(
                                candidate.id, candidates, by_candidate, event_limit=500,
                            ),
                        )
                candidate_json = ransomware_identity_candidate_json(candidate)
                candidate_sha = ransomware_identity_candidate_sha256(candidate)
                connection.execute(
                    "INSERT INTO ransomware_identity_review_events "
                    "(id, candidate_id, watch_id, transition_source_run_id, "
                    "older_claim_id, newer_claim_id, candidate_json, candidate_sha256, "
                    "decision, reason, recorded_at, previous_event_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid4()), candidate.id, watch_id,
                        candidate.transition_source_run_id, candidate.older_claim.id,
                        candidate.newer_claim.id, candidate_json, candidate_sha,
                        decision, reason, recorded_at,
                        history[-1].id if history else None,
                    ),
                )
                _, _, _, candidates, _, _, by_candidate = self._audit(connection)
                details = self._details(
                    candidate.id, candidates, by_candidate, event_limit=500,
                )
                connection.commit()
                return RansomwareIdentityReviewMutation(
                    "recorded" if len(details.events) == 1 else "updated", details,
                )
            except BaseException:
                connection.rollback()
                raise

    def details(self, candidate_id, *, event_limit):
        with self._storage._connection(readonly=True) as connection:
            _, _, _, candidates, _, _, by_candidate = self._audit(connection)
        return self._details(
            candidate_id, candidates, by_candidate, event_limit=event_limit,
        )

    def states(self, watch_id):
        with self._storage._connection(readonly=True) as connection:
            watches, _, _, _, watch_ids, _, by_candidate = self._audit(connection)
        if watch_id not in watches:
            raise ValidationError("Ransomware izlemesi bulunamadı.")
        return tuple(
            self._state(candidate_id, by_candidate[candidate_id])
            for candidate_id in sorted(
                (key for key, value in watch_ids.items() if value == watch_id),
                key=lambda key: by_candidate[key][-1].sequence,
            )
        )

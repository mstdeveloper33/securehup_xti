"""Append-only SQLite decisions for exact social profile observations."""

from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.adapters.sqlite_brand_username_watches import (
    SQLiteBrandUsernameWatchRepository,
    _profile_url,
    _sha256,
    _timestamp,
    _uuid,
)
from xti.domain.assets import ValidationError
from xti.domain.brand_username import ALL_PLATFORM_HOSTS, normalize_brand_username
from xti.domain.brand_username_reviews import (
    BrandUsernameReviewCandidate,
    BrandUsernameReviewDetails,
    BrandUsernameReviewEvent,
    BrandUsernameReviewMutation,
    BrandUsernameReviewNotificationEvidence,
    BrandUsernameReviewState,
    brand_username_review_candidate_id,
    brand_username_review_candidate_json,
    brand_username_review_candidate_sha256,
    normalize_brand_username_review_decision,
    normalize_brand_username_review_reason,
)


_SELECT = (
    "sequence, id, candidate_id, watch_id, run_id, platform, candidate_json, "
    "candidate_sha256, decision, reason, recorded_at, previous_event_id"
)
_NOTIFICATION_SELECT = (
    "sequence, id, candidate_id, review_event_id, event_type, origin, "
    "created_at, read_at"
)
_CANDIDATE_FIELDS = {
    "definition_sha256", "id", "observed_at", "platform", "profile_url",
    "run_id", "run_sequence", "state_sha256", "username", "watch_id",
}
_MAX_EVENTS = 100_000


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON number")


class SQLiteBrandUsernameReviewRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _candidate_json(value: object) -> BrandUsernameReviewCandidate:
        if not isinstance(value, str) or len(value.encode("utf-8")) > 10_000:
            raise ValueError("Invalid candidate JSON")
        payload = json.loads(value, object_pairs_hook=_object, parse_constant=_constant)
        if not isinstance(payload, dict) or set(payload) != _CANDIDATE_FIELDS:
            raise ValueError("Invalid candidate fields")
        platform = payload["platform"]
        if not isinstance(platform, str) or platform not in ALL_PLATFORM_HOSTS:
            raise ValueError("Invalid platform")
        candidate = BrandUsernameReviewCandidate(
            id=_uuid(payload["id"]),
            watch_id=_uuid(payload["watch_id"]),
            run_id=_uuid(payload["run_id"]),
            run_sequence=payload["run_sequence"],
            definition_sha256=_sha256(payload["definition_sha256"]),
            username=normalize_brand_username(payload["username"]),
            platform=platform,
            profile_url=_profile_url(platform, payload["profile_url"]),
            state_sha256=_sha256(payload["state_sha256"]),
            observed_at=_timestamp(
                payload["observed_at"], field="Profil gözlem zamanı",
            ),
        )
        if (
            type(candidate.run_sequence) is not int
            or candidate.run_sequence < 1
            or brand_username_review_candidate_json(candidate) != value
        ):
            raise ValueError("Invalid canonical candidate")
        return candidate

    @staticmethod
    def _validate_candidate(candidate, *, watches, runs, items):
        if not isinstance(candidate, BrandUsernameReviewCandidate):
            raise ValueError("Invalid candidate")
        candidate = replace(candidate, current_review=None)
        watch = watches.get(candidate.watch_id)
        run = runs.get(candidate.run_id)
        matching = [
            item for item in items
            if item.run_id == candidate.run_id and item.platform == candidate.platform
        ]
        if (
            watch is None
            or run is None
            or run.status != "complete"
            or run.watch_id != watch.id
            or run.sequence != candidate.run_sequence
            or run.definition_sha256 != candidate.definition_sha256
            or run.username != candidate.username
            or run.checked_at != candidate.observed_at
            or len(matching) != 1
        ):
            raise ValueError("Candidate source mismatch")
        item = matching[0]
        if (
            item.status != "found_unverified"
            or item.profile_url != candidate.profile_url
            or item.state_sha256 != candidate.state_sha256
            or candidate.id != brand_username_review_candidate_id(
                watch_id=watch.id,
                definition_sha256=run.definition_sha256,
                platform=item.platform,
                state_sha256=item.state_sha256,
            )
        ):
            raise ValueError("Candidate state mismatch")
        return candidate

    @classmethod
    def _audit(cls, connection):
        watches, _, runs, items = SQLiteBrandUsernameWatchRepository._audit(connection)
        rows = connection.execute(
            f"SELECT {_SELECT} FROM brand_username_review_events "
            "ORDER BY sequence LIMIT ?",
            (_MAX_EVENTS + 1,),
        ).fetchall()
        if len(rows) > _MAX_EVENTS:
            raise StorageError("Profil kararı geçmişi güvenli sınırı aşıyor.")
        candidates = {}
        watch_ids = {}
        records = []
        try:
            for row in rows:
                if type(row[0]) is not int or row[0] < 1:
                    raise ValueError("Invalid sequence")
                event_id = _uuid(row[1])
                candidate_id = _uuid(row[2])
                watch_id = _uuid(row[3])
                run_id = _uuid(row[4])
                platform = row[5]
                candidate = cls._validate_candidate(
                    cls._candidate_json(row[6]),
                    watches=watches,
                    runs=runs,
                    items=items,
                )
                candidate_sha = _sha256(row[7])
                if (
                    candidate.id != candidate_id
                    or candidate.watch_id != watch_id
                    or candidate.run_id != run_id
                    or candidate.platform != platform
                    or brand_username_review_candidate_sha256(candidate) != candidate_sha
                ):
                    raise ValueError("Candidate columns mismatch")
                event = BrandUsernameReviewEvent(
                    sequence=row[0],
                    id=event_id,
                    candidate_id=candidate_id,
                    watch_id=watch_id,
                    run_id=run_id,
                    decision=normalize_brand_username_review_decision(row[8]),
                    reason=normalize_brand_username_review_reason(row[9]),
                    recorded_at=_timestamp(row[10], field="Profil kararı zamanı"),
                    previous_event_id=(
                        _uuid(row[11]) if row[11] is not None else None
                    ),
                    candidate_sha256=candidate_sha,
                )
                if datetime.fromisoformat(event.recorded_at) < datetime.fromisoformat(
                    candidate.observed_at
                ):
                    raise ValueError("Decision predates candidate")
                existing = candidates.get(candidate_id)
                if existing is not None and brand_username_review_candidate_json(
                    existing
                ) != brand_username_review_candidate_json(candidate):
                    raise ValueError("Candidate snapshot changed")
                candidates[candidate_id] = candidate
                watch_ids[candidate_id] = watch_id
                records.append(event)
        except (
            TypeError, ValueError, ValidationError, OverflowError, json.JSONDecodeError,
        ) as error:
            raise StorageError("Profil kararı geçmişi bozuk; işlem durduruldu.") from error
        if len({event.sequence for event in records}) != len(records):
            raise StorageError("Profil kararı sırası bozuk; işlem durduruldu.")
        by_candidate = {candidate_id: [] for candidate_id in candidates}
        for event in records:
            by_candidate[event.candidate_id].append(event)
        for history in by_candidate.values():
            for index, event in enumerate(history):
                expected_previous = history[index - 1].id if index else None
                if event.previous_event_id != expected_previous:
                    raise StorageError("Profil kararı zinciri bozuk; işlem durduruldu.")
                if index and datetime.fromisoformat(
                    history[index - 1].recorded_at
                ) > datetime.fromisoformat(event.recorded_at):
                    raise StorageError("Profil kararı zamanı bozuk; işlem durduruldu.")
                if event.candidate_sha256 != history[0].candidate_sha256:
                    raise StorageError("Profil kararı kanıtı değişmiş; işlem durduruldu.")
        event_by_id = {event.id: event for event in records}
        notification_rows = connection.execute(
            f"SELECT {_NOTIFICATION_SELECT} FROM brand_username_review_notifications "
            "ORDER BY sequence LIMIT ?",
            (_MAX_EVENTS + 1,),
        ).fetchall()
        if len(notification_rows) > _MAX_EVENTS:
            raise StorageError("Sosyal profil bildirim sayısı güvenli sınırı aşıyor.")
        notifications = []
        try:
            for row in notification_rows:
                if type(row[0]) is not int or row[0] < 1:
                    raise ValueError("Invalid notification sequence")
                notification_id = _uuid(row[1])
                candidate_id = _uuid(row[2])
                review_event_id = _uuid(row[3])
                event = event_by_id.get(review_event_id)
                if (
                    candidate_id not in candidates
                    or event is None
                    or event.candidate_id != candidate_id
                    or event.decision != "possible_impersonation"
                    or row[4] != "social_profile_possible_impersonation"
                    or row[5] != "new"
                ):
                    raise ValueError("Invalid notification evidence")
                created_at = _timestamp(row[6], field="Sosyal profil bildirim zamanı")
                read_at = (
                    _timestamp(row[7], field="Sosyal profil okunma zamanı")
                    if row[7] is not None else None
                )
                if created_at != event.recorded_at:
                    raise ValueError("Notification time mismatch")
                notifications.append((
                    row[0], notification_id, candidate_id, review_event_id,
                    created_at, read_at,
                ))
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError(
                "Sosyal profil bildirim geçmişi bozuk; işlem durduruldu."
            ) from error
        if (
            len({row[0] for row in notifications}) != len(notifications)
            or len({row[1] for row in notifications}) != len(notifications)
            or len({row[2] for row in notifications}) != len(notifications)
            or len({row[3] for row in notifications}) != len(notifications)
        ):
            raise StorageError("Sosyal profil bildirim tekilliği bozuk; işlem durduruldu.")
        return (
            watches, runs, items, candidates, watch_ids, tuple(records),
            by_candidate, tuple(notifications),
        )

    @staticmethod
    def _candidate_for(watch_id, platform, *, watches, runs, items):
        watch = watches.get(watch_id)
        if watch is None:
            raise ValidationError("Sosyal kullanıcı adı izlemesi bulunamadı.")
        if platform not in watch.platforms:
            raise ValidationError("Platform bu izlemenin güncel tanımında yok.")
        definition = SQLiteBrandUsernameWatchRepository._definition(watch)
        complete = sorted(
            (
                run for run in runs.values()
                if run.watch_id == watch.id
                and run.definition_sha256 == definition
                and run.status == "complete"
            ),
            key=lambda value: value.sequence,
        )
        if not complete:
            raise ValidationError(
                "Güncel izleme tanımı için başarılı çalışma yok; "
                "önce watch-run çalıştırın."
            )
        run = complete[-1]
        matching = [
            item for item in items
            if item.run_id == run.id and item.platform == platform
        ]
        if len(matching) != 1:
            raise StorageError("Profil inceleme kanıtı bulunamadı.")
        item = matching[0]
        if item.status != "found_unverified" or item.profile_url is None:
            raise ValidationError(
                "Platform son başarılı çalışmada profil olarak raporlanmadı; "
                "karar verilemez."
            )
        return BrandUsernameReviewCandidate(
            id=brand_username_review_candidate_id(
                watch_id=watch.id,
                definition_sha256=run.definition_sha256,
                platform=item.platform,
                state_sha256=item.state_sha256,
            ),
            watch_id=watch.id,
            run_id=run.id,
            run_sequence=run.sequence,
            definition_sha256=run.definition_sha256,
            username=run.username,
            platform=item.platform,
            profile_url=item.profile_url,
            state_sha256=item.state_sha256,
            observed_at=run.checked_at,
        )

    @staticmethod
    def _state(candidate_id, history, candidates):
        latest = history[-1]
        return BrandUsernameReviewState(
            candidate_id=candidate_id,
            decision=latest.decision,
            reason=latest.reason,
            reviewed_at=latest.recorded_at,
            event_count=len(history),
            state_sha256=candidates[candidate_id].state_sha256,
        )

    @classmethod
    def _details(cls, candidate_id, candidates, by_candidate, *, event_limit):
        candidate = candidates.get(candidate_id)
        history = by_candidate.get(candidate_id)
        if candidate is None or not history:
            raise ValidationError("Kayıtlı profil kararı bulunamadı.")
        current = cls._state(candidate_id, history, candidates)
        return BrandUsernameReviewDetails(
            candidate=replace(candidate, current_review=current),
            current=current,
            events=tuple(history[-event_limit:]),
            total_event_count=len(history),
        )

    def current_candidate(self, watch_id, platform):
        with self._storage._connection(readonly=True) as connection:
            watches, runs, items, _, _, _, _, _ = self._audit(connection)
        return self._candidate_for(
            watch_id, platform, watches=watches, runs=runs, items=items,
        )

    def record(self, candidate, *, decision, reason, recorded_at):
        decision = normalize_brand_username_review_decision(decision)
        reason = normalize_brand_username_review_reason(reason)
        try:
            recorded_at = _timestamp(recorded_at, field="Profil kararı zamanı")
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("Profil kararı zamanı geçersiz.") from error
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                (
                    watches, runs, items, candidates, _, _, by_candidate, notifications,
                ) = self._audit(connection)
                if not isinstance(candidate, BrandUsernameReviewCandidate):
                    raise ValidationError("Geçerli bir profil inceleme adayı gerekli.")
                current = self._candidate_for(
                    candidate.watch_id,
                    candidate.platform,
                    watches=watches,
                    runs=runs,
                    items=items,
                )
                if current.id != candidate.id:
                    raise ValidationError(
                        "Profil kanıtı karar sırasında değişti; "
                        "güncel sonucu yeniden inceleyin."
                    )
                history = by_candidate.get(current.id, [])
                frozen = candidates.get(current.id, current)
                if history:
                    latest = history[-1]
                    if datetime.fromisoformat(recorded_at) < datetime.fromisoformat(
                        latest.recorded_at
                    ):
                        raise ValidationError("Profil kararı zamanı önceki karardan eski.")
                    if latest.decision == decision and latest.reason == reason:
                        notification = next(
                            (row for row in notifications if row[2] == current.id),
                            None,
                        )
                        connection.commit()
                        return BrandUsernameReviewMutation(
                            "unchanged",
                            self._details(
                                current.id, candidates, by_candidate, event_limit=500,
                            ),
                            notification[1] if notification is not None else None,
                            False,
                        )
                candidate_json = brand_username_review_candidate_json(frozen)
                candidate_sha = brand_username_review_candidate_sha256(frozen)
                event_id = str(uuid4())
                connection.execute(
                    "INSERT INTO brand_username_review_events "
                    "(id, candidate_id, watch_id, run_id, platform, candidate_json, "
                    "candidate_sha256, decision, reason, recorded_at, previous_event_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event_id, frozen.id, frozen.watch_id, frozen.run_id,
                        frozen.platform, candidate_json, candidate_sha, decision, reason,
                        recorded_at, history[-1].id if history else None,
                    ),
                )
                notification_id = next(
                    (row[1] for row in notifications if row[2] == frozen.id),
                    None,
                )
                notification_created = False
                if decision == "possible_impersonation" and notification_id is None:
                    notification_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO brand_username_review_notifications "
                        "(sequence, id, candidate_id, review_event_id, event_type, "
                        "origin, created_at, read_at) VALUES (?, ?, ?, ?, "
                        "'social_profile_possible_impersonation', 'new', ?, NULL)",
                        (
                            next_notification_sequence(connection), notification_id,
                            frozen.id, event_id, recorded_at,
                        ),
                    )
                    notification_created = True
                (
                    _, _, _, candidates, _, _, by_candidate, notifications,
                ) = self._audit(connection)
                details = self._details(
                    frozen.id, candidates, by_candidate, event_limit=500,
                )
                connection.commit()
                return BrandUsernameReviewMutation(
                    "recorded" if details.total_event_count == 1 else "updated",
                    details,
                    notification_id,
                    notification_created,
                )
            except BaseException:
                connection.rollback()
                raise

    def details(self, candidate_id, *, event_limit):
        with self._storage._connection(readonly=True) as connection:
            _, _, _, candidates, _, _, by_candidate, _ = self._audit(connection)
        return self._details(
            candidate_id, candidates, by_candidate, event_limit=event_limit,
        )

    def states(self, watch_id):
        with self._storage._connection(readonly=True) as connection:
            (
                watches, _, _, candidates, watch_ids, _, by_candidate, _,
            ) = self._audit(connection)
        if watch_id not in watches:
            raise ValidationError("Sosyal kullanıcı adı izlemesi bulunamadı.")
        return tuple(
            self._state(candidate_id, by_candidate[candidate_id], candidates)
            for candidate_id in sorted(
                (key for key, value in watch_ids.items() if value == watch_id),
                key=lambda key: by_candidate[key][-1].sequence,
            )
        )

    @classmethod
    def notification_evidence(
        cls, connection, notification_id: str,
    ) -> BrandUsernameReviewNotificationEvidence:
        (
            watches, _, _, candidates, _, records, by_candidate, notifications,
        ) = cls._audit(connection)
        notification = next(
            (row for row in notifications if row[1] == notification_id), None,
        )
        if notification is None:
            raise StorageError("Sosyal profil bildiriminin kanıtı bulunamadı.")
        event = next(
            (value for value in records if value.id == notification[3]), None,
        )
        if event is None:
            raise StorageError("Sosyal profil bildiriminin karar olayı bulunamadı.")
        candidate = candidates[notification[2]]
        current = cls._state(candidate.id, by_candidate[candidate.id], candidates)
        return BrandUsernameReviewNotificationEvidence(
            notification_id=notification[1],
            watch_name=watches[candidate.watch_id].display_name,
            candidate=replace(candidate, current_review=current),
            trigger=event,
            current=current,
        )

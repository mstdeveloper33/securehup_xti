"""Transactional collection profiles with validated immutable revisions."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.collection_profiles import (
    PROFILE_ACTIONS,
    CollectionProfile,
    CollectionProfileDefinition,
    CollectionProfileDetails,
    CollectionProfileEvent,
    CollectionProfileMutation,
    canonical_definition_json,
    definition_sha256,
    normalize_profile_definition,
    normalize_profile_name,
    normalize_profile_reason,
    parse_definition_json,
    profile_name_key,
)
from xti.domain.cti_knowledge import normalize_knowledge_id


_MAX_PROFILES = 10_000
_MAX_EVENTS = 100_000
_PROFILE_COLUMNS = (
    "id, name_key, display_name, revision, definition_json, definition_sha256, "
    "active, created_at, updated_at"
)
_EVENT_COLUMNS = (
    "sequence, id, profile_id, action, revision, display_name, definition_json, "
    "definition_sha256, reason, recorded_at"
)


def _time(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValidationError("Profil kayıt zamanı geçersiz.")
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError) as error:
        raise ValidationError("Profil kayıt zamanı saat dilimi bilgili olmalı.") from error


def _positive(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise ValueError("invalid sequence or revision")
    return value


def _limit(value: int, *, maximum: int = 500) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValidationError(f"Profil sonuç sınırı 1–{maximum} arasında olmalı.")
    return value


class SQLiteCollectionProfileRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _profile(row) -> CollectionProfile:
        try:
            definition = parse_definition_json(row[4])
            display_name = normalize_profile_name(row[2])
            created_at, updated_at = _time(row[7]), _time(row[8])
            if (
                row[1] != profile_name_key(display_name) or row[2] != display_name
                or row[5] != definition_sha256(definition)
                or type(row[6]) is not int or row[6] not in {0, 1}
                or created_at != row[7] or updated_at != row[8]
                or datetime.fromisoformat(created_at) > datetime.fromisoformat(updated_at)
            ):
                raise ValueError("non-canonical profile")
            return CollectionProfile(
                normalize_knowledge_id(row[0]), row[1], display_name, _positive(row[3]),
                definition, row[5], bool(row[6]), created_at, updated_at,
            )
        except (TypeError, ValueError, OverflowError) as error:
            raise StorageError("Toplama profil kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row) -> CollectionProfileEvent:
        try:
            definition = parse_definition_json(row[6])
            display_name = normalize_profile_name(row[5])
            recorded_at = _time(row[9])
            if (
                row[3] not in PROFILE_ACTIONS or display_name != row[5]
                or row[7] != definition_sha256(definition) or recorded_at != row[9]
                or (row[3] == "revoked" and normalize_profile_reason(row[8]) != row[8])
                or (row[3] != "revoked" and row[8] != "")
            ):
                raise ValueError("invalid event")
            return CollectionProfileEvent(
                _positive(row[0]), normalize_knowledge_id(row[1]),
                normalize_knowledge_id(row[2]), row[3], _positive(row[4]),
                display_name, definition, row[7], row[8], recorded_at,
            )
        except (TypeError, ValueError, OverflowError) as error:
            raise StorageError("Toplama profil geçmişi bozuk; işlem durduruldu.") from error

    @classmethod
    def _audit(cls, connection):
        rows = connection.execute(
            f"SELECT {_PROFILE_COLUMNS} FROM collection_profiles ORDER BY id LIMIT ?",
            (_MAX_PROFILES + 1,),
        ).fetchall()
        event_rows = connection.execute(
            f"SELECT {_EVENT_COLUMNS} FROM collection_profile_events ORDER BY sequence LIMIT ?",
            (_MAX_EVENTS + 1,),
        ).fetchall()
        if len(rows) > _MAX_PROFILES or len(event_rows) > _MAX_EVENTS:
            raise StorageError("Toplama profil geçmişi güvenli okuma sınırını aşıyor.")
        profiles = {profile.id: profile for profile in map(cls._profile, rows)}
        events = tuple(map(cls._event, event_rows))
        histories: dict[str, list[CollectionProfileEvent]] = {key: [] for key in profiles}
        for event in events:
            if event.profile_id not in profiles:
                raise StorageError("Toplama profil geçmişinde kopuk bağlantı bulundu.")
            histories[event.profile_id].append(event)
        for profile in profiles.values():
            history = histories[profile.id]
            active = False
            previous = None
            for revision, event in enumerate(history, 1):
                invalid = (
                    event.revision != revision or profile_name_key(event.display_name) != profile.name_key
                    or (previous is None and event.action != "added")
                    or (previous is not None and event.action == "added")
                )
                if previous is not None:
                    same = (
                        event.display_name == previous.display_name
                        and event.definition == previous.definition
                    )
                    invalid = invalid or (
                        datetime.fromisoformat(event.recorded_at)
                        < datetime.fromisoformat(previous.recorded_at)
                        or (active and event.action not in {"updated", "revoked"})
                        or (not active and event.action != "reactivated")
                        or (event.action == "updated" and same)
                        or (event.action == "revoked" and not same)
                    )
                if invalid:
                    raise StorageError("Toplama profil yaşam döngüsü bozuk; işlem durduruldu.")
                active = event.action != "revoked"
                previous = event
            if (
                previous is None or profile.revision != previous.revision
                or profile.display_name != previous.display_name
                or profile.definition != previous.definition
                or profile.definition_sha256 != previous.definition_sha256
                or profile.active != active or profile.created_at != history[0].recorded_at
                or profile.updated_at != previous.recorded_at
            ):
                raise StorageError("Toplama profil güncel kaydı geçmişiyle uyuşmuyor.")
        return profiles, events

    @staticmethod
    def _find(profiles, name_key: str) -> CollectionProfile:
        for profile in profiles.values():
            if profile.name_key == name_key:
                return profile
        raise ValidationError("Toplama profili bulunamadı.")

    @staticmethod
    def _check_time(profile: CollectionProfile, recorded_at: str) -> None:
        if datetime.fromisoformat(recorded_at) < datetime.fromisoformat(profile.updated_at):
            raise ValidationError("Profil kayıt zamanı son değişiklikten önce olamaz.")

    @staticmethod
    def _append_event(connection, profile, action: str, reason: str) -> None:
        connection.execute(
            "INSERT INTO collection_profile_events "
            "(id, profile_id, action, revision, display_name, definition_json, "
            "definition_sha256, reason, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid4()), profile.id, action, profile.revision, profile.display_name,
                canonical_definition_json(profile.definition), profile.definition_sha256,
                reason, profile.updated_at,
            ),
        )

    def save(
        self, display_name: str, definition: CollectionProfileDefinition, *, recorded_at: str,
    ) -> CollectionProfileMutation:
        display_name = normalize_profile_name(display_name)
        name_key = profile_name_key(display_name)
        definition = normalize_profile_definition(definition)
        recorded_at = _time(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                profiles, events = self._audit(connection)
                previous = next((value for value in profiles.values() if value.name_key == name_key), None)
                if previous is not None:
                    self._check_time(previous, recorded_at)
                    if previous.active and previous.display_name == display_name and previous.definition == definition:
                        connection.commit()
                        return CollectionProfileMutation("unchanged", previous)
                if len(events) >= _MAX_EVENTS or (previous is None and len(profiles) >= _MAX_PROFILES):
                    raise StorageError("Toplama profil geçmişi kayıt sınırına ulaştı.")
                profile = CollectionProfile(
                    previous.id if previous else str(uuid4()), name_key, display_name,
                    previous.revision + 1 if previous else 1, definition, definition_sha256(definition),
                    True, previous.created_at if previous else recorded_at, recorded_at,
                )
                action = "added" if previous is None else "updated" if previous.active else "reactivated"
                if previous is None:
                    connection.execute(
                        f"INSERT INTO collection_profiles ({_PROFILE_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                        (profile.id, name_key, display_name, profile.revision,
                         canonical_definition_json(definition), profile.definition_sha256,
                         profile.created_at, recorded_at),
                    )
                else:
                    connection.execute(
                        "UPDATE collection_profiles SET display_name=?, revision=?, definition_json=?, "
                        "definition_sha256=?, active=1, updated_at=? WHERE id=?",
                        (display_name, profile.revision, canonical_definition_json(definition),
                         profile.definition_sha256, recorded_at, profile.id),
                    )
                self._append_event(connection, profile, action, "")
                self._audit(connection)
                connection.commit()
                return CollectionProfileMutation(action, profile)
            except BaseException:
                connection.rollback()
                raise

    def revoke(self, name: str, *, reason: str, recorded_at: str) -> CollectionProfileMutation:
        name_key, reason, recorded_at = profile_name_key(name), normalize_profile_reason(reason), _time(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                profiles, events = self._audit(connection)
                previous = self._find(profiles, name_key)
                self._check_time(previous, recorded_at)
                if not previous.active:
                    connection.commit()
                    return CollectionProfileMutation("unchanged", previous)
                if len(events) >= _MAX_EVENTS:
                    raise StorageError("Toplama profil geçmişi kayıt sınırına ulaştı.")
                profile = CollectionProfile(
                    previous.id, previous.name_key, previous.display_name, previous.revision + 1,
                    previous.definition, previous.definition_sha256, False, previous.created_at, recorded_at,
                )
                connection.execute(
                    "UPDATE collection_profiles SET revision=?, active=0, updated_at=? WHERE id=?",
                    (profile.revision, recorded_at, profile.id),
                )
                self._append_event(connection, profile, "revoked", reason)
                self._audit(connection)
                connection.commit()
                return CollectionProfileMutation("revoked", profile)
            except BaseException:
                connection.rollback()
                raise

    def get(self, name: str) -> CollectionProfile:
        name_key = profile_name_key(name)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            profiles, _ = self._audit(connection)
            return self._find(profiles, name_key)

    def list(self, *, active_only: bool = True, limit: int = 100) -> tuple[CollectionProfile, ...]:
        _limit(limit, maximum=501)
        if type(active_only) is not bool:
            raise ValidationError("Profil etkinlik filtresi doğru/yanlış olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            profiles, _ = self._audit(connection)
            return tuple(sorted(
                (profile for profile in profiles.values() if not active_only or profile.active),
                key=lambda value: (value.name_key, value.id),
            )[:limit])

    def details(self, name: str, *, event_limit: int = 50) -> CollectionProfileDetails:
        name_key = profile_name_key(name)
        _limit(event_limit)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            profiles, events = self._audit(connection)
            profile = self._find(profiles, name_key)
            history = tuple(event for event in reversed(events) if event.profile_id == profile.id)
            return CollectionProfileDetails(profile, history[:event_limit], len(history))

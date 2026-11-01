"""SQLite journal for durable CTI search tags and append-only analyst notes."""

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_saved_searches import SQLiteCtiSavedSearchRepository
from xti.domain.assets import ValidationError
from xti.domain.cti_hunting_journal import (
    HUNTING_TAG_ACTIONS,
    CtiHuntingJournal,
    CtiHuntingNote,
    CtiHuntingTag,
    CtiHuntingTagEvent,
    CtiHuntingTagMutation,
    hunting_tag_key,
    normalize_hunting_note_body,
    normalize_hunting_note_kind,
    normalize_hunting_tag,
)
from xti.domain.cti_indicators import normalize_cti_timestamp


_TAG_SELECT = (
    "saved_search_id, tag_key, display_tag, active, created_at, updated_at"
)
_EVENT_SELECT = (
    "sequence, id, saved_search_id, tag_key, display_tag, action, recorded_at"
)
_NOTE_SELECT = (
    "sequence, id, saved_search_id, run_id, note_kind, body, recorded_at"
)
_MAX_TAGS = 100_000
_MAX_TAG_EVENTS = 200_000
_MAX_NOTES = 100_000
_MAX_ACTIVE_TAGS_PER_SEARCH = 50


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid UUID")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("Non-canonical UUID")
    return normalized


def _timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    normalized = normalize_cti_timestamp(value, field=field)
    if normalized != value:
        raise ValueError("Non-canonical timestamp")
    return normalized


class SQLiteCtiHuntingJournalRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _tag(row, searches) -> CtiHuntingTag:
        try:
            search_id = _uuid(row[0])
            if search_id not in searches:
                raise ValueError("Missing saved search")
            display_tag = normalize_hunting_tag(row[2])
            if row[1] != hunting_tag_key(display_tag):
                raise ValueError("Non-canonical tag")
            if type(row[3]) is not int or row[3] not in {0, 1}:
                raise ValueError("Invalid activity")
            tag = CtiHuntingTag(
                saved_search_id=search_id, tag_key=row[1], display_tag=display_tag,
                active=bool(row[3]),
                created_at=_timestamp(row[4], field="CTI avcılık etiketi oluşturma zamanı"),
                updated_at=_timestamp(row[5], field="CTI avcılık etiketi güncelleme zamanı"),
            )
            created = datetime.fromisoformat(tag.created_at)
            updated = datetime.fromisoformat(tag.updated_at)
            search_created = datetime.fromisoformat(searches[search_id].created_at)
            if created < search_created or created > updated:
                raise ValueError("Invalid tag time")
            return tag
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("CTI avcılık etiketi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row, searches, tags) -> CtiHuntingTagEvent:
        try:
            if type(row[0]) is not int or row[0] < 1:
                raise ValueError("Invalid sequence")
            event_id, search_id = _uuid(row[1]), _uuid(row[2])
            display_tag = normalize_hunting_tag(row[4])
            tag_key = hunting_tag_key(display_tag)
            if (
                search_id not in searches or row[3] != tag_key
                or (search_id, tag_key) not in tags or row[5] not in HUNTING_TAG_ACTIONS
            ):
                raise ValueError("Invalid tag event")
            event = CtiHuntingTagEvent(
                sequence=row[0], id=event_id, saved_search_id=search_id,
                tag_key=tag_key, display_tag=display_tag, action=row[5],
                recorded_at=_timestamp(row[6], field="CTI avcılık etiketi olay zamanı"),
            )
            if datetime.fromisoformat(event.recorded_at) < datetime.fromisoformat(
                searches[search_id].created_at
            ):
                raise ValueError("Event predates search")
            return event
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("CTI avcılık etiketi geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _note(row, searches, runs) -> CtiHuntingNote:
        try:
            if type(row[0]) is not int or row[0] < 1:
                raise ValueError("Invalid sequence")
            note_id, search_id = _uuid(row[1]), _uuid(row[2])
            if search_id not in searches:
                raise ValueError("Missing saved search")
            run_id = _uuid(row[3]) if row[3] is not None else None
            if run_id is not None:
                run = runs.get(run_id)
                if run is None or run.saved_search_id != search_id:
                    raise ValueError("Misdirected run note")
            note = CtiHuntingNote(
                sequence=row[0], id=note_id, saved_search_id=search_id,
                run_id=run_id, note_kind=normalize_hunting_note_kind(row[4]),
                body=normalize_hunting_note_body(row[5]),
                recorded_at=_timestamp(row[6], field="CTI avcılık notu zamanı"),
            )
            recorded = datetime.fromisoformat(note.recorded_at)
            if recorded < datetime.fromisoformat(searches[search_id].created_at):
                raise ValueError("Note predates search")
            if run_id is not None and recorded < datetime.fromisoformat(runs[run_id].executed_at):
                raise ValueError("Note predates run")
            return note
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("CTI avcılık notu bozuk; işlem durduruldu.") from error

    @classmethod
    def _audit(cls, connection):
        searches, _, runs, _, _ = SQLiteCtiSavedSearchRepository._audit(connection)
        tag_rows = connection.execute(
            f"SELECT {_TAG_SELECT} FROM cti_saved_search_tags "
            "ORDER BY saved_search_id, tag_key LIMIT ?", (_MAX_TAGS + 1,),
        ).fetchall()
        if len(tag_rows) > _MAX_TAGS:
            raise StorageError("CTI avcılık etiketi sayısı güvenli sınırı aşıyor.")
        tag_records = tuple(cls._tag(row, searches) for row in tag_rows)
        tags = {(tag.saved_search_id, tag.tag_key): tag for tag in tag_records}
        if len(tags) != len(tag_records):
            raise StorageError("CTI avcılık etiketi kimliği bozuk; işlem durduruldu.")
        active_counts: dict[str, int] = {}
        for tag in tag_records:
            if tag.active:
                active_counts[tag.saved_search_id] = active_counts.get(tag.saved_search_id, 0) + 1
        if any(value > _MAX_ACTIVE_TAGS_PER_SEARCH for value in active_counts.values()):
            raise StorageError("Bir CTI aramasındaki etkin etiket sayısı güvenli sınırı aşıyor.")

        event_rows = connection.execute(
            f"SELECT {_EVENT_SELECT} FROM cti_saved_search_tag_events "
            "ORDER BY sequence LIMIT ?", (_MAX_TAG_EVENTS + 1,),
        ).fetchall()
        if len(event_rows) > _MAX_TAG_EVENTS:
            raise StorageError("CTI avcılık etiketi geçmişi güvenli sınırı aşıyor.")
        events = tuple(cls._event(row, searches, tags) for row in event_rows)
        if len({event.sequence for event in events}) != len(events):
            raise StorageError("CTI avcılık etiketi olay sırası bozuk; işlem durduruldu.")
        by_tag: dict[tuple[str, str], list[CtiHuntingTagEvent]] = {
            key: [] for key in tags
        }
        for event in events:
            by_tag[(event.saved_search_id, event.tag_key)].append(event)
        for key, tag in tags.items():
            history = by_tag[key]
            if not history or history[0].action != "added":
                raise StorageError("CTI avcılık etiketi yaşam döngüsü bozuk; işlem durduruldu.")
            active = False
            display = None
            previous_time = None
            for index, event in enumerate(history):
                event_time = datetime.fromisoformat(event.recorded_at)
                if previous_time is not None and previous_time > event_time:
                    raise StorageError(
                        "CTI avcılık etiketi olay zamanı bozuk; işlem durduruldu."
                    )
                previous_time = event_time
                if event.action == "added":
                    if index != 0 or active:
                        raise StorageError(
                            "CTI avcılık etiketi yaşam döngüsü bozuk; işlem durduruldu."
                        )
                    active = True
                elif event.action == "updated":
                    if not active or display == event.display_tag:
                        raise StorageError(
                            "CTI avcılık etiketi yaşam döngüsü bozuk; işlem durduruldu."
                        )
                elif event.action == "removed":
                    if not active:
                        raise StorageError(
                            "CTI avcılık etiketi yaşam döngüsü bozuk; işlem durduruldu."
                        )
                    active = False
                elif event.action == "reactivated":
                    if active:
                        raise StorageError(
                            "CTI avcılık etiketi yaşam döngüsü bozuk; işlem durduruldu."
                        )
                    active = True
                display = event.display_tag
            if (
                active != tag.active or display != tag.display_tag
                or history[0].recorded_at != tag.created_at
                or history[-1].recorded_at != tag.updated_at
            ):
                raise StorageError("CTI avcılık etiketi özeti bozuk; işlem durduruldu.")

        note_rows = connection.execute(
            f"SELECT {_NOTE_SELECT} FROM cti_saved_search_notes "
            "ORDER BY sequence LIMIT ?", (_MAX_NOTES + 1,),
        ).fetchall()
        if len(note_rows) > _MAX_NOTES:
            raise StorageError("CTI avcılık notu geçmişi güvenli sınırı aşıyor.")
        notes = tuple(cls._note(row, searches, runs) for row in note_rows)
        if len({note.sequence for note in notes}) != len(notes):
            raise StorageError("CTI avcılık notu sırası bozuk; işlem durduruldu.")
        return searches, runs, tags, events, notes

    def add_tag(self, **values) -> CtiHuntingTagMutation:
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                searches, _, tags, _, _ = self._audit(connection)
                search_id, tag_key = values["saved_search_id"], values["tag_key"]
                if search_id not in searches:
                    raise ValidationError("Kayıtlı CTI araması bulunamadı.")
                old = tags.get((search_id, tag_key))
                if old is not None and old.active and old.display_tag == values["display_tag"]:
                    connection.commit()
                    return CtiHuntingTagMutation(action="unchanged", tag=old)
                if old is None or not old.active:
                    active_count = sum(
                        tag.saved_search_id == search_id and tag.active for tag in tags.values()
                    )
                    if active_count >= _MAX_ACTIVE_TAGS_PER_SEARCH:
                        raise ValidationError("Bir kayıtlı CTI aramasında en fazla 50 etkin etiket olabilir.")
                action = "added" if old is None else ("reactivated" if not old.active else "updated")
                if old is None:
                    connection.execute(
                        "INSERT INTO cti_saved_search_tags VALUES (?, ?, ?, 1, ?, ?)",
                        (search_id, tag_key, values["display_tag"], values["recorded_at"],
                         values["recorded_at"]),
                    )
                else:
                    connection.execute(
                        "UPDATE cti_saved_search_tags SET display_tag=?, active=1, updated_at=? "
                        "WHERE saved_search_id=? AND tag_key=?",
                        (values["display_tag"], values["recorded_at"], search_id, tag_key),
                    )
                connection.execute(
                    "INSERT INTO cti_saved_search_tag_events "
                    "(id, saved_search_id, tag_key, display_tag, action, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid4()), search_id, tag_key, values["display_tag"], action,
                     values["recorded_at"]),
                )
                row = connection.execute(
                    f"SELECT {_TAG_SELECT} FROM cti_saved_search_tags "
                    "WHERE saved_search_id=? AND tag_key=?", (search_id, tag_key),
                ).fetchone()
                tag = self._tag(row, searches)
                connection.commit()
                return CtiHuntingTagMutation(action=action, tag=tag)
            except BaseException:
                connection.rollback()
                raise

    def remove_tag(self, **values) -> CtiHuntingTagMutation:
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                searches, _, tags, _, _ = self._audit(connection)
                search_id, tag_key = values["saved_search_id"], values["tag_key"]
                if search_id not in searches:
                    raise ValidationError("Kayıtlı CTI araması bulunamadı.")
                old = tags.get((search_id, tag_key))
                if old is None:
                    raise ValidationError("CTI avcılık etiketi bulunamadı.")
                if not old.active:
                    connection.commit()
                    return CtiHuntingTagMutation(action="unchanged", tag=old)
                connection.execute(
                    "UPDATE cti_saved_search_tags SET active=0, updated_at=? "
                    "WHERE saved_search_id=? AND tag_key=?",
                    (values["recorded_at"], search_id, tag_key),
                )
                connection.execute(
                    "INSERT INTO cti_saved_search_tag_events "
                    "(id, saved_search_id, tag_key, display_tag, action, recorded_at) "
                    "VALUES (?, ?, ?, ?, 'removed', ?)",
                    (str(uuid4()), search_id, tag_key, old.display_tag, values["recorded_at"]),
                )
                row = connection.execute(
                    f"SELECT {_TAG_SELECT} FROM cti_saved_search_tags "
                    "WHERE saved_search_id=? AND tag_key=?", (search_id, tag_key),
                ).fetchone()
                tag = self._tag(row, searches)
                connection.commit()
                return CtiHuntingTagMutation(action="removed", tag=tag)
            except BaseException:
                connection.rollback()
                raise

    def add_note(self, **values) -> CtiHuntingNote:
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                searches, runs, _, _, _ = self._audit(connection)
                search_id, run_id = values["saved_search_id"], values["run_id"]
                if search_id not in searches:
                    raise ValidationError("Kayıtlı CTI araması bulunamadı.")
                if run_id is not None:
                    run = runs.get(run_id)
                    if run is None:
                        raise ValidationError("CTI arama çalışması bulunamadı.")
                    if run.saved_search_id != search_id:
                        raise ValidationError("CTI arama çalışması bu kayıtlı aramaya ait değil.")
                note_id = str(uuid4())
                connection.execute(
                    "INSERT INTO cti_saved_search_notes "
                    "(id, saved_search_id, run_id, note_kind, body, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (note_id, search_id, run_id, values["note_kind"], values["body"],
                     values["recorded_at"]),
                )
                row = connection.execute(
                    f"SELECT {_NOTE_SELECT} FROM cti_saved_search_notes WHERE id=?",
                    (note_id,),
                ).fetchone()
                note = self._note(row, searches, runs)
                connection.commit()
                return note
            except BaseException:
                connection.rollback()
                raise

    def journal(self, saved_search_id, *, note_limit, event_limit):
        with self._storage._connection(readonly=True) as connection:
            searches, _, tags, events, notes = self._audit(connection)
            search = searches.get(saved_search_id)
            if search is None:
                raise ValidationError("Kayıtlı CTI araması bulunamadı.")
            selected_tags = tuple(sorted(
                (tag for tag in tags.values()
                 if tag.saved_search_id == saved_search_id and tag.active),
                key=lambda tag: (tag.tag_key, tag.display_tag),
            ))
            all_events = [
                event for event in events if event.saved_search_id == saved_search_id
            ]
            all_notes = [note for note in notes if note.saved_search_id == saved_search_id]
            return CtiHuntingJournal(
                saved_search=search, tags=selected_tags,
                tag_events=tuple(reversed(all_events[-event_limit:])),
                notes=tuple(reversed(all_notes[-note_limit:])),
                total_tag_count=len(selected_tags),
                total_tag_event_count=len(all_events), total_note_count=len(all_notes),
            )

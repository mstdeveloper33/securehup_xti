"""Atomic SQLite storage for durable CTI searches and complete difference runs."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cti_knowledge import SQLiteCtiKnowledgeRepository
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import (
    normalize_assertion_reason,
    normalize_cti_timestamp,
    normalize_indicator_type,
    normalize_indicator_value,
)
from xti.domain.cti_knowledge import (
    SEARCH_MATCH_TYPES,
    normalize_entity_name,
    normalize_entity_type,
    normalize_search_kind,
    normalize_search_query,
    search_query_key,
)
from xti.domain.cti_saved_searches import (
    SAVED_SEARCH_ACTIONS,
    SAVED_SEARCH_ITEM_ACTIONS,
    CtiSavedSearch,
    CtiSavedSearchDetails,
    CtiSavedSearchChangeEvidence,
    CtiSavedSearchEvent,
    CtiSavedSearchMutation,
    CtiSavedSearchRun,
    CtiSavedSearchRunItem,
    CtiSavedSearchRunReport,
    CtiSavedSearchSummary,
    definition_sha256,
    normalize_saved_search_name,
    saved_search_name_key,
    search_result_state_sha256,
)


_SEARCH_SELECT = (
    "id, name_key, display_name, query, query_key, kind, entity_type, "
    "indicator_type, active_only, active, created_at, updated_at"
)
_EVENT_SELECT = (
    "id, saved_search_id, action, definition_sha256, reason, recorded_at"
)
_RUN_SELECT = (
    "sequence, id, saved_search_id, definition_sha256, previous_run_id, executed_at, "
    "total_count, added_count, updated_count, unchanged_count, removed_count, result_sha256"
)
_ITEM_SELECT = (
    "id, run_id, kind, record_id, record_type, display_value, matched_field, "
    "matched_value, match_type, action, state_sha256"
)
_NOTIFICATION_SELECT = (
    "sequence, id, run_id, saved_search_id, event_type, origin, created_at, read_at"
)
_HEX64 = re.compile(r"[0-9a-f]{64}", re.ASCII)
_MAX_SEARCHES = 10_000
_MAX_EVENTS = 100_000
_MAX_RUNS = 100_000
_MAX_ITEMS = 400_000
_MAX_NOTIFICATIONS = 100_000
_COMPLETE_RESULT_LIMIT = 20_000


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


def _sha256(value: object) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise ValueError("Invalid SHA-256")
    return value


def _result_sha(items) -> str:
    payload = [
        {"kind": item.kind, "record_id": item.record_id, "state_sha256": item.state_sha256}
        for item in sorted(items, key=lambda value: (value.kind, value.record_id))
        if item.action != "removed"
    ]
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SQLiteCtiSavedSearchRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _search(row) -> CtiSavedSearch:
        try:
            display_name = normalize_saved_search_name(row[2])
            query = normalize_search_query(row[3])
            kind = normalize_search_kind(row[5])
            entity_type = normalize_entity_type(row[6]) if row[6] is not None else None
            indicator_type = (
                normalize_indicator_type(row[7]) if row[7] is not None else None
            )
            if type(row[8]) is not int or row[8] not in {0, 1}:
                raise ValueError("Invalid history scope")
            if type(row[9]) is not int or row[9] not in {0, 1}:
                raise ValueError("Invalid activity")
            if (kind == "entity" and indicator_type is not None) or (
                kind == "indicator" and entity_type is not None
            ):
                raise ValueError("Conflicting filters")
            record = CtiSavedSearch(
                id=_uuid(row[0]), name_key=saved_search_name_key(display_name),
                display_name=display_name, query=query, query_key=search_query_key(query),
                kind=kind, entity_type=entity_type, indicator_type=indicator_type,
                active_only=bool(row[8]), active=bool(row[9]),
                created_at=_timestamp(row[10], field="CTI kayıtlı arama oluşturma zamanı"),
                updated_at=_timestamp(row[11], field="CTI kayıtlı arama güncelleme zamanı"),
            )
            if row[1] != record.name_key or row[4] != record.query_key:
                raise ValueError("Non-canonical search")
            if datetime.fromisoformat(record.created_at) > datetime.fromisoformat(record.updated_at):
                raise ValueError("Reversed search time")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Kayıtlı CTI arama tanımı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _event(row, searches: dict[str, CtiSavedSearch]) -> CtiSavedSearchEvent:
        try:
            event_id, search_id = _uuid(row[0]), _uuid(row[1])
            if search_id not in searches or row[2] not in SAVED_SEARCH_ACTIONS:
                raise ValueError("Invalid event reference")
            reason = row[4]
            if row[2] == "revoked":
                reason = normalize_assertion_reason(reason)
            elif reason != "":
                raise ValueError("Unexpected reason")
            event = CtiSavedSearchEvent(
                id=event_id, saved_search_id=search_id, action=row[2],
                definition_sha256=_sha256(row[3]), reason=reason,
                recorded_at=_timestamp(row[5], field="CTI kayıtlı arama olay zamanı"),
            )
            if datetime.fromisoformat(event.recorded_at) < datetime.fromisoformat(
                searches[search_id].created_at
            ):
                raise ValueError("Event predates search")
            return event
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Kayıtlı CTI arama geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _run(row, searches: dict[str, CtiSavedSearch]) -> CtiSavedSearchRun:
        try:
            if type(row[0]) is not int or row[0] < 1:
                raise ValueError("Invalid sequence")
            run_id, search_id = _uuid(row[1]), _uuid(row[2])
            if search_id not in searches:
                raise ValueError("Missing saved search")
            previous = _uuid(row[4]) if row[4] is not None else None
            counts = row[6:11]
            if any(type(value) is not int or value < 0 for value in counts):
                raise ValueError("Invalid counts")
            if row[6] != row[7] + row[8] + row[9]:
                raise ValueError("Inconsistent current counts")
            run = CtiSavedSearchRun(
                sequence=row[0], id=run_id, saved_search_id=search_id,
                definition_sha256=_sha256(row[3]), previous_run_id=previous,
                executed_at=_timestamp(row[5], field="CTI kayıtlı arama çalışma zamanı"),
                total_count=row[6], added_count=row[7], updated_count=row[8],
                unchanged_count=row[9], removed_count=row[10],
                result_sha256=_sha256(row[11]),
            )
            if datetime.fromisoformat(run.executed_at) < datetime.fromisoformat(
                searches[search_id].created_at
            ):
                raise ValueError("Run predates search")
            return run
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Kayıtlı CTI arama çalışması bozuk; işlem durduruldu.") from error

    @staticmethod
    def _item(row, runs: dict[str, CtiSavedSearchRun]) -> CtiSavedSearchRunItem:
        try:
            item_id, run_id = _uuid(row[0]), _uuid(row[1])
            if run_id not in runs or row[2] not in {"entity", "indicator"}:
                raise ValueError("Invalid item reference")
            kind = row[2]
            record_id = _uuid(row[3])
            if kind == "entity":
                record_type = normalize_entity_type(row[4])
                display_value = normalize_entity_name(row[5])
                if row[6] not in {"name", "alias"}:
                    raise ValueError("Invalid entity match field")
                matched_value = normalize_entity_name(row[7])
            else:
                record_type = normalize_indicator_type(row[4])
                display_value = normalize_indicator_value(record_type, row[5])
                if row[6] != "value":
                    raise ValueError("Invalid indicator match field")
                matched_value = normalize_indicator_value(record_type, row[7])
            if row[8] not in SEARCH_MATCH_TYPES or row[9] not in SAVED_SEARCH_ITEM_ACTIONS:
                raise ValueError("Invalid match or action")
            return CtiSavedSearchRunItem(
                id=item_id, run_id=run_id, kind=kind, record_id=record_id,
                record_type=record_type, display_value=display_value,
                matched_field=row[6], matched_value=matched_value,
                match_type=row[8], action=row[9], state_sha256=_sha256(row[10]),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Kayıtlı CTI arama sonucu bozuk; işlem durduruldu.") from error

    @staticmethod
    def _notification(row, searches, runs):
        try:
            if type(row[0]) is not int or row[0] < 1:
                raise ValueError("Invalid sequence")
            notification_id = _uuid(row[1])
            run_id, search_id = _uuid(row[2]), _uuid(row[3])
            run, search = runs.get(run_id), searches.get(search_id)
            if (
                run is None or search is None or run.saved_search_id != search.id
                or run.previous_run_id is None
                or run.added_count + run.updated_count + run.removed_count == 0
                or row[4] != "cti_saved_search_changed" or row[5] != "new"
            ):
                raise ValueError("Invalid notification relation")
            created_at = _timestamp(row[6], field="CTI arama bildirim zamanı")
            read_at = (
                _timestamp(row[7], field="CTI arama bildirim okuma zamanı")
                if row[7] is not None else None
            )
            if created_at != run.executed_at:
                raise ValueError("Notification time mismatch")
            return (row[0], notification_id, run_id, search_id, created_at, read_at)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Kayıtlı CTI arama bildirimi bozuk; işlem durduruldu.") from error

    @classmethod
    def _audit(cls, connection):
        search_rows = connection.execute(
            f"SELECT {_SEARCH_SELECT} FROM cti_saved_searches ORDER BY id LIMIT ?",
            (_MAX_SEARCHES + 1,),
        ).fetchall()
        if len(search_rows) > _MAX_SEARCHES:
            raise StorageError("Kayıtlı CTI arama sayısı güvenli sınırı aşıyor.")
        searches = {record.id: record for record in map(cls._search, search_rows)}
        event_rows = connection.execute(
            f"SELECT {_EVENT_SELECT} FROM cti_saved_search_events ORDER BY rowid LIMIT ?",
            (_MAX_EVENTS + 1,),
        ).fetchall()
        if len(event_rows) > _MAX_EVENTS:
            raise StorageError("Kayıtlı CTI arama geçmişi güvenli sınırı aşıyor.")
        events = tuple(cls._event(row, searches) for row in event_rows)
        events_by_search: dict[str, list[CtiSavedSearchEvent]] = {
            key: [] for key in searches
        }
        for event in events:
            events_by_search[event.saved_search_id].append(event)
        for search in searches.values():
            history = events_by_search[search.id]
            if (
                not history or history[0].action != "added"
                or history[-1].definition_sha256 != cls._definition(search)
                or (search.active and history[-1].action == "revoked")
                or (not search.active and history[-1].action != "revoked")
                or history[0].recorded_at != search.created_at
                or history[-1].recorded_at != search.updated_at
                or any(
                    datetime.fromisoformat(left.recorded_at)
                    > datetime.fromisoformat(right.recorded_at)
                    for left, right in zip(history, history[1:])
                )
            ):
                raise StorageError("Kayıtlı CTI arama yaşam döngüsü bozuk; işlem durduruldu.")
        run_rows = connection.execute(
            f"SELECT {_RUN_SELECT} FROM cti_saved_search_runs ORDER BY sequence LIMIT ?",
            (_MAX_RUNS + 1,),
        ).fetchall()
        if len(run_rows) > _MAX_RUNS:
            raise StorageError("Kayıtlı CTI arama çalışma geçmişi güvenli sınırı aşıyor.")
        runs = {record.id: record for record in (cls._run(row, searches) for row in run_rows)}
        sequences = {record.sequence for record in runs.values()}
        if len(sequences) != len(runs):
            raise StorageError("Kayıtlı CTI arama çalışma sırası bozuk; işlem durduruldu.")
        for run in runs.values():
            if run.definition_sha256 not in {
                event.definition_sha256 for event in events_by_search[run.saved_search_id]
            }:
                raise StorageError("Kayıtlı CTI arama çalışma tanımı bozuk; işlem durduruldu.")
            if run.previous_run_id is not None:
                previous = runs.get(run.previous_run_id)
                if (
                    previous is None or previous.saved_search_id != run.saved_search_id
                    or previous.definition_sha256 != run.definition_sha256
                    or previous.sequence >= run.sequence
                ):
                    raise StorageError("Kayıtlı CTI arama çalışma zinciri bozuk; işlem durduruldu.")
        item_rows = connection.execute(
            f"SELECT {_ITEM_SELECT} FROM cti_saved_search_run_items "
            "ORDER BY run_id, kind, record_id LIMIT ?", (_MAX_ITEMS + 1,),
        ).fetchall()
        if len(item_rows) > _MAX_ITEMS:
            raise StorageError("Kayıtlı CTI arama sonuç geçmişi güvenli sınırı aşıyor.")
        items = tuple(cls._item(row, runs) for row in item_rows)
        entity_rows = connection.execute(
            "SELECT id FROM cti_entities ORDER BY id LIMIT ?", (_MAX_SEARCHES + 1,),
        ).fetchall()
        indicator_rows = connection.execute(
            "SELECT id FROM cti_indicators ORDER BY id LIMIT ?", (_MAX_SEARCHES + 1,),
        ).fetchall()
        if len(entity_rows) > _MAX_SEARCHES or len(indicator_rows) > _MAX_SEARCHES:
            raise StorageError("Kayıtlı CTI arama hedef kapsamı güvenli sınırı aşıyor.")
        entity_ids = {_uuid(row[0]) for row in entity_rows}
        indicator_ids = {_uuid(row[0]) for row in indicator_rows}
        if any(
            item.record_id not in (entity_ids if item.kind == "entity" else indicator_ids)
            for item in items
        ):
            raise StorageError("Kayıtlı CTI arama sonuç hedefi bozuk; işlem durduruldu.")
        by_run: dict[str, list[CtiSavedSearchRunItem]] = {key: [] for key in runs}
        for item in items:
            by_run[item.run_id].append(item)
        for run in runs.values():
            selected = by_run[run.id]
            actions = {action: 0 for action in SAVED_SEARCH_ITEM_ACTIONS}
            for item in selected:
                actions[item.action] += 1
            if (
                len(selected) != run.total_count + run.removed_count
                or actions["added"] != run.added_count
                or actions["updated"] != run.updated_count
                or actions["unchanged"] != run.unchanged_count
                or actions["removed"] != run.removed_count
                or _result_sha(selected) != run.result_sha256
            ):
                raise StorageError("Kayıtlı CTI arama çalışma özeti bozuk; işlem durduruldu.")
        notification_rows = connection.execute(
            f"SELECT {_NOTIFICATION_SELECT} FROM cti_saved_search_notifications "
            "ORDER BY sequence LIMIT ?", (_MAX_NOTIFICATIONS + 1,),
        ).fetchall()
        if len(notification_rows) > _MAX_NOTIFICATIONS:
            raise StorageError("Kayıtlı CTI arama bildirim geçmişi güvenli sınırı aşıyor.")
        notifications = tuple(
            cls._notification(row, searches, runs) for row in notification_rows
        )
        if len({value[0] for value in notifications}) != len(notifications):
            raise StorageError("Kayıtlı CTI arama bildirim sırası bozuk; işlem durduruldu.")
        return searches, events, runs, tuple(items), notifications

    @staticmethod
    def _definition(search: CtiSavedSearch) -> str:
        return definition_sha256(
            query=search.query, query_key=search.query_key, kind=search.kind,
            entity_type=search.entity_type, indicator_type=search.indicator_type,
            active_only=search.active_only,
        )

    def upsert(self, **values) -> CtiSavedSearchMutation:
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._audit(connection)
                row = connection.execute(
                    f"SELECT {_SEARCH_SELECT} FROM cti_saved_searches WHERE name_key=?",
                    (values["name_key"],),
                ).fetchone()
                if row is None:
                    search_id, action = str(uuid4()), "added"
                    connection.execute(
                        "INSERT INTO cti_saved_searches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                        (search_id, values["name_key"], values["display_name"], values["query"],
                         values["query_key"], values["kind"], values["entity_type"],
                         values["indicator_type"], int(values["active_only"]),
                         values["recorded_at"], values["recorded_at"]),
                    )
                else:
                    old = self._search(row)
                    same = (
                        old.display_name == values["display_name"] and old.query == values["query"]
                        and old.query_key == values["query_key"] and old.kind == values["kind"]
                        and old.entity_type == values["entity_type"]
                        and old.indicator_type == values["indicator_type"]
                        and old.active_only == values["active_only"]
                    )
                    if same and old.active:
                        connection.commit()
                        return CtiSavedSearchMutation(action="unchanged", saved_search=old)
                    search_id = old.id
                    action = "reactivated" if not old.active else "updated"
                    connection.execute(
                        "UPDATE cti_saved_searches SET display_name=?, query=?, query_key=?, kind=?, "
                        "entity_type=?, indicator_type=?, active_only=?, active=1, updated_at=? WHERE id=?",
                        (values["display_name"], values["query"], values["query_key"], values["kind"],
                         values["entity_type"], values["indicator_type"], int(values["active_only"]),
                         values["recorded_at"], search_id),
                    )
                search = self._search(connection.execute(
                    f"SELECT {_SEARCH_SELECT} FROM cti_saved_searches WHERE id=?", (search_id,),
                ).fetchone())
                connection.execute(
                    "INSERT INTO cti_saved_search_events VALUES (?, ?, ?, ?, '', ?)",
                    (str(uuid4()), search.id, action, self._definition(search), values["recorded_at"]),
                )
                connection.commit()
                return CtiSavedSearchMutation(action=action, saved_search=search)
            except BaseException:
                connection.rollback()
                raise

    def revoke(self, saved_search_id, *, reason, recorded_at):
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._audit(connection)
                row = connection.execute(
                    f"SELECT {_SEARCH_SELECT} FROM cti_saved_searches WHERE id=?", (saved_search_id,),
                ).fetchone()
                if row is None:
                    raise ValidationError("Kayıtlı CTI araması bulunamadı.")
                search = self._search(row)
                if not search.active:
                    connection.commit()
                    return CtiSavedSearchMutation(action="unchanged", saved_search=search)
                connection.execute(
                    "UPDATE cti_saved_searches SET active=0, updated_at=? WHERE id=?",
                    (recorded_at, search.id),
                )
                connection.execute(
                    "INSERT INTO cti_saved_search_events VALUES (?, ?, 'revoked', ?, ?, ?)",
                    (str(uuid4()), search.id, self._definition(search), reason, recorded_at),
                )
                updated = self._search(connection.execute(
                    f"SELECT {_SEARCH_SELECT} FROM cti_saved_searches WHERE id=?", (search.id,),
                ).fetchone())
                connection.commit()
                return CtiSavedSearchMutation(action="revoked", saved_search=updated)
            except BaseException:
                connection.rollback()
                raise

    def list(self, *, active_only, limit):
        with self._storage._connection(readonly=True) as connection:
            searches, _, runs, _, _ = self._audit(connection)
            selected = sorted(
                (value for value in searches.values() if not active_only or value.active),
                key=lambda value: (value.name_key, value.id),
            )[:limit]
            result = []
            for search in selected:
                history = sorted(
                    (run for run in runs.values() if run.saved_search_id == search.id),
                    key=lambda value: value.sequence, reverse=True,
                )
                result.append(CtiSavedSearchSummary(search, len(history), history[0] if history else None))
            return tuple(result)

    def details(self, saved_search_id, *, event_limit, run_limit):
        with self._storage._connection(readonly=True) as connection:
            searches, events, runs, _, _ = self._audit(connection)
            search = searches.get(saved_search_id)
            if search is None:
                raise ValidationError("Kayıtlı CTI araması bulunamadı.")
            selected_events = list(reversed(
                [value for value in events if value.saved_search_id == saved_search_id]
            ))
            selected_runs = sorted(
                (value for value in runs.values() if value.saved_search_id == saved_search_id),
                key=lambda value: value.sequence, reverse=True,
            )
            return CtiSavedSearchDetails(
                search, tuple(selected_events[:event_limit]), tuple(selected_runs[:run_limit]),
                len(selected_events), len(selected_runs),
            )

    def run(self, saved_search_id, *, executed_at, item_limit):
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                searches, _, runs, all_items, _ = self._audit(connection)
                search = searches.get(saved_search_id)
                if search is None:
                    raise ValidationError("Kayıtlı CTI araması bulunamadı.")
                if not search.active:
                    raise ValidationError("Geri çekilmiş kayıtlı CTI araması çalıştırılamaz.")
                definition = self._definition(search)
                report = SQLiteCtiKnowledgeRepository(self._storage.path).search(
                    query=search.query, query_key=search.query_key, kind=search.kind,
                    entity_type=search.entity_type, indicator_type=search.indicator_type,
                    active_only=search.active_only, checked_at=executed_at,
                    limit=_COMPLETE_RESULT_LIMIT,
                )
                if report.total_match_count != len(report.results):
                    raise StorageError("Kayıtlı CTI arama sonucu tam alınamadı; çalışma kaydedilmedi.")
                history = sorted(
                    (value for value in runs.values() if value.saved_search_id == search.id),
                    key=lambda value: value.sequence, reverse=True,
                )
                latest = history[0] if history else None
                previous = (
                    latest if latest is not None and latest.definition_sha256 == definition else None
                )
                previous_items = {
                    (item.kind, item.record_id): item for item in all_items
                    if previous is not None and item.run_id == previous.id and item.action != "removed"
                }
                run_id = str(uuid4())
                items = []
                for result in report.results:
                    key = (result.kind, result.record_id)
                    state = search_result_state_sha256(result)
                    prior = previous_items.pop(key, None)
                    action = "added" if prior is None else (
                        "unchanged" if prior.state_sha256 == state else "updated"
                    )
                    items.append(CtiSavedSearchRunItem(
                        id=str(uuid4()), run_id=run_id, kind=result.kind,
                        record_id=result.record_id, record_type=result.record_type,
                        display_value=result.display_value, matched_field=result.matched_field,
                        matched_value=result.matched_value, match_type=result.match_type,
                        action=action, state_sha256=state,
                    ))
                for prior in previous_items.values():
                    items.append(CtiSavedSearchRunItem(
                        id=str(uuid4()), run_id=run_id, kind=prior.kind,
                        record_id=prior.record_id, record_type=prior.record_type,
                        display_value=prior.display_value, matched_field=prior.matched_field,
                        matched_value=prior.matched_value, match_type=prior.match_type,
                        action="removed", state_sha256=prior.state_sha256,
                    ))
                items.sort(key=lambda value: (value.action, value.kind, value.record_id))
                counts = {action: 0 for action in SAVED_SEARCH_ITEM_ACTIONS}
                for item in items:
                    counts[item.action] += 1
                current_count = len(items) - counts["removed"]
                run = CtiSavedSearchRun(
                    sequence=0, id=run_id, saved_search_id=search.id,
                    definition_sha256=definition,
                    previous_run_id=previous.id if previous else None,
                    executed_at=executed_at, total_count=current_count,
                    added_count=counts["added"], updated_count=counts["updated"],
                    unchanged_count=counts["unchanged"], removed_count=counts["removed"],
                    result_sha256=_result_sha(items),
                )
                cursor = connection.execute(
                    "INSERT INTO cti_saved_search_runs "
                    "(id, saved_search_id, definition_sha256, previous_run_id, executed_at, "
                    "total_count, added_count, updated_count, unchanged_count, removed_count, result_sha256) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (run.id, run.saved_search_id, run.definition_sha256, run.previous_run_id,
                     run.executed_at, run.total_count, run.added_count, run.updated_count,
                     run.unchanged_count, run.removed_count, run.result_sha256),
                )
                run = CtiSavedSearchRun(
                    sequence=cursor.lastrowid, id=run.id, saved_search_id=run.saved_search_id,
                    definition_sha256=run.definition_sha256, previous_run_id=run.previous_run_id,
                    executed_at=run.executed_at, total_count=run.total_count,
                    added_count=run.added_count, updated_count=run.updated_count,
                    unchanged_count=run.unchanged_count, removed_count=run.removed_count,
                    result_sha256=run.result_sha256,
                )
                connection.executemany(
                    "INSERT INTO cti_saved_search_run_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(item.id, item.run_id, item.kind, item.record_id, item.record_type,
                      item.display_value, item.matched_field, item.matched_value,
                      item.match_type, item.action, item.state_sha256) for item in items],
                )
                notification_id = None
                if (
                    previous is not None
                    and run.added_count + run.updated_count + run.removed_count > 0
                ):
                    notification_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO cti_saved_search_notifications "
                        "(sequence, id, run_id, saved_search_id, event_type, origin, "
                        "created_at, read_at) VALUES (?, ?, ?, ?, "
                        "'cti_saved_search_changed', 'new', ?, NULL)",
                        (next_notification_sequence(connection), notification_id,
                         run.id, search.id, executed_at),
                    )
                connection.commit()
                return CtiSavedSearchRunReport(
                    search, run, tuple(items[:item_limit]), len(items), notification_id,
                )
            except BaseException:
                connection.rollback()
                raise

    def run_details(self, run_id, *, item_limit):
        with self._storage._connection(readonly=True) as connection:
            searches, _, runs, all_items, notifications = self._audit(connection)
            run = runs.get(run_id)
            if run is None:
                raise ValidationError("Kayıtlı CTI arama çalışması bulunamadı.")
            items = sorted(
                (item for item in all_items if item.run_id == run.id),
                key=lambda value: (value.action, value.kind, value.record_id),
            )
            return CtiSavedSearchRunReport(
                searches[run.saved_search_id], run, tuple(items[:item_limit]), len(items),
                next((value[1] for value in notifications if value[2] == run.id), None),
            )

    @classmethod
    def notification_evidence(
        cls, connection, notification_id: str,
    ) -> CtiSavedSearchChangeEvidence:
        searches, _, runs, _, notifications = cls._audit(connection)
        notification = next(
            (value for value in notifications if value[1] == notification_id), None,
        )
        if notification is None:
            raise StorageError("Kayıtlı CTI arama bildiriminin kanıtı bulunamadı.")
        run = runs[notification[2]]
        search = searches[notification[3]]
        return CtiSavedSearchChangeEvidence(
            saved_search_id=search.id, display_name=search.display_name,
            query=search.query, run_id=run.id, executed_at=run.executed_at,
            total_count=run.total_count, added_count=run.added_count,
            updated_count=run.updated_count, unchanged_count=run.unchanged_count,
            removed_count=run.removed_count,
        )

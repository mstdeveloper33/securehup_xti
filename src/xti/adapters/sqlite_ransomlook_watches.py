"""Atomic organization watches over the latest complete RansomLook snapshot."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomlook_claims import SQLiteRansomLookClaimRepository
from xti.adapters.sqlite_collection_receipts import record_collection_step_receipt
from xti.domain.collection_history import CollectionOperationToken
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_assertion_reason, normalize_cti_timestamp
from xti.domain.ransomlook_ransomware import RansomLookClaim, RansomLookClaimSnapshot
from xti.domain.ransomlook_watches import (
    RANSOMLOOK_WATCH_ACTIONS,
    RANSOMLOOK_WATCH_ITEM_ACTIONS,
    RANSOMLOOK_WATCH_MATCH_MODES,
    RansomLookWatch,
    RansomLookWatchDetails,
    RansomLookWatchEvent,
    RansomLookWatchMatch,
    RansomLookWatchMutation,
    RansomLookWatchRun,
    RansomLookWatchRunItem,
    RansomLookWatchRunReport,
    RansomLookWatchSummary,
    match_ransomlook_claim,
    normalize_ransomlook_watch_name,
    normalize_ransomlook_watch_query,
    ransomlook_watch_definition_sha256,
    ransomlook_watch_match_state_sha256,
    ransomlook_watch_name_key,
    ransomlook_watch_query_key,
)


_WATCH_SELECT = (
    "id, name_key, display_name, query, query_key, match_mode, active, "
    "created_at, updated_at"
)
_EVENT_SELECT = "id, watch_id, action, definition_sha256, reason, recorded_at"
_RUN_SELECT = (
    "sequence, id, watch_id, source_run_id, definition_sha256, previous_run_id, "
    "executed_at, total_count, added_count, updated_count, unchanged_count, "
    "removed_count, result_sha256"
)
_ITEM_SELECT = (
    "id, run_id, claim_id, group_name, victim, discovered_at, matched_value, "
    "match_type, action, state_sha256"
)
_MAX_WATCHES = 10_000
_MAX_EVENTS = 100_000
_MAX_RUNS = 100_000
_MAX_ITEMS = 500_000


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid UUID")
    normalized = str(UUID(value))
    if value != normalized:
        raise ValueError("Non-canonical UUID")
    return normalized


def _timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid timestamp")
    normalized = normalize_cti_timestamp(value, field=field)
    if value != normalized:
        raise ValueError("Non-canonical timestamp")
    return normalized


def _sha256(value: object) -> str:
    if (
        not isinstance(value, str) or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("Invalid SHA-256")
    return value


def _result_sha(items) -> str:
    payload = [
        {"claim_id": item.match.claim.id, "state_sha256": item.state_sha256}
        for item in sorted(items, key=lambda value: value.match.claim.id)
        if item.action != "removed"
    ]
    canonical = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class SQLiteRansomLookWatchRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _definition(watch: RansomLookWatch) -> str:
        return ransomlook_watch_definition_sha256(
            query=watch.query, query_key=watch.query_key,
            match_mode=watch.match_mode,
        )

    @classmethod
    def _watch(cls, row) -> RansomLookWatch:
        try:
            watch_id = _uuid(row[0])
            name = normalize_ransomlook_watch_name(row[2])
            if row[5] not in RANSOMLOOK_WATCH_MATCH_MODES:
                raise ValueError("Invalid match mode")
            query = normalize_ransomlook_watch_query(row[3], match_mode=row[5])
            if type(row[6]) is not int or row[6] not in {0, 1}:
                raise ValueError("Invalid activity")
            watch = RansomLookWatch(
                id=watch_id, name_key=ransomlook_watch_name_key(name),
                display_name=name, query=query,
                query_key=ransomlook_watch_query_key(query), match_mode=row[5],
                active=bool(row[6]),
                created_at=_timestamp(row[7], field="RansomLook izleme oluşturma zamanı"),
                updated_at=_timestamp(row[8], field="RansomLook izleme güncelleme zamanı"),
            )
            if row[1] != watch.name_key or row[4] != watch.query_key:
                raise ValueError("Non-canonical watch")
            if datetime.fromisoformat(watch.created_at) > datetime.fromisoformat(watch.updated_at):
                raise ValueError("Reversed watch time")
            return watch
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("RansomLook izleme tanımı bozuk; işlem durduruldu.") from error

    @classmethod
    def _event(cls, row, watches) -> RansomLookWatchEvent:
        try:
            event_id, watch_id = _uuid(row[0]), _uuid(row[1])
            if watch_id not in watches or row[2] not in RANSOMLOOK_WATCH_ACTIONS:
                raise ValueError("Invalid event")
            reason = row[4]
            if row[2] == "revoked":
                reason = normalize_assertion_reason(reason)
            elif reason != "":
                raise ValueError("Unexpected reason")
            return RansomLookWatchEvent(
                event_id, watch_id, row[2], _sha256(row[3]), reason,
                _timestamp(row[5], field="RansomLook izleme olay zamanı"),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("RansomLook izleme geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _run(row, watches, source_run_ids) -> RansomLookWatchRun:
        try:
            if type(row[0]) is not int or row[0] < 1:
                raise ValueError("Invalid sequence")
            run_id, watch_id, source_run_id = _uuid(row[1]), _uuid(row[2]), _uuid(row[3])
            if watch_id not in watches or source_run_id not in source_run_ids:
                raise ValueError("Missing run relation")
            previous = _uuid(row[5]) if row[5] is not None else None
            counts = row[7:12]
            if any(type(value) is not int or value < 0 for value in counts):
                raise ValueError("Invalid counts")
            if row[7] != row[8] + row[9] + row[10]:
                raise ValueError("Inconsistent current count")
            return RansomLookWatchRun(
                row[0], run_id, watch_id, source_run_id, _sha256(row[4]), previous,
                _timestamp(row[6], field="RansomLook izleme çalışma zamanı"),
                *counts, _sha256(row[12]),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("RansomLook izleme çalışması bozuk; işlem durduruldu.") from error

    @staticmethod
    def _item(row, runs) -> RansomLookWatchRunItem:
        try:
            item_id, run_id = _uuid(row[0]), _uuid(row[1])
            if run_id not in runs:
                raise ValueError("Missing run")
            claim = SQLiteRansomLookClaimRepository._claim(RansomLookClaim(
                id=_sha256(row[2]), group=row[3], victim=row[4], discovered_at=row[5],
            ))
            if row[6] != claim.victim or row[7] not in RANSOMLOOK_WATCH_MATCH_MODES:
                raise ValueError("Invalid match")
            if row[8] not in RANSOMLOOK_WATCH_ITEM_ACTIONS:
                raise ValueError("Invalid action")
            match = RansomLookWatchMatch(claim, row[6], row[7])
            state = _sha256(row[9])
            if state != ransomlook_watch_match_state_sha256(match):
                raise ValueError("Invalid state")
            return RansomLookWatchRunItem(item_id, run_id, match, row[8], state)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("RansomLook izleme sonucu bozuk; işlem durduruldu.") from error

    @classmethod
    def _audit(cls, connection):
        watch_rows = connection.execute(
            f"SELECT {_WATCH_SELECT} FROM ransomlook_watches ORDER BY id LIMIT ?",
            (_MAX_WATCHES + 1,),
        ).fetchall()
        if len(watch_rows) > _MAX_WATCHES:
            raise StorageError("RansomLook izleme sayısı güvenli sınırı aşıyor.")
        watches = {watch.id: watch for watch in map(cls._watch, watch_rows)}

        event_rows = connection.execute(
            f"SELECT {_EVENT_SELECT} FROM ransomlook_watch_events ORDER BY rowid LIMIT ?",
            (_MAX_EVENTS + 1,),
        ).fetchall()
        if len(event_rows) > _MAX_EVENTS:
            raise StorageError("RansomLook izleme olay sayısı güvenli sınırı aşıyor.")
        events = tuple(cls._event(row, watches) for row in event_rows)
        by_watch_events = {key: [] for key in watches}
        for event in events:
            by_watch_events[event.watch_id].append(event)
        for watch in watches.values():
            history = by_watch_events[watch.id]
            if (
                not history or history[0].action != "added"
                or history[-1].definition_sha256 != cls._definition(watch)
                or (watch.active and history[-1].action == "revoked")
                or (not watch.active and history[-1].action != "revoked")
                or history[0].recorded_at != watch.created_at
                or history[-1].recorded_at != watch.updated_at
                or any(
                    datetime.fromisoformat(left.recorded_at)
                    > datetime.fromisoformat(right.recorded_at)
                    for left, right in zip(history, history[1:])
                )
            ):
                raise StorageError(
                    "RansomLook izleme yaşam döngüsü bozuk; işlem durduruldu."
                )

        source_rows = connection.execute(
            "SELECT id FROM ransomlook_claim_runs WHERE status='complete'"
        ).fetchall()
        source_run_ids = {_uuid(row[0]) for row in source_rows}
        run_rows = connection.execute(
            f"SELECT {_RUN_SELECT} FROM ransomlook_watch_runs ORDER BY sequence LIMIT ?",
            (_MAX_RUNS + 1,),
        ).fetchall()
        if len(run_rows) > _MAX_RUNS:
            raise StorageError("RansomLook izleme çalışma sayısı güvenli sınırı aşıyor.")
        runs = {
            run.id: run
            for run in (cls._run(row, watches, source_run_ids) for row in run_rows)
        }
        if len({run.sequence for run in runs.values()}) != len(runs):
            raise StorageError("RansomLook izleme çalışma sırası bozuk.")
        definitions = {
            key: {event.definition_sha256 for event in values}
            for key, values in by_watch_events.items()
        }
        for run in runs.values():
            if run.definition_sha256 not in definitions[run.watch_id]:
                raise StorageError("RansomLook izleme çalışma tanımı bozuk.")
            if run.previous_run_id is not None:
                previous = runs.get(run.previous_run_id)
                if (
                    previous is None or previous.watch_id != run.watch_id
                    or previous.definition_sha256 != run.definition_sha256
                    or previous.sequence >= run.sequence
                ):
                    raise StorageError("RansomLook izleme çalışma zinciri bozuk.")

        item_rows = connection.execute(
            f"SELECT {_ITEM_SELECT} FROM ransomlook_watch_run_items "
            "ORDER BY run_id, claim_id LIMIT ?", (_MAX_ITEMS + 1,),
        ).fetchall()
        if len(item_rows) > _MAX_ITEMS:
            raise StorageError("RansomLook izleme sonuç sayısı güvenli sınırı aşıyor.")
        items = tuple(cls._item(row, runs) for row in item_rows)
        by_run = {key: [] for key in runs}
        for item in items:
            by_run[item.run_id].append(item)
        for run in runs.values():
            selected = by_run[run.id]
            counts = {action: 0 for action in RANSOMLOOK_WATCH_ITEM_ACTIONS}
            for item in selected:
                counts[item.action] += 1
            if (
                len(selected) != run.total_count + run.removed_count
                or counts["added"] != run.added_count
                or counts["updated"] != run.updated_count
                or counts["unchanged"] != run.unchanged_count
                or counts["removed"] != run.removed_count
                or _result_sha(selected) != run.result_sha256
            ):
                raise StorageError("RansomLook izleme çalışma özeti bozuk.")
        return watches, events, runs, items

    def upsert(self, **values) -> RansomLookWatchMutation:
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._audit(connection)
                row = connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM ransomlook_watches WHERE name_key=?",
                    (values["name_key"],),
                ).fetchone()
                if row is None:
                    watch_id, action = str(uuid4()), "added"
                    connection.execute(
                        "INSERT INTO ransomlook_watches VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                        (
                            watch_id, values["name_key"], values["display_name"],
                            values["query"], values["query_key"], values["match_mode"],
                            values["recorded_at"], values["recorded_at"],
                        ),
                    )
                else:
                    old = self._watch(row)
                    same = (
                        old.display_name == values["display_name"]
                        and old.query == values["query"]
                        and old.query_key == values["query_key"]
                        and old.match_mode == values["match_mode"]
                    )
                    if same and old.active:
                        connection.commit()
                        return RansomLookWatchMutation("unchanged", old)
                    watch_id = old.id
                    action = "reactivated" if not old.active else "updated"
                    connection.execute(
                        "UPDATE ransomlook_watches SET display_name=?, query=?, query_key=?, "
                        "match_mode=?, active=1, updated_at=? WHERE id=?",
                        (
                            values["display_name"], values["query"], values["query_key"],
                            values["match_mode"], values["recorded_at"], watch_id,
                        ),
                    )
                watch = self._watch(connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM ransomlook_watches WHERE id=?",
                    (watch_id,),
                ).fetchone())
                connection.execute(
                    "INSERT INTO ransomlook_watch_events VALUES (?, ?, ?, ?, '', ?)",
                    (
                        str(uuid4()), watch.id, action, self._definition(watch),
                        values["recorded_at"],
                    ),
                )
                connection.commit()
                return RansomLookWatchMutation(action, watch)
            except BaseException:
                connection.rollback()
                raise

    def revoke(self, watch_id, *, reason, recorded_at):
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._audit(connection)
                row = connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM ransomlook_watches WHERE id=?",
                    (watch_id,),
                ).fetchone()
                if row is None:
                    raise ValidationError("RansomLook izlemesi bulunamadı.")
                watch = self._watch(row)
                if not watch.active:
                    connection.commit()
                    return RansomLookWatchMutation("unchanged", watch)
                connection.execute(
                    "UPDATE ransomlook_watches SET active=0, updated_at=? WHERE id=?",
                    (recorded_at, watch.id),
                )
                connection.execute(
                    "INSERT INTO ransomlook_watch_events VALUES "
                    "(?, ?, 'revoked', ?, ?, ?)",
                    (
                        str(uuid4()), watch.id, self._definition(watch), reason,
                        recorded_at,
                    ),
                )
                updated = self._watch(connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM ransomlook_watches WHERE id=?",
                    (watch.id,),
                ).fetchone())
                connection.commit()
                return RansomLookWatchMutation("revoked", updated)
            except BaseException:
                connection.rollback()
                raise

    def list(self, *, active_only, limit):
        with self._storage._connection(readonly=True) as connection:
            watches, _, runs, _ = self._audit(connection)
        selected = sorted(
            (watch for watch in watches.values() if not active_only or watch.active),
            key=lambda watch: (watch.name_key, watch.id),
        )[:limit]
        return tuple(
            RansomLookWatchSummary(
                watch,
                len(history := [run for run in runs.values() if run.watch_id == watch.id]),
                max(history, key=lambda run: run.sequence) if history else None,
            )
            for watch in selected
        )

    def details(self, watch_id, *, event_limit, run_limit):
        with self._storage._connection(readonly=True) as connection:
            watches, events, runs, _ = self._audit(connection)
        watch = watches.get(watch_id)
        if watch is None:
            raise ValidationError("RansomLook izlemesi bulunamadı.")
        selected_events = list(reversed([
            event for event in events if event.watch_id == watch.id
        ]))
        selected_runs = sorted(
            (run for run in runs.values() if run.watch_id == watch.id),
            key=lambda run: run.sequence, reverse=True,
        )
        return RansomLookWatchDetails(
            watch, tuple(selected_events[:event_limit]), tuple(selected_runs[:run_limit]),
            len(selected_events), len(selected_runs),
        )

    @staticmethod
    def _insert_item(connection, item: RansomLookWatchRunItem) -> None:
        claim = item.match.claim
        connection.execute(
            "INSERT INTO ransomlook_watch_run_items VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id, item.run_id, claim.id, claim.group, claim.victim,
                claim.discovered_at, item.match.matched_value, item.match.match_type,
                item.action, item.state_sha256,
            ),
        )

    def run(
        self, watch_id, snapshot, *, executed_at, item_limit,
        operation: CollectionOperationToken | None = None,
    ):
        if not isinstance(snapshot, RansomLookClaimSnapshot):
            raise ValidationError("RansomLook izleme snapshot'ı geçersiz.")
        try:
            executed_at = _timestamp(executed_at, field="RansomLook izleme çalışma zamanı")
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("RansomLook izleme çalışma zamanı geçersiz.") from error
        if type(item_limit) is not int or not 1 <= item_limit <= 500:
            raise ValidationError("RansomLook izleme sonuç sınırı 1–500 arasında olmalı.")
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                watches, _, runs, all_items = self._audit(connection)
                watch = watches.get(watch_id)
                if watch is None:
                    raise ValidationError("RansomLook izlemesi bulunamadı.")
                if not watch.active:
                    raise ValidationError("Geri çekilmiş RansomLook izlemesi çalıştırılamaz.")

                source_runs, source_items = SQLiteRansomLookClaimRepository._audit(connection)
                source_run = next(
                    (run for run in reversed(source_runs) if run.status == "complete"), None,
                )
                current_claims: dict[str, RansomLookClaim] = {}
                by_source_run: dict[str, list] = {}
                for item in source_items:
                    by_source_run.setdefault(item.run_id, []).append(item)
                for source_history in source_runs:
                    if source_run is not None and source_history.sequence > source_run.sequence:
                        break
                    for item in by_source_run.get(source_history.id, ()):
                        if item.action in {"added", "updated"}:
                            current_claims[item.claim.id] = item.claim
                        elif item.action == "removed":
                            current_claims.pop(item.claim.id, None)
                supplied = {claim.id: claim for claim in snapshot.claims}
                if (
                    source_run is None or source_run != snapshot.run
                    or len(supplied) != len(snapshot.claims) or supplied != current_claims
                ):
                    raise StorageError(
                        "RansomLook kaynak snapshot kanıtı yerel geçmişle uyuşmuyor."
                    )

                definition = self._definition(watch)
                history = sorted(
                    (run for run in runs.values() if run.watch_id == watch.id),
                    key=lambda run: run.sequence, reverse=True,
                )
                latest = history[0] if history else None
                previous = latest if latest and latest.definition_sha256 == definition else None
                previous_items = {
                    item.match.claim.id: item for item in all_items
                    if previous is not None and item.run_id == previous.id
                    and item.action != "removed"
                }
                run_id = str(uuid4())
                items: list[RansomLookWatchRunItem] = []
                for claim in snapshot.claims:
                    match = match_ransomlook_claim(
                        claim, query_key=watch.query_key, match_mode=watch.match_mode,
                    )
                    if match is None:
                        continue
                    state = ransomlook_watch_match_state_sha256(match)
                    prior = previous_items.pop(claim.id, None)
                    action = "added" if prior is None else (
                        "unchanged" if prior.state_sha256 == state else "updated"
                    )
                    items.append(RansomLookWatchRunItem(
                        str(uuid4()), run_id, match, action, state,
                    ))
                for prior in previous_items.values():
                    items.append(RansomLookWatchRunItem(
                        str(uuid4()), run_id, prior.match, "removed", prior.state_sha256,
                    ))
                order = {"added": 0, "updated": 1, "removed": 2, "unchanged": 3}
                items.sort(key=lambda item: (
                    order[item.action], item.match.claim.victim.casefold(),
                    item.match.claim.id,
                ))
                counts = {action: 0 for action in RANSOMLOOK_WATCH_ITEM_ACTIONS}
                for item in items:
                    counts[item.action] += 1
                total = len(items) - counts["removed"]
                result_sha = _result_sha(items)
                cursor = connection.execute(
                    "INSERT INTO ransomlook_watch_runs "
                    "(id, watch_id, source_run_id, definition_sha256, previous_run_id, "
                    "executed_at, total_count, added_count, updated_count, unchanged_count, "
                    "removed_count, result_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id, watch.id, snapshot.run.id, definition,
                        previous.id if previous else None, executed_at, total,
                        counts["added"], counts["updated"], counts["unchanged"],
                        counts["removed"], result_sha,
                    ),
                )
                for item in items:
                    self._insert_item(connection, item)
                run = RansomLookWatchRun(
                    cursor.lastrowid, run_id, watch.id, snapshot.run.id, definition,
                    previous.id if previous else None, executed_at, total,
                    counts["added"], counts["updated"], counts["unchanged"],
                    counts["removed"], result_sha,
                )
                record_collection_step_receipt(
                    connection, operation, result_kind="ransomlook_watch_run",
                    result_id=run.id, result_status="complete",
                )
                connection.commit()
                attention = 0 if previous is None else run.added_count + run.updated_count
                return RansomLookWatchRunReport(
                    watch, run, tuple(items[:item_limit]), len(items), attention,
                    previous is None,
                )
            except BaseException:
                connection.rollback()
                raise

    def run_details(self, run_id, *, item_limit):
        with self._storage._connection(readonly=True) as connection:
            watches, _, runs, items = self._audit(connection)
        run = runs.get(run_id)
        if run is None:
            raise ValidationError("RansomLook izleme çalışması bulunamadı.")
        selected = sorted(
            (item for item in items if item.run_id == run.id),
            key=lambda item: (
                item.action, item.match.claim.victim.casefold(), item.match.claim.id,
            ),
        )
        attention = (
            0 if run.previous_run_id is None else run.added_count + run.updated_count
        )
        return RansomLookWatchRunReport(
            watches[run.watch_id], run, tuple(selected[:item_limit]), len(selected),
            attention, run.previous_run_id is None,
        )

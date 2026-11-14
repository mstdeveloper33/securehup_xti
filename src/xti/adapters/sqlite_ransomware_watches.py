"""Atomic local watches over the latest complete ransomware-claim snapshot."""

from datetime import datetime
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_collection_receipts import record_collection_step_receipt
from xti.domain.collection_history import CollectionOperationToken
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cti_indicators import normalize_assertion_reason, normalize_cti_timestamp
from xti.domain.ransomware_claims import RansomwareClaim, RansomwareClaimSnapshot
from xti.domain.ransomware_watches import (
    RANSOMWARE_WATCH_ACTIONS,
    RANSOMWARE_WATCH_ITEM_ACTIONS,
    RANSOMWARE_WATCH_KINDS,
    RANSOMWARE_WATCH_MATCH_MODES,
    RansomwareWatch,
    RansomwareWatchChangeEvidence,
    RansomwareWatchDetails,
    RansomwareWatchEvent,
    RansomwareWatchMatch,
    RansomwareWatchMutation,
    RansomwareWatchRun,
    RansomwareWatchRunItem,
    RansomwareWatchRunReport,
    RansomwareWatchSummary,
    match_ransomware_claim,
    normalize_ransomware_watch_name,
    normalize_ransomware_watch_query,
    ransomware_watch_definition_sha256,
    ransomware_watch_match_state_sha256,
    ransomware_watch_name_key,
    ransomware_watch_query_key,
)


_WATCH_SELECT = (
    "id, name_key, display_name, kind, query, query_key, match_mode, active, "
    "created_at, updated_at"
)
_EVENT_SELECT = "id, watch_id, action, definition_sha256, reason, recorded_at"
_RUN_SELECT = (
    "sequence, id, watch_id, source_run_id, definition_sha256, previous_run_id, "
    "executed_at, total_count, added_count, updated_count, unchanged_count, "
    "removed_count, result_sha256"
)
_ITEM_SELECT = (
    "id, run_id, claim_id, group_name, victim, country, sector, discovered_at, "
    "claim_status, website, last_seen_at, delisted_at, first_party, "
    "source_post_available, matched_field, matched_value, match_type, action, state_sha256"
)
_NOTIFICATION_SELECT = (
    "sequence, id, run_id, watch_id, event_type, origin, created_at, read_at"
)
_MAX_WATCHES = 10_000
_MAX_EVENTS = 100_000
_MAX_RUNS = 100_000
_MAX_ITEMS = 500_000
_MAX_NOTIFICATIONS = 100_000


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


def _result_sha(items: tuple[RansomwareWatchRunItem, ...] | list[RansomwareWatchRunItem]) -> str:
    payload = [
        {"claim_id": item.match.claim.id, "state_sha256": item.state_sha256}
        for item in sorted(items, key=lambda value: value.match.claim.id)
        if item.action != "removed"
    ]
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SQLiteRansomwareWatchRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _definition(watch: RansomwareWatch) -> str:
        return ransomware_watch_definition_sha256(
            query=watch.query, query_key=watch.query_key,
            kind=watch.kind, match_mode=watch.match_mode,
        )

    @classmethod
    def _watch(cls, row) -> RansomwareWatch:
        try:
            watch_id = _uuid(row[0])
            name = normalize_ransomware_watch_name(row[2])
            if row[3] not in RANSOMWARE_WATCH_KINDS or row[6] not in RANSOMWARE_WATCH_MATCH_MODES:
                raise ValueError("Invalid watch mode")
            query = normalize_ransomware_watch_query(
                row[4], kind=row[3], match_mode=row[6],
            )
            if type(row[7]) is not int or row[7] not in {0, 1}:
                raise ValueError("Invalid activity")
            watch = RansomwareWatch(
                id=watch_id, name_key=ransomware_watch_name_key(name), display_name=name,
                kind=row[3], query=query,
                query_key=ransomware_watch_query_key(query, kind=row[3]),
                match_mode=row[6], active=bool(row[7]),
                created_at=_timestamp(row[8], field="ransomware izleme oluşturma zamanı"),
                updated_at=_timestamp(row[9], field="ransomware izleme güncelleme zamanı"),
            )
            if row[1] != watch.name_key or row[5] != watch.query_key:
                raise ValueError("Non-canonical watch")
            if datetime.fromisoformat(watch.created_at) > datetime.fromisoformat(watch.updated_at):
                raise ValueError("Reversed watch time")
            return watch
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Ransomware izleme tanımı bozuk; işlem durduruldu.") from error

    @classmethod
    def _event(cls, row, watches: dict[str, RansomwareWatch]) -> RansomwareWatchEvent:
        try:
            event_id, watch_id = _uuid(row[0]), _uuid(row[1])
            if watch_id not in watches or row[2] not in RANSOMWARE_WATCH_ACTIONS:
                raise ValueError("Invalid event")
            reason = row[4]
            if row[2] == "revoked":
                reason = normalize_assertion_reason(reason)
            elif reason != "":
                raise ValueError("Unexpected reason")
            return RansomwareWatchEvent(
                event_id, watch_id, row[2], _sha256(row[3]), reason,
                _timestamp(row[5], field="ransomware izleme olay zamanı"),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Ransomware izleme geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _run(row, watches: dict[str, RansomwareWatch], source_run_ids: set[str]) -> RansomwareWatchRun:
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
            return RansomwareWatchRun(
                row[0], run_id, watch_id, source_run_id, _sha256(row[4]), previous,
                _timestamp(row[6], field="ransomware izleme çalışma zamanı"),
                *counts, _sha256(row[12]),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Ransomware izleme çalışması bozuk; işlem durduruldu.") from error

    @staticmethod
    def _item(row, runs: dict[str, RansomwareWatchRun]) -> RansomwareWatchRunItem:
        try:
            item_id, run_id = _uuid(row[0]), _uuid(row[1])
            if run_id not in runs:
                raise ValueError("Missing run")
            claim = RansomwareClaim(
                id=row[2], group=row[3], victim=row[4], country=row[5], sector=row[6],
                discovered_at=row[7], status=row[8], website=row[9],
                last_seen_at=row[10], delisted_at=row[11],
                first_party=None if row[12] is None else bool(row[12]),
                source_post_available=bool(row[13]),
            )
            claim = SQLiteRansomwareClaimRepository._claim(claim)
            if row[12] not in {None, 0, 1} or row[13] not in {0, 1}:
                raise ValueError("Invalid booleans")
            if row[14] not in {"victim", "website"} or row[16] not in {
                "exact", "contains", "subdomain",
            } or row[17] not in RANSOMWARE_WATCH_ITEM_ACTIONS:
                raise ValueError("Invalid match")
            if not isinstance(row[15], str) or not 1 <= len(row[15]) <= 300:
                raise ValueError("Invalid matched value")
            if row[14] == "victim":
                if row[15] != claim.victim or row[16] not in {"exact", "contains"}:
                    raise ValueError("Invalid victim match")
            elif normalize_domain(row[15]) != row[15] or row[16] not in {
                "exact", "subdomain",
            }:
                raise ValueError("Invalid website match")
            match = RansomwareWatchMatch(claim, row[14], row[15], row[16])
            state = _sha256(row[18])
            if state != ransomware_watch_match_state_sha256(match):
                raise ValueError("Invalid state")
            return RansomwareWatchRunItem(item_id, run_id, match, row[17], state)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Ransomware izleme sonucu bozuk; işlem durduruldu.") from error

    @staticmethod
    def _notification(row, watches, runs):
        try:
            if type(row[0]) is not int or row[0] < 1:
                raise ValueError("Invalid sequence")
            notification_id, run_id, watch_id = _uuid(row[1]), _uuid(row[2]), _uuid(row[3])
            run, watch = runs.get(run_id), watches.get(watch_id)
            if (
                run is None or watch is None or run.watch_id != watch.id
                or run.previous_run_id is None or run.added_count + run.updated_count == 0
                or row[4] != "ransomware_watch_changed" or row[5] != "new"
            ):
                raise ValueError("Invalid notification")
            created = _timestamp(row[6], field="ransomware izleme bildirim zamanı")
            read_at = (
                _timestamp(row[7], field="ransomware izleme bildirim okuma zamanı")
                if row[7] is not None else None
            )
            if created != run.executed_at:
                raise ValueError("Time mismatch")
            return row[0], notification_id, run_id, watch_id, created, read_at
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Ransomware izleme bildirimi bozuk; işlem durduruldu.") from error

    @classmethod
    def _audit(cls, connection):
        watch_rows = connection.execute(
            f"SELECT {_WATCH_SELECT} FROM ransomware_watches ORDER BY id LIMIT ?",
            (_MAX_WATCHES + 1,),
        ).fetchall()
        if len(watch_rows) > _MAX_WATCHES:
            raise StorageError("Ransomware izleme sayısı güvenli sınırı aşıyor.")
        watches = {watch.id: watch for watch in map(cls._watch, watch_rows)}
        event_rows = connection.execute(
            f"SELECT {_EVENT_SELECT} FROM ransomware_watch_events ORDER BY rowid LIMIT ?",
            (_MAX_EVENTS + 1,),
        ).fetchall()
        if len(event_rows) > _MAX_EVENTS:
            raise StorageError("Ransomware izleme olay sayısı güvenli sınırı aşıyor.")
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
                raise StorageError("Ransomware izleme yaşam döngüsü bozuk; işlem durduruldu.")
        source_rows = connection.execute(
            "SELECT id FROM ransomware_claim_runs WHERE status='complete'"
        ).fetchall()
        source_run_ids = {_uuid(row[0]) for row in source_rows}
        run_rows = connection.execute(
            f"SELECT {_RUN_SELECT} FROM ransomware_watch_runs ORDER BY sequence LIMIT ?",
            (_MAX_RUNS + 1,),
        ).fetchall()
        if len(run_rows) > _MAX_RUNS:
            raise StorageError("Ransomware izleme çalışma sayısı güvenli sınırı aşıyor.")
        runs = {
            run.id: run for run in
            (cls._run(row, watches, source_run_ids) for row in run_rows)
        }
        if len({run.sequence for run in runs.values()}) != len(runs):
            raise StorageError("Ransomware izleme çalışma sırası bozuk.")
        definitions = {
            key: {event.definition_sha256 for event in values}
            for key, values in by_watch_events.items()
        }
        for run in runs.values():
            if run.definition_sha256 not in definitions[run.watch_id]:
                raise StorageError("Ransomware izleme çalışma tanımı bozuk.")
            if run.previous_run_id is not None:
                previous = runs.get(run.previous_run_id)
                if (
                    previous is None or previous.watch_id != run.watch_id
                    or previous.definition_sha256 != run.definition_sha256
                    or previous.sequence >= run.sequence
                ):
                    raise StorageError("Ransomware izleme çalışma zinciri bozuk.")
        item_rows = connection.execute(
            f"SELECT {_ITEM_SELECT} FROM ransomware_watch_run_items "
            "ORDER BY run_id, claim_id LIMIT ?", (_MAX_ITEMS + 1,),
        ).fetchall()
        if len(item_rows) > _MAX_ITEMS:
            raise StorageError("Ransomware izleme sonuç sayısı güvenli sınırı aşıyor.")
        items = tuple(cls._item(row, runs) for row in item_rows)
        by_run = {key: [] for key in runs}
        for item in items:
            by_run[item.run_id].append(item)
        for run in runs.values():
            selected = by_run[run.id]
            counts = {action: 0 for action in RANSOMWARE_WATCH_ITEM_ACTIONS}
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
                raise StorageError("Ransomware izleme çalışma özeti bozuk.")
        notification_rows = connection.execute(
            f"SELECT {_NOTIFICATION_SELECT} FROM ransomware_watch_notifications "
            "ORDER BY sequence LIMIT ?", (_MAX_NOTIFICATIONS + 1,),
        ).fetchall()
        if len(notification_rows) > _MAX_NOTIFICATIONS:
            raise StorageError("Ransomware izleme bildirim sayısı güvenli sınırı aşıyor.")
        notifications = tuple(cls._notification(row, watches, runs) for row in notification_rows)
        if len({row[0] for row in notifications}) != len(notifications):
            raise StorageError("Ransomware izleme bildirim sırası bozuk.")
        return watches, events, runs, items, notifications

    def upsert(self, **values) -> RansomwareWatchMutation:
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._audit(connection)
                row = connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM ransomware_watches WHERE name_key=?",
                    (values["name_key"],),
                ).fetchone()
                if row is None:
                    watch_id, action = str(uuid4()), "added"
                    connection.execute(
                        "INSERT INTO ransomware_watches VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                        (watch_id, values["name_key"], values["display_name"], values["kind"],
                         values["query"], values["query_key"], values["match_mode"],
                         values["recorded_at"], values["recorded_at"]),
                    )
                else:
                    old = self._watch(row)
                    same = (
                        old.display_name == values["display_name"]
                        and old.kind == values["kind"] and old.query == values["query"]
                        and old.query_key == values["query_key"]
                        and old.match_mode == values["match_mode"]
                    )
                    if same and old.active:
                        connection.commit()
                        return RansomwareWatchMutation("unchanged", old)
                    watch_id = old.id
                    action = "reactivated" if not old.active else "updated"
                    connection.execute(
                        "UPDATE ransomware_watches SET display_name=?, kind=?, query=?, "
                        "query_key=?, match_mode=?, active=1, updated_at=? WHERE id=?",
                        (values["display_name"], values["kind"], values["query"],
                         values["query_key"], values["match_mode"], values["recorded_at"],
                         watch_id),
                    )
                watch = self._watch(connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM ransomware_watches WHERE id=?", (watch_id,),
                ).fetchone())
                connection.execute(
                    "INSERT INTO ransomware_watch_events VALUES (?, ?, ?, ?, '', ?)",
                    (str(uuid4()), watch.id, action, self._definition(watch), values["recorded_at"]),
                )
                connection.commit()
                return RansomwareWatchMutation(action, watch)
            except BaseException:
                connection.rollback()
                raise

    def revoke(self, watch_id, *, reason, recorded_at):
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._audit(connection)
                row = connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM ransomware_watches WHERE id=?", (watch_id,),
                ).fetchone()
                if row is None:
                    raise ValidationError("Ransomware izlemesi bulunamadı.")
                watch = self._watch(row)
                if not watch.active:
                    connection.commit()
                    return RansomwareWatchMutation("unchanged", watch)
                connection.execute(
                    "UPDATE ransomware_watches SET active=0, updated_at=? WHERE id=?",
                    (recorded_at, watch.id),
                )
                connection.execute(
                    "INSERT INTO ransomware_watch_events VALUES (?, ?, 'revoked', ?, ?, ?)",
                    (str(uuid4()), watch.id, self._definition(watch), reason, recorded_at),
                )
                updated = self._watch(connection.execute(
                    f"SELECT {_WATCH_SELECT} FROM ransomware_watches WHERE id=?", (watch.id,),
                ).fetchone())
                connection.commit()
                return RansomwareWatchMutation("revoked", updated)
            except BaseException:
                connection.rollback()
                raise

    def list(self, *, active_only, limit):
        with self._storage._connection(readonly=True) as connection:
            watches, _, runs, _, _ = self._audit(connection)
        selected = sorted(
            (watch for watch in watches.values() if not active_only or watch.active),
            key=lambda watch: (watch.name_key, watch.id),
        )[:limit]
        return tuple(
            RansomwareWatchSummary(
                watch,
                len(history := [run for run in runs.values() if run.watch_id == watch.id]),
                max(history, key=lambda run: run.sequence) if history else None,
            )
            for watch in selected
        )

    def details(self, watch_id, *, event_limit, run_limit):
        with self._storage._connection(readonly=True) as connection:
            watches, events, runs, _, _ = self._audit(connection)
        watch = watches.get(watch_id)
        if watch is None:
            raise ValidationError("Ransomware izlemesi bulunamadı.")
        selected_events = list(reversed([event for event in events if event.watch_id == watch.id]))
        selected_runs = sorted(
            (run for run in runs.values() if run.watch_id == watch.id),
            key=lambda run: run.sequence, reverse=True,
        )
        return RansomwareWatchDetails(
            watch, tuple(selected_events[:event_limit]), tuple(selected_runs[:run_limit]),
            len(selected_events), len(selected_runs),
        )

    @staticmethod
    def _insert_item(connection, item: RansomwareWatchRunItem) -> None:
        claim, match = item.match.claim, item.match
        connection.execute(
            "INSERT INTO ransomware_watch_run_items VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item.id, item.run_id, claim.id, claim.group, claim.victim, claim.country,
             claim.sector, claim.discovered_at, claim.status, claim.website,
             claim.last_seen_at, claim.delisted_at,
             None if claim.first_party is None else int(claim.first_party),
             int(claim.source_post_available), match.matched_field, match.matched_value,
             match.match_type, item.action, item.state_sha256),
        )

    def run(
        self, watch_id, snapshot, *, executed_at, item_limit,
        operation: CollectionOperationToken | None = None,
    ):
        if not isinstance(snapshot, RansomwareClaimSnapshot):
            raise ValidationError("Ransomware izleme snapshot'ı geçersiz.")
        try:
            executed_at = _timestamp(executed_at, field="ransomware izleme çalışma zamanı")
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise ValidationError("Ransomware izleme çalışma zamanı geçersiz.") from error
        if type(item_limit) is not int or not 1 <= item_limit <= 500:
            raise ValidationError("Ransomware izleme sonuç sınırı 1–500 arasında olmalı.")
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                watches, _, runs, all_items, _ = self._audit(connection)
                watch = watches.get(watch_id)
                if watch is None:
                    raise ValidationError("Ransomware izlemesi bulunamadı.")
                if not watch.active:
                    raise ValidationError("Geri çekilmiş ransomware izlemesi çalıştırılamaz.")
                latest_source = connection.execute(
                    "SELECT id FROM ransomware_claim_runs WHERE status='complete' "
                    "ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                if latest_source is None or latest_source[0] != snapshot.run.id:
                    raise StorageError(
                        "Ransomware kaynak snapshot'ı çalışma sırasında değişti; yeniden deneyin."
                    )
                source_runs, source_items = SQLiteRansomwareClaimRepository._audit(connection)
                source_run = next(
                    (run for run in reversed(source_runs) if run.status == "complete"), None,
                )
                current_claims: dict[str, RansomwareClaim] = {}
                source_items_by_run: dict[str, list] = {}
                for item in source_items:
                    source_items_by_run.setdefault(item.run_id, []).append(item)
                for run in source_runs:
                    if source_run is not None and run.sequence > source_run.sequence:
                        break
                    for item in source_items_by_run.get(run.id, ()):
                        if item.action in {"added", "updated"}:
                            current_claims[item.claim.id] = item.claim
                        elif item.action == "removed":
                            current_claims.pop(item.claim.id, None)
                supplied = {claim.id: claim for claim in snapshot.claims}
                if (
                    source_run is None or source_run != snapshot.run
                    or len(supplied) != len(snapshot.claims)
                    or supplied != current_claims
                ):
                    raise StorageError(
                        "Ransomware kaynak snapshot kanıtı yerel geçmişle uyuşmuyor."
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
                    if previous is not None and item.run_id == previous.id and item.action != "removed"
                }
                run_id = str(uuid4())
                items: list[RansomwareWatchRunItem] = []
                for claim in snapshot.claims:
                    match = match_ransomware_claim(
                        claim, kind=watch.kind, query_key=watch.query_key,
                        match_mode=watch.match_mode,
                    )
                    if match is None:
                        continue
                    state = ransomware_watch_match_state_sha256(match)
                    prior = previous_items.pop(claim.id, None)
                    action = "added" if prior is None else (
                        "unchanged" if prior.state_sha256 == state else "updated"
                    )
                    items.append(RansomwareWatchRunItem(
                        str(uuid4()), run_id, match, action, state,
                    ))
                for prior in previous_items.values():
                    items.append(RansomwareWatchRunItem(
                        str(uuid4()), run_id, prior.match, "removed", prior.state_sha256,
                    ))
                order = {"added": 0, "updated": 1, "removed": 2, "unchanged": 3}
                items.sort(key=lambda item: (
                    order[item.action], item.match.claim.victim.casefold(), item.match.claim.id,
                ))
                counts = {action: 0 for action in RANSOMWARE_WATCH_ITEM_ACTIONS}
                for item in items:
                    counts[item.action] += 1
                total = len(items) - counts["removed"]
                cursor = connection.execute(
                    "INSERT INTO ransomware_watch_runs "
                    "(id, watch_id, source_run_id, definition_sha256, previous_run_id, executed_at, "
                    "total_count, added_count, updated_count, unchanged_count, removed_count, result_sha256) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (run_id, watch.id, snapshot.run.id, definition,
                     previous.id if previous else None, executed_at, total, counts["added"],
                     counts["updated"], counts["unchanged"], counts["removed"],
                     _result_sha(items)),
                )
                for item in items:
                    self._insert_item(connection, item)
                run = RansomwareWatchRun(
                    cursor.lastrowid, run_id, watch.id, snapshot.run.id, definition,
                    previous.id if previous else None, executed_at, total, counts["added"],
                    counts["updated"], counts["unchanged"], counts["removed"],
                    _result_sha(items),
                )
                notification_id = None
                if previous is not None and run.added_count + run.updated_count > 0:
                    notification_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO ransomware_watch_notifications "
                        "(sequence, id, run_id, watch_id, event_type, origin, created_at, read_at) "
                        "VALUES (?, ?, ?, ?, 'ransomware_watch_changed', 'new', ?, NULL)",
                        (next_notification_sequence(connection), notification_id,
                         run.id, watch.id, executed_at),
                    )
                record_collection_step_receipt(
                    connection, operation, result_kind="threatcluster_watch_run",
                    result_id=run.id, result_status="complete",
                )
                connection.commit()
                return RansomwareWatchRunReport(
                    watch, run, tuple(items[:item_limit]), len(items), notification_id,
                    previous is None,
                )
            except BaseException:
                connection.rollback()
                raise

    def run_details(self, run_id, *, item_limit):
        with self._storage._connection(readonly=True) as connection:
            watches, _, runs, items, notifications = self._audit(connection)
        run = runs.get(run_id)
        if run is None:
            raise ValidationError("Ransomware izleme çalışması bulunamadı.")
        selected = sorted(
            (item for item in items if item.run_id == run.id),
            key=lambda item: (item.action, item.match.claim.victim.casefold(), item.match.claim.id),
        )
        return RansomwareWatchRunReport(
            watches[run.watch_id], run, tuple(selected[:item_limit]), len(selected),
            next((row[1] for row in notifications if row[2] == run.id), None),
            run.previous_run_id is None,
        )

    @classmethod
    def notification_evidence(
        cls, connection, notification_id: str,
    ) -> RansomwareWatchChangeEvidence:
        watches, _, runs, _, notifications = cls._audit(connection)
        notification = next((row for row in notifications if row[1] == notification_id), None)
        if notification is None:
            raise StorageError("Ransomware izleme bildiriminin kanıtı bulunamadı.")
        run = runs[notification[2]]
        watch = watches[notification[3]]
        return RansomwareWatchChangeEvidence(
            watch.id, watch.display_name, watch.kind, watch.query, run.id,
            run.source_run_id, run.executed_at, run.total_count, run.added_count,
            run.updated_count, run.unchanged_count, run.removed_count,
        )

"""Audited group ledger with durable metered-call reservations and atomic receipts."""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.mention_groups import (
    GROUP_POLICY, MAX_GROUPS, MAX_GROUP_RUNS, MAX_GROUP_EVENTS,
    MAX_GROUP_EVENT_BYTES, MAX_GROUP_TOTAL_BYTES,
    MentionGroup, MentionGroupAttempt, MentionGroupBudget, MentionGroupDefinition,
    MentionGroupOperation, MentionGroupRun, canonical_json, definition_from_data,
    normalize_group_name, request_from_data, utc_day, validate_definition,
    validate_group_id, validate_requests,
)
from xti.domain.mentions import mention_time, request_key


def _sha(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _chain(previous, sha):
    return _sha(canonical_json([GROUP_POLICY, previous, sha]))


def _time(value):
    return datetime.fromisoformat(mention_time(value))


def _index(value, count):
    if type(value) is not int or not 0 <= value < count:
        raise ValidationError("Grup hedef sırası geçersiz.")
    return value


def _reason(value):
    if (not isinstance(value, str) or not 3 <= len(value) <= 500
            or value != " ".join(value.split()) or any(not c.isprintable() for c in value)):
        raise ValidationError("Grup işlem nedeni 3–500 görünür karakter olmalı.")
    return value


def _exact(data, keys):
    if not isinstance(data, dict) or set(data) != set(keys):
        raise ValueError("Unexpected event fields")


def _pairs(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate key")
        data[key] = value
    return data


@dataclass
class _State:
    groups: dict
    runs: dict
    reservations: dict
    count: int = 0
    byte_count: int = 0
    chain: str | None = None
    recorded_at: str | None = None


def _group(state, identifier):
    if not isinstance(identifier, str):
        raise ValidationError("Grup adı veya kimliği gerekli.")
    if identifier in state.groups:
        return state.groups[identifier]
    key = normalize_group_name(identifier).casefold()
    group = next((value for value in state.groups.values() if value.name.casefold() == key), None)
    if group is None:
        raise ValidationError("Firma izleme grubu bulunamadı.")
    return group


def _run(state, identifier):
    validate_group_id(identifier)
    if identifier not in state.runs:
        raise ValidationError("Firma izleme çalışması bulunamadı.")
    return state.runs[identifier]


def _open_run(state, group_id):
    return next((run for run in state.runs.values() if run.group_id == group_id and run.status == "running"), None)


def _budget(state, group, at):
    day = utc_day(at)
    used = state.reservations.get((group.id, day), 0)
    return MentionGroupBudget(group.id, day, used, group.definition.daily_queries,
                              max(0, group.definition.daily_queries - used))


def _begin_checks(state, group, requests, at):
    if not group.active:
        raise ValidationError("Firma izleme grubu etkin değil.")
    validate_requests(group.definition, requests)
    if _open_run(state, group.id) is not None:
        raise ValidationError("Grubun tamamlanmamış çalışması var; önce mevcut çalışmayı sürdürün.")
    previous = [run for run in state.runs.values() if run.group_id == group.id]
    if previous and _time(at) < max(_time(run.started_at) for run in previous) + timedelta(hours=group.definition.interval_hours):
        raise ValidationError("Grubun sonraki arama zamanı henüz gelmedi; sorgu gönderilmedi.")
    if _budget(state, group, at).remaining_queries < len(requests):
        raise ValidationError("Günlük sorgu bütçesi grubun tüm hedefleri için yetersiz; arama başlatılmadı.")


def _set_attempt(state, run, attempt):
    attempts = list(run.attempts)
    attempts[attempt.index] = attempt
    state.runs[run.id] = replace(run, attempts=tuple(attempts))


def _replay(state, *, group_id, run_id, action, at, data, connection, source_runs):
    validate_group_id(group_id)
    _time(at)
    if state.recorded_at is not None and _time(at) < _time(state.recorded_at):
        raise ValueError("Event time regressed")
    if action == "saved":
        _exact(data, {"name", "revision", "definition"})
        if run_id is not None or type(data["revision"]) is not int:
            raise ValueError("Invalid definition event")
        name, revision, definition = data["name"], data["revision"], definition_from_data(data["definition"])
        if normalize_group_name(name) != name or any(g.id != group_id and g.name.casefold() == name.casefold() for g in state.groups.values()):
            raise ValueError("Ambiguous group name")
        previous = state.groups.get(group_id)
        if revision != (previous.revision + 1 if previous else 1) or _open_run(state, group_id):
            raise ValueError("Definition revision or open work")
        if previous and previous.name.casefold() != name.casefold():
            raise ValueError("Group identity cannot be renamed")
        state.groups[group_id] = MentionGroup(group_id, name, revision, definition, True,
            previous.created_at if previous else at, at)
    elif action == "disabled":
        _exact(data, {"reason", "revision"})
        _reason(data["reason"])
        group = state.groups[group_id]
        if run_id is not None or not group.active or type(data["revision"]) is not int or data["revision"] != group.revision + 1:
            raise ValueError("Invalid disabled group")
        state.groups[group_id] = replace(group, revision=group.revision + 1, active=False, updated_at=at)
    elif action == "begun":
        _exact(data, {"group_revision", "definition", "attempts"})
        validate_group_id(run_id)
        if run_id in state.runs or not isinstance(data["attempts"], list):
            raise ValueError("Duplicate or invalid work")
        group = state.groups[group_id]
        definition = definition_from_data(data["definition"])
        if type(data["group_revision"]) is not int or data["group_revision"] != group.revision or definition != group.definition:
            raise ValueError("Work definition differs")
        attempts = []
        for index, item in enumerate(data["attempts"]):
            _exact(item, {"id", "request"})
            validate_group_id(item["id"])
            attempts.append(MentionGroupAttempt(item["id"], index, request_from_data(item["request"])))
        identifiers = [attempt.id for attempt in attempts]
        if len(identifiers) != len(set(identifiers)) or any(
            attempt.id in identifiers for other in state.runs.values() for attempt in other.attempts
        ):
            raise ValueError("Duplicate attempt identity")
        _begin_checks(state, group, tuple(attempt.request for attempt in attempts), at)
        state.runs[run_id] = MentionGroupRun(run_id, group_id, group.revision, definition, at, tuple(attempts))
    else:
        run = _run(state, run_id)
        if run.group_id != group_id or run.status != "running":
            raise ValueError("Invalid work state")
        if action == "finished":
            _exact(data, {"status"})
            if any(attempt.status in {"pending", "reserved"} or
                   (attempt.status == "complete" and attempt.notification_run_id is None) for attempt in run.attempts):
                raise ValueError("Unfinished source or notice stage")
            status = ("complete" if all(a.status == "complete" for a in run.attempts)
                      else "partial" if any(a.status == "complete" for a in run.attempts) else "failed")
            if data["status"] != status:
                raise ValueError("Wrong result status")
            state.runs[run.id] = replace(run, status=status, finished_at=at)
        else:
            if not isinstance(data, dict) or "index" not in data:
                raise ValueError("Missing attempt index")
            attempt = run.attempts[_index(data["index"], len(run.attempts))]
            if action == "reserved":
                _exact(data, {"index", "attempt_id", "result_run_id"})
                validate_group_id(data["result_run_id"])
                group = state.groups[group_id]
                if any(a.result_run_id == data["result_run_id"] for r in state.runs.values() for a in r.attempts):
                    raise ValueError("Duplicate source result identity")
                if (attempt.status != "pending" or data["attempt_id"] != attempt.id or not group.active
                        or any(a.status == "reserved" for a in run.attempts)
                        or any(a.index < attempt.index and a.status == "pending" for a in run.attempts)
                        or _budget(state, group, at).remaining_queries < 1):
                    raise ValueError("Cannot reserve attempt")
                daykey = (group_id, utc_day(at))
                state.reservations[daykey] = state.reservations.get(daykey, 0) + 1
                _set_attempt(state, run, replace(attempt, status="reserved", started_at=at,
                                               result_run_id=data["result_run_id"]))
            elif action == "result":
                _exact(data, {"index", "attempt_id", "result_run_id", "status"})
                if (attempt.status != "reserved" or attempt.id != data["attempt_id"]
                        or attempt.result_run_id != data["result_run_id"] or data["status"] not in {"complete", "failed"}):
                    raise ValueError("Unexpected source receipt")
                if source_runs is None:
                    from xti.adapters.sqlite_mentions import read_mentions_catalog
                    source_runs = {r.id: r for r in read_mentions_catalog(connection).runs}
                source = source_runs[attempt.result_run_id]
                if (source.request != attempt.request or source.status != data["status"]
                        or source.started_at != attempt.started_at or source.finished_at != at):
                    raise ValueError("Source evidence differs from attempt")
                _set_attempt(state, run, replace(attempt, status=source.status, finished_at=at,
                    error_code="source_failed" if source.status == "failed" else None))
            elif action == "unknown":
                _exact(data, {"index"})
                if attempt.status != "reserved":
                    raise ValueError("Only reserved work can become unknown")
                if connection.execute("SELECT 1 FROM mentions_runs WHERE id=?", (attempt.result_run_id,)).fetchone():
                    raise ValueError("Source row without atomic receipt")
                _set_attempt(state, run, replace(attempt, status="unknown", finished_at=at,
                                               error_code="interrupted_unknown"))
            elif action == "skipped":
                _exact(data, {"index", "reason"})
                _reason(data["reason"])
                if attempt.status != "pending":
                    raise ValueError("Cannot skip attempted work")
                _set_attempt(state, run, replace(attempt, status="skipped", finished_at=at,
                                               error_code=data["reason"]))
            elif action == "notified":
                _exact(data, {"index", "notification_run_id"})
                validate_group_id(data["notification_run_id"])
                if attempt.status != "complete" or attempt.notification_run_id is not None:
                    raise ValueError("Cannot attach notification")
                row = connection.execute("SELECT group_id,request_key,mention_run_id,search_run_id,created_at "
                    "FROM mention_notification_operations WHERE operation_id=?", (attempt.id,)).fetchone()
                if (row is None or tuple(row[:4]) != (group_id, request_key(attempt.request),
                        attempt.result_run_id, data["notification_run_id"]) or _time(row[4]) > _time(at)):
                    raise ValueError("Notification receipt differs")
                _set_attempt(state, run, replace(attempt, notification_run_id=data["notification_run_id"], notification_at=at))
            else:
                raise ValueError("Unknown group event")
    state.recorded_at = at
    return source_runs


def _audit(connection):
    try:
        count, byte_count, maximum = connection.execute("SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(payload_json AS BLOB))),0),"
            "COALESCE(MAX(LENGTH(CAST(payload_json AS BLOB))),0) FROM mention_group_events").fetchone()
        if count > MAX_GROUP_EVENTS or byte_count > MAX_GROUP_TOTAL_BYTES or maximum > MAX_GROUP_EVENT_BYTES:
            raise ValueError("Group evidence capacity")
        allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='mention_group_events'").fetchall()
        if len(allocated) > 1 or (not allocated and count) or (allocated and allocated[0][0] != count):
            raise ValueError("Group ledger tail removed")
        state, source_runs = _State({}, {}, {}), None
        for sequence, identifier, group_id, run_id, action, at, payload, sha, chain in connection.execute(
            "SELECT sequence,id,group_id,run_id,action,recorded_at,payload_json,payload_sha256,chain_sha256 "
            "FROM mention_group_events ORDER BY sequence"
        ):
            validate_group_id(identifier)
            if sequence != state.count + 1 or _sha(payload) != sha or _chain(state.chain, sha) != chain:
                raise ValueError("Group ledger chain differs")
            envelope = json.loads(payload, object_pairs_hook=_pairs)
            _exact(envelope, {"policy", "group_id", "run_id", "action", "recorded_at", "data"})
            if (canonical_json(envelope) != payload or
                    (envelope["policy"], envelope["group_id"], envelope["run_id"], envelope["action"], envelope["recorded_at"])
                    != (GROUP_POLICY, group_id, run_id, action, at)):
                raise ValueError("Noncanonical or mismatched group evidence")
            source_runs = _replay(state, group_id=group_id, run_id=run_id, action=action,
                                 at=at, data=envelope["data"], connection=connection, source_runs=source_runs)
            state.count, state.chain = sequence, chain
        state.byte_count = byte_count
        if len(state.groups) > MAX_GROUPS or len(state.runs) > MAX_GROUP_RUNS:
            raise ValueError("Group/run capacity")
        if any(a.notification_run_id is not None for r in state.runs.values() for a in r.attempts):
            from xti.adapters.sqlite_mention_notifications import SQLiteMentionNotificationBridge
            from xti.adapters.sqlite_global_saved_searches import SQLiteGlobalSavedSearchRepository
            from xti.adapters.sqlite_mentions import read_mentions_catalog
            sources = {r.id: r for r in read_mentions_catalog(connection).runs}
            SQLiteMentionNotificationBridge._audit_bindings(connection,
                SQLiteGlobalSavedSearchRepository._audit(connection), sources)
        return state
    except (ValidationError, TypeError, ValueError, KeyError, AttributeError, IndexError,
            OverflowError, UnicodeError, RecursionError) as error:
        raise StorageError("Firma izleme grubu geçmişi bozuk veya kapasite sınırını aşıyor; kayıtlar değiştirilmedi.") from error


def _append(connection, state, *, group_id, run_id, action, at, data):
    payload = canonical_json({"policy": GROUP_POLICY, "group_id": group_id, "run_id": run_id,
                              "action": action, "recorded_at": at, "data": data})
    data = json.loads(payload)["data"]
    if (state.count >= MAX_GROUP_EVENTS or len(payload) > MAX_GROUP_EVENT_BYTES
            or state.byte_count + len(payload) > MAX_GROUP_TOTAL_BYTES):
        raise StorageError("Firma izleme geçmişi kapasitesi doldu; kayıtlar değiştirilmedi.")
    if not connection.in_transaction:
        raise StorageError("Grup olayı açık transaction içinde yazılmalı.")
    try:
        _replay(state, group_id=group_id, run_id=run_id, action=action, at=at, data=data,
                connection=connection, source_runs=None)
    except (ValueError, TypeError, KeyError, IndexError) as error:
        raise ValidationError("Grup işlemi mevcut çalışma durumu, kapsamı veya zamanıyla uyuşmuyor.") from error
    sha = _sha(payload)
    chain = _chain(state.chain, sha)
    connection.execute("INSERT INTO mention_group_events VALUES (?,?,?,?,?,?,?,?,?)",
        (state.count + 1, str(uuid4()), group_id, run_id, action, at, payload, sha, chain))
    state.count += 1
    state.byte_count += len(payload)
    state.chain = chain


def validate_group_operation(connection, operation, request=None):
    if operation is None:
        return
    if not isinstance(operation, MentionGroupOperation):
        raise ValidationError("Geçerli grup çalışma işlemi gerekli.")
    state = _audit(connection)
    run = _run(state, operation.run_id)
    attempt = run.attempts[_index(operation.index, len(run.attempts))]
    if (run.status != "running" or attempt.status != "reserved" or attempt.id != operation.attempt_id
            or attempt.result_run_id != operation.result_run_id
            or request_key(attempt.request) != operation.request_key
            or (request is not None and request != attempt.request)):
        raise ValidationError("Grup kaynak işlemi ayrılan hedefle uyuşmuyor.")
    return state, run, attempt


def record_group_result(connection, operation, source_run):
    if operation is None:
        return
    state, run, attempt = validate_group_operation(connection, operation, source_run.request)
    if source_run.id != operation.result_run_id or source_run.started_at != attempt.started_at:
        raise ValidationError("Grup kaynak sonucu ayrılan işlemle uyuşmuyor.")
    _append(connection, state, group_id=run.group_id, run_id=run.id, action="result", at=source_run.finished_at,
        data={"index": attempt.index, "attempt_id": attempt.id, "result_run_id": source_run.id, "status": source_run.status})


class SQLiteMentionGroupRepository:
    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    def _read(self, callback):
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return callback(_audit(connection))

    def _write(self, callback):
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                result = callback(connection, _audit(connection))
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def save(self, name, definition, *, recorded_at):
        name = normalize_group_name(name)
        validate_definition(definition)
        mention_time(recorded_at)
        def write(connection, state):
            previous = next((g for g in state.groups.values() if g.name.casefold() == name.casefold()), None)
            if previous and _open_run(state, previous.id):
                raise ValidationError("Tamamlanmamış çalışma varken grup tanımı değiştirilemez.")
            if previous and previous.active and previous.name == name and previous.definition == definition:
                return previous
            if previous is None and len(state.groups) >= MAX_GROUPS:
                raise StorageError("Firma izleme grubu kapasitesi doldu.")
            identifier = previous.id if previous else str(uuid4())
            _append(connection, state, group_id=identifier, run_id=None, action="saved", at=recorded_at,
                data={"name": name, "revision": previous.revision + 1 if previous else 1, "definition": asdict(definition)})
            return state.groups[identifier]
        return self._write(write)

    def disable(self, identifier, *, reason, recorded_at):
        _reason(reason)
        mention_time(recorded_at)
        def write(connection, state):
            group = _group(state, identifier)
            if group.active:
                _append(connection, state, group_id=group.id, run_id=None, action="disabled", at=recorded_at,
                        data={"reason": reason, "revision": group.revision + 1})
            return state.groups[group.id]
        return self._write(write)

    def get(self, identifier):
        return self._read(lambda state: _group(state, identifier))

    def list(self, *, active_only=True):
        if type(active_only) is not bool:
            raise ValidationError("Etkin grup seçimi doğru/yanlış olmalı.")
        return self._read(lambda state: tuple(sorted((g for g in state.groups.values() if g.active or not active_only),
                                                   key=lambda g: (g.name.casefold(), g.id))))

    def budget(self, identifier, *, at):
        mention_time(at)
        return self._read(lambda state: _budget(state, _group(state, identifier), at))

    def begin(self, identifier, requests, *, started_at, request_id=None):
        mention_time(started_at)
        run_id = validate_group_id(request_id) if request_id is not None else str(uuid4())
        def write(connection, state):
            group = _group(state, identifier)
            if run_id in state.runs:
                run = state.runs[run_id]
                if run.group_id != group.id or tuple(a.request for a in run.attempts) != requests:
                    raise ValidationError("İstek kimliği farklı grup veya hedeflerle daha önce kullanıldı.")
                return run
            _begin_checks(state, group, requests, started_at)
            if len(state.runs) >= MAX_GROUP_RUNS:
                raise StorageError("Firma izleme çalışma kapasitesi doldu.")
            # Worst-case future events (reserve/result/notice) fit before source work begins.
            required = 2 + len(requests) * 3
            if state.count + required > MAX_GROUP_EVENTS or state.byte_count + required * MAX_GROUP_EVENT_BYTES > MAX_GROUP_TOTAL_BYTES:
                raise StorageError("Grup geçmişinde yeni çalışma için yeterli kayıt alanı yok.")
            _append(connection, state, group_id=group.id, run_id=run_id, action="begun", at=started_at,
                data={"group_revision": group.revision, "definition": asdict(group.definition),
                      "attempts": [{"id": str(uuid4()), "request": asdict(request)} for request in requests]})
            return state.runs[run_id]
        return self._write(write)

    def reserve_attempt(self, run_id, index, *, started_at):
        mention_time(started_at)
        def write(connection, state):
            run = _run(state, run_id)
            attempt = run.attempts[_index(index, len(run.attempts))]
            if run.status != "running" or attempt.status != "pending":
                raise ValidationError("Bu grup hedefi daha önce ayrılmış veya tamamlanmış; yeniden sorgulanamaz.")
            group = state.groups[run.group_id]
            if not group.active:
                raise ValidationError("Firma izleme grubu etkin değil; yeni sorgu gönderilemez.")
            pending = sum(a.status == "pending" for a in run.attempts)
            if _budget(state, group, started_at).remaining_queries < pending:
                raise ValidationError("Günlük sorgu bütçesi kalan hedefler için yetersiz.")
            # All mention source runs share one chronological ledger. A clock
            # regression is already knowable here, before reserving a query or HTTP.
            from xti.adapters.sqlite_mentions import read_mentions_catalog
            sources = read_mentions_catalog(connection).runs
            if sources and _time(started_at) < _time(sources[-1].finished_at):
                raise ValidationError("Grup arama zamanı son kaynak çalışmasından eski; sorgu ayrılmadı veya gönderilmedi.")
            result_id = str(uuid4())
            _append(connection, state, group_id=run.group_id, run_id=run.id, action="reserved", at=started_at,
                data={"index": index, "attempt_id": attempt.id, "result_run_id": result_id})
            return MentionGroupOperation(run.id, attempt.id, index, request_key(attempt.request), result_id)
        return self._write(write)

    def recover(self, run_id, *, recorded_at):
        mention_time(recorded_at)
        def write(connection, state):
            run = _run(state, run_id)
            for attempt in run.attempts:
                if attempt.status == "reserved":
                    _append(connection, state, group_id=run.group_id, run_id=run.id, action="unknown", at=recorded_at,
                            data={"index": attempt.index})
            return state.runs[run.id]
        return self._write(write)

    def skip_pending(self, run_id, *, reason, recorded_at):
        _reason(reason)
        mention_time(recorded_at)
        def write(connection, state):
            run = _run(state, run_id)
            for attempt in run.attempts:
                if attempt.status == "pending":
                    _append(connection, state, group_id=run.group_id, run_id=run.id, action="skipped", at=recorded_at,
                            data={"index": attempt.index, "reason": reason})
            return state.runs[run.id]
        return self._write(write)

    def record_notification(self, run_id, index, *, notification_run_id, recorded_at):
        validate_group_id(notification_run_id)
        mention_time(recorded_at)
        def write(connection, state):
            run = _run(state, run_id)
            attempt = run.attempts[_index(index, len(run.attempts))]
            if attempt.notification_run_id == notification_run_id:
                return run
            if attempt.notification_run_id is not None:
                raise ValidationError("Grup hedefi farklı bir bildirim çalışmasına zaten bağlı.")
            _append(connection, state, group_id=run.group_id, run_id=run.id, action="notified", at=recorded_at,
                    data={"index": index, "notification_run_id": notification_run_id})
            return state.runs[run.id]
        return self._write(write)

    def finish(self, run_id, *, finished_at):
        mention_time(finished_at)
        def write(connection, state):
            run = _run(state, run_id)
            if run.status != "running":
                return run
            if any(a.status in {"pending", "reserved"} or (a.status == "complete" and a.notification_run_id is None) for a in run.attempts):
                raise ValidationError("Grup çalışmasında tamamlanmamış kaynak veya bildirim aşaması var.")
            status = ("complete" if all(a.status == "complete" for a in run.attempts)
                      else "partial" if any(a.status == "complete" for a in run.attempts) else "failed")
            _append(connection, state, group_id=run.group_id, run_id=run.id, action="finished", at=finished_at,
                    data={"status": status})
            return state.runs[run.id]
        return self._write(write)

    def find_run(self, run_id):
        validate_group_id(run_id)
        return self._read(lambda state: state.runs.get(run_id))

    def run_show(self, run_id):
        return self._read(lambda state: _run(state, run_id))

    def runs(self, identifier):
        def read(state):
            group = _group(state, identifier)
            return tuple(r for r in state.runs.values() if r.group_id == group.id)
        return self._read(read)

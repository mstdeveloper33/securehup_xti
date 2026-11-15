"""Atomically retain bounded search runs; reconstruct results from audited evidence."""

from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.mentions import (
    MENTION_POLICY, MAX_MENTION_RUNS, MAX_MENTION_RECORDS,
    MAX_MENTION_RUN_BYTES, MAX_MENTION_TOTAL_BYTES,
    MentionCatalog, MentionRecord, MentionRun, hit_sha256, match_hit,
    mention_time, mention_uuid, request_key, result_id, run_from_json, run_json, validate_request,
    validate_response,
)


def _sha(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _chain(previous, payload_sha):
    return _sha(json.dumps([MENTION_POLICY, previous, payload_sha], separators=(",", ":")))


def _advance(current, run):
    added = updated = unchanged = 0
    if run.response is None:
        return added, updated, unchanged
    key = request_key(run.request)
    for hit in run.response.hits:
        identifier, state = result_id(run.request, hit.url), hit_sha256(hit)
        terms, fields = match_hit(run.request.target, hit)
        old = current.get(identifier)
        if old is None:
            added += 1
            current[identifier] = MentionRecord(identifier, key, run.request, hit, terms, fields,
                run.finished_at, run.finished_at, run.finished_at, run.id, run.id, run.id, state)
        else:
            changed = old.state_sha256 != state
            updated += changed
            unchanged += not changed
            current[identifier] = replace(old, hit=hit, matched_terms=terms, match_fields=fields,
                last_seen_at=run.finished_at, last_seen_run_id=run.id,
                last_changed_at=run.finished_at if changed else old.last_changed_at,
                last_change_run_id=run.id if changed else old.last_change_run_id, state_sha256=state)
    if len(current) > MAX_MENTION_RECORDS:
        raise ValidationError("Saklanan içerik adayı kapasitesi doldu; kayıtlar değiştirilmedi.")
    return added, updated, unchanged


@dataclass
class _State:
    records: dict[str, MentionRecord]
    runs: tuple[MentionRun, ...]
    chain: str | None
    byte_count: int


def _audit(connection):
    try:
        count, byte_count, largest = connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(payload_json AS BLOB))),0),"
            "COALESCE(MAX(LENGTH(CAST(payload_json AS BLOB))),0) FROM mentions_runs"
        ).fetchone()
        if count > MAX_MENTION_RUNS or byte_count > MAX_MENTION_TOTAL_BYTES or largest > MAX_MENTION_RUN_BYTES:
            raise ValueError("Evidence capacity")
        allocated = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='mentions_runs'").fetchall()
        if (len(allocated) > 1 or (not allocated and count != 0)
                or (allocated and (type(allocated[0][0]) is not int or allocated[0][0] != count))):
            raise ValueError("Allocated run sequence differs from retained history")
        if connection.execute(
            "SELECT 1 FROM mentions_runs WHERE length(id)>36 OR length(request_key)!=64 "
            "OR length(payload_sha256)!=64 OR length(chain_sha256)!=64 LIMIT 1"
        ).fetchone():
            raise ValueError("Metadata capacity")
        records, runs, previous = {}, [], None
        for sequence, identifier, key, status, payload, sha, chain in connection.execute(
            "SELECT sequence,id,request_key,status,payload_json,payload_sha256,chain_sha256 "
            "FROM mentions_runs ORDER BY sequence"
        ):
            if sequence != len(runs) + 1 or _sha(payload) != sha or _chain(previous, sha) != chain:
                raise ValueError("Broken run chain")
            run = run_from_json(payload)
            if (run.sequence, run.id, request_key(run.request), run.status) != (sequence, identifier, key, status):
                raise ValueError("Run metadata differs")
            if runs and datetime.fromisoformat(run.started_at) < datetime.fromisoformat(runs[-1].finished_at):
                raise ValueError("Run overlaps earlier work")
            counts = _advance(records, run)
            if counts != (run.added_count, run.updated_count, run.unchanged_count):
                raise ValueError("Replay counts differ")
            runs.append(run)
            previous = chain
        return _State(records, tuple(runs), previous, byte_count)
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError, UnicodeError, RecursionError) as error:
        raise StorageError("İçerik araması geçmişi bozuk veya kapasite sınırını aşıyor; kayıtlar değiştirilmedi.") from error


def read_mentions_catalog(connection, *, through_run_id=None):
    state = _audit(connection)
    if through_run_id is not None:
        mention_uuid(through_run_id)
        index = next((i for i, run in enumerate(state.runs) if run.id == through_run_id), None)
        if index is None:
            raise ValidationError("İçerik geçmişi kesiti için kaynak çalışması bulunamadı.")
        records = {}
        runs = state.runs[:index + 1]
        for run in runs:
            _advance(records, run)
        return MentionCatalog(tuple(records[key] for key in sorted(records)), runs)
    return MentionCatalog(tuple(state.records[key] for key in sorted(state.records)), state.runs)


class SQLiteMentionRepository:
    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _capacity(state, additional_bytes=0):
        if len(state.runs) >= MAX_MENTION_RUNS or state.byte_count + additional_bytes > MAX_MENTION_TOTAL_BYTES:
            raise StorageError("İçerik araması geçmişi kapasitesi doldu; kayıtlar değiştirilmedi.")

    def validate(self, *, max_results=20, pending_runs=1, operation=None):
        if type(max_results) is not int or not 1 <= max_results <= 20:
            raise ValidationError("İçerik araması sonuç sınırı 1–20 olmalı.")
        if type(pending_runs) is not int or not 1 <= pending_runs <= 20:
            raise ValidationError("Bekleyen içerik arama sayısı 1–20 olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            state = _audit(connection)
            from xti.adapters.sqlite_mention_groups import validate_group_operation
            validate_group_operation(connection, operation)
            # Reserve a worst-case response before any metered request can begin.
            self._capacity(state, MAX_MENTION_RUN_BYTES * pending_runs)
            if len(state.runs) + pending_runs > MAX_MENTION_RUNS:
                raise StorageError("İçerik çalışma kapasitesi tüm grup hedefleri için yetersiz.")
            if len(state.records) + max_results * pending_runs > MAX_MENTION_RECORDS:
                raise StorageError("İçerik aday kapasitesi yeni arama için yetersiz; kredi kullanılmadı.")

    def _write(self, request, response, *, error, started_at, finished_at, operation=None):
        validate_request(request)
        mention_time(started_at)
        mention_time(finished_at)
        if response is not None:
            validate_response(response, request)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                state = _audit(connection)
                self._capacity(state)
                from xti.adapters.sqlite_mention_groups import validate_group_operation, record_group_result
                validate_group_operation(connection, operation, request)
                identifier = operation.result_run_id if operation is not None else str(uuid4())
                run = MentionRun(len(state.runs) + 1, identifier, request,
                    "complete" if response is not None else "failed", started_at, finished_at,
                    response, error, 0, 0, 0)
                if state.runs and datetime.fromisoformat(started_at) < datetime.fromisoformat(state.runs[-1].finished_at):
                    raise ValidationError("İçerik araması önceki çalışmadan eski zamanda yazılamaz.")
                counts = _advance(state.records, run)
                run = replace(run, added_count=counts[0], updated_count=counts[1], unchanged_count=counts[2])
                payload = run_json(run)
                self._capacity(state, len(payload))
                sha = _sha(payload)
                connection.execute("INSERT INTO mentions_runs VALUES (?,?,?,?,?,?,?)",
                    (run.sequence, run.id, request_key(request), run.status, payload, sha, _chain(state.chain, sha)))
                record_group_result(connection, operation, run)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return run

    def apply(self, request, response, *, started_at, finished_at, operation=None):
        validate_response(response, request)
        return self._write(request, response, error=None, started_at=started_at, finished_at=finished_at, operation=operation)

    def record_failure(self, request, *, error, started_at, finished_at, operation=None):
        return self._write(request, None, error=error, started_at=started_at, finished_at=finished_at, operation=operation)

    def catalog(self):
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return read_mentions_catalog(connection)

    def run_show(self, identifier):
        mention_uuid(identifier)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            state = _audit(connection)
            run = next((run for run in state.runs if run.id == identifier), None)
            if run is None:
                raise ValidationError("İçerik araması çalışması bulunamadı.")
            return run



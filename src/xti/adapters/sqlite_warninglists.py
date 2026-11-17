"""Append-only receipts and deduplicated upstream payloads in the company DB."""

from datetime import datetime
import re
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.cti_knowledge import normalize_knowledge_id
from xti.domain.warninglists import (
    MAX_BYTES, POLICIES, WarninglistRun, WarninglistRunNotFound, WarninglistState, normalize_revision,
    parse_warninglist, policy_for,
)


RUN_SELECT = "id,list_id,revision,started_at,finished_at,status,snapshot_sha256,error"


def _run(row):
    try:
        run = WarninglistRun(*row)
        normalize_knowledge_id(run.id)
        policy_for(run.list_id)
        if run.revision is not None:
            normalize_revision(run.revision)
        if any(normalize_cti_timestamp(value) != value for value in (run.started_at, run.finished_at)):
            raise ValueError("Noncanonical time")
        if datetime.fromisoformat(run.finished_at) < datetime.fromisoformat(run.started_at):
            raise ValueError("Time order")
        if run.status == "complete":
            if run.revision is None or run.error is not None or not isinstance(run.snapshot_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", run.snapshot_sha256) is None:
                raise ValueError("Invalid complete receipt")
        elif run.status == "failed":
            if run.snapshot_sha256 is not None or not isinstance(run.error, str) or not 1 <= len(run.error) <= 1000 or not run.error.isprintable():
                raise ValueError("Invalid failed receipt")
        else:
            raise ValueError("Invalid status")
        return run
    except (ValueError, TypeError, AttributeError) as error:
        raise StorageError("Warninglist kaynak çalışma kaydı bozuk.") from error


def _snapshot(connection, run):
    if run.status != "complete":
        return None
    row = connection.execute(
        "SELECT LENGTH(content) FROM warninglist_snapshots WHERE sha256=?", (run.snapshot_sha256,),
    ).fetchone()
    if row is None or type(row[0]) is not int or not 0 < row[0] <= MAX_BYTES:
        raise StorageError("Warninglist kaynak içeriği eksik veya sınır dışında.")
    content = connection.execute("SELECT content FROM warninglist_snapshots WHERE sha256=?", (run.snapshot_sha256,)).fetchone()[0]
    try:
        snapshot = parse_warninglist(run.list_id, content)
        if snapshot.sha256 != run.snapshot_sha256:
            raise ValidationError("Hash mismatch")
    except ValidationError as error:
        raise StorageError("Warninglist kaynak içeriği doğrulanamadı.") from error
    return snapshot


def read_warninglists(connection):
    states = []
    for identifier in POLICIES:
        latest = connection.execute(f"SELECT {RUN_SELECT} FROM warninglist_runs WHERE list_id=? ORDER BY rowid DESC LIMIT 1", (identifier,)).fetchone()
        success = connection.execute(f"SELECT {RUN_SELECT} FROM warninglist_runs WHERE list_id=? AND status='complete' ORDER BY rowid DESC LIMIT 1", (identifier,)).fetchone()
        latest, success = _run(latest) if latest else None, _run(success) if success else None
        snapshot = _snapshot(connection, success) if success else None
        states.append(WarninglistState(identifier, latest, success, snapshot))
    return tuple(states)


class SQLiteWarninglistRepository:
    def __init__(self, path):
        self.storage = SQLiteAssetRepository(path)

    def record(self, list_id, *, revision, started_at, finished_at, content, error):
        policy_for(list_id)
        snapshot = parse_warninglist(list_id, content) if content is not None else None
        if (snapshot is None) != (error is not None):
            raise ValidationError("Warninglist sonucu içerik veya hata taşımalı.")
        run = _run((str(uuid4()), list_id, revision, started_at, finished_at,
                    "complete" if snapshot else "failed", snapshot.sha256 if snapshot else None, error))
        with self.storage._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = next(state for state in read_warninglists(connection) if state.list_id == list_id)
            if snapshot and previous.snapshot and snapshot.version < previous.snapshot.version:
                snapshot = None
                run = WarninglistRun(run.id, list_id, revision, started_at, finished_at,
                    "failed", None, "Kaynak liste sürümü geriye gitti; önceki geçerli liste korundu.")
            if snapshot:
                existing = connection.execute("SELECT content FROM warninglist_snapshots WHERE sha256=?", (snapshot.sha256,)).fetchone()
                if existing is not None and existing[0] != content:
                    raise StorageError("Warninglist içerik kimliği mevcut kayıtla uyuşmuyor.")
                if existing is None:
                    connection.execute("INSERT INTO warninglist_snapshots(sha256,content) VALUES (?,?)", (snapshot.sha256, content))
            connection.execute(f"INSERT INTO warninglist_runs({RUN_SELECT}) VALUES (?,?,?,?,?,?,?,?)",
                (run.id, run.list_id, run.revision, run.started_at, run.finished_at,
                 run.status, run.snapshot_sha256, run.error))
            connection.commit()
        return run

    def read(self):
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return read_warninglists(connection)

    def history(self, list_id, *, offset, limit):
        policy_for(list_id)
        with self.storage._connection(readonly=True) as connection:
            return tuple(_run(row) for row in connection.execute(
                f"SELECT {RUN_SELECT} FROM warninglist_runs WHERE list_id=? ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (list_id, limit, offset)))

    def show(self, run_id):
        normalize_knowledge_id(run_id)
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = connection.execute(f"SELECT {RUN_SELECT} FROM warninglist_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise WarninglistRunNotFound("Warninglist çalışması seçili alanda bulunamadı.")
            run = _run(row)
            return run, _snapshot(connection, run)

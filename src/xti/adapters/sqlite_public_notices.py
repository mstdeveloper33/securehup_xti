"""Atomic, compact public catalog history with audited complete snapshot replay."""

from dataclasses import asdict
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_receipts import (
    record_collection_step_receipt, validate_public_notice_operation,
)
from xti.domain.collection_history import CollectionOperationToken
from xti.domain.assets import ValidationError
from xti.domain.public_notices import (
    HIBP_ATTRIBUTION, HIBP_LICENSE, HIBP_SOURCE_NAME, HIBP_SOURCE_URL, MAX_NOTICES,
    PublicNotice, PublicNoticeChange, PublicNoticeFeed, PublicNoticeHistory, PublicNoticeRefreshReport,
    PublicNoticeRun, PublicNoticeSnapshot, PublicNoticeStatus, notice_json,
    notice_sha256, notice_text, notice_timestamp, validate_notice,
)


MAX_RUNS = 10_000
MAX_CHANGES = 1_000_000
_RUN_COLUMNS = tuple(PublicNoticeRun.__dataclass_fields__)
_RUN_SELECT = ", ".join(_RUN_COLUMNS)


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode("ascii")).hexdigest()


def _snapshot_hash(current: dict[str, PublicNotice]) -> str:
    return _hash([(key, notice_sha256(current[key])) for key in sorted(current)])


def _chain(previous: str | None, run: PublicNoticeRun, changes: tuple[PublicNoticeChange, ...]) -> str:
    return _hash([previous, asdict(run), sorted(
        (item.action, item.notice.id, item.state_sha256) for item in changes)])


def _sha(value) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("Invalid hash")
    return value


def _uuid(value) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Invalid UUID")
    return value


def _times(started: str, finished: str) -> None:
    notice_timestamp(started)
    notice_timestamp(finished)
    if datetime.fromisoformat(finished) < datetime.fromisoformat(started):
        raise ValidationError("Kamu olay çalışması bitiş zamanı başlangıçtan önce olamaz.")


def _bounds(limit, offset=0, maximum=500) -> None:
    if type(limit) is not int or not 1 <= limit <= maximum or type(offset) is not int or not 0 <= offset <= MAX_CHANGES:
        raise ValidationError("Kamu olay görünüm sınırı veya başlangıcı geçersiz.")


def _record(raw: str) -> PublicNotice:
    decoded = json.loads(raw)
    if not isinstance(decoded, dict) or set(decoded) != set(PublicNotice.__dataclass_fields__):
        raise ValueError("Invalid record shape")
    if not isinstance(decoded["data_classes"], list):
        raise ValueError("Invalid categories")
    decoded["data_classes"] = tuple(decoded["data_classes"])
    record = validate_notice(PublicNotice(**decoded))
    if notice_json(record) != raw:
        raise ValueError("Noncanonical record")
    return record


def _audit(connection):
    """One caller-owned read transaction; neither repairs nor external lookups."""
    try:
        raw_runs = connection.execute(f"SELECT {_RUN_SELECT}, chain_sha256 FROM public_notice_runs ORDER BY sequence").fetchmany(MAX_RUNS + 1)
        raw_changes = connection.execute(
            "SELECT run_id, notice_id, action, record_json, state_sha256 FROM public_notice_changes ORDER BY sequence"
        ).fetchmany(MAX_CHANGES + 1)
        if len(raw_runs) > MAX_RUNS or len(raw_changes) > MAX_CHANGES:
            raise ValueError("History boundary exceeded")
        runs = tuple(PublicNoticeRun(*row[:-1]) for row in raw_runs)
        grouped: dict[str, list[PublicNoticeChange]] = {run.id: [] for run in runs}
        changes = []
        identities = set()
        for run_id, identifier, action, record_json, sha in raw_changes:
            record = _record(record_json)
            if (run_id not in grouped or identifier != record.id or action not in {"added", "updated", "removed"}
                    or (run_id, identifier) in identities or _sha(sha) != notice_sha256(record)):
                raise ValueError("Invalid history record")
            identities.add((run_id, identifier))
            change = PublicNoticeChange(run_id, action, record, sha)
            grouped[run_id].append(change)
            changes.append(change)
        current: dict[str, PublicNotice] = {}
        previous_chain = None
        previous_sequence = 0
        for run, row in zip(runs, raw_runs):
            _uuid(run.id)
            if type(run.sequence) is not int or run.sequence <= previous_sequence:
                raise ValueError("Invalid sequence")
            previous_sequence = run.sequence
            _times(run.started_at, run.finished_at)
            counts = (run.notice_count, run.added_count, run.updated_count, run.unchanged_count, run.removed_count)
            if any(type(count) is not int or not 0 <= count <= MAX_NOTICES for count in counts):
                raise ValueError("Invalid counters")
            items = tuple(grouped[run.id])
            if run.status == "failed":
                if any(counts) or items or run.fetched_at is not None or run.content_sha256 is not None or run.snapshot_sha256 is not None:
                    raise ValueError("Failure has source result")
                notice_text(run.error, maximum=2000)
            elif run.status == "complete":
                if run.error is not None or run.notice_count < 1:
                    raise ValueError("Invalid complete result")
                notice_timestamp(run.fetched_at)
                _sha(run.content_sha256)
                if datetime.fromisoformat(run.fetched_at) > datetime.fromisoformat(run.finished_at) + timedelta(minutes=15):
                    raise ValueError("Future fetch")
                counts_by_action = {action: sum(item.action == action for item in items) for action in ("added", "updated", "removed")}
                if counts_by_action != {"added": run.added_count, "updated": run.updated_count, "removed": run.removed_count}:
                    raise ValueError("Change counts differ")
                for item in items:
                    before = current.get(item.notice.id)
                    if item.action == "added":
                        if before is not None:
                            raise ValueError("Existing add")
                        current[item.notice.id] = item.notice
                    elif item.action == "updated":
                        if before is None or notice_sha256(before) == item.state_sha256:
                            raise ValueError("Missing or unchanged update")
                        current[item.notice.id] = item.notice
                    else:
                        if before is None or notice_sha256(before) != item.state_sha256:
                            raise ValueError("Invalid removed record")
                        del current[item.notice.id]
                if (len(current) != run.notice_count
                        or run.unchanged_count != run.notice_count - run.added_count - run.updated_count
                        or _sha(run.snapshot_sha256) != _snapshot_hash(current)):
                    raise ValueError("Snapshot digest or count differs")
            else:
                raise ValueError("Invalid status")
            if _sha(row[-1]) != _chain(previous_chain, run, items):
                raise ValueError("History chain differs")
            previous_chain = row[-1]
        return runs, tuple(changes), current, previous_chain
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as error:
        raise StorageError("Kamu olay kataloğu geçmişi veya kanıt bütünlüğü bozuk; kayıtlar değiştirilmedi.") from error


def read_public_notice_snapshot(connection) -> PublicNoticeSnapshot:
    """Read from an existing consistent transaction, for composed reports."""
    runs, _, current, _ = _audit(connection)
    complete = next((run for run in reversed(runs) if run.status == "complete"), None)
    return PublicNoticeSnapshot(runs[-1] if runs else None, complete,
                                tuple(current[key] for key in sorted(current)))


def read_public_notice_history(connection) -> PublicNoticeHistory:
    """Immutable metadata deltas ordered by run, for offline change reports."""
    runs, changes, _, _ = _audit(connection)
    return PublicNoticeHistory(runs, changes)


class SQLitePublicNoticeRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    def validate(self, *, operation: CollectionOperationToken | None = None) -> None:
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            _audit(connection)
            validate_public_notice_operation(connection, operation)

    @staticmethod
    def _insert(connection, run: PublicNoticeRun, changes: tuple[PublicNoticeChange, ...], previous_chain: str | None) -> None:
        values = tuple(getattr(run, key) for key in _RUN_COLUMNS) + (_chain(previous_chain, run, changes),)
        connection.execute(
            f"INSERT INTO public_notice_runs ({_RUN_SELECT}, chain_sha256) VALUES ({','.join('?' for _ in values)})", values,
        )
        for item in changes:
            connection.execute(
                "INSERT INTO public_notice_changes (run_id, notice_id, action, record_json, state_sha256) VALUES (?, ?, ?, ?, ?)",
                (run.id, item.notice.id, item.action, notice_json(item.notice), item.state_sha256),
            )

    def apply(self, feed: PublicNoticeFeed, *, started_at: str, finished_at: str,
              item_limit: int = 20,
              operation: CollectionOperationToken | None = None) -> PublicNoticeRefreshReport:
        _bounds(item_limit)
        _times(started_at, finished_at)
        try:
            if (not isinstance(feed, PublicNoticeFeed) or feed.source_name != HIBP_SOURCE_NAME
                    or feed.source_url != HIBP_SOURCE_URL or feed.attribution != HIBP_ATTRIBUTION
                    or feed.license != HIBP_LICENSE or not isinstance(feed.notices, tuple)
                    or not 1 <= len(feed.notices) <= MAX_NOTICES):
                raise ValueError("Invalid feed")
            notice_timestamp(feed.fetched_at)
            _sha(feed.content_sha256)
            fetched = datetime.fromisoformat(feed.fetched_at)
            if fetched > datetime.fromisoformat(finished_at) + timedelta(minutes=15):
                raise ValueError("Future fetch")
            incoming = {}
            for record in feed.notices:
                validate_notice(record)
                if record.id in incoming or datetime.fromisoformat(record.modified_at) > fetched + timedelta(minutes=15):
                    raise ValueError("Duplicate or future record")
                incoming[record.id] = record
        except (ValueError, TypeError, AttributeError, OverflowError) as error:
            raise ValidationError("Kamu olay kaynak sonucu geçersiz; kayıtlar değiştirilmedi.") from error
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                validate_public_notice_operation(connection, operation)
                runs, old_changes, current, previous_chain = _audit(connection)
                identifier = str(uuid4())
                changes = []
                for key, record in sorted(incoming.items()):
                    action = "added" if key not in current else ("updated" if notice_sha256(record) != notice_sha256(current[key]) else None)
                    if action:
                        changes.append(PublicNoticeChange(identifier, action, record, notice_sha256(record)))
                for key in sorted(current.keys() - incoming.keys()):
                    record = current[key]
                    changes.append(PublicNoticeChange(identifier, "removed", record, notice_sha256(record)))
                changes = tuple(changes)
                if len(runs) >= MAX_RUNS or len(old_changes) + len(changes) > MAX_CHANGES:
                    raise ValidationError("Kamu olay yerel geçmiş kapasitesi doldu; kayıtlar değiştirilmedi.")
                added = sum(item.action == "added" for item in changes)
                updated = sum(item.action == "updated" for item in changes)
                removed = sum(item.action == "removed" for item in changes)
                run = PublicNoticeRun(
                    (runs[-1].sequence + 1) if runs else 1, identifier, "complete", started_at, finished_at,
                    feed.fetched_at, feed.content_sha256, _snapshot_hash(incoming), len(incoming), added,
                    updated, len(incoming) - added - updated, removed, None,
                )
                self._insert(connection, run, changes, previous_chain)
                record_collection_step_receipt(
                    connection, operation, result_kind="public_notice_run",
                    result_id=run.id, result_status=run.status,
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return PublicNoticeRefreshReport(run, changes[:item_limit], len(changes),
                                         not any(old.status == "complete" for old in runs))

    def record_failure(self, *, started_at: str, finished_at: str, error: str,
                       operation: CollectionOperationToken | None = None) -> PublicNoticeRun:
        _times(started_at, finished_at)
        notice_text(error, maximum=2000)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                validate_public_notice_operation(connection, operation)
                runs, _, _, previous_chain = _audit(connection)
                if len(runs) >= MAX_RUNS:
                    raise ValidationError("Kamu olay yerel geçmiş kapasitesi doldu; kayıtlar değiştirilmedi.")
                run = PublicNoticeRun((runs[-1].sequence + 1) if runs else 1, str(uuid4()), "failed",
                                      started_at, finished_at, None, None, None, 0, 0, 0, 0, 0, error)
                self._insert(connection, run, (), previous_chain)
                record_collection_step_receipt(
                    connection, operation, result_kind="public_notice_run",
                    result_id=run.id, result_status=run.status,
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return run

    def status(self, *, run_limit: int = 10, offset: int = 0) -> PublicNoticeStatus:
        _bounds(run_limit, offset, 100)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            runs, _, _, _ = _audit(connection)
        complete = next((run for run in reversed(runs) if run.status == "complete"), None)
        return PublicNoticeStatus(runs[-1] if runs else None, complete,
                                  tuple(reversed(runs))[offset:offset + run_limit], len(runs), offset)

    def latest_snapshot(self) -> PublicNoticeSnapshot:
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return read_public_notice_snapshot(connection)

    def run_show(self, identifier: str, *, item_limit: int = 20, offset: int = 0) -> PublicNoticeRefreshReport:
        _bounds(item_limit, offset)
        try:
            _uuid(identifier)
        except (ValueError, TypeError, AttributeError) as error:
            raise ValidationError("Kamu olay çalışma kimliği geçersiz.") from error
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            runs, changes, _, _ = _audit(connection)
        run = next((run for run in runs if run.id == identifier), None)
        if run is None:
            raise ValidationError("Kamu olay çalışması bulunamadı.")
        selected = tuple(item for item in changes if item.run_id == identifier)
        baseline = run.status == "complete" and not any(old.status == "complete" and old.sequence < run.sequence for old in runs)
        return PublicNoticeRefreshReport(run, selected[offset:offset + item_limit], len(selected), baseline, offset)

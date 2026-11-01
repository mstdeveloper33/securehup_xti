"""Bounded orphan-observation cleanup with a pre-delete recovery snapshot."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3
import stat
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.operations import CleanupPlan, CleanupResult, CleanupRun, StorageUsage
from xti.domain.priority import parse_timestamp


POLICY_VERSION = "unlinked-observations-v1"
_OBSERVATION_COLUMNS = (
    "o.id, o.domain, o.raw_domain, o.source_name, o.source_sha256, "
    "o.source_line, o.observed_at, o.ingested_at"
)
_LINKED = "EXISTS (SELECT 1 FROM finding_observations f WHERE f.observation_id = o.id)"
_UNLINKED = "NOT " + _LINKED


def _parameters(older_than_days: int, limit: int, now: datetime) -> datetime:
    if type(older_than_days) is not int or not 7 <= older_than_days <= 3650:
        raise ValidationError("Saklama süresi 7–3650 gün arasında olmalı.")
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValidationError("Temizleme sınırı 1–10000 kayıt arasında olmalı.")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValidationError("Temizleme için saat dilimi belli bir zaman gerekli.")
    try:
        now = now.astimezone(timezone.utc)
        # A stable UTC day keeps a reviewed plan usable later in the same day.
        now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=older_than_days)
    except (ValueError, OverflowError) as error:
        raise ValidationError("Temizleme zamanı desteklenen aralığın dışında.") from error
    return now


def _token(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValidationError("Geçerli temizleme önizleme kimliği gerekli; önce önizleme al.")
    return value


def _file_size(path: Path, *, optional: bool = False) -> int:
    try:
        details = path.lstat()
    except FileNotFoundError:
        if optional:
            return 0
        raise StorageError("Kayıt dosyasının boyutu okunamadı.") from None
    if not stat.S_ISREG(details.st_mode):
        raise StorageError("Kayıt alanında beklenmeyen dosya türü var; boyut okunamadı.")
    return details.st_size


class SQLiteMaintenanceRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    def usage(self) -> StorageUsage:
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            observations = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            linked = connection.execute(
                "SELECT COUNT(*) FROM observations o WHERE " + _LINKED
            ).fetchone()[0]
            pages = connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = connection.execute("PRAGMA page_size").fetchone()[0]
            free_pages = connection.execute("PRAGMA freelist_count").fetchone()[0]
            path = self._storage.path
            # File sizes are an instantaneous filesystem observation; logical
            # counts come from the same database read snapshot.
            result = StorageUsage(
                database_bytes=_file_size(path),
                wal_bytes=_file_size(path.with_name(path.name + "-wal"), optional=True),
                journal_bytes=_file_size(path.with_name(path.name + "-journal"), optional=True),
                logical_bytes=pages * page_size, reusable_bytes=free_pages * page_size,
                observation_count=observations, linked_observation_count=linked,
            )
            connection.rollback()
        return result

    def _selection(
        self, connection: sqlite3.Connection, older_than_days: int, limit: int, now: datetime,
    ) -> tuple[CleanupPlan, tuple[str, ...]]:
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=older_than_days)
        protected = connection.execute(
            "SELECT COUNT(*) FROM observations o WHERE " + _LINKED
        ).fetchone()[0]
        # Binding the canonical database path prevents applying a plan to a
        # restored/copy database accidentally selected by a different data-dir.
        metadata = (POLICY_VERSION, str(self._storage.path.resolve(strict=True)),
                    cutoff.isoformat(), older_than_days, limit)
        digest = hashlib.sha256()
        digest.update(json.dumps(metadata, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
        eligible = invalid = 0
        selected: list[str] = []
        # Stream all candidates but retain only the bounded selected IDs. The
        # full eligible contents affect the token, including the next batch.
        for row in connection.execute(
            "SELECT " + _OBSERVATION_COLUMNS + " FROM observations o WHERE " + _UNLINKED +
            " ORDER BY o.rowid"
        ):
            ingested = parse_timestamp(row[7])
            if ingested is None or ingested > now:
                invalid += 1
                continue
            if ingested >= cutoff:
                continue
            try:
                payload = json.dumps(row, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            except (ValueError, TypeError) as error:
                raise StorageError("Gözlem kaydı beklenen biçimde değil; temizleme durduruldu.") from error
            digest.update(payload.encode("utf-8"))
            digest.update(b"\n")
            eligible += 1
            if len(selected) < limit:
                selected.append(row[0])
        digest.update(str(eligible).encode("ascii"))
        return CleanupPlan(
            policy_version=POLICY_VERSION, cutoff=cutoff.isoformat(), older_than_days=older_than_days,
            limit=limit, eligible_count=eligible, selected_count=len(selected),
            remaining_count=eligible - len(selected), protected_count=protected,
            invalid_time_count=invalid, token=digest.hexdigest(),
        ), tuple(selected)

    def preview(self, older_than_days: int, limit: int, now: datetime) -> CleanupPlan:
        now = _parameters(older_than_days, limit, now)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            plan, _ = self._selection(connection, older_than_days, limit, now)
            connection.rollback()
        return plan

    @staticmethod
    def _delete(connection: sqlite3.Connection, selected: tuple[str, ...]) -> int:
        # The selection cursor has been exhausted before any DELETE occurs.
        cursor = connection.executemany(
            "DELETE FROM observations WHERE id = ? AND NOT EXISTS "
            "(SELECT 1 FROM finding_observations f WHERE f.observation_id = observations.id)",
            ((identifier,) for identifier in selected),
        )
        return cursor.rowcount

    @staticmethod
    def _record(connection: sqlite3.Connection, run: CleanupRun) -> None:
        connection.execute(
            "INSERT INTO cleanup_runs (id, created_at, cutoff, deleted_count, token, backup) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run.id, run.created_at, run.cutoff, run.deleted_count, run.token, run.backup),
        )

    def apply(self, older_than_days: int, limit: int, now: datetime, token: str) -> CleanupResult:
        now = _parameters(older_than_days, limit, now)
        token = _token(token)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._storage._check_integrity(connection)
                plan, selected = self._selection(connection, older_than_days, limit, now)
                if not hmac.compare_digest(plan.token, token):
                    raise ValidationError("Temizleme önizlemesi değişti veya başka kayıt alanına ait; yeniden önizleme al.")
                if not selected:
                    connection.rollback()
                    return CleanupResult(plan=plan, deleted_count=0, backup=None, run=None)
                run_id = str(uuid4())
                destination = (self._storage.path.parent / "backups" /
                               f"{self._storage.path.stem}.pre-cleanup-{run_id}.db")
                # This separate reader backs up the pre-delete committed state
                # while BEGIN IMMEDIATE excludes all concurrent SQLite writers.
                backup = self._storage.backup(destination)
                deleted = self._delete(connection, selected)
                if deleted != len(selected):
                    raise StorageError("Temizleme seçimi değişti; işlem geri alındı.")
                run = CleanupRun(
                    id=run_id, created_at=now.isoformat(), cutoff=plan.cutoff,
                    deleted_count=deleted, token=plan.token, backup=str(backup),
                )
                self._record(connection, run)
                self._storage._check_integrity(connection)
                connection.commit()
                return CleanupResult(plan=plan, deleted_count=deleted, backup=str(backup), run=run)
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _run(row) -> CleanupRun:
        try:
            identifier, created, cutoff, count, token, backup = row
            if (not isinstance(identifier, str) or not identifier or len(identifier) > 64
                    or not identifier.isprintable() or parse_timestamp(created) is None
                    or parse_timestamp(cutoff) is None or type(count) is not int or count < 1
                    or not isinstance(backup, str) or not backup or len(backup) > 4096
                    or not Path(backup).is_absolute()):
                raise ValueError("Invalid cleanup record")
            _token(token)
            return CleanupRun(identifier, created, cutoff, count, token, backup)
        except (ValueError, TypeError) as error:
            raise StorageError("Temizleme geçmişi beklenen biçimde değil.") from error

    def history(self, limit: int) -> tuple[CleanupRun, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Geçmiş sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT id, created_at, cutoff, deleted_count, token, backup FROM cleanup_runs "
                "ORDER BY rowid DESC LIMIT ?", (limit,),
            ).fetchall()
        return tuple(self._run(row) for row in rows)

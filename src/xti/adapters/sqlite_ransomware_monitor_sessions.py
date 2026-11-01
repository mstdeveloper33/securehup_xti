"""Audited foreground ransomware monitor sessions over durable source/watch runs."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_ransomware_claims import SQLiteRansomwareClaimRepository
from xti.adapters.sqlite_ransomware_watches import SQLiteRansomwareWatchRepository
from xti.domain.assets import ValidationError
from xti.domain.cti_indicators import normalize_cti_timestamp
from xti.domain.ransomware_watches import (
    RANSOMWARE_MONITOR_SESSION_STATUSES,
    RANSOMWARE_MONITOR_STOP_REASONS,
    RansomwareMonitorSession,
    RansomwareMonitorSessionDetails,
    RansomwareWatchMonitorCycle,
)


_SESSION_SELECT = (
    "sequence, id, status, started_at, finished_at, stop_reason, planned_cycles, "
    "interval_seconds, max_duration_seconds, max_watches, source_item_limit, "
    "watch_item_limit, error"
)
_CYCLE_SELECT = (
    "id, session_id, cycle, source_run_id, planned_watch_count, "
    "completed_watch_count, baseline_watch_count, total_count, added_count, "
    "updated_count, unchanged_count, removed_count, notification_count"
)
_LINK_SELECT = "id, cycle_id, position, watch_run_id"
_MAX_SESSIONS = 100_000
_MAX_CYCLES = 100_000
_MAX_LINKS = 100_000


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


def _error(value: object, *, required: bool) -> str:
    if not isinstance(value, str) or len(value) > 500 or any(
        not character.isprintable() for character in value
    ):
        raise ValueError("Invalid error")
    normalized = " ".join(value.strip().split())
    if value != normalized or bool(value) != required:
        raise ValueError("Invalid error state")
    return value


@dataclass(frozen=True, slots=True)
class _SessionBase:
    sequence: int
    id: str
    status: str
    started_at: str
    finished_at: str | None
    stop_reason: str
    planned_cycles: int
    interval_seconds: int
    max_duration_seconds: int
    max_watches: int
    source_item_limit: int
    watch_item_limit: int
    error: str


class SQLiteRansomwareMonitorSessionRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _base(row) -> _SessionBase:
        try:
            if type(row[0]) is not int or row[0] < 1:
                raise ValueError("Invalid sequence")
            if row[2] not in RANSOMWARE_MONITOR_SESSION_STATUSES:
                raise ValueError("Invalid status")
            started = _timestamp(row[3], field="ransomware monitor başlangıç zamanı")
            finished = (
                _timestamp(row[4], field="ransomware monitor bitiş zamanı")
                if row[4] is not None else None
            )
            if row[5] not in RANSOMWARE_MONITOR_STOP_REASONS:
                raise ValueError("Invalid stop reason")
            limits = row[6:12]
            ranges = (
                (1, 1000), (300, 86400), (1, 604800),
                (1, 500), (1, 500), (1, 500),
            )
            if any(
                type(value) is not int or not low <= value <= high
                for value, (low, high) in zip(limits, ranges)
            ):
                raise ValueError("Invalid limits")
            status = row[2]
            if status == "running":
                if finished is not None or row[5] != "":
                    raise ValueError("Invalid running state")
                error = _error(row[12], required=False)
            elif status in {"complete", "partial"}:
                if finished is None or row[5] not in {"cycles", "duration"}:
                    raise ValueError("Invalid finished state")
                error = _error(row[12], required=False)
            elif status == "interrupted":
                if finished is None or row[5] != "interrupted":
                    raise ValueError("Invalid interrupted state")
                error = _error(row[12], required=False)
            else:
                if finished is None or row[5] != "error":
                    raise ValueError("Invalid failed state")
                error = _error(row[12], required=True)
            if finished is not None and datetime.fromisoformat(finished) < datetime.fromisoformat(started):
                raise ValueError("Reversed session time")
            return _SessionBase(
                row[0], _uuid(row[1]), status, started, finished, row[5],
                *limits, error,
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Ransomware monitor oturum kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _cycle(
        row, bases: dict[str, _SessionBase], source_runs, watch_runs, notifications,
        linked_watch_run_ids: tuple[str, ...],
    ) -> RansomwareWatchMonitorCycle:
        try:
            _uuid(row[0])
            session_id, source_run_id = _uuid(row[1]), _uuid(row[3])
            base = bases.get(session_id)
            source = source_runs.get(source_run_id)
            if base is None or source is None:
                raise ValueError("Missing relation")
            counts = row[2:3] + row[4:13]
            if any(type(value) is not int or value < 0 for value in counts):
                raise ValueError("Invalid cycle counts")
            cycle = row[2]
            if not 1 <= cycle <= base.planned_cycles:
                raise ValueError("Invalid cycle number")
            planned, completed, baseline = row[4:7]
            if planned > base.max_watches or completed > planned or baseline > completed:
                raise ValueError("Invalid watch counts")
            if row[7] != row[8] + row[9] + row[10] or row[12] > completed:
                raise ValueError("Invalid summary")
            related = []
            for run_id in linked_watch_run_ids:
                run = watch_runs.get(run_id)
                if run is None or run.source_run_id != source.id:
                    raise ValueError("Invalid linked watch run")
                related.append(run)
            related_ids = {run.id for run in related}
            actual = (
                len(related),
                sum(run.previous_run_id is None for run in related),
                sum(run.total_count for run in related),
                sum(run.added_count for run in related),
                sum(run.updated_count for run in related),
                sum(run.unchanged_count for run in related),
                sum(run.removed_count for run in related),
                sum(item[2] in related_ids for item in notifications),
            )
            if actual != (completed, baseline, *row[7:13]):
                raise ValueError("Cycle evidence mismatch")
            if source.status == "failed" and any(row[5:13]):
                raise ValueError("Failed source has watch results")
            return RansomwareWatchMonitorCycle(
                cycle=cycle, source_run_id=source.id,
                source_status=source.status,
                source_finished_at=source.finished_at,
                source_record_count=source.source_record_count,
                planned_watch_count=planned,
                completed_watch_count=completed,
                baseline_watch_count=baseline,
                total_count=row[7], added_count=row[8], updated_count=row[9],
                unchanged_count=row[10], removed_count=row[11],
                notification_count=row[12], source_error=source.error,
                watch_run_ids=linked_watch_run_ids,
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Ransomware monitor tur kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _session(
        base: _SessionBase, cycles: tuple[RansomwareWatchMonitorCycle, ...],
    ) -> RansomwareMonitorSession:
        completed = len(cycles)
        successful = sum(item.source_status == "complete" for item in cycles)
        failed = sum(item.source_status == "failed" for item in cycles)
        if completed != successful + failed or completed > base.planned_cycles:
            raise StorageError("Ransomware monitor oturum özeti bozuk.")
        if [item.cycle for item in cycles] != list(range(1, completed + 1)):
            raise StorageError("Ransomware monitor tur sırası bozuk.")
        if any(
            datetime.fromisoformat(item.source_finished_at)
            < datetime.fromisoformat(base.started_at)
            for item in cycles
        ):
            raise StorageError("Ransomware monitor tur zamanı bozuk.")
        if base.finished_at is not None and any(
            datetime.fromisoformat(item.source_finished_at)
            > datetime.fromisoformat(base.finished_at)
            for item in cycles
        ):
            raise StorageError("Ransomware monitor bitiş zamanı bozuk.")
        if base.status == "complete" and (completed == 0 or failed != 0):
            raise StorageError("Ransomware monitor tamamlanma durumu bozuk.")
        if base.status == "partial" and completed > 0 and failed == 0:
            raise StorageError("Ransomware monitor kısmi durumu bozuk.")
        if base.stop_reason == "cycles" and completed != base.planned_cycles:
            raise StorageError("Ransomware monitor tur bitiş nedeni bozuk.")
        if base.stop_reason == "duration" and completed >= base.planned_cycles:
            raise StorageError("Ransomware monitor süre bitiş nedeni bozuk.")
        return RansomwareMonitorSession(
            sequence=base.sequence, id=base.id, status=base.status,
            started_at=base.started_at, finished_at=base.finished_at,
            stop_reason=base.stop_reason, planned_cycles=base.planned_cycles,
            interval_seconds=base.interval_seconds,
            max_duration_seconds=base.max_duration_seconds,
            max_watches=base.max_watches,
            source_item_limit=base.source_item_limit,
            watch_item_limit=base.watch_item_limit, error=base.error,
            completed_cycles=completed, successful_cycles=successful,
            failed_cycles=failed,
            completed_watch_runs=sum(item.completed_watch_count for item in cycles),
            baseline_watch_runs=sum(item.baseline_watch_count for item in cycles),
            total_count=sum(item.total_count for item in cycles),
            added_count=sum(item.added_count for item in cycles),
            updated_count=sum(item.updated_count for item in cycles),
            unchanged_count=sum(item.unchanged_count for item in cycles),
            removed_count=sum(item.removed_count for item in cycles),
            notification_count=sum(item.notification_count for item in cycles),
        )

    @classmethod
    def _audit(cls, connection):
        session_rows = connection.execute(
            f"SELECT {_SESSION_SELECT} FROM ransomware_monitor_sessions "
            "ORDER BY sequence LIMIT ?", (_MAX_SESSIONS + 1,),
        ).fetchall()
        if len(session_rows) > _MAX_SESSIONS:
            raise StorageError("Ransomware monitor oturum sayısı güvenli sınırı aşıyor.")
        bases = {base.id: base for base in map(cls._base, session_rows)}
        if len(bases) != len(session_rows) or len({base.sequence for base in bases.values()}) != len(bases):
            raise StorageError("Ransomware monitor oturum kimliği veya sırası bozuk.")

        source_runs, _ = SQLiteRansomwareClaimRepository._audit(connection)
        source_by_id = {run.id: run for run in source_runs}
        _, _, watch_runs, _, notifications = SQLiteRansomwareWatchRepository._audit(connection)
        cycle_rows = connection.execute(
            f"SELECT {_CYCLE_SELECT} FROM ransomware_monitor_cycles "
            "ORDER BY session_id, cycle LIMIT ?", (_MAX_CYCLES + 1,),
        ).fetchall()
        if len(cycle_rows) > _MAX_CYCLES:
            raise StorageError("Ransomware monitor tur sayısı güvenli sınırı aşıyor.")
        try:
            cycle_ids = {_uuid(row[0]) for row in cycle_rows}
            if len(cycle_ids) != len(cycle_rows):
                raise ValueError("Duplicate cycle id")
            link_rows = connection.execute(
                f"SELECT {_LINK_SELECT} FROM ransomware_monitor_cycle_watch_runs "
                "ORDER BY cycle_id, position LIMIT ?", (_MAX_LINKS + 1,),
            ).fetchall()
            if len(link_rows) > _MAX_LINKS:
                raise ValueError("Too many cycle links")
            linked: dict[str, list[tuple[int, str]]] = {
                cycle_id: [] for cycle_id in cycle_ids
            }
            link_ids: set[str] = set()
            linked_run_ids: set[str] = set()
            for row in link_rows:
                link_id, cycle_id, watch_run_id = (
                    _uuid(row[0]), _uuid(row[1]), _uuid(row[3])
                )
                if (
                    link_id in link_ids or watch_run_id in linked_run_ids
                    or cycle_id not in linked or watch_run_id not in watch_runs
                    or type(row[2]) is not int or not 1 <= row[2] <= 500
                ):
                    raise ValueError("Invalid cycle link")
                link_ids.add(link_id)
                linked_run_ids.add(watch_run_id)
                linked[cycle_id].append((row[2], watch_run_id))
            linked_ids: dict[str, tuple[str, ...]] = {}
            for cycle_id, values in linked.items():
                values.sort()
                if [position for position, _ in values] != list(
                    range(1, len(values) + 1)
                ):
                    raise ValueError("Invalid cycle link order")
                linked_ids[cycle_id] = tuple(run_id for _, run_id in values)
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError(
                "Ransomware monitor tur-izleme bağlantısı bozuk; işlem durduruldu."
            ) from error
        cycle_pairs = [
            (
                row[1],
                cls._cycle(
                    row, bases, source_by_id, watch_runs, notifications,
                    linked_ids[row[0]],
                ),
            )
            for row in cycle_rows
        ]
        by_session = {session_id: [] for session_id in bases}
        for session_id, cycle in cycle_pairs:
            by_session[session_id].append(cycle)
        sessions = {
            session_id: cls._session(base, tuple(by_session[session_id]))
            for session_id, base in bases.items()
        }
        return sessions, {key: tuple(value) for key, value in by_session.items()}

    def start(self, **values) -> RansomwareMonitorSession:
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._audit(connection)
                started_at = _timestamp(
                    values["started_at"], field="ransomware monitor başlangıç zamanı",
                )
                ranges = {
                    "planned_cycles": (1, 1000),
                    "interval_seconds": (300, 86400),
                    "max_duration_seconds": (1, 604800),
                    "max_watches": (1, 500),
                    "source_item_limit": (1, 500),
                    "watch_item_limit": (1, 500),
                }
                if any(
                    type(values[key]) is not int or not low <= values[key] <= high
                    for key, (low, high) in ranges.items()
                ):
                    raise ValidationError("Ransomware monitor oturum sınırları geçersiz.")
                session_id = str(uuid4())
                connection.execute(
                    "INSERT INTO ransomware_monitor_sessions "
                    "(id, status, started_at, finished_at, stop_reason, planned_cycles, "
                    "interval_seconds, max_duration_seconds, max_watches, source_item_limit, "
                    "watch_item_limit, error) VALUES (?, 'running', ?, NULL, '', ?, ?, ?, ?, ?, ?, '')",
                    (session_id, started_at, values["planned_cycles"],
                     values["interval_seconds"], values["max_duration_seconds"],
                     values["max_watches"], values["source_item_limit"],
                     values["watch_item_limit"]),
                )
                sessions, _ = self._audit(connection)
                connection.commit()
                return sessions[session_id]
            except BaseException:
                connection.rollback()
                raise

    def record_cycle(self, session_id, cycle):
        if not isinstance(cycle, RansomwareWatchMonitorCycle):
            raise ValidationError("Ransomware monitor tur sonucu geçersiz.")
        try:
            if (
                not isinstance(cycle.watch_run_ids, tuple)
                or len(cycle.watch_run_ids) != cycle.completed_watch_count
                or len(set(cycle.watch_run_ids)) != len(cycle.watch_run_ids)
            ):
                raise ValueError("Invalid watch run links")
            watch_run_ids = tuple(_uuid(value) for value in cycle.watch_run_ids)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError(
                "Ransomware monitor tur izleme bağlantıları geçersiz."
            ) from error
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                sessions, cycles = self._audit(connection)
                session = sessions.get(session_id)
                if session is None:
                    raise ValidationError("Ransomware monitor oturumu bulunamadı.")
                if session.status != "running":
                    raise ValidationError("Tamamlanmış ransomware monitor oturumuna tur eklenemez.")
                if cycle.cycle != len(cycles[session.id]) + 1:
                    raise ValidationError("Ransomware monitor tur sırası geçersiz.")
                cycle_id = str(uuid4())
                connection.execute(
                    "INSERT INTO ransomware_monitor_cycles VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (cycle_id, session.id, cycle.cycle, cycle.source_run_id,
                     cycle.planned_watch_count, cycle.completed_watch_count,
                     cycle.baseline_watch_count, cycle.total_count, cycle.added_count,
                     cycle.updated_count, cycle.unchanged_count, cycle.removed_count,
                     cycle.notification_count),
                )
                for position, run_id in enumerate(watch_run_ids, start=1):
                    connection.execute(
                        "INSERT INTO ransomware_monitor_cycle_watch_runs "
                        "VALUES (?, ?, ?, ?)",
                        (str(uuid4()), cycle_id, position, run_id),
                    )
                sessions, _ = self._audit(connection)
                connection.commit()
                return sessions[session.id]
            except BaseException:
                connection.rollback()
                raise

    def finish(self, session_id, *, status, stop_reason, finished_at, error):
        if status not in {"complete", "partial", "interrupted", "failed"}:
            raise ValidationError("Ransomware monitor oturum bitiş durumu geçersiz.")
        try:
            finished_at = _timestamp(
                finished_at, field="ransomware monitor bitiş zamanı",
            )
            error = _error(error, required=status == "failed")
        except (TypeError, ValueError, ValidationError, OverflowError) as exception:
            raise ValidationError("Ransomware monitor oturum bitiş bilgisi geçersiz.") from exception
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                sessions, _ = self._audit(connection)
                session = sessions.get(session_id)
                if session is None:
                    raise ValidationError("Ransomware monitor oturumu bulunamadı.")
                if session.status != "running":
                    raise ValidationError("Ransomware monitor oturumu zaten tamamlanmış.")
                connection.execute(
                    "UPDATE ransomware_monitor_sessions SET status=?, finished_at=?, "
                    "stop_reason=?, error=? WHERE id=?",
                    (status, finished_at, stop_reason, error, session.id),
                )
                sessions, _ = self._audit(connection)
                connection.commit()
                return sessions[session.id]
            except BaseException:
                connection.rollback()
                raise

    def list(self, *, limit):
        with self._storage._connection(readonly=True) as connection:
            sessions, _ = self._audit(connection)
        return tuple(sorted(
            sessions.values(), key=lambda item: item.sequence, reverse=True,
        )[:limit])

    def details(self, session_id, *, cycle_limit):
        with self._storage._connection(readonly=True) as connection:
            sessions, cycles = self._audit(connection)
        session = sessions.get(session_id)
        if session is None:
            raise ValidationError("Ransomware monitor oturumu bulunamadı.")
        values = cycles[session.id]
        return RansomwareMonitorSessionDetails(
            session=session, cycles=values[-cycle_limit:],
            total_cycle_count=len(values),
        )

"""Atomic session/job links and compact, immutable first-attempt reporting."""

from contextlib import contextmanager
import math
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cooldowns import _timestamp
from xti.adapters.sqlite_jobs import SQLiteJobRepository, _JOB_COLUMNS, _dumps, _loads
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.jobs import ScanJob
from xti.domain.monitoring import (
    MonitorAttempt, MonitorDetails, MonitorEntry, MonitorRun, MonitorSpec,
)


_RUN_COLUMNS = (
    "id, targets, providers, typos, rule_version, max_cycles, interval_seconds, "
    "max_duration_seconds, status, started_at, finished_at, elapsed_seconds, stop_reason"
)
_PROVIDERS = frozenset({"crt.sh", "urlscan"})
_FINAL_REASONS = {
    "completed": frozenset({"cycles", "duration"}),
    "interrupted": frozenset({"cancelled", "recovered"}),
    "failed": frozenset({"error"}),
}
_RECOVERY_ERROR = "İzleme denemesi tamamlanmadan durdu; bu çalışma yeniden başlatılmadı."


def _identifier(value: str) -> None:
    if (not isinstance(value, str) or not value or len(value) > 64
            or not value.isprintable() or value.isspace()):
        raise ValidationError("Geçerli bir izleme denemesi kimliği gerekli.")


def _spec(value: MonitorSpec) -> MonitorSpec:
    if not isinstance(value, MonitorSpec):
        raise ValueError("Invalid monitoring specification")
    if (not isinstance(value.targets, tuple) or not 1 <= len(value.targets) <= 5
            or any(normalize_domain(item) != item for item in value.targets)
            or len(set(value.targets)) != len(value.targets)):
        raise ValueError("Invalid monitored targets")
    if (not isinstance(value.providers, tuple) or not 1 <= len(value.providers) <= 2
            or any(item not in _PROVIDERS for item in value.providers)
            or len(set(value.providers)) != len(value.providers)):
        raise ValueError("Invalid monitored providers")
    if (type(value.typos) is not bool or not isinstance(value.rule_version, str)
            or not value.rule_version or len(value.rule_version) > 512
            or not value.rule_version.isprintable() or value.rule_version.isspace()):
        raise ValueError("Invalid rule configuration")
    for number, lower, upper in (
        (value.max_cycles, 1, 1000), (value.interval_seconds, 300, 86400),
        (value.max_duration_seconds, 1, 604800),
    ):
        if type(number) is not int or not lower <= number <= upper:
            raise ValueError("Invalid session bound")
    return value


def _elapsed(value: float | None) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid elapsed duration")
    return float(value)


class SQLiteMonitorRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @contextmanager
    def _write(self):
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _now(value: str) -> str:
        try:
            return _timestamp(value).isoformat()
        except (ValueError, TypeError, OverflowError) as error:
            raise ValidationError("İzleme denemesi için saat dilimi belli geçerli zaman gerekli.") from error

    @staticmethod
    def _row(row) -> MonitorRun:
        try:
            _identifier(row[0])
            targets, providers = _loads(row[1]), _loads(row[2])
            if not isinstance(targets, list) or not isinstance(providers, list) or row[3] not in (0, 1):
                raise ValueError("Invalid specification fields")
            spec = _spec(MonitorSpec(
                tuple(targets), tuple(providers), bool(row[3]), row[4], row[5], row[6], row[7],
            ))
            started = _timestamp(row[9]).isoformat()
            finished = _timestamp(row[10]).isoformat() if row[10] is not None else None
            elapsed = _elapsed(row[11])
            if row[8] == "running":
                if finished is not None or elapsed is not None or row[12] is not None:
                    raise ValueError("Running session has a finish")
            elif row[8] not in _FINAL_REASONS or row[12] not in _FINAL_REASONS[row[8]] or finished is None:
                raise ValueError("Invalid final session state")
            # The wall clock may move backward; elapsed time is independently monotonic.
            return MonitorRun(row[0], spec, row[8], started, finished, elapsed, row[12])
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as error:
            raise StorageError("İzleme denemesinin kaydı bozuk; işlem durduruldu.") from error

    @classmethod
    def _get_run(cls, connection, run_id: str) -> MonitorRun:
        row = connection.execute(
            "SELECT " + _RUN_COLUMNS + " FROM monitor_runs WHERE id = ?", (run_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("İzleme denemesi bulunamadı; 'xti monitor list' ile kimliği kontrol et.")
        return cls._row(row)

    def create(self, spec: MonitorSpec, now: str) -> MonitorRun:
        try:
            _spec(spec)
        except (ValueError, TypeError) as error:
            raise ValidationError("İzleme denemesinin adres, kaynak veya çalışma sınırları geçersiz.") from error
        now = self._now(now)
        with self._write() as connection:
            if connection.execute("SELECT 1 FROM monitor_runs WHERE status = 'running' LIMIT 1").fetchone():
                raise ValidationError("Önce önceki izleme denemesini 'monitor recover' ile kapat.")
            saved = {row[0] for row in connection.execute(
                "SELECT value FROM assets WHERE value IN (" + ",".join("?" for _ in spec.targets) + ")",
                spec.targets,
            )}
            if saved != set(spec.targets):
                raise ValidationError("İzlenecek adreslerin tamamı önce kayıtlı olmalı.")
            run_id = str(uuid4())
            connection.execute(
                "INSERT INTO monitor_runs (" + _RUN_COLUMNS + ") "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, NULL, NULL, NULL)",
                (run_id, _dumps(spec.targets), _dumps(spec.providers), int(spec.typos),
                 spec.rule_version, spec.max_cycles, spec.interval_seconds, spec.max_duration_seconds, now),
            )
            return self._get_run(connection, run_id)

    def enqueue(self, run_id: str, cycle: int, provider: str, now: str) -> ScanJob:
        _identifier(run_id)
        if (type(cycle) is not int or not 1 <= cycle <= 1000
                or not isinstance(provider, str) or provider not in _PROVIDERS):
            raise ValidationError("Geçerli izleme turu ve kaynağı gerekli.")
        now = self._now(now)
        with self._write() as connection:
            run = self._get_run(connection, run_id)
            if run.status != "running" or provider not in run.spec.providers or cycle > run.spec.max_cycles:
                raise ValidationError("Bu izleme denemesinde belirtilen çalışma başlatılamaz.")
            scheduled = connection.execute(
                "SELECT COUNT(*) FROM monitor_jobs WHERE run_id = ?", (run_id,),
            ).fetchone()[0]
            expected_cycle, index = divmod(scheduled, len(run.spec.providers))
            if cycle != expected_cycle + 1 or provider != run.spec.providers[index]:
                raise ValidationError("İzleme çalışması zaten kayıtlı veya beklenen sırada değil.")
            job_id = str(uuid4())
            connection.execute(
                "INSERT INTO scan_jobs (" + _JOB_COLUMNS + ") "
                "VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, 0)",
                (job_id, _dumps(run.spec.targets), int(run.spec.typos), provider,
                 run.spec.rule_version, now, now),
            )
            connection.execute(
                "INSERT INTO monitor_jobs (run_id, cycle, provider, job_id) VALUES (?, ?, ?, ?)",
                (run_id, cycle, provider, job_id),
            )
            return SQLiteJobRepository._get_job(connection, job_id)

    @staticmethod
    def _retire_pending(connection, run_id: str, now: str) -> None:
        connection.execute(
            "UPDATE scan_attempts SET status = 'interrupted', finished_at = ?, error = ? "
            "WHERE status = 'running' AND job_id IN (SELECT job_id FROM monitor_jobs WHERE run_id = ?)",
            (now, _RECOVERY_ERROR, run_id),
        )
        connection.execute(
            "UPDATE scan_jobs SET status = 'interrupted', updated_at = ? "
            "WHERE status IN ('queued', 'running') AND id IN "
            "(SELECT job_id FROM monitor_jobs WHERE run_id = ?)", (now, run_id),
        )

    def finish(
        self, run_id: str, status: str, reason: str, now: str,
        elapsed_seconds: float | None,
    ) -> MonitorRun:
        _identifier(run_id)
        if (not isinstance(status, str) or status not in _FINAL_REASONS
                or not isinstance(reason, str) or reason not in _FINAL_REASONS[status]):
            raise ValidationError("İzleme denemesinin bitiş nedeni ve durumu geçersiz.")
        now = self._now(now)
        try:
            elapsed = _elapsed(elapsed_seconds)
        except (ValueError, TypeError, OverflowError) as error:
            raise ValidationError("İzleme denemesinin ölçülen süresi geçersiz.") from error
        with self._write() as connection:
            run = self._get_run(connection, run_id)
            if run.status != "running":
                raise ValidationError("Bu izleme denemesi zaten kapanmış; geçmişi değiştirilemez.")
            if status == "completed":
                if reason == "cycles":
                    scheduled = connection.execute(
                        "SELECT COUNT(*) FROM monitor_jobs WHERE run_id = ?", (run_id,),
                    ).fetchone()[0]
                    if scheduled != run.spec.max_cycles * len(run.spec.providers):
                        raise ValidationError("Planlanan bütün izleme turları bitmeden tur sınırıyla kapatılamaz.")
                    if connection.execute(
                        "SELECT 1 FROM monitor_jobs m LEFT JOIN scan_attempts a "
                        "ON a.job_id = m.job_id AND a.number = 1 WHERE m.run_id = ? "
                        "AND (a.id IS NULL OR a.status NOT IN ('complete', 'partial', 'failed', 'interrupted')) LIMIT 1",
                        (run_id,),
                    ).fetchone():
                        raise ValidationError("İzleme turlarının ilk denemeleri henüz bitmemiş.")
                pending = {row[0] for row in connection.execute(
                    "SELECT DISTINCT j.status FROM scan_jobs j JOIN monitor_jobs m ON m.job_id = j.id "
                    "WHERE m.run_id = ? AND j.status IN ('queued', 'running')", (run_id,),
                )}
                if "running" in pending or (reason == "cycles" and pending):
                    raise ValidationError("Bekleyen izleme çalışmaları varken deneme tamamlandı sayılamaz.")
                if pending:
                    # A deadline can expire after atomic enqueue and before the
                    # owner starts the job. Retire it without inventing a try.
                    self._retire_pending(connection, run_id, now)
            else:
                self._retire_pending(connection, run_id, now)
            connection.execute(
                "UPDATE monitor_runs SET status = ?, finished_at = ?, elapsed_seconds = ?, stop_reason = ? "
                "WHERE id = ?", (status, now, elapsed, reason, run_id),
            )
            return self._get_run(connection, run_id)

    def recover(self, now: str) -> int:
        now = self._now(now)
        with self._write() as connection:
            rows = connection.execute(
                "SELECT " + _RUN_COLUMNS + " FROM monitor_runs WHERE status = 'running' ORDER BY rowid"
            ).fetchall()
            for row in rows:
                run = self._row(row)
                self._retire_pending(connection, run.id, now)
                connection.execute(
                    "UPDATE monitor_runs SET status = 'interrupted', finished_at = ?, "
                    "elapsed_seconds = NULL, stop_reason = 'recovered' WHERE id = ?", (now, run.id),
                )
            return len(rows)

    def list(self, limit: int = 20) -> tuple[MonitorRun, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("İzleme listesi sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            return tuple(self._row(row) for row in connection.execute(
                "SELECT " + _RUN_COLUMNS + " FROM monitor_runs ORDER BY rowid DESC LIMIT ?", (limit,),
            ))

    @staticmethod
    def _entry(connection, run: MonitorRun, cycle: int, provider: str, job_id: str) -> MonitorEntry:
        if type(cycle) is not int or not 1 <= cycle <= run.spec.max_cycles or provider not in run.spec.providers:
            raise StorageError("İzleme denemesinin iş bağlantısı bozuk.")
        try:
            job = SQLiteJobRepository._get_job(connection, job_id)
        except ValidationError as error:
            raise StorageError("İzleme denemesinin bağlı işi bulunamadı.") from error
        if (job.targets != run.spec.targets or job.provider != provider
                or job.typos != run.spec.typos or job.rule_version != run.spec.rule_version):
            raise StorageError("İzleme denemesi ile bağlı işin kapsamı uyuşmuyor.")
        count, maximum = connection.execute(
            "SELECT COUNT(*), MAX(number) FROM scan_attempts WHERE job_id = ?", (job.id,),
        ).fetchone()
        if count != job.attempt_count or (count and maximum != count):
            raise StorageError("İzleme işinin deneme geçmişi eksik veya tutarsız.")
        if not count:
            if job.status not in {"queued", "interrupted"}:
                raise StorageError("İzleme işinin çalışma kaydı bulunamadı.")
            return MonitorEntry(cycle, provider, job, None)
        first = connection.execute(
            "SELECT id FROM scan_attempts WHERE job_id = ? AND number = 1", (job.id,),
        ).fetchone()
        if first is None:
            raise StorageError("İzleme işinin ilk çalışma kaydı bulunamadı.")
        attempt = SQLiteJobRepository._get_attempt(connection, first[0])
        if (attempt.job_id != job.id or attempt.number != 1
                or (count == 1 and job.status != attempt.status)
                or (attempt.result is not None and attempt.result.targets != run.spec.targets)
                or (attempt.status in {"complete", "partial"} and attempt.result is None)
                or (attempt.status == "complete" and (
                    not attempt.queries or any(query.status != "complete" for query in attempt.queries)
                ))):
            raise StorageError("İzleme denemesinin kayıtlı sonucu tutarsız.")
        compact = MonitorAttempt(
            id=attempt.id, number=attempt.number, status=attempt.status,
            started_at=attempt.started_at, finished_at=attempt.finished_at,
            error=attempt.error or next((query.error for query in reversed(attempt.queries) if query.error), None),
            query_count=len(attempt.queries),
            failed_queries=sum(query.status == "failed" for query in attempt.queries),
            partial_queries=sum(query.status == "partial" for query in attempt.queries),
            summary=attempt.result.summary if attempt.result is not None else None,
        )
        return MonitorEntry(cycle, provider, job, compact)

    def get(self, run_id: str) -> MonitorDetails:
        _identifier(run_id)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            try:
                run = self._get_run(connection, run_id)
                entries = []
                for cycle, provider, job_id in connection.execute(
                    "SELECT cycle, provider, job_id FROM monitor_jobs WHERE run_id = ? ORDER BY rowid", (run_id,),
                ):
                    if len(entries) >= run.spec.max_cycles * len(run.spec.providers):
                        raise StorageError("İzleme denemesinin iş sayısı sınırı aşıyor.")
                    expected_cycle, index = divmod(len(entries), len(run.spec.providers))
                    if cycle != expected_cycle + 1 or provider != run.spec.providers[index]:
                        raise StorageError("İzleme denemesinin çalışma sırası eksik veya tutarsız.")
                    entries.append(self._entry(connection, run, cycle, provider, job_id))
                if run.status == "completed":
                    if run.stop_reason == "cycles" and len(entries) != run.spec.max_cycles * len(run.spec.providers):
                        raise StorageError("Tamamlanmış izleme denemesinin tur geçmişi eksik.")
                    if any(
                        (entry.attempt is not None and entry.attempt.status == "running")
                        or (entry.attempt is None and (
                            run.stop_reason == "cycles" or entry.job.status != "interrupted"
                        ))
                        for entry in entries
                    ):
                        raise StorageError("Tamamlanmış izleme denemesinde bitmemiş çalışma kaydı var.")
                return MonitorDetails(run, tuple(entries))
            finally:
                connection.rollback()

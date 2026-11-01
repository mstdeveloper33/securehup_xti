"""Short atomic transactions for durable jobs and their execution history."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.discovery import QueryResult, ScanResult
from xti.domain.findings import ImportSummary
from xti.domain.jobs import JOB_STATUSES, RETRYABLE_STATUSES, JobDetails, ScanAttempt, ScanJob
from xti.ports.jobs import WorkerBusyError


_JOB_COLUMNS = "id, targets, typos, provider, rule_version, status, created_at, updated_at, attempt_count"
_ATTEMPT_COLUMNS = "id, job_id, number, status, started_at, finished_at, progress, error, queries, result"
_RESULT_STATUSES = {"complete", "partial", "failed"}
_FINISHED_STATUSES = _RESULT_STATUSES | {"interrupted"}
_MAX_JSON = 4 * 1024 * 1024
_MAX_TEXT = 4096


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value, *, optional=False, maximum=_MAX_TEXT):
    if value is None and optional:
        return None
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("Invalid text")
    return value


def _integer(value, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid integer")
    return value


def _strings(value, *, minimum=0, maximum=10000, item_size=253):
    if not isinstance(value, (list, tuple)) or not minimum <= len(value) <= maximum:
        raise ValueError("Invalid string list")
    return tuple(_text(item, maximum=item_size) for item in value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError("Invalid JSON constant")


def _loads(value: str):
    if not isinstance(value, str) or len(value) > _MAX_JSON:
        raise ValueError("Invalid JSON size")
    return json.loads(value, object_pairs_hook=_unique_object, parse_constant=_bad_constant)


def _dumps(value) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    if len(encoded) > _MAX_JSON:
        raise ValidationError("İş geçmişi kaydı boyut sınırını aşıyor.")
    return encoded


def _query(value) -> QueryResult:
    if not isinstance(value, dict):
        raise ValueError("Invalid query")
    common = {"pattern", "source_url", "status", "skipped_names", "error", "warnings"}
    fields = set(value)
    # 0.4 history used a certificate-specific count. Read it without rewriting
    # saved evidence; new providers use a generic count and explicit scope notes.
    if fields == common | {"certificate_count"}:
        count = value["certificate_count"]
        coverage_notes = ()
    elif fields in (common | {"record_count"}, common | {"record_count", "coverage_notes"}):
        count = value["record_count"]
        coverage_notes = _strings(value.get("coverage_notes", ()), maximum=100, item_size=_MAX_TEXT)
    else:
        raise ValueError("Invalid query fields")
    if value["status"] not in _RESULT_STATUSES:
        raise ValueError("Invalid query status")
    return QueryResult(
        _text(value["pattern"], maximum=255), _text(value["source_url"]), value["status"],
        _integer(count), _integer(value["skipped_names"]),
        _text(value["error"], optional=True),
        _strings(value["warnings"], maximum=100, item_size=_MAX_TEXT),
        coverage_notes,
    )


def _queries(value) -> tuple[QueryResult, ...]:
    if not isinstance(value, (list, tuple)) or len(value) > 100:
        raise ValueError("Invalid query list")
    result = tuple(_query(item) for item in value)
    if len({item.pattern for item in result}) != len(result):
        raise ValueError("Repeated query")
    return result


def _result(value) -> ScanResult:
    if not isinstance(value, dict) or set(value) != {
        "targets", "started_at", "finished_at", "status", "queries", "summary", "candidate_domains",
    }:
        raise ValueError("Invalid scan result")
    if value["status"] not in _RESULT_STATUSES:
        raise ValueError("Invalid result status")
    summary = value["summary"]
    legacy_summary_keys = ("total_records", "observations_created", "observations_existing",
                           "findings_created", "findings_existing")
    summary_keys = legacy_summary_keys + ("findings_suppressed",)
    if not isinstance(summary, dict) or frozenset(summary) not in {
        frozenset(legacy_summary_keys), frozenset(summary_keys),
    }:
        raise ValueError("Invalid summary")
    return ScanResult(
        _strings(value["targets"], minimum=1, maximum=5),
        _text(value["started_at"]), _text(value["finished_at"]), value["status"],
        _queries(value["queries"]),
        ImportSummary(
            *(_integer(summary[key]) for key in legacy_summary_keys),
            findings_suppressed=_integer(summary.get("findings_suppressed", 0)),
        ),
        _strings(value["candidate_domains"]),
    )


class SQLiteJobRepository:
    def __init__(self, path: Path) -> None:
        self.database = SQLiteAssetRepository(path)

    @contextmanager
    def _write(self):
        with self.database._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _job(row) -> ScanJob:
        try:
            targets = _strings(_loads(row[1]), minimum=1, maximum=5)
            if row[2] not in (0, 1) or row[5] not in JOB_STATUSES:
                raise ValueError("Invalid job state")
            return ScanJob(
                _text(row[0]), targets, bool(row[2]), _text(row[3]), _text(row[4]), row[5],
                _text(row[6]), _text(row[7]), _integer(row[8]),
            )
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise StorageError("İş geçmişindeki kayıt bozuk; işlem durduruldu.") from exc

    @staticmethod
    def _attempt(row) -> ScanAttempt:
        try:
            if row[3] not in _FINISHED_STATUSES | {"running"}:
                raise ValueError("Invalid attempt status")
            result = _result(_loads(row[9])) if row[9] is not None else None
            queries = _queries(_loads(row[8]))
            if result is not None and (result.status != row[3] or result.queries != queries):
                raise ValueError("Inconsistent attempt result")
            if (row[3] == "running") != (row[5] is None):
                raise ValueError("Inconsistent finish time")
            return ScanAttempt(
                _text(row[0]), _text(row[1]), _integer(row[2], minimum=1), row[3],
                _text(row[4]), _text(row[5], optional=True),
                _text(row[6], optional=True), _text(row[7], optional=True), queries, result,
            )
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            raise StorageError("İşin çalışma geçmişi bozuk; işlem durduruldu.") from exc

    @classmethod
    def _get_job(cls, connection, job_id: str) -> ScanJob:
        row = connection.execute(
            "SELECT " + _JOB_COLUMNS + " FROM scan_jobs WHERE id = ?", (job_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("İş bulunamadı. Kimliği 'xti jobs list' ile kontrol et.")
        return cls._job(row)

    @classmethod
    def _get_attempt(cls, connection, attempt_id: str) -> ScanAttempt:
        row = connection.execute(
            "SELECT " + _ATTEMPT_COLUMNS + " FROM scan_attempts WHERE id = ?", (attempt_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("Çalışma kaydı bulunamadı.")
        return cls._attempt(row)

    def create(self, targets: tuple[str, ...], typos: bool, provider: str, rule_version: str) -> ScanJob:
        try:
            targets = _strings(targets, minimum=1, maximum=5)
            if len(set(targets)) != len(targets) or type(typos) is not bool:
                raise ValueError
            if not _text(provider) or not _text(rule_version):
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise ValidationError("Geçerli adresler, kaynak ve kural sürümü gerekli.") from exc
        with self._write() as connection:
            now, job_id = _now(), str(uuid4())
            connection.execute(
                "INSERT INTO scan_jobs (" + _JOB_COLUMNS + ") VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, 0)",
                (job_id, _dumps(targets), int(typos), provider, rule_version, now, now),
            )
            return self._get_job(connection, job_id)

    def list(self, status: str | None = None, limit: int = 20) -> list[ScanJob]:
        if status is not None and status not in JOB_STATUSES:
            raise ValidationError("Geçersiz iş durumu.")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValidationError("İş listesi sınırı 1–1000 arasında olmalı.")
        with self.database._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT " + _JOB_COLUMNS + " FROM scan_jobs "
                + ("WHERE status = ? " if status is not None else "")
                + "ORDER BY rowid DESC LIMIT ?",
                (status, limit) if status is not None else (limit,),
            ).fetchall()
            return [self._job(row) for row in rows]

    def get(self, job_id: str) -> JobDetails:
        with self.database._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            try:
                return self._details(connection, job_id)
            finally:
                connection.rollback()

    @classmethod
    def _details(cls, connection, job_id: str) -> JobDetails:
        job = cls._get_job(connection, job_id)
        attempts = tuple(cls._attempt(row) for row in connection.execute(
            "SELECT " + _ATTEMPT_COLUMNS + " FROM scan_attempts WHERE job_id = ? ORDER BY number",
            (job_id,),
        ))
        if len(attempts) != job.attempt_count:
            raise StorageError("İş ile çalışma geçmişinin sayısı uyuşmuyor.")
        return JobDetails(job, attempts)

    def latest_by_provider(self) -> list[JobDetails]:
        with self.database._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            try:
                rows = connection.execute(
                    "SELECT j.id FROM scan_jobs j JOIN scan_attempts a ON a.job_id = j.id "
                    "WHERE a.rowid IN (SELECT MAX(a2.rowid) FROM scan_attempts a2 "
                    "JOIN scan_jobs j2 ON j2.id = a2.job_id GROUP BY j2.provider) "
                    "ORDER BY j.provider"
                ).fetchall()
                return [self._details(connection, row[0]) for row in rows]
            finally:
                connection.rollback()

    def recover_interrupted(self, reason: str) -> int:
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError("Kurtarma gerekçesi gerekli.")
        with self._write() as connection:
            now = _now()
            count = connection.execute(
                "SELECT COUNT(*) FROM scan_jobs WHERE status = 'running'"
            ).fetchone()[0]
            connection.execute(
                "UPDATE scan_attempts SET status = 'interrupted', finished_at = ?, error = ? "
                "WHERE status = 'running'", (now, reason[:_MAX_TEXT]),
            )
            connection.execute(
                "UPDATE scan_jobs SET status = 'interrupted', updated_at = ? WHERE status = 'running'", (now,),
            )
            return count

    def start(
        self, job_id: str | None = None, *, monitor_id: str | None = None,
    ) -> ScanAttempt | None:
        if monitor_id is not None and (
            job_id is None or not isinstance(monitor_id, str) or not monitor_id
            or len(monitor_id) > 64 or not monitor_id.isprintable()
        ):
            raise ValidationError("İzleme işini başlatmak için geçerli oturum ve iş kimliği gerekli.")
        with self._write() as connection:
            if connection.execute("SELECT 1 FROM scan_jobs WHERE status = 'running' LIMIT 1").fetchone():
                raise WorkerBusyError("Başka bir iş çalışıyor; önce mevcut işin bitmesini bekle.")
            if job_id is None:
                row = connection.execute(
                    "SELECT j.id FROM scan_jobs j WHERE j.status = 'queued' "
                    "AND NOT EXISTS (SELECT 1 FROM monitor_jobs m WHERE m.job_id = j.id) "
                    "ORDER BY j.rowid LIMIT 1"
                ).fetchone()
                if row is None:
                    return None
                job_id = row[0]
            job = self._get_job(connection, job_id)
            owner = connection.execute(
                "SELECT m.run_id, r.status FROM monitor_jobs m "
                "LEFT JOIN monitor_runs r ON r.id = m.run_id WHERE m.job_id = ?", (job_id,),
            ).fetchone()
            if owner is not None:
                if (
                    monitor_id != owner[0] or owner[1] != "running"
                    or job.status != "queued" or job.attempt_count != 0
                ):
                    raise ValidationError(
                        "Bu iş izleme denemesine bağlı; ayrı çalıştırılamaz veya yeniden denenemez. "
                        "Yeni bir 'monitor start' denemesi başlat."
                    )
            elif monitor_id is not None:
                raise ValidationError("Bu iş belirtilen izleme denemesine ait değil.")
            if job.status not in RETRYABLE_STATUSES | {"queued"}:
                raise ValidationError("Bu iş yeniden çalıştırılamaz; yeni arama başlat.")
            now, attempt_id = _now(), str(uuid4())
            number = job.attempt_count + 1
            connection.execute(
                "UPDATE scan_jobs SET status = 'running', updated_at = ?, attempt_count = ? WHERE id = ?",
                (now, number, job_id),
            )
            connection.execute(
                "INSERT INTO scan_attempts (" + _ATTEMPT_COLUMNS + ") "
                "VALUES (?, ?, ?, 'running', ?, NULL, NULL, NULL, '[]', NULL)",
                (attempt_id, job_id, number, now),
            )
            return self._get_attempt(connection, attempt_id)

    def progress(self, attempt_id: str, message: str, query: QueryResult | None = None) -> None:
        if not isinstance(message, str):
            raise ValidationError("İlerleme açıklaması metin olmalı.")
        try:
            checked_query = _query(asdict(query)) if query is not None else None
        except (ValueError, TypeError, KeyError) as exc:
            raise ValidationError("Geçersiz kaynak sorgusu kaydı.") from exc
        with self._write() as connection:
            attempt = self._get_attempt(connection, attempt_id)
            job = self._get_job(connection, attempt.job_id)
            if attempt.status != "running" or job.status != "running":
                raise ValidationError("Bu çalışma tamamlandı; eski ilerleme güncellemesi kabul edilmedi.")
            queries = attempt.queries
            if checked_query is not None:
                if any(item.pattern == checked_query.pattern for item in queries):
                    raise ValidationError("Aynı sorgu bu çalışma geçmişinde zaten kayıtlı.")
                queries += (checked_query,)
                if len(queries) > 100:
                    raise ValidationError("Çalışma sorgu sınırını aştı.")
            connection.execute(
                "UPDATE scan_attempts SET progress = ?, queries = ? WHERE id = ? AND status = 'running'",
                (message[:_MAX_TEXT], _dumps([asdict(item) for item in queries]), attempt_id),
            )
            connection.execute("UPDATE scan_jobs SET updated_at = ? WHERE id = ?", (_now(), job.id))

    def finish(
        self, attempt_id: str, status: str, *, result: ScanResult | None = None,
        error: str | None = None,
    ) -> ScanAttempt:
        if status not in _FINISHED_STATUSES:
            raise ValidationError("Geçersiz çalışma bitiş durumu.")
        if error is not None and not isinstance(error, str):
            raise ValidationError("Hata açıklaması metin olmalı.")
        try:
            checked_result = _result(asdict(result)) if result is not None else None
        except (ValueError, TypeError, KeyError) as exc:
            raise ValidationError("Geçersiz arama sonuç kaydı.") from exc
        if (checked_result is not None and checked_result.status != status) or (
            status in {"complete", "partial"} and checked_result is None
        ):
            raise ValidationError("Çalışma durumu ve arama sonucu uyuşmuyor.")
        with self._write() as connection:
            attempt = self._get_attempt(connection, attempt_id)
            job = self._get_job(connection, attempt.job_id)
            if attempt.status != "running" or job.status != "running":
                raise ValidationError("Bu çalışma artık etkin değil; bitiş güncellemesi kabul edilmedi.")
            queries = attempt.queries
            if checked_result is not None:
                if checked_result.targets != job.targets:
                    raise ValidationError("Arama sonucu işin izlenen adresleriyle uyuşmuyor.")
                if queries and queries != checked_result.queries:
                    raise ValidationError("Arama sonucu kayıtlı sorgu geçmişiyle uyuşmuyor.")
                queries = checked_result.queries
            now = _now()
            connection.execute(
                "UPDATE scan_attempts SET status = ?, finished_at = ?, error = ?, queries = ?, result = ? "
                "WHERE id = ? AND status = 'running'",
                (status, now, error[:_MAX_TEXT] if error is not None else None,
                 _dumps([asdict(item) for item in queries]),
                 _dumps(asdict(checked_result)) if checked_result is not None else None, attempt_id),
            )
            connection.execute(
                "UPDATE scan_jobs SET status = ?, updated_at = ? WHERE id = ? AND status = 'running'",
                (status, now, job.id),
            )
            return self._get_attempt(connection, attempt_id)

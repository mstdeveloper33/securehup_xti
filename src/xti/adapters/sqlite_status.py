"""One read snapshot of local counts and per-asset source history.

Only selected attempts load result/query JSON. Metadata is streamed, so a long
history costs read time without loading every saved result into memory. The
existing schema stores targets in JSON; this adapter does not require SQLite's
optional JSON extension or create indexes during a status read.
"""

from pathlib import Path
import sqlite3

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cooldowns import SQLiteCooldownRepository
from xti.adapters.sqlite_jobs import SQLiteJobRepository, _JOB_COLUMNS
from xti.adapters.sqlite_notification_sequence import notification_counts
from xti.domain.assets import Asset, ValidationError, normalize_domain
from xti.domain.jobs import JOB_STATUSES, ScanJob
from xti.domain.status import AssetHistory, SourceHistory, StatusAttempt, StatusSnapshot


_FINDING_STATUSES = ("new", "suspicious", "dismissed", "uncertain")
_JOB_FIELDS = ", ".join("j." + field.strip() for field in _JOB_COLUMNS.split(","))


class SQLiteStatusRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _validate(providers: tuple[str, ...], domain: str | None, limit: int) -> str | None:
        if (
            not isinstance(providers, tuple) or not 1 <= len(providers) <= 20
            or any(not isinstance(item, str) or not item or len(item) > 64
                   or not item.isprintable() or item.isspace() for item in providers)
            or len(set(providers)) != len(providers)
        ):
            raise ValidationError("Durum özeti için geçerli, tekil kaynak adları gerekli.")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Durum özeti adres sınırı 1–100 arasında olmalı.")
        return normalize_domain(domain) if domain is not None else None

    @staticmethod
    def _counts(connection: sqlite3.Connection, table: str, states) -> dict[str, int]:
        # Table names are fixed call-site constants, never external input.
        counts = dict.fromkeys(sorted(states), 0)
        for status, count in connection.execute(f"SELECT status, COUNT(*) FROM {table} GROUP BY status"):
            if status not in counts:
                raise StorageError("Durum özetindeki kayıt türü geçersiz; işlem durduruldu.")
            counts[status] = count
        return counts

    @staticmethod
    def _assets(connection: sqlite3.Connection, domain: str | None, limit: int) -> tuple[Asset, ...]:
        rows = connection.execute(
            "SELECT id, value, created_at FROM assets "
            + ("WHERE value = ? " if domain is not None else "")
            + "ORDER BY value LIMIT ?", (domain, limit) if domain is not None else (limit,),
        )
        assets = []
        try:
            for identifier, value, created_at in rows:
                if (not isinstance(identifier, str) or not identifier or len(identifier) > 64
                        or not identifier.isprintable() or normalize_domain(value) != value
                        or not isinstance(created_at, str) or len(created_at) > 4096):
                    raise ValueError("Invalid saved asset")
                assets.append(Asset(identifier, value, created_at))
        except (ValueError, TypeError) as error:
            raise StorageError("Durum özetindeki adres kaydı bozuk; işlem durduruldu.") from error
        if domain is not None and not assets:
            raise ValidationError("Adres kayıtlı değil. Önce 'xti assets list' ile adreslerini kontrol et.")
        return tuple(assets)

    @staticmethod
    def _summary(
        connection: sqlite3.Connection, identifier: str, job: ScanJob, checked_jobs: set[str],
    ) -> StatusAttempt:
        if job.id not in checked_jobs:
            count, last_number = connection.execute(
                "SELECT COUNT(*), MAX(number) FROM scan_attempts WHERE job_id = ?", (job.id,),
            ).fetchone()
            if count != job.attempt_count or last_number != job.attempt_count:
                raise StorageError("Durum özetindeki işin çalışma geçmişi eksik veya tutarsız.")
            last_status = connection.execute(
                "SELECT status FROM scan_attempts WHERE job_id = ? AND number = ?",
                (job.id, last_number),
            ).fetchone()
            if last_status is None or last_status[0] != job.status:
                raise StorageError("Durum özetindeki iş ile son denemenin durumu uyuşmuyor.")
            checked_jobs.add(job.id)
        attempt = SQLiteJobRepository._get_attempt(connection, identifier)
        if (
            attempt.job_id != job.id or attempt.number > job.attempt_count
            or (attempt.number == job.attempt_count and attempt.status != job.status)
            or (attempt.status in {"complete", "partial"} and attempt.result is None)
            or (attempt.result is not None and attempt.result.targets != job.targets)
            or (attempt.status == "complete" and (
                not attempt.queries or any(q.status != "complete" for q in attempt.queries)
            ))
        ):
            raise StorageError("Durum özetindeki iş ve deneme kayıtları uyuşmuyor.")
        error = attempt.error or next((q.error for q in reversed(attempt.queries) if q.error), None)
        return StatusAttempt(
            attempt.id, attempt.job_id, attempt.number, attempt.status,
            attempt.started_at, attempt.finished_at, len(attempt.queries),
            sum(q.status == "failed" for q in attempt.queries),
            sum(q.status == "partial" for q in attempt.queries), error, job.rule_version, job.typos,
        )

    @classmethod
    def _histories(
        cls, connection: sqlite3.Connection, assets: tuple[Asset, ...], providers: tuple[str, ...],
    ) -> tuple[AssetHistory, ...]:
        keys = {(asset.value, provider) for asset in assets for provider in providers}
        if not keys:
            return ()
        queued = dict.fromkeys(keys, 0)
        latest: dict[tuple[str, str], StatusAttempt] = {}
        complete: dict[tuple[str, str], StatusAttempt] = {}
        checked_jobs: set[str] = set()
        placeholders = ",".join("?" for _ in providers)
        for row in connection.execute(
            "SELECT " + _JOB_COLUMNS + " FROM scan_jobs WHERE status = 'queued' "
            f"AND provider IN ({placeholders})", providers,
        ):
            job = SQLiteJobRepository._job(row)
            matching = {(target, job.provider) for target in job.targets} & keys
            if matching and job.attempt_count != 0:
                raise StorageError("Sıradaki işin beklenmeyen çalışma geçmişi var.")
            for key in matching:
                queued[key] += 1

        # rowid is insertion order, including a new retry of a much older job.
        # The result and queries columns are deliberately absent from this scan.
        for row in connection.execute(
            "SELECT a.id, a.status, " + _JOB_FIELDS + " FROM scan_attempts a "
            "JOIN scan_jobs j ON j.id = a.job_id "
            f"WHERE j.provider IN ({placeholders}) ORDER BY a.rowid DESC", providers,
        ):
            identifier, status = row[:2]
            job = SQLiteJobRepository._job(row[2:])
            matching = {(target, job.provider) for target in job.targets} & keys
            needed = [key for key in matching
                      if key not in latest or (status == "complete" and key not in complete)]
            if not needed:
                continue
            summary = cls._summary(connection, identifier, job, checked_jobs)
            for key in needed:
                latest.setdefault(key, summary)
                if summary.status == "complete":
                    complete.setdefault(key, summary)
            if len(latest) == len(keys) and len(complete) == len(keys):
                break

        return tuple(AssetHistory(asset, tuple(
            SourceHistory(provider, latest.get((asset.value, provider)),
                          complete.get((asset.value, provider)), queued[(asset.value, provider)])
            for provider in providers
        )) for asset in assets)

    def snapshot(
        self, providers: tuple[str, ...], domain: str | None, limit: int,
    ) -> StatusSnapshot:
        domain = self._validate(providers, domain, limit)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            try:
                asset_count = connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
                observation_count = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
                finding_counts = self._counts(connection, "findings", _FINDING_STATUSES)
                job_counts = self._counts(connection, "scan_jobs", JOB_STATUSES)
                total, unread = notification_counts(connection)
                assets = self._assets(connection, domain, limit)
                histories = self._histories(connection, assets, providers)
                cooldowns = tuple(SQLiteCooldownRepository._row(row) for row in connection.execute(
                    "SELECT provider, not_before, recorded_at, reason FROM provider_cooldowns ORDER BY provider"
                ))
                return StatusSnapshot(
                    asset_count, observation_count, finding_counts, job_counts,
                    total, unread, histories, cooldowns,
                )
            finally:
                connection.rollback()

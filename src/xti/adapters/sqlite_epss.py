"""Atomic current EPSS catalog with bounded source-run history."""

from datetime import date, datetime
import hashlib
import re
from pathlib import Path
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.vulnerability import (
    EpssCatalogSnapshot,
    EpssCatalogStatus,
    EpssScore,
    EpssScoreDetails,
    FIRST_EPSS_SOURCE,
    FIRST_EPSS_URL,
    StoredEpssScore,
    VulnerabilitySourceRun,
    normalize_cve_id,
    normalize_probability,
)


_MODEL_VERSION = re.compile(r"v[0-9]{4}\.[0-9]{2}\.[0-9]{2}", re.ASCII)


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64 or not value.isprintable():
        raise ValueError("Invalid identifier")
    return value


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("Invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timezone required")
    return value


def _digest(value: object) -> str:
    if (
        not isinstance(value, str) or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("Invalid digest")
    return value


def _text(value: object, maximum: int) -> str:
    if (
        not isinstance(value, str) or not value or value != value.strip()
        or len(value) > maximum or any(not character.isprintable() for character in value)
    ):
        raise ValueError("Invalid text")
    return value


def _score_state(score: EpssScore) -> tuple[EpssScore, str]:
    if not isinstance(score, EpssScore):
        raise ValidationError("EPSS kaynağı beklenen kayıt türünü vermedi.")
    try:
        cve_id = normalize_cve_id(score.cve_id)
        epss = normalize_probability(score.epss, field="olasılık")
        percentile = normalize_probability(score.percentile, field="yüzdelik dilim")
        if (cve_id, epss, percentile) != (score.cve_id, score.epss, score.percentile):
            raise ValueError("Non-canonical score")
    except (TypeError, ValueError, ValidationError) as error:
        raise ValidationError("EPSS kaydı geçersiz; katalog değiştirilmedi.") from error
    normalized = EpssScore(cve_id, epss, percentile)
    digest = hashlib.sha256(
        f"{cve_id},{epss},{percentile}".encode("ascii")
    ).hexdigest()
    return normalized, digest


class SQLiteEpssRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _validate_times(started_at: str, finished_at: str) -> tuple[str, str]:
        try:
            started = _timestamp(started_at)
            finished = _timestamp(finished_at)
            if datetime.fromisoformat(finished) < datetime.fromisoformat(started):
                raise ValueError("Reversed time")
            return started, finished
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("EPSS çalışma zamanları geçersiz.") from error

    @staticmethod
    def _snapshot(snapshot: EpssCatalogSnapshot):
        if not isinstance(snapshot, EpssCatalogSnapshot):
            raise ValidationError("EPSS kaynağı beklenen katalog sonucunu vermedi.")
        try:
            if snapshot.source != FIRST_EPSS_SOURCE or snapshot.source_url != FIRST_EPSS_URL:
                raise ValueError("Wrong source")
            if _MODEL_VERSION.fullmatch(snapshot.model_version) is None:
                raise ValueError("Invalid model")
            date.fromisoformat(snapshot.score_date)
            digest = _digest(snapshot.content_sha256)
            if (
                not isinstance(snapshot.entries, tuple) or not snapshot.entries
                or len(snapshot.entries) > 1_000_000
            ):
                raise ValueError("Invalid entries")
            encoded = [_score_state(entry) for entry in snapshot.entries]
            ids = [item[0].cve_id for item in encoded]
            if ids != sorted(ids) or len(ids) != len(set(ids)):
                raise ValueError("Entries not unique and sorted")
            return snapshot.model_version, snapshot.score_date, digest, encoded
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            if isinstance(error, ValidationError):
                raise
            raise ValidationError("EPSS katalog özeti geçersiz; kayıt değiştirilmedi.") from error

    @staticmethod
    def _select_run(connection, run_id: str):
        return connection.execute(
            "SELECT sequence, id, source, status, source_url, source_version, "
            "source_timestamp, content_sha256, started_at, finished_at, record_count, "
            "created_count, updated_count, unchanged_count, deactivated_count, "
            "reactivated_count, error FROM vulnerability_source_runs WHERE id = ?",
            (run_id,),
        ).fetchone()

    @staticmethod
    def _run(row) -> VulnerabilitySourceRun:
        try:
            run = VulnerabilitySourceRun(
                id=_identifier(row[1]), sequence=row[0], source=row[2], status=row[3],
                source_url=row[4], source_version=row[5], source_timestamp=row[6],
                content_sha256=row[7], started_at=_timestamp(row[8]),
                finished_at=_timestamp(row[9]), record_count=row[10],
                created_count=row[11], updated_count=row[12], unchanged_count=row[13],
                deactivated_count=row[14], reactivated_count=row[15], error=row[16],
            )
            if (
                type(run.sequence) is not int or run.sequence <= 0
                or run.source != FIRST_EPSS_SOURCE or run.source_url != FIRST_EPSS_URL
                or run.status not in {"complete", "failed"}
                or any(type(value) is not int or value < 0 for value in (
                    run.record_count, run.created_count, run.updated_count,
                    run.unchanged_count, run.deactivated_count, run.reactivated_count,
                ))
            ):
                raise ValueError("Invalid run")
            if run.status == "complete":
                if _MODEL_VERSION.fullmatch(_text(run.source_version, 100)) is None:
                    raise ValueError("Invalid model")
                date.fromisoformat(_text(run.source_timestamp, 10))
                _digest(run.content_sha256)
                if run.error is not None:
                    raise ValueError("Complete run error")
            else:
                if any((run.record_count, run.created_count, run.updated_count,
                        run.unchanged_count, run.deactivated_count, run.reactivated_count)):
                    raise ValueError("Failed run counts")
                _text(run.error, 1000)
                if any(value is not None for value in (
                    run.source_version, run.source_timestamp, run.content_sha256,
                )):
                    raise ValueError("Failed run metadata")
            if datetime.fromisoformat(run.finished_at) < datetime.fromisoformat(run.started_at):
                raise ValueError("Reversed run")
            return run
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("EPSS kaynak çalışma geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _stored(row) -> StoredEpssScore:
        try:
            score = EpssScore(
                normalize_cve_id(row[0]),
                normalize_probability(row[1], field="olasılık"),
                normalize_probability(row[2], field="yüzdelik dilim"),
            )
            if score.cve_id != row[0] or _score_state(score)[1] != _digest(row[3]):
                raise ValueError("State mismatch")
            if row[4] not in (0, 1) or _MODEL_VERSION.fullmatch(row[5]) is None:
                raise ValueError("Invalid metadata")
            date.fromisoformat(row[6])
            return StoredEpssScore(
                score=score, active=bool(row[4]), state_sha256=row[3],
                model_version=row[5], score_date=row[6],
                first_seen_at=_timestamp(row[7]), last_seen_at=_timestamp(row[8]),
                updated_at=_timestamp(row[9]), latest_run_id=_identifier(row[10]),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("EPSS katalog kaydı bozuk; işlem durduruldu.") from error

    def apply(
        self, snapshot: EpssCatalogSnapshot, *, started_at: str, finished_at: str,
    ) -> VulnerabilitySourceRun:
        started_at, finished_at = self._validate_times(started_at, finished_at)
        model, score_date, content_digest, encoded = self._snapshot(snapshot)
        run_id = str(uuid4())
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO vulnerability_source_runs "
                    "(id, source, status, source_url, source_version, source_timestamp, "
                    "content_sha256, started_at, finished_at, record_count, created_count, "
                    "updated_count, unchanged_count, deactivated_count, reactivated_count, error) "
                    "VALUES (?, 'first_epss', 'complete', ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, NULL)",
                    (run_id, FIRST_EPSS_URL, model, score_date, content_digest,
                     started_at, finished_at, len(encoded)),
                )
                existing_rows = connection.execute(
                    "SELECT cve_id, state_sha256, active FROM epss_scores"
                ).fetchall()
                existing = {row[0]: row for row in existing_rows}
                incoming = {item[0].cve_id for item in encoded}
                created = updated = unchanged = reactivated = deactivated = 0
                for score, state_digest in encoded:
                    previous = existing.get(score.cve_id)
                    if previous is None:
                        created += 1
                        connection.execute(
                            "INSERT INTO epss_scores "
                            "(cve_id, epss, percentile, state_sha256, active, model_version, "
                            "score_date, first_seen_at, last_seen_at, updated_at, latest_run_id) "
                            "VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)",
                            (score.cve_id, score.epss, score.percentile, state_digest,
                             model, score_date, finished_at, finished_at, finished_at, run_id),
                        )
                    else:
                        changed = previous[1] != state_digest
                        was_active = previous[2] == 1
                        if changed:
                            updated += 1
                        elif not was_active:
                            reactivated += 1
                        else:
                            unchanged += 1
                        connection.execute(
                            "UPDATE epss_scores SET epss = ?, percentile = ?, state_sha256 = ?, "
                            "active = 1, model_version = ?, score_date = ?, last_seen_at = ?, "
                            "updated_at = CASE WHEN ? THEN ? ELSE updated_at END, "
                            "latest_run_id = ? WHERE cve_id = ?",
                            (score.epss, score.percentile, state_digest, model, score_date,
                             finished_at, int(changed or not was_active), finished_at,
                             run_id, score.cve_id),
                        )
                for cve_id, previous in existing.items():
                    if cve_id in incoming or previous[2] != 1:
                        continue
                    deactivated += 1
                    connection.execute(
                        "UPDATE epss_scores SET active = 0, updated_at = ?, latest_run_id = ? "
                        "WHERE cve_id = ?", (finished_at, run_id, cve_id),
                    )
                connection.execute(
                    "UPDATE vulnerability_source_runs SET created_count = ?, updated_count = ?, "
                    "unchanged_count = ?, deactivated_count = ?, reactivated_count = ? "
                    "WHERE id = ?",
                    (created, updated, unchanged, deactivated, reactivated, run_id),
                )
                result = self._run(self._select_run(connection, run_id))
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def record_failure(
        self, *, started_at: str, finished_at: str, error: str,
    ) -> VulnerabilitySourceRun:
        started_at, finished_at = self._validate_times(started_at, finished_at)
        try:
            error = _text(error, 1000)
        except ValueError as cause:
            raise ValidationError("EPSS kaynak hata açıklaması geçersiz.") from cause
        run_id = str(uuid4())
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO vulnerability_source_runs "
                    "(id, source, status, source_url, source_version, source_timestamp, "
                    "content_sha256, started_at, finished_at, record_count, created_count, "
                    "updated_count, unchanged_count, deactivated_count, reactivated_count, error) "
                    "VALUES (?, 'first_epss', 'failed', ?, NULL, NULL, NULL, ?, ?, "
                    "0, 0, 0, 0, 0, 0, ?)",
                    (run_id, FIRST_EPSS_URL, started_at, finished_at, error),
                )
                result = self._run(self._select_run(connection, run_id))
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def list(self, *, active_only: bool, limit: int) -> tuple[StoredEpssScore, ...]:
        if type(active_only) is not bool or type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("EPSS liste isteği geçersiz.")
        where = "WHERE active = 1" if active_only else ""
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT cve_id, epss, percentile, state_sha256, active, model_version, "
                "score_date, first_seen_at, last_seen_at, updated_at, latest_run_id "
                f"FROM epss_scores {where} ORDER BY epss DESC, cve_id LIMIT ?", (limit,),
            ).fetchall()
        return tuple(self._stored(row) for row in rows)

    def details(self, cve_id: str) -> EpssScoreDetails:
        cve_id = normalize_cve_id(cve_id)
        with self._storage._connection(readonly=True) as connection:
            row = connection.execute(
                "SELECT cve_id, epss, percentile, state_sha256, active, model_version, "
                "score_date, first_seen_at, last_seen_at, updated_at, latest_run_id "
                "FROM epss_scores WHERE cve_id = ?", (cve_id,),
            ).fetchone()
        if row is None:
            raise ValidationError("CVE, yerel EPSS kataloğunda bulunamadı.")
        return EpssScoreDetails(self._stored(row))

    def status(self, *, run_limit: int) -> EpssCatalogStatus:
        if type(run_limit) is not int or not 1 <= run_limit <= 100:
            raise ValidationError("EPSS çalışma geçmişi sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            active, inactive = connection.execute(
                "SELECT SUM(active = 1), SUM(active = 0) FROM epss_scores"
            ).fetchone()
            rows = connection.execute(
                "SELECT sequence, id, source, status, source_url, source_version, "
                "source_timestamp, content_sha256, started_at, finished_at, record_count, "
                "created_count, updated_count, unchanged_count, deactivated_count, "
                "reactivated_count, error FROM vulnerability_source_runs "
                "WHERE source = 'first_epss' ORDER BY sequence DESC LIMIT ?", (run_limit,),
            ).fetchall()
            connection.rollback()
        runs = tuple(self._run(row) for row in rows)
        return EpssCatalogStatus(
            active_count=active or 0,
            inactive_count=inactive or 0,
            latest_run=runs[0] if runs else None,
            recent_runs=runs,
            notes=(
                "EPSS, önümüzdeki 30 günde gözlenebilecek istismar için nüfus düzeyi tahminidir.",
                "EPSS bir önem, etki, tam risk veya bu bilgisayarda maruziyet kanıtı değildir.",
                "Günlük puan geçmişi yerelde çoğaltılmaz; yalnız güncel tam katalog tutulur.",
                "Başarısız güncelleme önceki geçerli kataloğu silmez veya boş saymaz.",
            ),
        )

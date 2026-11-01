"""Atomic local NVD CVE records and append-only change evidence."""

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.vulnerability import (
    CvssMetric,
    NVD_CVE_SOURCE,
    NVD_CVE_URL,
    NvdCatalogStatus,
    NvdCve,
    NvdCveDetails,
    NvdCveEvent,
    NvdCveSnapshot,
    StoredNvdCve,
    VulnerabilitySourceRun,
    normalize_nvd_window,
    normalize_cve_id,
    nvd_cve_url,
    nvd_window_url,
    validate_nvd_window_page,
)


MAX_STATE_JSON = 128 * 1024
MAX_RECORD_JSON = 4 * 1024 * 1024
_SEVERITIES = {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL"}


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite JSON number")


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


def _text(value: object, maximum: int, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if (
        not isinstance(value, str) or not value or value != value.strip()
        or len(value) > maximum or any(not character.isprintable() for character in value)
    ):
        raise ValueError("Invalid text")
    return value


def _score(value: object, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    text = _text(value, 20)
    number = float(text)
    if not 0 <= number <= 10:
        raise ValueError("Invalid score")
    return text


def _metric(metric: CvssMetric) -> CvssMetric:
    if not isinstance(metric, CvssMetric):
        raise ValueError("Invalid metric")
    severity = _text(metric.base_severity, 20, optional=True)
    if severity is not None and severity not in _SEVERITIES:
        raise ValueError("Invalid severity")
    return CvssMetric(
        source=_text(metric.source, 500),
        metric_type=_text(metric.metric_type, 50),
        version=_text(metric.version, 10),
        vector=_text(metric.vector, 1000),
        base_score=_score(metric.base_score),
        base_severity=severity,
        exploitability_score=_score(metric.exploitability_score, optional=True),
        impact_score=_score(metric.impact_score, optional=True),
    )


def _record(record: NvdCve) -> NvdCve:
    if not isinstance(record, NvdCve):
        raise ValidationError("NVD kaynağı beklenen CVE türünü vermedi.")
    try:
        cve_id = normalize_cve_id(record.cve_id)
        if cve_id != record.cve_id:
            raise ValueError("Non-canonical CVE")
        published = _timestamp(record.published_at)
        modified = _timestamp(record.last_modified_at)
        if datetime.fromisoformat(modified) < datetime.fromisoformat(published):
            raise ValueError("Reversed CVE time")
        metrics = tuple(_metric(value) for value in record.cvss_metrics)
        if not isinstance(record.cvss_metrics, tuple) or len(metrics) > 400:
            raise ValueError("Invalid metrics")
        if (
            not isinstance(record.cwes, tuple) or len(record.cwes) > 100
            or tuple(sorted(set(record.cwes))) != record.cwes
        ):
            raise ValueError("Invalid CWEs")
        cwes = tuple(_text(value, 100) for value in record.cwes)
        if type(record.reference_count) is not int or not 0 <= record.reference_count <= 5000:
            raise ValueError("Invalid reference count")
        return NvdCve(
            cve_id=cve_id,
            source_identifier=_text(record.source_identifier, 500),
            published_at=published,
            last_modified_at=modified,
            vuln_status=_text(record.vuln_status, 100),
            english_description=_text(
                record.english_description, 20_000, optional=True,
            ),
            cvss_metrics=metrics,
            cwes=cwes,
            reference_count=record.reference_count,
        )
    except (TypeError, ValueError, ValidationError, OverflowError) as error:
        raise ValidationError("NVD CVE kaydı geçersiz; yerel kayıt değiştirilmedi.") from error


def encode_nvd_record(record: NvdCve) -> tuple[NvdCve, str]:
    validated = _record(record)
    encoded = json.dumps(
        asdict(validated), ensure_ascii=True, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
    if len(encoded) > MAX_STATE_JSON:
        raise ValidationError("NVD CVE özeti güvenli kayıt sınırını aştı.")
    return validated, encoded


def decode_nvd_record(value: object) -> NvdCve:
    if not isinstance(value, str) or len(value) > MAX_STATE_JSON:
        raise ValueError("Invalid NVD state")
    data = json.loads(value, object_pairs_hook=_object, parse_constant=_constant)
    fields = {
        "cve_id", "source_identifier", "published_at", "last_modified_at",
        "vuln_status", "english_description", "cvss_metrics", "cwes",
        "reference_count",
    }
    if not isinstance(data, dict) or set(data) != fields:
        raise ValueError("Invalid NVD state fields")
    if not isinstance(data["cvss_metrics"], list) or not isinstance(data["cwes"], list):
        raise ValueError("Invalid NVD state collections")
    data["cvss_metrics"] = tuple(CvssMetric(**metric) for metric in data["cvss_metrics"])
    data["cwes"] = tuple(data["cwes"])
    return _record(NvdCve(**data))


def _source_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 500:
        raise ValueError("Invalid source URL")
    parsed = urlsplit(value)
    if f"{parsed.scheme}://{parsed.netloc}{parsed.path}" != NVD_CVE_URL:
        raise ValueError("Wrong NVD URL")
    values = parse_qs(parsed.query, strict_parsing=True)
    if set(values) == {"cveId"} and len(values["cveId"]) == 1:
        canonical = nvd_cve_url(normalize_cve_id(values["cveId"][0]))
    elif set(values) == {
        "lastModStartDate", "lastModEndDate", "resultsPerPage", "startIndex",
    } and all(len(items) == 1 for items in values.values()):
        start, end = normalize_nvd_window(
            values["lastModStartDate"][0], values["lastModEndDate"][0],
        )
        try:
            page_size = int(values["resultsPerPage"][0])
            start_index = int(values["startIndex"][0])
        except ValueError as error:
            raise ValueError("Wrong NVD window query") from error
        validate_nvd_window_page(page_size, start_index)
        canonical = nvd_window_url(start, end, page_size, start_index)
    else:
        raise ValueError("Wrong NVD query")
    if value != canonical:
        raise ValueError("Non-canonical NVD URL")
    return value


def _is_single_cve_url(value: str) -> bool:
    return set(parse_qs(urlsplit(value).query, strict_parsing=True)) == {"cveId"}


def prepare_nvd_storage_record(record: NvdCve, record_json: str):
    """Validate one parsed NVD record and produce its canonical storage fields."""
    validated, state = encode_nvd_record(record)
    if not isinstance(record_json, str) or len(record_json) > MAX_RECORD_JSON:
        raise ValidationError("NVD CVE ham kaydı güvenli kayıt sınırını aştı.")
    try:
        raw = json.loads(record_json, object_pairs_hook=_object, parse_constant=_constant)
        canonical = json.dumps(
            raw, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as error:
        raise ValidationError("NVD CVE ham kaydı geçersiz; kayıt değiştirilmedi.") from error
    if canonical != record_json or not isinstance(raw, dict) or raw.get("id") != validated.cve_id:
        raise ValidationError("NVD CVE ham kaydı özetle uyuşmuyor; kayıt değiştirilmedi.")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return validated, state, canonical, digest


class SQLiteNvdRepository:
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
            raise ValidationError("NVD çalışma zamanları geçersiz.") from error

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
                source_url=_source_url(row[4]), source_version=row[5],
                source_timestamp=row[6], content_sha256=row[7],
                started_at=_timestamp(row[8]), finished_at=_timestamp(row[9]),
                record_count=row[10], created_count=row[11], updated_count=row[12],
                unchanged_count=row[13], deactivated_count=row[14],
                reactivated_count=row[15], error=row[16],
            )
            if (
                type(run.sequence) is not int or run.sequence <= 0
                or run.source != NVD_CVE_SOURCE or run.status not in {"complete", "failed"}
                or any(type(value) is not int or value < 0 for value in (
                    run.record_count, run.created_count, run.updated_count,
                    run.unchanged_count, run.deactivated_count, run.reactivated_count,
                ))
                or run.deactivated_count or run.reactivated_count
            ):
                raise ValueError("Invalid run")
            if run.status == "complete":
                if (
                    run.source_version != "2.0"
                    or (_is_single_cve_url(run.source_url) and run.record_count != 1)
                    or (not _is_single_cve_url(run.source_url) and run.record_count > 100)
                ):
                    raise ValueError("Invalid complete run")
                _timestamp(run.source_timestamp)
                _digest(run.content_sha256)
                if run.error is not None or sum((
                    run.created_count, run.updated_count, run.unchanged_count,
                )) != run.record_count:
                    raise ValueError("Invalid complete counts")
            else:
                if any((run.record_count, run.created_count, run.updated_count,
                        run.unchanged_count, run.deactivated_count,
                        run.reactivated_count)):
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
            raise StorageError("NVD kaynak çalışma geçmişi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _stored(row) -> StoredNvdCve:
        try:
            record = decode_nvd_record(row[1])
            record_json = row[2]
            if not isinstance(record_json, str) or len(record_json) > MAX_RECORD_JSON:
                raise ValueError("Invalid raw record")
            raw = json.loads(record_json, object_pairs_hook=_object, parse_constant=_constant)
            if not isinstance(raw, dict) or raw.get("id") != record.cve_id:
                raise ValueError("Raw record mismatch")
            digest = hashlib.sha256(record_json.encode("utf-8")).hexdigest()
            if record.cve_id != row[0] or digest != _digest(row[3]):
                raise ValueError("State mismatch")
            return StoredNvdCve(
                record=record, state_sha256=row[3], first_seen_at=_timestamp(row[4]),
                last_seen_at=_timestamp(row[5]), updated_at=_timestamp(row[6]),
                latest_run_id=_identifier(row[7]),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("NVD CVE kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _snapshot(snapshot: NvdCveSnapshot):
        if not isinstance(snapshot, NvdCveSnapshot):
            raise ValidationError("NVD kaynağı beklenen CVE sonucunu vermedi.")
        try:
            record, state, canonical, state_digest = prepare_nvd_storage_record(
                snapshot.record, snapshot.record_json,
            )
            if snapshot.source != NVD_CVE_SOURCE:
                raise ValueError("Wrong source")
            if _source_url(snapshot.source_url) != nvd_cve_url(record.cve_id):
                raise ValueError("Wrong source URL")
            if snapshot.api_version != "2.0":
                raise ValueError("Wrong API version")
            response_timestamp = _timestamp(snapshot.response_timestamp)
            content_digest = _digest(snapshot.content_sha256)
            return (
                record, state, canonical, state_digest, response_timestamp, content_digest,
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            if isinstance(error, ValidationError):
                raise
            raise ValidationError("NVD CVE özeti geçersiz; kayıt değiştirilmedi.") from error

    def apply(
        self, snapshot: NvdCveSnapshot, *, started_at: str, finished_at: str,
    ) -> VulnerabilitySourceRun:
        started_at, finished_at = self._validate_times(started_at, finished_at)
        record, state, raw, digest, response_at, content_digest = self._snapshot(snapshot)
        run_id = str(uuid4())
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                previous = connection.execute(
                    "SELECT state_sha256 FROM nvd_cve_records WHERE cve_id = ?",
                    (record.cve_id,),
                ).fetchone()
                created = int(previous is None)
                updated = int(previous is not None and previous[0] != digest)
                unchanged = int(previous is not None and previous[0] == digest)
                connection.execute(
                    "INSERT INTO vulnerability_source_runs "
                    "(id, source, status, source_url, source_version, source_timestamp, "
                    "content_sha256, started_at, finished_at, record_count, created_count, "
                    "updated_count, unchanged_count, deactivated_count, reactivated_count, error) "
                    "VALUES (?, 'nvd_cve', 'complete', ?, '2.0', ?, ?, ?, ?, 1, ?, ?, ?, 0, 0, NULL)",
                    (run_id, snapshot.source_url, response_at, content_digest, started_at,
                     finished_at, created, updated, unchanged),
                )
                if previous is None:
                    connection.execute(
                        "INSERT INTO nvd_cve_records "
                        "(cve_id, state, record_json, state_sha256, first_seen_at, "
                        "last_seen_at, updated_at, latest_run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (record.cve_id, state, raw, digest, finished_at, finished_at,
                         finished_at, run_id),
                    )
                else:
                    connection.execute(
                        "UPDATE nvd_cve_records SET state = ?, record_json = ?, "
                        "state_sha256 = ?, last_seen_at = ?, "
                        "updated_at = CASE WHEN ? THEN ? ELSE updated_at END, "
                        "latest_run_id = ? WHERE cve_id = ?",
                        (state, raw, digest, finished_at, updated, finished_at, run_id,
                         record.cve_id),
                    )
                if created or updated:
                    connection.execute(
                        "INSERT INTO nvd_cve_events "
                        "(id, cve_id, run_id, action, state, record_json, state_sha256, "
                        "recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (str(uuid4()), record.cve_id, run_id,
                         "added" if created else "updated", state, raw, digest, finished_at),
                    )
                result = self._run(self._select_run(connection, run_id))
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def record_failure(
        self, cve_id: str, *, started_at: str, finished_at: str, error: str,
    ) -> VulnerabilitySourceRun:
        cve_id = normalize_cve_id(cve_id)
        started_at, finished_at = self._validate_times(started_at, finished_at)
        try:
            error = _text(error, 1000)
        except ValueError as cause:
            raise ValidationError("NVD kaynak hata açıklaması geçersiz.") from cause
        run_id = str(uuid4())
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO vulnerability_source_runs "
                    "(id, source, status, source_url, source_version, source_timestamp, "
                    "content_sha256, started_at, finished_at, record_count, created_count, "
                    "updated_count, unchanged_count, deactivated_count, reactivated_count, error) "
                    "VALUES (?, 'nvd_cve', 'failed', ?, NULL, NULL, NULL, ?, ?, "
                    "0, 0, 0, 0, 0, 0, ?)",
                    (run_id, nvd_cve_url(cve_id), started_at, finished_at, error),
                )
                result = self._run(self._select_run(connection, run_id))
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise

    def list(self, *, limit: int) -> tuple[StoredNvdCve, ...]:
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("NVD liste isteği geçersiz.")
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT cve_id, state, record_json, state_sha256, first_seen_at, "
                "last_seen_at, updated_at, latest_run_id FROM nvd_cve_records "
                "ORDER BY cve_id DESC LIMIT ?", (limit,),
            ).fetchall()
        return tuple(self._stored(row) for row in rows)

    def details(self, cve_id: str, *, event_limit: int) -> NvdCveDetails:
        cve_id = normalize_cve_id(cve_id)
        if type(event_limit) is not int or not 1 <= event_limit <= 100:
            raise ValidationError("NVD değişiklik geçmişi sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT cve_id, state, record_json, state_sha256, first_seen_at, "
                "last_seen_at, updated_at, latest_run_id FROM nvd_cve_records "
                "WHERE cve_id = ?", (cve_id,),
            ).fetchone()
            if row is None:
                raise ValidationError(
                    "CVE, yerel NVD kaydında bulunamadı. Önce NVD eşitlemesi yapın."
                )
            total = connection.execute(
                "SELECT COUNT(*) FROM nvd_cve_events WHERE cve_id = ?", (cve_id,),
            ).fetchone()[0]
            event_rows = connection.execute(
                "SELECT id, cve_id, run_id, action, state, record_json, state_sha256, "
                "recorded_at FROM nvd_cve_events WHERE cve_id = ? "
                "ORDER BY rowid DESC LIMIT ?", (cve_id, event_limit),
            ).fetchall()
            connection.rollback()
        record = self._stored(row)
        events = []
        for item in event_rows:
            try:
                decoded = decode_nvd_record(item[4])
                raw = json.loads(item[5], object_pairs_hook=_object, parse_constant=_constant)
                digest = hashlib.sha256(item[5].encode("utf-8")).hexdigest()
                if (
                    decoded.cve_id != cve_id or raw.get("id") != cve_id
                    or digest != _digest(item[6]) or item[3] not in {"added", "updated"}
                ):
                    raise ValueError("Event mismatch")
                events.append(NvdCveEvent(
                    _identifier(item[0]), cve_id, _identifier(item[2]), item[3],
                    item[6], _timestamp(item[7]),
                ))
            except (TypeError, ValueError, ValidationError, OverflowError) as error:
                raise StorageError("NVD değişiklik geçmişi bozuk; işlem durduruldu.") from error
        return NvdCveDetails(record, tuple(events), total)

    def status(self, *, run_limit: int) -> NvdCatalogStatus:
        if type(run_limit) is not int or not 1 <= run_limit <= 100:
            raise ValidationError("NVD çalışma geçmişi sınırı 1–100 arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            count = connection.execute("SELECT COUNT(*) FROM nvd_cve_records").fetchone()[0]
            rows = connection.execute(
                "SELECT sequence, id, source, status, source_url, source_version, "
                "source_timestamp, content_sha256, started_at, finished_at, record_count, "
                "created_count, updated_count, unchanged_count, deactivated_count, "
                "reactivated_count, error FROM vulnerability_source_runs "
                "WHERE source = 'nvd_cve' ORDER BY sequence DESC LIMIT ?", (run_limit,),
            ).fetchall()
            connection.rollback()
        runs = tuple(self._run(row) for row in rows)
        return NvdCatalogStatus(
            record_count=count,
            latest_run=runs[0] if runs else None,
            recent_runs=runs,
            notes=(
                "Bu dilim açıkça istenen tek CVE veya küçük tarih pencerelerini yerelde tutar; tam NVD aynası değildir.",
                "CVSS önem ve teknik etki bağlamıdır; EPSS, KEV ve varlık maruziyetiyle aynı değildir.",
                "Bir NVD/CPE kaydı, kayıtlı varlıkta ürün veya zafiyet bulunduğunu kanıtlamaz.",
                "Başarısız sorgu önceki geçerli CVE kaydını değiştirmez.",
            ),
        )

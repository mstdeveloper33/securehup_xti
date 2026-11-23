"""SQLite lifecycle for normalized sensor and completed sandbox telemetry."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import sqlite3
from uuid import uuid4

from xti.adapters.retention_payloads import archived_value
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.cases import CaseEvidenceSnapshot, canonical_snapshot
from xti.domain.telemetry import (
    CASE_LIMITATIONS, DECISIONS, INPUT_FORMATS, POLICY, PREFIX, RECORD_KINDS,
    TelemetryPreview, TelemetryRecord, TelemetryError, canonical, digest,
    normalize_import_request, normalize_record, parameters, preview_from_records,
    source_definition, validate_case_payload,
    validate_record_for_source,
)
from xti.domain.mentions import mention_uuid


def _sha(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("invalid sha")
    return value


def _loads(value: str):
    if not isinstance(value, str):
        raise ValueError("invalid json")
    return json.loads(value)


def _time(value: object) -> str:
    from xti.domain.cti_indicators import normalize_cti_timestamp
    return normalize_cti_timestamp(value, field="Telemetri kayıt zamanı")


def _uuid(value: object) -> str:
    normalized = mention_uuid(value)
    if normalized != value:
        raise ValueError("non-canonical uuid")
    return normalized


def _sequence(value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("invalid sequence")
    return value


def _name_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _page(rows: list[dict], limit: int) -> dict:
    selected = rows[:limit]
    return {
        "items": selected,
        "next_after": selected[-1]["sequence"] if len(rows) > limit and selected else None,
        "has_more": len(rows) > limit,
    }


def _source_payload(row) -> dict:
    value = {
        "sequence": row[0], "id": row[1], "organization_id": row[2],
        "name": row[4], "source_kind": row[5], "input_format": row[6],
        "description": row[7], "revision": row[8], "enabled": bool(row[9]),
        "created_at": row[10], "updated_at": row[11],
    }
    expected = source_definition({
        "name": value["name"], "organization_id": value["organization_id"],
        "source_kind": value["source_kind"], "input_format": value["input_format"],
        "description": value["description"],
    })
    if (_sequence(row[0]) != row[0] or _uuid(row[1]) != row[1]
            or _uuid(row[2]) != row[2] or row[3] != _name_key(expected["name"])
            or type(row[8]) is not int or row[8] < 1
            or type(row[9]) is not int or row[9] not in {0, 1}
            or _time(row[10]) != row[10] or _time(row[11]) != row[11]
            or row[10] > row[11]):
        raise StorageError("Telemetri kaynak kaydı bozuk; işlem durduruldu.")
    return value


def _source_row(connection, identifier: str):
    row = connection.execute(
        "SELECT sequence,id,organization_id,name_key,display_name,source_kind,input_format,"
        "description,revision,enabled,created_at,updated_at FROM telemetry_sources WHERE id=?",
        (identifier,),
    ).fetchone()
    if row is None:
        raise TelemetryError("not_found", "Telemetri kaynağı bulunamadı.")
    value = _source_payload(row)
    return row, value


def _run_payload(row) -> dict:
    ignored = _loads(row[19])
    if not isinstance(ignored, list):
        raise ValueError("invalid ignored reasons")
    reason_total = 0
    for item in ignored:
        if (not isinstance(item, dict) or set(item) != {"reason", "count"}
                or not isinstance(item["reason"], str)
                or not 1 <= len(item["reason"]) <= 240
                or type(item["count"]) is not int or item["count"] < 1):
            raise ValueError("invalid ignored reason")
        reason_total += item["count"]
    value = {
        "sequence": row[0], "id": row[1], "source_id": row[2],
        "source_revision": row[3], "request_key": row[4],
        "request_sha256": _sha(row[5]), "input_format": row[6],
        "content_sha256": _sha(row[7]), "preview_sha256": _sha(row[8]),
        "status": row[9], "input_count": row[10], "record_count": row[11],
        "ignored_count": row[12], "duplicate_count": row[13],
        "added_count": row[14], "updated_count": row[15],
        "unchanged_count": row[16], "ignored_reasons": ignored,
        "error_code": row[17], "error": row[18],
        "started_at": row[20], "finished_at": row[21],
    }
    normalized_source, normalized_revision, normalized_key = normalize_import_request(
        row[2], row[3], row[4],
    )
    counts = row[10:17]
    if (_sequence(row[0]) != row[0] or _uuid(row[1]) != row[1]
            or normalized_source != row[2] or normalized_revision != row[3]
            or normalized_key != row[4] or row[6] not in INPUT_FORMATS
            or row[9] not in {"running", "complete", "interrupted"}
            or any(type(item) is not int or item < 0 for item in counts)
            or row[10] != row[11] + row[12] + row[13]
            or reason_total != row[12]
            or _time(row[20]) != row[20]
            or (row[21] is not None and (_time(row[21]) != row[21] or row[21] < row[20]))):
        raise ValueError("invalid telemetry run")
    result_total = row[14] + row[15] + row[16]
    if row[9] == "running" and (
            result_total != 0 or row[17] is not None or row[18] is not None or row[21] is not None):
        raise ValueError("invalid running telemetry run")
    if row[9] == "complete" and (
            result_total != row[11] or row[17] is not None or row[18] is not None
            or row[21] is None):
        raise ValueError("invalid completed telemetry run")
    if row[9] == "interrupted" and (
            result_total != 0 or not isinstance(row[17], str) or not row[17]
            or not isinstance(row[18], str) or not row[18] or row[21] is None):
        raise ValueError("invalid interrupted telemetry run")
    return value


def _run_row(connection, identifier: str):
    row = connection.execute(
        "SELECT sequence,id,source_id,source_revision,request_key,request_sha256,input_format,"
        "content_sha256,preview_sha256,status,input_count,record_count,ignored_count,"
        "duplicate_count,added_count,updated_count,unchanged_count,error_code,error,ignored_json,"
        "started_at,finished_at FROM telemetry_runs WHERE id=?",
        (identifier,),
    ).fetchone()
    if row is None:
        raise TelemetryError("not_found", "Telemetri içe alma çalışması bulunamadı.")
    value = _run_payload(row)
    _source_record, source = _source_row(connection, value["source_id"])
    if (value["source_revision"] > source["revision"]
            or value["input_format"] != source["input_format"]):
        raise StorageError("Telemetri çalışma-kaynak bağı bozuk; işlem durduruldu.")
    item_count = connection.execute(
        "SELECT COUNT(*) FROM telemetry_run_items WHERE run_id=?", (value["id"],),
    ).fetchone()[0]
    if ((value["status"] == "complete" and item_count != value["record_count"])
            or (value["status"] != "complete" and item_count != 0)):
        raise StorageError("Telemetri çalışma kalemleri sayaçla uyuşmuyor.")
    return row, value


def _review_rows(connection, record_id: str) -> list[dict]:
    rows = connection.execute(
        "SELECT sequence,id,record_id,record_revision,revision,decision,reason,actor,recorded_at "
        "FROM telemetry_reviews WHERE record_id=? ORDER BY sequence", (record_id,),
    ).fetchall()
    result = []
    for row in rows:
        normalized = parameters(PREFIX + "review", {
            "identifier": row[2], "expected_revision": row[3],
            "decision": row[5], "reason": row[6], "actor": row[7],
            "idempotency_key": "integrity-review",
        })
        if (_sequence(row[0]) != row[0] or _uuid(row[1]) != row[1]
                or normalized["identifier"] != record_id
                or type(row[4]) is not int or row[4] < 1
                or row[5] not in DECISIONS or _time(row[8]) != row[8]):
            raise ValueError("invalid review time")
        result.append({
            "sequence": row[0], "id": row[1], "record_id": row[2],
            "record_revision": row[3], "revision": row[4], "decision": row[5],
            "reason": row[6], "actor": row[7], "recorded_at": row[8],
        })
    return result


def read_record_in(connection, identifier: str) -> dict:
    row = connection.execute(
        "SELECT r.sequence,r.id,r.organization_id,r.source_id,r.native_key,r.record_kind,"
        "r.event_at,r.summary,r.body_json,r.body_sha256,r.revision,r.review_revision,"
        "r.first_run_id,r.last_run_id,r.first_seen_at,r.last_seen_at,"
        "s.display_name,s.source_kind,s.input_format,s.revision,s.enabled "
        "FROM telemetry_records r JOIN telemetry_sources s ON s.id=r.source_id WHERE r.id=?",
        (identifier,),
    ).fetchone()
    if row is None:
        raise TelemetryError("not_found", "Telemetri kaydı bulunamadı.")
    body_json = archived_value(
        connection, run_id=row[1], family="telemetry_records", field="snapshot",
        value=row[8], checksum=row[9],
    )
    body = _loads(body_json)
    normalized = normalize_record(body)
    _source_record, source = _source_row(connection, row[3])
    validate_record_for_source(normalized, source["source_kind"])
    if (_sequence(row[0]) != row[0] or _uuid(row[1]) != row[1]
            or _uuid(row[2]) != row[2] or _uuid(row[3]) != row[3]
            or canonical(asdict(normalized)) != body_json or digest(asdict(normalized)) != row[9]
            or normalized.native_id != row[4] or normalized.kind != row[5]
            or normalized.event_at != row[6] or normalized.summary != row[7]
            or type(row[10]) is not int or row[10] < 1
            or type(row[11]) is not int or row[11] < 0
            or _uuid(row[12]) != row[12] or _uuid(row[13]) != row[13]
            or _time(row[14]) != row[14] or _time(row[15]) != row[15]
            or row[14] > row[15] or row[2] != source["organization_id"]
            or row[16] != source["name"] or row[17] != source["source_kind"]
            or row[18] != source["input_format"] or row[19] != source["revision"]
            or type(row[20]) is not int or bool(row[20]) != source["enabled"]):
        raise StorageError("Telemetri kanıt kaydı bozuk; işlem durduruldu.")
    run_rows = connection.execute(
        "SELECT id,source_id,status FROM telemetry_runs WHERE id IN (?,?)",
        (row[12], row[13]),
    ).fetchall()
    run_map = {item[0]: item for item in run_rows}
    if (set(run_map) != {row[12], row[13]}
            or any(item[1] != row[3] or item[2] != "complete" for item in run_map.values())):
        raise StorageError("Telemetri kayıt-çalışma bağı bozuk; işlem durduruldu.")
    version_summary = connection.execute(
        "SELECT COUNT(*),MIN(revision),MAX(revision),"
        "SUM(CASE WHEN action='added' THEN 1 ELSE 0 END) "
        "FROM telemetry_record_versions WHERE record_id=?", (row[1],),
    ).fetchone()
    if (version_summary[0] != row[10] or version_summary[1] != 1
            or version_summary[2] != row[10] or version_summary[3] != 1):
        raise StorageError("Telemetri sürüm zinciri bozuk; işlem durduruldu.")
    reviews = _review_rows(connection, identifier)
    if len(reviews) != row[11] or any(item["revision"] != index for index, item in enumerate(reviews, 1)):
        raise StorageError("Telemetri inceleme zinciri bozuk; işlem durduruldu.")
    current_review = reviews[-1] if reviews else None
    return {
        "sequence": row[0], "id": row[1], "organization_id": row[2],
        "source_id": row[3], "native_id": row[4], "kind": row[5],
        "event_at": row[6], "summary": row[7], "body": body,
        "body_sha256": row[9], "revision": row[10],
        "review_revision": row[11], "review": current_review,
        "needs_review": current_review is None or current_review["record_revision"] != row[10],
        "first_run_id": row[12], "last_run_id": row[13],
        "first_seen_at": row[14], "last_seen_at": row[15],
        "source": {
            "id": source["id"], "name": source["name"],
            "source_kind": source["source_kind"],
            "input_format": source["input_format"],
            "revision": source["revision"], "enabled": source["enabled"],
        },
    }


def case_snapshot(connection, identifier: str) -> CaseEvidenceSnapshot:
    record = read_record_in(connection, identifier)
    payload = {
        "kind": "telemetry_record", "policy": POLICY,
        "source": record["source"],
        "record": {key: record[key] for key in (
            "id", "organization_id", "source_id", "native_id", "kind", "event_at",
            "summary", "body", "body_sha256", "revision", "first_run_id",
            "last_run_id", "first_seen_at", "last_seen_at",
        )},
        "review": record["review"],
        "limitations": list(CASE_LIMITATIONS),
    }
    validate_case_payload(payload)
    encoded, sha256 = canonical_snapshot(payload)
    return CaseEvidenceSnapshot(
        "telemetry", identifier, record["summary"],
        "telemetry record-show " + identifier, encoded, sha256,
    )


def validate_case_snapshot(value):
    return validate_case_payload(value)


class SQLiteTelemetryRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.storage = SQLiteAssetRepository(path)

    @staticmethod
    def capabilities() -> dict:
        return {
            "policy": POLICY,
            "source_kinds": ["honeypot", "sinkhole", "sandbox"],
            "input_formats": list(INPUT_FORMATS),
            "record_kinds": list(RECORD_KINDS),
            "limits": {"file_bytes": 32 * 1024 * 1024, "file_records": 50_000,
                       "platform_records": 1_000, "record_bytes": 64 * 1024},
            "stored": ["normalized observation", "source provenance", "hash", "review history"],
            "retention": {
                "family": "telemetry_records", "lossless_archive": True,
                "transparent_read": True, "explicit_hold": True,
                "active_case_auto_protected": True,
            },
            "never_stored": [
                "passwords", "usernames", "raw commands", "sample binaries",
                "packet captures", "memory dumps", "raw sandbox reports",
            ],
            "execution": "XTI does not execute malware; CAPE runs in separately isolated infrastructure.",
        }

    @staticmethod
    def _request(operation: str, values: dict) -> str:
        return digest({"operation": operation, "values": {
            key: value for key, value in values.items() if key != "idempotency_key"
        }})

    @staticmethod
    def _mutation_replay(connection, key: str, request_sha: str):
        row = connection.execute(
            "SELECT request_sha256,result_json,result_sha256 FROM telemetry_mutations WHERE request_key=?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        if row[0] != request_sha or hashlib.sha256(row[1].encode("ascii")).hexdigest() != row[2]:
            raise TelemetryError("idempotency_conflict", "Telemetri tekrar anahtarı başka bir isteğe bağlı.")
        result = _loads(row[1])
        result["replayed"] = True
        return result

    @staticmethod
    def _store_mutation(connection, key: str, request_sha: str, result: dict, at: str):
        value = {**result, "replayed": False}
        encoded = canonical(value)
        connection.execute(
            "INSERT INTO telemetry_mutations (id,request_key,request_sha256,result_json,result_sha256,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (str(uuid4()), key, request_sha, encoded,
             hashlib.sha256(encoded.encode("ascii")).hexdigest(), at),
        )
        return value

    def read(self, operation: str, values: dict) -> dict:
        if operation == PREFIX + "capabilities":
            return self.capabilities()
        try:
            with self.storage._connection(readonly=True) as connection:
                connection.execute("BEGIN")
                if operation == PREFIX + "source.get":
                    _row, source = _source_row(connection, values["identifier"])
                    events = self._source_events(connection, source["id"])
                    expected_snapshot = {key: source[key] for key in (
                        "id", "organization_id", "name", "source_kind", "input_format",
                        "description", "revision", "enabled", "created_at", "updated_at",
                    )}
                    if (len(events) != source["revision"] or not events
                            or events[-1]["revision"] != source["revision"]
                            or events[-1]["snapshot"] != expected_snapshot):
                        raise StorageError("Telemetri kaynak olay zinciri güncel kayıtla uyuşmuyor.")
                    source["events"] = events
                    return source
                if operation == PREFIX + "run.get":
                    _row, run = _run_row(connection, values["identifier"])
                    run["items"] = self._run_items(connection, run["id"], 500)
                    return run
                if operation == PREFIX + "record.get":
                    record = read_record_in(connection, values["identifier"])
                    record["versions"] = self._versions(connection, record["id"], 500)
                    record["reviews"] = _review_rows(connection, record["id"])
                    return record
                if operation == PREFIX + "sources":
                    return self._sources(connection, values)
                if operation == PREFIX + "runs":
                    return self._runs(connection, values)
                if operation == PREFIX + "records":
                    return self._records(connection, values)
                if operation == PREFIX + "reviews":
                    record = read_record_in(connection, values["identifier"])
                    rows = [item for item in _review_rows(connection, record["id"])
                            if item["sequence"] > values["after"]]
                    return {**_page(rows, values["limit"]), "record_id": record["id"]}
                if operation == PREFIX + "report":
                    return self._report(connection, values["organization_id"])
                raise ValidationError("Telemetri okuma işlemi bilinmiyor.")
        except (TelemetryError, StorageError):
            raise
        except (sqlite3.Error, TypeError, ValueError, KeyError, IndexError,
                json.JSONDecodeError, ValidationError) as error:
            raise StorageError("Telemetri kayıtları bozuk veya okunamıyor; kısmi sonuç üretilmedi.") from error

    def mutate(self, operation: str, values: dict, at: str) -> dict:
        at = _time(at)
        if operation not in {PREFIX + "source.add", PREFIX + "source.update", PREFIX + "review", PREFIX + "recover"}:
            raise ValidationError("Telemetri yazma işlemi bilinmiyor.")
        try:
            with self.storage._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                request_sha = self._request(operation, values)
                replay = self._mutation_replay(connection, values["idempotency_key"], request_sha)
                if replay is not None:
                    return replay
                if operation == PREFIX + "source.add":
                    result = self._add_source(connection, values, at)
                elif operation == PREFIX + "source.update":
                    result = self._update_source(connection, values, at)
                elif operation == PREFIX + "review":
                    result = self._review(connection, values, at)
                else:
                    result = self._recover(connection, values, at)
                result = self._store_mutation(
                    connection, values["idempotency_key"], request_sha, result, at,
                )
                connection.commit()
                return result
        except (TelemetryError, ValidationError, StorageError):
            raise
        except sqlite3.IntegrityError as error:
            raise ValidationError("Telemetri kaydı mevcut kapsam veya benzersizlik kuralıyla çakışıyor.") from error
        except (sqlite3.Error, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise StorageError("Telemetri yazımı güvenli biçimde tamamlanamadı.") from error

    @staticmethod
    def _add_source(connection, values, at):
        definition = source_definition({key: values[key] for key in (
            "name", "organization_id", "source_kind", "input_format", "description",
        )})
        organization = connection.execute(
            "SELECT active FROM organizations WHERE id=?", (definition["organization_id"],),
        ).fetchone()
        if organization is None or organization[0] != 1:
            raise ValidationError("Etkin ve aynı çalışma alanındaki kuruluş gerekli.")
        identifier = str(uuid4())
        connection.execute(
            "INSERT INTO telemetry_sources (id,organization_id,name_key,display_name,source_kind,"
            "input_format,description,revision,enabled,created_at,updated_at) VALUES (?,?,?,?,?,?,?,1,1,?,?)",
            (identifier, definition["organization_id"], _name_key(definition["name"]),
             definition["name"], definition["source_kind"], definition["input_format"],
             definition["description"], at, at),
        )
        source = {
            "id": identifier, **definition, "revision": 1, "enabled": True,
            "created_at": at, "updated_at": at,
        }
        SQLiteTelemetryRepository._source_event(connection, source, "added", "İlk telemetri kaynak tanımı", at)
        return {"action": "added", "source": source}

    @staticmethod
    def _source_event(connection, source, action, reason, at):
        snapshot = {key: source[key] for key in (
            "id", "organization_id", "name", "source_kind", "input_format",
            "description", "revision", "enabled", "created_at", "updated_at",
        )}
        encoded = canonical(snapshot)
        connection.execute(
            "INSERT INTO telemetry_source_events (id,source_id,action,revision,snapshot_json,"
            "snapshot_sha256,reason,recorded_at) VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid4()), source["id"], action, source["revision"], encoded,
             hashlib.sha256(encoded.encode("ascii")).hexdigest(), reason, at),
        )

    @staticmethod
    def _update_source(connection, values, at):
        _row, source = _source_row(connection, values["identifier"])
        if source["revision"] != values["expected_revision"]:
            raise TelemetryError("revision_conflict", "Telemetri kaynak sürümü değişti; güncel kaydı okuyun.")
        if not any(key in values for key in ("name", "description", "enabled")):
            raise ValidationError("Telemetri kaynak güncellemesi en az bir değişiklik içermeli.")
        updated = dict(source)
        if "name" in values: updated["name"] = values["name"]
        if "description" in values: updated["description"] = values["description"]
        if "enabled" in values: updated["enabled"] = values["enabled"]
        changed = any(updated[key] != source[key] for key in ("name", "description", "enabled"))
        if not changed:
            return {"action": "unchanged", "source": source}
        updated["revision"] += 1; updated["updated_at"] = at
        connection.execute(
            "UPDATE telemetry_sources SET name_key=?,display_name=?,description=?,revision=?,enabled=?,updated_at=? WHERE id=?",
            (_name_key(updated["name"]), updated["name"], updated["description"],
             updated["revision"], int(updated["enabled"]), at, updated["id"]),
        )
        action = "enabled" if not source["enabled"] and updated["enabled"] else "disabled" if source["enabled"] and not updated["enabled"] else "updated"
        SQLiteTelemetryRepository._source_event(connection, updated, action, values["reason"], at)
        return {"action": action, "source": updated}

    @staticmethod
    def _review(connection, values, at):
        record = read_record_in(connection, values["identifier"])
        if record["revision"] != values["expected_revision"]:
            raise TelemetryError("revision_conflict", "Telemetri kaydı değişti; güncel kanıtı yeniden inceleyin.")
        revision = record["review_revision"] + 1
        result = {
            "id": str(uuid4()), "record_id": record["id"],
            "record_revision": record["revision"], "revision": revision,
            "decision": values["decision"], "reason": values["reason"],
            "actor": values["actor"], "recorded_at": at,
        }
        connection.execute(
            "INSERT INTO telemetry_reviews (id,record_id,record_revision,revision,decision,reason,actor,recorded_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            tuple(result[key] for key in ("id", "record_id", "record_revision", "revision", "decision", "reason", "actor", "recorded_at")),
        )
        connection.execute(
            "UPDATE telemetry_records SET review_revision=? WHERE id=?",
            (revision, record["id"]),
        )
        return {"action": "reviewed", "review": result}

    @staticmethod
    def _recover(connection, values, at):
        _row, source = _source_row(connection, values["source_id"])
        rows = connection.execute(
            "SELECT id FROM telemetry_runs WHERE source_id=? AND status='running' ORDER BY sequence",
            (source["id"],),
        ).fetchall()
        for row in rows:
            connection.execute(
                "UPDATE telemetry_runs SET status='interrupted',error_code='recovered',error=?,finished_at=? WHERE id=?",
                (values["reason"], at, row[0]),
            )
        return {"action": "recovered", "source_id": source["id"],
                "recovered_count": len(rows), "run_ids": [row[0] for row in rows]}

    def reserve(self, source_id: str, expected_revision: int, preview: TelemetryPreview,
                idempotency_key: str, at: str) -> tuple[dict, bool]:
        at = _time(at)
        request = {
            "source_id": source_id, "source_revision": expected_revision,
            "input_format": preview.input_format, "content_sha256": preview.content_sha256,
            "preview_sha256": preview.preview_sha256,
        }
        request_sha = digest(request)
        try:
            with self.storage._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                _row, source = _source_row(connection, source_id)
                if source["revision"] != expected_revision:
                    raise TelemetryError("revision_conflict", "Telemetri kaynak sürümü değişti.")
                if not source["enabled"]:
                    raise TelemetryError("source_disabled", "Telemetri kaynağı devre dışı.")
                if source["input_format"] != preview.input_format:
                    raise ValidationError("Önizleme biçimi kayıtlı telemetri kaynağıyla uyuşmuyor.")
                for record in preview.records:
                    validate_record_for_source(record, source["source_kind"])
                existing = connection.execute(
                    "SELECT id,request_sha256 FROM telemetry_runs WHERE request_key=?",
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    if existing[1] != request_sha:
                        raise TelemetryError("idempotency_conflict", "Telemetri içe alma anahtarı başka içeriğe bağlı.")
                    _row, run = _run_row(connection, existing[0])
                    return run, True
                identifier = str(uuid4())
                connection.execute(
                    "INSERT INTO telemetry_runs (id,source_id,source_revision,request_key,request_sha256,"
                    "input_format,content_sha256,preview_sha256,status,input_count,record_count,ignored_count,"
                    "duplicate_count,added_count,updated_count,unchanged_count,ignored_json,error_code,error,"
                    "started_at,finished_at) VALUES (?,?,?,?,?,?,?,?, 'running',?,?,?,?,0,0,0,?,NULL,NULL,?,NULL)",
                    (identifier, source_id, expected_revision, idempotency_key, request_sha,
                     preview.input_format, preview.content_sha256, preview.preview_sha256,
                     preview.input_count, preview.record_count, preview.ignored_count,
                     preview.duplicate_count, canonical(list(preview.ignored_reasons)), at),
                )
                connection.commit()
                _row, run = _run_row(connection, identifier)
                return run, False
        except (TelemetryError, ValidationError, StorageError):
            raise
        except (sqlite3.Error, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise StorageError("Telemetri içe alma rezervasyonu tamamlanamadı.") from error

    def finish(self, run_id: str, records: tuple[TelemetryRecord, ...], at: str) -> dict:
        at = _time(at)
        try:
            with self.storage._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                _row, run = _run_row(connection, run_id)
                if run["status"] == "complete":
                    return {**run, "replayed": True}
                if run["status"] != "running":
                    raise TelemetryError("invalid_run_state", "Telemetri çalışması tamamlanabilir durumda değil.")
                _source_record, source = _source_row(connection, run["source_id"])
                if source["revision"] != run["source_revision"] or not source["enabled"]:
                    connection.execute(
                        "UPDATE telemetry_runs SET status='interrupted',error_code='source_changed',"
                        "error='Kaynak tanımı çalışma sırasında değişti.',finished_at=? WHERE id=?", (at, run_id),
                    )
                    connection.commit()
                    raise TelemetryError("source_changed", "Kaynak tanımı değişti; yeni önizleme gerekli.")
                if len(records) != run["record_count"]:
                    raise ValidationError("Telemetri önizleme kayıt sayısı değişti.")
                verified = preview_from_records(
                    records, input_format=run["input_format"],
                    content_sha256=run["content_sha256"],
                    input_count=run["input_count"],
                    ignored_count=run["ignored_count"],
                    ignored_reasons=tuple(run["ignored_reasons"]),
                )
                if verified.preview_sha256 != run["preview_sha256"]:
                    raise ValidationError("Telemetri önizlemesi rezervasyondan sonra değişti.")
                counts = {"added": 0, "updated": 0, "unchanged": 0}
                for record in records:
                    validate_record_for_source(record, source["source_kind"])
                    body = asdict(record); body_json = canonical(body); body_sha = digest(body)
                    current = connection.execute(
                        "SELECT id,body_sha256,revision,organization_id FROM telemetry_records "
                        "WHERE source_id=? AND native_key=?", (source["id"], record.native_id),
                    ).fetchone()
                    if current is None:
                        record_id, revision, action = str(uuid4()), 1, "added"
                        connection.execute(
                            "INSERT INTO telemetry_records (id,organization_id,source_id,native_key,record_kind,"
                            "event_at,summary,body_json,body_sha256,revision,review_revision,first_run_id,last_run_id,"
                            "first_seen_at,last_seen_at) VALUES (?,?,?,?,?,?,?,?,?,1,0,?,?,?,?)",
                            (record_id, source["organization_id"], source["id"], record.native_id,
                             record.kind, record.event_at, record.summary, body_json, body_sha,
                             run_id, run_id, at, at),
                        )
                    else:
                        record_id, old_sha, revision, organization_id = current
                        if organization_id != source["organization_id"]:
                            raise StorageError("Telemetri kuruluş bağı bozuk.")
                        if old_sha == body_sha:
                            action = "unchanged"
                            connection.execute(
                                "UPDATE telemetry_records SET last_run_id=?,last_seen_at=? WHERE id=?",
                                (run_id, at, record_id),
                            )
                        else:
                            action, revision = "updated", revision + 1
                            connection.execute(
                                "UPDATE telemetry_records SET record_kind=?,event_at=?,summary=?,body_json=?,"
                                "body_sha256=?,revision=?,last_run_id=?,last_seen_at=? WHERE id=?",
                                (record.kind, record.event_at, record.summary, body_json, body_sha,
                                 revision, run_id, at, record_id),
                            )
                    if action in {"added", "updated"}:
                        connection.execute(
                            "INSERT INTO telemetry_record_versions (id,record_id,run_id,revision,action,body_json,"
                            "body_sha256,recorded_at) VALUES (?,?,?,?,?,?,?,?)",
                            (str(uuid4()), record_id, run_id, revision, action, body_json, body_sha, at),
                        )
                    connection.execute(
                        "INSERT INTO telemetry_run_items (id,run_id,record_id,action,record_revision,body_sha256) "
                        "VALUES (?,?,?,?,?,?)",
                        (str(uuid4()), run_id, record_id, action, revision, body_sha),
                    )
                    counts[action] += 1
                connection.execute(
                    "UPDATE telemetry_runs SET status='complete',added_count=?,updated_count=?,unchanged_count=?,"
                    "finished_at=? WHERE id=?",
                    (counts["added"], counts["updated"], counts["unchanged"], at, run_id),
                )
                connection.commit()
                _row, result = _run_row(connection, run_id)
                return {**result, "replayed": False}
        except (TelemetryError, ValidationError, StorageError):
            raise
        except (sqlite3.Error, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise StorageError("Telemetri kayıtları atomik olarak tamamlanamadı; recovery çalıştırın.") from error

    @staticmethod
    def _source_events(connection, source_id):
        rows = connection.execute(
            "SELECT sequence,id,action,revision,snapshot_json,snapshot_sha256,reason,recorded_at "
            "FROM telemetry_source_events WHERE source_id=? ORDER BY sequence", (source_id,),
        ).fetchall()
        result = []
        snapshot_fields = {
            "id", "organization_id", "name", "source_kind", "input_format",
            "description", "revision", "enabled", "created_at", "updated_at",
        }
        for expected_revision, row in enumerate(rows, 1):
            snapshot = _loads(row[4])
            if not isinstance(snapshot, dict) or set(snapshot) != snapshot_fields:
                raise StorageError("Telemetri kaynak olay anlık görüntüsü bozuk.")
            definition = source_definition({key: snapshot[key] for key in (
                "name", "organization_id", "source_kind", "input_format", "description",
            )})
            if (_sequence(row[0]) != row[0] or _uuid(row[1]) != row[1]
                    or row[2] not in {"added", "updated", "enabled", "disabled"}
                    or row[3] != expected_revision
                    or snapshot["id"] != source_id or _uuid(snapshot["id"]) != snapshot["id"]
                    or snapshot["organization_id"] != definition["organization_id"]
                    or snapshot["revision"] != row[3]
                    or type(snapshot["revision"]) is not int or snapshot["revision"] < 1
                    or type(snapshot["enabled"]) is not bool
                    or _time(snapshot["created_at"]) != snapshot["created_at"]
                    or _time(snapshot["updated_at"]) != snapshot["updated_at"]
                    or snapshot["created_at"] > snapshot["updated_at"]
                    or not isinstance(row[6], str) or not 3 <= len(row[6]) <= 2000
                    or _time(row[7]) != row[7]
                    or canonical(snapshot) != row[4]
                    or hashlib.sha256(row[4].encode("ascii")).hexdigest() != row[5]):
                raise StorageError("Telemetri kaynak olay zinciri bozuk.")
            result.append({"sequence": row[0], "id": row[1], "action": row[2],
                           "revision": row[3], "snapshot": snapshot,
                           "snapshot_sha256": row[5], "reason": row[6], "recorded_at": row[7]})
        if rows and rows[0][2] != "added":
            raise StorageError("Telemetri kaynak olay zinciri ekleme olayıyla başlamıyor.")
        return result

    @staticmethod
    def _run_items(connection, run_id, limit):
        run = connection.execute(
            "SELECT source_id,status FROM telemetry_runs WHERE id=?", (run_id,),
        ).fetchone()
        if run is None:
            raise StorageError("Telemetri çalışma kalemi üst kaydı bulunamadı.")
        rows = connection.execute(
            "SELECT sequence,id,record_id,action,record_revision,body_sha256 FROM telemetry_run_items "
            "WHERE run_id=? ORDER BY sequence LIMIT ?", (run_id, limit + 1),
        ).fetchall()
        items = []
        for row in rows[:limit]:
            if (_sequence(row[0]) != row[0] or _uuid(row[1]) != row[1]
                    or _uuid(row[2]) != row[2]
                    or row[3] not in {"added", "updated", "unchanged"}
                    or type(row[4]) is not int or row[4] < 1):
                raise StorageError("Telemetri çalışma kalemi bozuk.")
            record = connection.execute(
                "SELECT source_id,revision FROM telemetry_records WHERE id=?", (row[2],),
            ).fetchone()
            if record is None or record[0] != run[0] or row[4] > record[1]:
                raise StorageError("Telemetri çalışma kalemi kayıt bağı bozuk.")
            items.append({
                "sequence": row[0], "id": row[1], "record_id": row[2],
                "action": row[3], "record_revision": row[4],
                "body_sha256": _sha(row[5]),
            })
        return {"items": items, "has_more": len(rows) > limit}

    @staticmethod
    def _versions(connection, record_id, limit):
        rows = connection.execute(
            "SELECT sequence,id,run_id,revision,action,body_json,body_sha256,recorded_at "
            "FROM telemetry_record_versions WHERE record_id=? ORDER BY sequence LIMIT ?",
            (record_id, limit + 1),
        ).fetchall()
        result = []
        for row in rows[:limit]:
            body_json = archived_value(
                connection, run_id=record_id, family="telemetry_records",
                field=f"version.{row[3]}", value=row[5], checksum=row[6],
            )
            body = _loads(body_json); normalized = normalize_record(body)
            if (_sequence(row[0]) != row[0] or _uuid(row[1]) != row[1]
                    or _uuid(row[2]) != row[2]
                    or type(row[3]) is not int or row[3] < 1
                    or row[4] not in {"added", "updated"}
                    or canonical(asdict(normalized)) != body_json
                    or digest(asdict(normalized)) != row[6]
                    or _time(row[7]) != row[7]):
                raise StorageError("Telemetri sürüm kanıtı bozuk.")
            result.append({"sequence": row[0], "id": row[1], "run_id": row[2],
                           "revision": row[3], "action": row[4], "body": body,
                           "body_sha256": row[6], "recorded_at": row[7]})
        return {"items": result, "has_more": len(rows) > limit}

    @staticmethod
    def _sources(connection, values):
        where, parameters = ["sequence>?"], [values["after"]]
        if values.get("organization_id"):
            where.append("organization_id=?"); parameters.append(values["organization_id"])
        rows = connection.execute(
            "SELECT sequence,id,organization_id,name_key,display_name,source_kind,input_format,description,"
            "revision,enabled,created_at,updated_at FROM telemetry_sources WHERE " + " AND ".join(where)
            + " ORDER BY sequence LIMIT ?", (*parameters, values["limit"] + 1),
        ).fetchall()
        items = [_source_payload(row) for row in rows]
        return _page(items, values["limit"])

    @staticmethod
    def _runs(connection, values):
        where, parameters = ["r.sequence>?"], [values["after"]]
        if values.get("source_id"):
            where.append("r.source_id=?"); parameters.append(values["source_id"])
        if values.get("organization_id"):
            where.append("s.organization_id=?"); parameters.append(values["organization_id"])
        rows = connection.execute(
            "SELECT r.sequence,r.id,r.source_id,r.source_revision,r.request_key,r.request_sha256,r.input_format,"
            "r.content_sha256,r.preview_sha256,r.status,r.input_count,r.record_count,r.ignored_count,r.duplicate_count,"
            "r.added_count,r.updated_count,r.unchanged_count,r.error_code,r.error,r.ignored_json,"
            "r.started_at,r.finished_at FROM telemetry_runs r JOIN telemetry_sources s ON s.id=r.source_id WHERE "
            + " AND ".join(where) + " ORDER BY r.sequence LIMIT ?", (*parameters, values["limit"] + 1),
        ).fetchall()
        items = [_run_row(connection, row[1])[1] for row in rows]
        return _page(items, values["limit"])

    @staticmethod
    def _records(connection, values):
        where, parameters = ["r.sequence>?"], [values["after"]]
        if values.get("source_id"):
            where.append("r.source_id=?"); parameters.append(values["source_id"])
        if values.get("organization_id"):
            where.append("r.organization_id=?"); parameters.append(values["organization_id"])
        if values.get("record_kind"):
            where.append("r.record_kind=?"); parameters.append(values["record_kind"])
        rows = connection.execute(
            "SELECT r.id FROM telemetry_records r WHERE " + " AND ".join(where)
            + " ORDER BY r.sequence LIMIT ?", (*parameters, values["limit"] + 1),
        ).fetchall()
        items = [read_record_in(connection, row[0]) for row in rows]
        return _page(items, values["limit"])

    @staticmethod
    def _report(connection, organization_id):
        organization = connection.execute(
            "SELECT display_name,active FROM organizations WHERE id=?", (organization_id,),
        ).fetchone()
        if organization is None:
            raise TelemetryError("not_found", "Telemetri kuruluş kapsamı bulunamadı.")
        counts = dict(connection.execute(
            "SELECT record_kind,COUNT(*) FROM telemetry_records WHERE organization_id=? GROUP BY record_kind",
            (organization_id,),
        ))
        sources = connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(enabled),0) FROM telemetry_sources WHERE organization_id=?",
            (organization_id,),
        ).fetchone()
        runs = connection.execute(
            "SELECT COUNT(*),COALESCE(SUM(status='running'),0),COALESCE(SUM(status='interrupted'),0) "
            "FROM telemetry_runs WHERE source_id IN (SELECT id FROM telemetry_sources WHERE organization_id=?)",
            (organization_id,),
        ).fetchone()
        reviews = connection.execute(
            "SELECT COUNT(*) FROM telemetry_reviews WHERE record_id IN "
            "(SELECT id FROM telemetry_records WHERE organization_id=?)", (organization_id,),
        ).fetchone()[0]
        needs_review = connection.execute(
            "SELECT COUNT(*) FROM telemetry_records r WHERE r.organization_id=? AND NOT EXISTS "
            "(SELECT 1 FROM telemetry_reviews v WHERE v.record_id=r.id AND v.record_revision=r.revision)",
            (organization_id,),
        ).fetchone()[0]
        return {
            "organization": {"id": organization_id, "name": organization[0], "active": bool(organization[1])},
            "sources": {"total": sources[0], "enabled": sources[1]},
            "runs": {"total": runs[0], "running": runs[1], "interrupted": runs[2]},
            "records": {"total": sum(counts.values()), "by_kind": {kind: counts.get(kind, 0) for kind in RECORD_KINDS}},
            "reviews": {"total": reviews, "needs_review": needs_review},
            "notes": [
                "Telemetri kaydı kaynak gözlemidir; tek başına doğrulanmış saldırı veya zararlılık hükmü değildir.",
                "Alarm için P07 birleşik izleme politikasında telemetry kayıt türünü seçin.",
            ],
        }


def search_records(connection):
    rows = connection.execute(
        "SELECT r.id FROM telemetry_records r ORDER BY r.sequence"
    ).fetchall()
    return [read_record_in(connection, row[0]) for row in rows]

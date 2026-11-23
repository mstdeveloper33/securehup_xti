"""SQLite P08 policy, hold, archive, restore and audit implementation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from uuid import uuid4

from xti.adapters.retention_payloads import TELEMETRY_BUNDLE, marker, pack, parse_marker, unpack
from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_telemetry import read_record_in as read_telemetry_record_in
from xti.adapters.sqlite_unified_monitoring import SQLiteUnifiedMonitoringRepository
from xti.domain.assets import ValidationError
from xti.domain.content_monitoring import canonical, digest
from xti.domain.data_retention import (
    FAMILIES, FAMILY, HOLD_KINDS, POLICY, PREFIX, TELEMETRY_FAMILY,
    RetentionError, catalog, cutoff, policy_definition, request_sha256, utc_time,
)
from xti.domain.unified_monitoring import folded


P = "retention_"
MAX_POLICIES = 1000
MAX_POLICY_EVENTS = 10_000
MAX_HOLDS = 20_000
MAX_HOLD_EVENTS = 50_000
MAX_RUNS = 20_000
MAX_ARCHIVE_ITEMS = 50_000
MAX_AUDIT_EVENTS = 50_000
MAX_MUTATIONS = 50_000
MAX_ARCHIVE_RAW_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_PACKED_BYTES = 256 * 1024 * 1024


def _sha(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("invalid sha256")
    return value


def _json(value: object, checksum: object, maximum: int = 8 * 1024 * 1024):
    if not isinstance(value, str) or len(value.encode("ascii")) > maximum:
        raise ValueError("invalid json size")
    parsed = json.loads(value)
    if canonical(parsed) != value or digest(parsed) != _sha(checksum):
        raise ValueError("invalid json digest")
    return parsed


def _time(value: object) -> str:
    return utc_time(value)


def _chain(previous: str | None, payload: dict) -> str:
    return digest({"previous": previous, "event": payload})


class SQLiteDataRetentionRepository:
    def __init__(self, path: Path) -> None:
        self.storage = SQLiteAssetRepository(path)

    @staticmethod
    def _ensure_room(connection, table: str, increment: int = 1) -> None:
        limits = {
            "policies": MAX_POLICIES, "policy_events": MAX_POLICY_EVENTS,
            "holds": MAX_HOLDS, "hold_events": MAX_HOLD_EVENTS,
            "runs": MAX_RUNS, "archive_items": MAX_ARCHIVE_ITEMS,
            "audit_events": MAX_AUDIT_EVENTS, "mutations": MAX_MUTATIONS,
        }
        if table not in limits or type(increment) is not int or increment < 0:
            raise StorageError("Saklama kapasite isteği geçersiz.")
        count = connection.execute(f"SELECT COUNT(*) FROM {P + table}").fetchone()[0]
        if type(count) is not int or count + increment > limits[table]:
            raise RetentionError("capacity", "Saklama kayıt kapasitesi doldu.")

    @classmethod
    def _guard(cls, connection) -> None:
        for table in (
            "policies", "policy_events", "holds", "hold_events", "runs",
            "archive_items", "audit_events", "mutations",
        ):
            cls._ensure_room(connection, table, 0)
        raw, packed = connection.execute(
            "SELECT COALESCE(SUM(snapshot_raw_size+report_raw_size),0),"
            "COALESCE(SUM(LENGTH(snapshot_body)+LENGTH(report_body)),0) "
            "FROM retention_archive_items WHERE active=1"
        ).fetchone()
        if (type(raw) is not int or type(packed) is not int or raw < 0 or packed < 0
                or raw > MAX_ARCHIVE_RAW_BYTES or packed > MAX_ARCHIVE_PACKED_BYTES):
            raise StorageError("Saklama arşivi güvenli kapasite sınırını aşıyor.")
        cls._family_guard(connection)
        cls._audit(connection)

    @staticmethod
    def _record_owner(connection, family: str, record_id: str) -> str | None:
        if family == FAMILY:
            row = connection.execute(
                "SELECT p.organization_id FROM monitoring_runs r JOIN monitoring_policies p "
                "ON p.id=r.policy_id WHERE r.id=?", (record_id,),
            ).fetchone()
        elif family == TELEMETRY_FAMILY:
            row = connection.execute(
                "SELECT organization_id FROM telemetry_records WHERE id=?", (record_id,),
            ).fetchone()
        else:
            raise StorageError("Saklama veri ailesi bozuk.")
        return row[0] if row is not None else None

    @classmethod
    def _family_guard(cls, connection) -> None:
        try:
            holds = connection.execute(
                "SELECT organization_id,family,record_id FROM retention_holds "
                "WHERE record_id IS NOT NULL"
            ).fetchall()
            archives = connection.execute(
                "SELECT organization_id,family,record_id,active_key,active "
                "FROM retention_archive_items"
            ).fetchall()
            for organization_id, family, record_id in holds:
                if cls._record_owner(connection, family, record_id) != organization_id:
                    raise ValueError()
            for organization_id, family, record_id, active_key, active in archives:
                if cls._record_owner(connection, family, record_id) != organization_id:
                    raise ValueError()
                if active:
                    expected = family + ":" + record_id
                    if ((family == FAMILY and active_key != expected)
                            or (family == TELEMETRY_FAMILY
                                and (not isinstance(active_key, str)
                                     or not active_key.startswith(expected + ":")))):
                        raise ValueError()
        except (TypeError, ValueError):
            raise StorageError("Saklama veri ailesi bağlantısı bozuk.") from None

    @staticmethod
    def _organization(connection, identifier: str, *, active: bool = False) -> dict:
        row = connection.execute(
            "SELECT id,display_name,active FROM organizations WHERE id=?", (identifier,),
        ).fetchone()
        if row is None:
            raise RetentionError("not_found", "Saklama kuruluşu bulunamadı.")
        if active and row[2] != 1:
            raise RetentionError("inactive", "Etkin olmayan kuruluş için yeni saklama işlemi yapılamaz.")
        return {"id": row[0], "display_name": row[1], "active": bool(row[2])}

    @classmethod
    def _audit(cls, connection) -> tuple[list[dict], str | None]:
        rows = connection.execute(
            "SELECT sequence,id,organization_id,action,resource_kind,resource_id,actor,reason,"
            "details_json,details_sha256,previous_chain_sha256,chain_sha256,recorded_at "
            "FROM retention_audit_events ORDER BY sequence"
        ).fetchall()
        if len(rows) > MAX_AUDIT_EVENTS:
            raise StorageError("Saklama denetim günlüğü kapasitesi aşıyor.")
        events, previous, previous_at = [], None, None
        try:
            for expected, row in enumerate(rows, 1):
                details = _json(row[8], row[9], 1_000_000)
                recorded_at = _time(row[12])
                payload = {
                    "id": row[1], "organization_id": row[2], "action": row[3],
                    "resource_kind": row[4], "resource_id": row[5], "actor": row[6],
                    "reason": row[7], "details": details, "recorded_at": recorded_at,
                }
                if (row[0] != expected or row[10] != previous
                        or row[11] != _chain(previous, payload)
                        or previous_at is not None and recorded_at < previous_at):
                    raise ValueError()
                events.append({"sequence": row[0], **payload, "chain_sha256": row[11]})
                previous, previous_at = row[11], recorded_at
            allocated = connection.execute(
                "SELECT seq FROM sqlite_sequence WHERE name='retention_audit_events'"
            ).fetchone()
            if (allocated is None and events) or allocated is not None and allocated[0] != len(events):
                raise ValueError()
            return events, previous
        except (ValueError, TypeError, KeyError, ValidationError, json.JSONDecodeError) as error:
            raise StorageError("Saklama denetim zinciri tutarsız.") from error

    @classmethod
    def _append_audit(cls, connection, *, organization_id: str, action: str,
                      resource_kind: str, resource_id: str, actor: str, reason: str,
                      details: dict, at: str) -> dict:
        cls._ensure_room(connection, "audit_events")
        _, previous = cls._audit(connection)
        identifier = str(uuid4())
        payload = {
            "id": identifier, "organization_id": organization_id, "action": action,
            "resource_kind": resource_kind, "resource_id": resource_id,
            "actor": actor, "reason": reason, "details": details,
            "recorded_at": _time(at),
        }
        details_json = canonical(details)
        chain = _chain(previous, payload)
        connection.execute(
            "INSERT INTO retention_audit_events (id,organization_id,action,resource_kind,"
            "resource_id,actor,reason,details_json,details_sha256,previous_chain_sha256,"
            "chain_sha256,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (identifier, organization_id, action, resource_kind, resource_id, actor,
             reason, details_json, digest(details), previous, chain, at),
        )
        return {"sequence": connection.execute("SELECT last_insert_rowid()").fetchone()[0],
                **payload, "chain_sha256": chain}

    @classmethod
    def _policy_event(cls, connection, identifier: str) -> dict:
        row = connection.execute(
            "SELECT sequence,id,policy_id,revision,action,definition_json,definition_sha256,"
            "reason,actor,recorded_at FROM retention_policy_events WHERE id=?", (identifier,),
        ).fetchone()
        if row is None:
            raise StorageError("Saklama politika olayı bulunamadı.")
        try:
            definition = policy_definition(_json(row[5], row[6], 1_000_000))
            if (type(row[0]) is not int or row[0] < 1 or type(row[3]) is not int or row[3] < 1
                    or row[4] not in ("added", "updated", "reactivated", "disabled")):
                raise ValueError()
            return {"sequence": row[0], "id": row[1], "policy_id": row[2],
                    "revision": row[3], "action": row[4], "definition": definition,
                    "definition_sha256": row[6], "reason": row[7], "actor": row[8],
                    "recorded_at": _time(row[9])}
        except (ValueError, TypeError, KeyError, ValidationError, json.JSONDecodeError) as error:
            raise StorageError("Saklama politika olayı bozuk.") from error

    @classmethod
    def _policy(cls, connection, identifier: str) -> dict:
        row = connection.execute(
            "SELECT sequence,id,organization_id,name_key,revision,enabled,definition_json,"
            "definition_sha256,created_at,updated_at FROM retention_policies WHERE id=?",
            (identifier,),
        ).fetchone()
        if row is None:
            raise RetentionError("not_found", "Saklama politikası bulunamadı.")
        try:
            definition = policy_definition(_json(row[6], row[7], 1_000_000))
            organization = cls._organization(connection, row[2])
            event_id = connection.execute(
                "SELECT id FROM retention_policy_events WHERE policy_id=? AND revision=?",
                (row[1], row[4]),
            ).fetchone()
            if (definition["organization_id"] != row[2]
                    or folded(definition["name"]) != row[3]
                    or type(row[4]) is not int or row[4] < 1
                    or row[5] not in (0, 1) or event_id is None):
                raise ValueError()
            event = cls._policy_event(connection, event_id[0])
            if (event["definition"] != definition or event["recorded_at"] != _time(row[9])
                    or (event["action"] == "disabled") == bool(row[5])):
                raise ValueError()
            return {"sequence": row[0], "id": row[1], "organization": organization,
                    "revision": row[4], "enabled": bool(row[5]), "definition": definition,
                    "definition_sha256": row[7], "created_at": _time(row[8]),
                    "updated_at": _time(row[9]), "event": event}
        except (ValueError, TypeError, KeyError, ValidationError, json.JSONDecodeError) as error:
            raise StorageError("Saklama politika kaydı bozuk.") from error

    @classmethod
    def _hold(cls, connection, identifier: str) -> dict:
        row = connection.execute(
            "SELECT sequence,id,organization_id,family,scope_key,record_id,case_id,kind,"
            "revision,active,reason,actor,created_at,updated_at FROM retention_holds WHERE id=?",
            (identifier,),
        ).fetchone()
        if row is None:
            raise RetentionError("not_found", "Saklama koruması bulunamadı.")
        event = connection.execute(
            "SELECT sequence,id,revision,action,reason,actor,recorded_at FROM retention_hold_events "
            "WHERE hold_id=? AND revision=?", (row[1], row[8]),
        ).fetchone()
        try:
            if (row[3] not in FAMILIES or row[4] != (row[5] or "*") or row[7] not in HOLD_KINDS
                    or type(row[8]) is not int or row[8] < 1 or row[9] not in (0, 1)
                    or event is None or event[2] != row[8]
                    or (event[3] == "released") == bool(row[9])
                    or event[4] != row[10] or event[5] != row[11]
                    or _time(event[6]) != _time(row[13])):
                raise ValueError()
            return {"sequence": row[0], "id": row[1],
                    "organization": cls._organization(connection, row[2]),
                    "family": row[3], "scope_key": row[4], "record_id": row[5],
                    "case_id": row[6], "kind": row[7], "revision": row[8],
                    "active": bool(row[9]), "reason": row[10], "actor": row[11],
                    "created_at": _time(row[12]), "updated_at": _time(row[13]),
                    "event": {"sequence": event[0], "id": event[1], "revision": event[2],
                              "action": event[3], "reason": event[4], "actor": event[5],
                              "recorded_at": _time(event[6])}}
        except (ValueError, TypeError, ValidationError) as error:
            raise StorageError("Saklama koruma kaydı bozuk.") from error

    @classmethod
    def _run(cls, connection, identifier: str, *, details: bool = True) -> dict:
        row = connection.execute(
            "SELECT sequence,id,operation,policy_id,policy_event_id,target_run_id,request_key,"
            "request_sha256,status,plan_json,plan_sha256,receipt_json,receipt_sha256,actor,reason,"
            "error_code,error_message,started_at,finished_at FROM retention_runs WHERE id=?",
            (identifier,),
        ).fetchone()
        if row is None:
            raise RetentionError("not_found", "Saklama çalışması bulunamadı.")
        try:
            plan = _json(row[9], row[10])
            status = row[8]
            if row[2] not in ("archive", "restore") or status not in (
                "running", "complete", "failed", "interrupted",
            ):
                raise ValueError()
            receipt = None
            if status == "complete":
                if row[11] is None or row[12] is None or row[18] is None or row[15] or row[16]:
                    raise ValueError()
                receipt = _json(row[11], row[12])
            elif row[11] is not None or row[12] is not None:
                raise ValueError()
            if status == "running" and (row[15] or row[16] or row[18] is not None):
                raise ValueError()
            if status in ("failed", "interrupted") and (not row[15] or not row[16] or row[18] is None):
                raise ValueError()
            result = {"sequence": row[0], "id": row[1], "operation": row[2],
                      "policy_id": row[3], "policy_event_id": row[4],
                      "target_run_id": row[5], "status": status,
                      "actor": row[13], "reason": row[14], "error_code": row[15],
                      "error_message": row[16], "started_at": _time(row[17]),
                      "finished_at": _time(row[18]) if row[18] else None}
            if details:
                result.update({"plan": plan, "receipt": receipt})
            return result
        except (ValueError, TypeError, KeyError, ValidationError, json.JSONDecodeError) as error:
            raise StorageError("Saklama çalışma kaydı bozuk.") from error

    @classmethod
    def _mutation(cls, connection, operation: str, values: dict) -> dict | None:
        row = connection.execute(
            "SELECT request_sha256,operation,result_json,result_sha256 FROM retention_mutations "
            "WHERE request_key=?", (values["idempotency_key"],),
        ).fetchone()
        if row is None:
            return None
        checksum = request_sha256(operation, values)
        if row[0] != checksum or row[1] != operation:
            raise RetentionError("idempotency_conflict", "Tekrar anahtarı farklı bir saklama isteğine ait.")
        try:
            return _json(row[2], row[3])
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise StorageError("Saklama tekrar makbuzu bozuk.") from error

    @classmethod
    def _store_mutation(cls, connection, operation: str, values: dict,
                        result: dict, at: str) -> None:
        cls._ensure_room(connection, "mutations")
        raw = canonical(result)
        connection.execute(
            "INSERT INTO retention_mutations (id,request_key,request_sha256,operation,"
            "result_json,result_sha256,created_at) VALUES (?,?,?,?,?,?,?)",
            (str(uuid4()), values["idempotency_key"], request_sha256(operation, values),
             operation, raw, digest(result), at),
        )

    @staticmethod
    def _protection(connection, organization_id: str, family: str):
        hold_rows = connection.execute(
            "SELECT scope_key FROM retention_holds WHERE organization_id=? AND family=? AND active=1",
            (organization_id, family),
        ).fetchall()
        hold_all = any(row[0] == "*" for row in hold_rows)
        held_ids = {row[0] for row in hold_rows if row[0] != "*"}
        if family == FAMILY:
            case_ids = {
                row[0] for row in connection.execute(
                    "SELECT a.run_id FROM monitoring_alerts a "
                    "JOIN monitoring_policies p ON p.id=a.policy_id "
                    "JOIN case_evidence e ON e.evidence_type='unified_monitoring' "
                    "AND e.evidence_id=a.id AND e.active=1 WHERE p.organization_id=?",
                    (organization_id,),
                )
            }
        else:
            case_ids = {
                row[0] for row in connection.execute(
                    "SELECT e.evidence_id FROM case_evidence e JOIN telemetry_records r "
                    "ON r.id=e.evidence_id WHERE e.evidence_type='telemetry' AND e.active=1 "
                    "AND r.organization_id=?", (organization_id,),
                )
            }
        return hold_all, held_ids, case_ids

    @classmethod
    def _monitoring_plan(cls, connection, organization_id: str, boundary: str) -> dict:
        active_archives = {
            row[0] for row in connection.execute(
                "SELECT record_id FROM retention_archive_items WHERE active=1 AND family=?",
                (FAMILY,),
            )
        }
        hold_all, held_ids, case_ids = cls._protection(
            connection, organization_id, FAMILY,
        )
        counters = {key: 0 for key in (
            "recent", "explicit_hold", "case_protected", "already_archived",
            "no_payload", "no_saving",
        )}
        items = []
        rows = connection.execute(
            "SELECT r.id,r.snapshot_json,r.snapshot_sha256,r.report_json,r.report_sha256,"
            "r.finished_at FROM monitoring_runs r JOIN monitoring_policies p ON p.id=r.policy_id "
            "WHERE p.organization_id=? AND r.status='complete' ORDER BY r.sequence",
            (organization_id,),
        ).fetchall()
        for row in rows:
            run_id, snapshot_json, snapshot_sha, report_json, report_sha, finished_at = row
            finished_at = _time(finished_at)
            if finished_at >= boundary:
                counters["recent"] += 1; continue
            if run_id in active_archives:
                counters["already_archived"] += 1; continue
            if hold_all or run_id in held_ids:
                counters["explicit_hold"] += 1; continue
            if run_id in case_ids:
                counters["case_protected"] += 1; continue
            if report_json is None or parse_marker(report_json) is not None:
                counters["no_payload"] += 1; continue
            report_body, report_size = pack(report_json, report_sha)
            snapshot_body, snapshot_size = (None, 0)
            if snapshot_json is not None:
                if parse_marker(snapshot_json) is not None:
                    counters["no_payload"] += 1; continue
                snapshot_body, snapshot_size = pack(snapshot_json, snapshot_sha)
            packed_size = len(report_body) + (len(snapshot_body) if snapshot_body else 0)
            raw_size = report_size + snapshot_size
            if packed_size + 512 >= raw_size:
                counters["no_saving"] += 1; continue
            items.append({
                "family": FAMILY, "record_id": run_id, "finished_at": finished_at,
                "snapshot_sha256": snapshot_sha, "report_sha256": report_sha,
                "snapshot_raw_size": snapshot_size, "report_raw_size": report_size,
                "packed_bytes": packed_size,
            })
        return {"items": items, "counters": counters}

    @staticmethod
    def _telemetry_payload(connection, record_id: str, *, include_material: bool = False):
        row = connection.execute(
            "SELECT organization_id,body_json,body_sha256,revision,last_seen_at "
            "FROM telemetry_records WHERE id=?", (record_id,),
        ).fetchone()
        if row is None:
            raise StorageError("Arşivlenecek telemetri kaydı bulunamadı.")
        current_hot = parse_marker(row[1]) is None
        version_rows = connection.execute(
            "SELECT id,run_id,revision,action,body_json,body_sha256,recorded_at "
            "FROM telemetry_record_versions WHERE record_id=? ORDER BY revision", (record_id,),
        ).fetchall()
        if not current_hot and all(parse_marker(item[4]) is not None for item in version_rows):
            return None
        # Verify the current source/run/review chain before moving any remaining
        # hot body. Already archived immutable versions are resolved on demand.
        read_telemetry_record_in(connection, record_id)
        snapshot_size = 0
        snapshot_packed = 0
        snapshot_body = None
        if current_hot:
            snapshot_body, snapshot_size = pack(row[1], row[2])
            snapshot_packed = len(snapshot_body)

        versions = []
        pending_versions = 0
        selected_version_bytes = 0
        removed_bytes = snapshot_size
        marker_bytes = len(marker("0" * 36, "snapshot", row[2]).encode("ascii")) if current_hot else 0
        for version_id, run_id, revision, action, body_json, body_sha, recorded_at in version_rows:
            if parse_marker(body_json) is not None:
                continue
            parsed = _json(body_json, body_sha)
            body_bytes = len(body_json.encode("ascii"))
            if selected_version_bytes + body_bytes > 8 * 1024 * 1024:
                pending_versions += 1
                continue
            versions.append({
                "id": version_id, "run_id": run_id, "revision": revision,
                "action": action, "body": parsed, "body_sha256": body_sha,
                "recorded_at": _time(recorded_at),
            })
            selected_version_bytes += body_bytes
            removed_bytes += body_bytes
            marker_bytes += len(marker("0" * 36, f"version.{revision}", body_sha).encode("ascii"))
        if not current_hot and not versions:
            return None
        bundle = {"policy": TELEMETRY_BUNDLE, "record_id": record_id, "versions": versions}
        bundle_json, bundle_sha = canonical(bundle), digest(bundle)
        report_body, report_size = pack(bundle_json, bundle_sha)
        packed_size = snapshot_packed + len(report_body)
        if packed_size + marker_bytes >= removed_bytes:
            return {"no_saving": True}
        result = {
            "family": TELEMETRY_FAMILY, "record_id": record_id,
            "last_seen_at": _time(row[4]), "snapshot_sha256": row[2],
            "report_sha256": bundle_sha, "snapshot_raw_size": snapshot_size,
            "report_raw_size": report_size, "packed_bytes": packed_size,
            "current_body_archived": current_hot,
            "version_ids": [item["id"] for item in versions],
            "version_revisions": [item["revision"] for item in versions],
            "version_sha256": [item["body_sha256"] for item in versions],
            "pending_version_count": pending_versions,
            "generation_revision": max(
                [item["revision"] for item in versions] or [row[3]],
            ),
        }
        if include_material:
            return result, {
                "snapshot_body": snapshot_body, "report_body": report_body,
                "bundle": bundle, "versions": versions,
            }
        return result

    @classmethod
    def _telemetry_plan(cls, connection, organization_id: str, boundary: str) -> dict:
        hold_all, held_ids, case_ids = cls._protection(
            connection, organization_id, TELEMETRY_FAMILY,
        )
        counters = {key: 0 for key in (
            "recent", "explicit_hold", "case_protected", "already_archived",
            "no_payload", "no_saving",
        )}
        items = []
        rows = connection.execute(
            "SELECT id,last_seen_at FROM telemetry_records WHERE organization_id=? ORDER BY sequence",
            (organization_id,),
        ).fetchall()
        for record_id, last_seen_at in rows:
            last_seen_at = _time(last_seen_at)
            if last_seen_at >= boundary:
                counters["recent"] += 1; continue
            if hold_all or record_id in held_ids:
                counters["explicit_hold"] += 1; continue
            if record_id in case_ids:
                counters["case_protected"] += 1; continue
            item = cls._telemetry_payload(connection, record_id)
            if item is None:
                counters["already_archived"] += 1; continue
            if item.get("no_saving"):
                counters["no_saving"] += 1; continue
            items.append(item)
        return {"items": items, "counters": counters}

    @classmethod
    def _plan_in(cls, connection, policy: dict, at: str) -> dict:
        if not policy["enabled"] or not policy["organization"]["active"]:
            raise RetentionError("inactive", "Etkin olmayan saklama politikası önizlenemez.")
        definition = policy["definition"]
        boundary = cutoff(at, definition["archive_after_days"])
        counters = {key: 0 for key in (
            "recent", "explicit_hold", "case_protected", "already_archived",
            "no_payload", "no_saving",
        )}
        candidates, summaries = [], []
        for family in FAMILIES:
            if family not in definition["families"]:
                continue
            result = (cls._monitoring_plan(connection, policy["organization"]["id"], boundary)
                      if family == FAMILY else
                      cls._telemetry_plan(connection, policy["organization"]["id"], boundary))
            candidates.extend(result["items"])
            for key in counters:
                counters[key] += result["counters"][key]
            summaries.append({
                "family": family, "eligible_count": len(result["items"]),
                **{key + "_count": value for key, value in result["counters"].items()},
            })
        selected = candidates[:definition["batch_limit"]]
        for summary in summaries:
            summary["selected_count"] = sum(
                item["family"] == summary["family"] for item in selected
            )
        raw_total = sum(
            item["snapshot_raw_size"] + item["report_raw_size"] for item in selected
        )
        packed_total = sum(item["packed_bytes"] for item in selected)
        eligible = len(candidates)
        plan = {
            "policy": POLICY,
            "family": definition["families"][0] if len(definition["families"]) == 1 else None,
            "families": definition["families"], "family_summaries": summaries,
            "policy_id": policy["id"],
            "policy_revision": policy["revision"], "policy_event_id": policy["event"]["id"],
            "organization": policy["organization"], "generated_at": _time(at),
            "cutoff": boundary, "archive_after_days": definition["archive_after_days"],
            "batch_limit": definition["batch_limit"], "items": selected,
            "selected_count": len(selected), "eligible_count": eligible,
            "remaining_count": eligible - len(selected), **{key + "_count": value for key, value in counters.items()},
            "original_body_bytes": raw_total, "compressed_body_bytes": packed_total,
            "logical_record_delete": False, "case_evidence_auto_protected": True,
        }
        # The token fences the policy revision, eligible record identities and
        # their payload hashes.  Retention audit events are intentionally not
        # part of it: reserving the operation appends an audit event itself and
        # must not invalidate the immutable plan that was just reserved.
        plan["token"] = digest({"database": str(cls._path(connection)), "plan": plan})
        return plan

    @staticmethod
    def _path(connection) -> Path:
        row = connection.execute("PRAGMA database_list").fetchone()
        return Path(row[2]).resolve(strict=True)

    def plan(self, identifier: str, at: str) -> dict:
        with self.storage._connection(readonly=True) as connection, connection:
            connection.execute("BEGIN")
            self._guard(connection)
            return self._plan_in(connection, self._policy(connection, identifier), at)

    def read(self, operation: str, values: dict, at: str) -> dict:
        with self.storage._connection(readonly=True) as connection, connection:
            connection.execute("BEGIN"); self._guard(connection)
            if operation == PREFIX + "capabilities":
                return {"policy": POLICY, "network_access": False,
                        "automatic_delete": False, "backup_before_mutation": True,
                        "organization_scoped": True, "explicit_holds": list(HOLD_KINDS),
                        "managed_families": list(FAMILIES),
                        "archive_read_transparent": True,
                        "case_evidence_auto_protected": True}
            if operation == PREFIX + "catalog":
                return catalog()
            if operation == PREFIX + "policy.show":
                return self._policy(connection, values["identifier"])
            if operation == PREFIX + "run.show":
                return self._run(connection, values["identifier"])
            if operation == PREFIX + "hold.show":
                return self._hold(connection, values["identifier"])
            if operation == PREFIX + "policies":
                clauses, args = ["sequence>?"], [values["after"]]
                if "organization_id" in values:
                    clauses.append("organization_id=?"); args.append(values["organization_id"])
                if "enabled" in values:
                    clauses.append("enabled=?"); args.append(int(values["enabled"]))
                ids = connection.execute(
                    "SELECT id FROM retention_policies WHERE " + " AND ".join(clauses)
                    + " ORDER BY sequence LIMIT ?", (*args, values["limit"]),
                ).fetchall()
                total = connection.execute(
                    "SELECT COUNT(*) FROM retention_policies WHERE "
                    + " AND ".join(clauses[1:] or ["1=1"]), tuple(args[1:]),
                ).fetchone()[0]
                items = [self._policy(connection, row[0]) for row in ids]
            elif operation == PREFIX + "runs":
                clauses, args = ["sequence>?"], [values["after"]]
                for key in ("policy_id", "status"):
                    if key in values:
                        clauses.append(key + "=?"); args.append(values[key])
                ids = connection.execute(
                    "SELECT id FROM retention_runs WHERE " + " AND ".join(clauses)
                    + " ORDER BY sequence LIMIT ?", (*args, values["limit"]),
                ).fetchall()
                total = connection.execute(
                    "SELECT COUNT(*) FROM retention_runs WHERE "
                    + " AND ".join(clauses[1:] or ["1=1"]), tuple(args[1:]),
                ).fetchone()[0]
                items = [self._run(connection, row[0], details=False) for row in ids]
            elif operation == PREFIX + "holds":
                clauses, args = ["sequence>?"], [values["after"]]
                for key in ("organization_id", "family"):
                    if key in values:
                        clauses.append(key + "=?"); args.append(values[key])
                if "active" in values:
                    clauses.append("active=?"); args.append(int(values["active"]))
                ids = connection.execute(
                    "SELECT id FROM retention_holds WHERE " + " AND ".join(clauses)
                    + " ORDER BY sequence LIMIT ?", (*args, values["limit"]),
                ).fetchall()
                total = connection.execute(
                    "SELECT COUNT(*) FROM retention_holds WHERE "
                    + " AND ".join(clauses[1:] or ["1=1"]), tuple(args[1:]),
                ).fetchone()[0]
                items = [self._hold(connection, row[0]) for row in ids]
            else:
                events, _ = self._audit(connection)
                matching = [event for event in events
                            if ("organization_id" not in values
                                or event["organization_id"] == values["organization_id"])
                            and ("resource_kind" not in values
                                 or event["resource_kind"] == values["resource_kind"])]
                total = len(matching)
                items = [event for event in matching
                         if event["sequence"] > values["after"]][:values["limit"]]
            return {"items": items, "total_count": total,
                    "next_after": items[-1]["sequence"] if len(items) == values["limit"] else None}

    def _policy_mutation(self, connection, operation: str, values: dict, at: str) -> dict:
        replay = self._mutation(connection, operation, values)
        if replay is not None:
            return {**replay, "replayed": True}
        self._ensure_room(connection, "policy_events")
        if operation == PREFIX + "policy.add":
            self._ensure_room(connection, "policies")
            organization = self._organization(connection, values["organization_id"], active=True)
            definition = policy_definition({key: values[key] for key in (
                "name", "organization_id", "families", "archive_after_days", "batch_limit",
                "purpose", "retention_basis",
            )})
            if connection.execute(
                "SELECT 1 FROM retention_policies WHERE organization_id=? AND name_key=?",
                (organization["id"], folded(definition["name"])),
            ).fetchone():
                raise RetentionError("already_exists", "Bu kuruluşta aynı adlı saklama politikası var.")
            identifier, event_id, revision, action = str(uuid4()), str(uuid4()), 1, "added"
            created = at
        else:
            current = self._policy(connection, values["identifier"])
            if current["revision"] != values["expected_revision"]:
                raise RetentionError("revision_conflict", "Saklama politikası değişti; yeniden okuyun.")
            merged = dict(current["definition"]); merged.pop("policy", None)
            for key in ("name", "families", "archive_after_days", "batch_limit", "purpose", "retention_basis"):
                if key in values:
                    merged[key] = values[key]
            definition = policy_definition(merged)
            identifier, event_id, revision = current["id"], str(uuid4()), current["revision"] + 1
            enabled = False if operation == PREFIX + "policy.disable" else values.get("enabled", current["enabled"])
            action = "disabled" if not enabled else "reactivated" if not current["enabled"] else "updated"
            created = current["created_at"]
        enabled = True if operation == PREFIX + "policy.add" else action != "disabled"
        raw, checksum = canonical(definition), digest(definition)
        if operation == PREFIX + "policy.add":
            connection.execute(
                "INSERT INTO retention_policies (id,organization_id,name_key,revision,enabled,"
                "definition_json,definition_sha256,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (identifier, definition["organization_id"], folded(definition["name"]), revision,
                 int(enabled), raw, checksum, created, at),
            )
        else:
            connection.execute(
                "UPDATE retention_policies SET name_key=?,revision=?,enabled=?,definition_json=?,"
                "definition_sha256=?,updated_at=? WHERE id=?",
                (folded(definition["name"]), revision, int(enabled), raw, checksum, at, identifier),
            )
        connection.execute(
            "INSERT INTO retention_policy_events (id,policy_id,revision,action,definition_json,"
            "definition_sha256,reason,actor,recorded_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (event_id, identifier, revision, action, raw, checksum, values["reason"], values["actor"], at),
        )
        result = self._policy(connection, identifier)
        self._append_audit(
            connection, organization_id=definition["organization_id"],
            action="policy_" + action, resource_kind="retention_policy",
            resource_id=identifier, actor=values["actor"], reason=values["reason"],
            details={"revision": revision, "definition_sha256": checksum, "enabled": enabled}, at=at,
        )
        self._store_mutation(connection, operation, values, result, at)
        return result

    def _hold_mutation(self, connection, operation: str, values: dict, at: str) -> dict:
        replay = self._mutation(connection, operation, values)
        if replay is not None:
            return {**replay, "replayed": True}
        self._ensure_room(connection, "hold_events")
        if operation == PREFIX + "hold.add":
            organization = self._organization(connection, values["organization_id"], active=True)
            if values["kind"] == "case" and "case_id" not in values:
                raise RetentionError("validation_error", "Case koruması için case_id zorunludur.")
            if "case_id" in values and connection.execute(
                "SELECT 1 FROM cases WHERE id=?", (values["case_id"],),
            ).fetchone() is None:
                raise RetentionError("not_found", "Koruma vakası bulunamadı.")
            record_id = values.get("record_id")
            if record_id is not None:
                owner = self._record_owner(connection, values["family"], record_id)
                if owner != organization["id"]:
                    raise RetentionError("not_found", "Korunacak kayıt bu kuruluşta bulunamadı.")
            scope = record_id or "*"
            self._ensure_room(connection, "holds")
            identifier, revision, action = str(uuid4()), 1, "added"
            connection.execute(
                "INSERT INTO retention_holds (id,organization_id,family,scope_key,record_id,"
                "case_id,kind,revision,active,reason,actor,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,1,?,?,?,?)",
                (identifier, organization["id"], values["family"], scope, record_id,
                 values.get("case_id"), values["kind"], revision, values["reason"],
                 values["actor"], at, at),
            )
        else:
            current = self._hold(connection, values["identifier"])
            if current["revision"] != values["expected_revision"]:
                raise RetentionError("revision_conflict", "Saklama koruması değişti; yeniden okuyun.")
            if not current["active"]:
                raise RetentionError("inactive", "Saklama koruması zaten kaldırılmış.")
            identifier, revision, action = current["id"], current["revision"] + 1, "released"
            organization = current["organization"]
            connection.execute(
                "UPDATE retention_holds SET revision=?,active=0,reason=?,actor=?,updated_at=? WHERE id=?",
                (revision, values["reason"], values["actor"], at, identifier),
            )
        event_id = str(uuid4())
        connection.execute(
            "INSERT INTO retention_hold_events (id,hold_id,revision,action,reason,actor,recorded_at)"
            " VALUES (?,?,?,?,?,?,?)", (event_id, identifier, revision, action,
            values["reason"], values["actor"], at),
        )
        result = self._hold(connection, identifier)
        self._append_audit(
            connection, organization_id=result["organization"]["id"],
            action="hold_" + action, resource_kind="retention_hold", resource_id=identifier,
            actor=values["actor"], reason=values["reason"],
            details={"revision": revision, "family": result["family"],
                     "scope_key": result["scope_key"], "kind": result["kind"],
                     "case_id": result["case_id"]}, at=at,
        )
        self._store_mutation(connection, operation, values, result, at)
        return result

    def mutate(self, operation: str, values: dict, at: str) -> dict:
        with self.storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE"); self._guard(connection)
                if operation.startswith(PREFIX + "policy."):
                    result = self._policy_mutation(connection, operation, values, at)
                elif operation.startswith(PREFIX + "hold."):
                    result = self._hold_mutation(connection, operation, values, at)
                elif operation == PREFIX + "recover":
                    replay = self._mutation(connection, operation, values)
                    if replay is not None:
                        connection.rollback(); return {**replay, "replayed": True}
                    policy = self._policy(connection, values["identifier"])
                    rows = connection.execute(
                        "SELECT id FROM retention_runs WHERE policy_id=? AND status='running' ORDER BY sequence",
                        (policy["id"],),
                    ).fetchall()
                    for row in rows:
                        connection.execute(
                            "UPDATE retention_runs SET status='interrupted',error_code='interrupted',"
                            "error_message=?,finished_at=? WHERE id=? AND status='running'",
                            (values["reason"], at, row[0]),
                        )
                    result = {"policy_id": policy["id"], "recovered_count": len(rows),
                              "run_ids": [row[0] for row in rows]}
                    self._append_audit(
                        connection, organization_id=policy["organization"]["id"],
                        action="runs_recovered", resource_kind="retention_policy",
                        resource_id=policy["id"], actor=values["actor"], reason=values["reason"],
                        details=result, at=at,
                    )
                    self._store_mutation(connection, operation, values, result, at)
                else:
                    raise RetentionError("unsupported_operation", "Saklama yazma işlemi desteklenmiyor.")
                self._guard(connection); connection.commit(); return result
            except BaseException:
                connection.rollback(); raise

    def replay_run(self, values: dict) -> dict | None:
        is_archive = "expected_revision" in values
        operation = PREFIX + ("apply" if is_archive else "restore")
        stored_operation = "archive" if is_archive else "restore"
        with self.storage._connection(readonly=True) as connection, connection:
            connection.execute("BEGIN"); self._guard(connection)
            row = connection.execute(
                "SELECT id,request_sha256,operation FROM retention_runs WHERE request_key=?",
                (values["idempotency_key"],),
            ).fetchone()
            if row is None:
                return None
            if row[1] != request_sha256(operation, values) or row[2] != stored_operation:
                raise RetentionError("idempotency_conflict", "Tekrar anahtarı farklı saklama çalışmasına ait.")
            return self._run(connection, row[0])

    def reserve_archive(self, values: dict, plan: dict, at: str) -> tuple[dict, bool]:
        with self.storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE"); self._guard(connection)
                row = connection.execute(
                    "SELECT id,request_sha256,operation FROM retention_runs WHERE request_key=?",
                    (values["idempotency_key"],),
                ).fetchone()
                if row is not None:
                    if row[1] != request_sha256(PREFIX + "apply", values) or row[2] != "archive":
                        raise RetentionError("idempotency_conflict", "Tekrar anahtarı farklı saklama çalışmasına ait.")
                    result = self._run(connection, row[0]); connection.rollback(); return result, True
                policy = self._policy(connection, values["identifier"])
                current = self._plan_in(connection, policy, plan["generated_at"])
                if current["token"] != values["token"]:
                    raise RetentionError("snapshot_changed", "Saklama önizlemesi değişti; yeniden plan alın.")
                if connection.execute(
                    "SELECT 1 FROM retention_runs WHERE policy_id=? AND status='running'",
                    (policy["id"],),
                ).fetchone():
                    raise RetentionError("busy", "Bu saklama politikası için başka çalışma sürüyor.")
                self._ensure_room(connection, "runs")
                identifier = str(uuid4()); raw = canonical(current)
                connection.execute(
                    "INSERT INTO retention_runs (id,operation,policy_id,policy_event_id,target_run_id,"
                    "request_key,request_sha256,status,plan_json,plan_sha256,receipt_json,receipt_sha256,"
                    "actor,reason,error_code,error_message,started_at,finished_at) "
                    "VALUES (?,'archive',?,?,NULL,?,?,'running',?,?,NULL,NULL,?,?,NULL,NULL,?,NULL)",
                    (identifier, policy["id"], policy["event"]["id"], values["idempotency_key"],
                     request_sha256(PREFIX + "apply", values), raw, digest(current),
                     values["actor"], values["reason"], at),
                )
                self._append_audit(
                    connection, organization_id=policy["organization"]["id"],
                    action="archive_reserved", resource_kind="retention_run", resource_id=identifier,
                    actor=values["actor"], reason=values["reason"],
                    details={"policy_id": policy["id"], "plan_token": current["token"],
                             "selected_count": current["selected_count"]}, at=at,
                )
                result = self._run(connection, identifier); connection.commit(); return result, False
            except BaseException:
                connection.rollback(); raise

    def apply_archive(self, run_id: str, token: str, at: str) -> dict:
        with self.storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE"); self._guard(connection)
                run = self._run(connection, run_id)
                if run["status"] != "running" or run["operation"] != "archive":
                    raise RetentionError("run_terminal", "Saklama çalışması artık uygulanabilir değil.")
                policy = self._policy(connection, run["policy_id"])
                plan = self._plan_in(connection, policy, run["plan"]["generated_at"])
                if plan["token"] != token or run["plan"] != plan:
                    raise RetentionError("snapshot_changed", "Saklama önizlemesi değişti; işlem uygulanmadı.")
                backup = None
                items = []
                if plan["items"]:
                    destination = self.storage.path.parent / "backups" / f"{self.storage.path.stem}.pre-retention-{run_id}.db"
                    backup = self.storage.backup(destination)
                self._ensure_room(connection, "archive_items", len(plan["items"]))
                raw_total = packed_total = 0
                for planned in plan["items"]:
                    family = planned["family"]
                    if family == FAMILY:
                        record = SQLiteUnifiedMonitoringRepository._run(
                            connection, planned["record_id"],
                        )
                        row = connection.execute(
                            "SELECT snapshot_json,snapshot_sha256,report_json,report_sha256 "
                            "FROM monitoring_runs WHERE id=?", (planned["record_id"],),
                        ).fetchone()
                        if (row is None or record["status"] != "complete"
                                or row[1] != planned["snapshot_sha256"]
                                or row[3] != planned["report_sha256"]):
                            raise RetentionError(
                                "snapshot_changed", "Arşivlenecek izleme kanıtı değişti.",
                            )
                        snapshot_body, snapshot_size = (None, 0)
                        if row[0] is not None:
                            snapshot_body, snapshot_size = pack(row[0], row[1])
                        report_body, report_size = pack(row[2], row[3])
                        snapshot_sha, report_sha = row[1], row[3]
                        active_key = FAMILY + ":" + planned["record_id"]
                        material = None
                    elif family == TELEMETRY_FAMILY:
                        current = self._telemetry_payload(
                            connection, planned["record_id"], include_material=True,
                        )
                        if not isinstance(current, tuple) or current[0] != planned:
                            raise RetentionError(
                                "snapshot_changed", "Arşivlenecek telemetri kanıtı değişti.",
                            )
                        _current_plan, material = current
                        snapshot_body = material["snapshot_body"]
                        report_body = material["report_body"]
                        snapshot_size = planned["snapshot_raw_size"]
                        report_size = planned["report_raw_size"]
                        snapshot_sha = planned["snapshot_sha256"]
                        report_sha = planned["report_sha256"]
                        active_key = (
                            TELEMETRY_FAMILY + ":" + planned["record_id"] + ":"
                            + str(planned["generation_revision"])
                        )
                    else:
                        raise StorageError("Arşiv planında bilinmeyen veri ailesi var.")
                    item_id = str(uuid4())
                    connection.execute(
                        "INSERT INTO retention_archive_items (id,archive_run_id,organization_id,family,"
                        "record_id,active_key,snapshot_sha256,report_sha256,snapshot_raw_size,"
                        "report_raw_size,snapshot_body,report_body,active,created_at,restored_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,NULL)",
                        (item_id, run_id, policy["organization"]["id"], family,
                         planned["record_id"], active_key, snapshot_sha, report_sha, snapshot_size,
                         report_size, snapshot_body, report_body, at),
                    )
                    if family == FAMILY:
                        snapshot_marker = (marker(item_id, "snapshot", snapshot_sha)
                                           if snapshot_body is not None else None)
                        connection.execute(
                            "UPDATE monitoring_runs SET snapshot_json=?,report_json=? WHERE id=?",
                            (snapshot_marker, marker(item_id, "report", report_sha),
                             planned["record_id"]),
                        )
                        SQLiteUnifiedMonitoringRepository._run(connection, planned["record_id"])
                    else:
                        if planned["current_body_archived"]:
                            current_body = connection.execute(
                                "SELECT body_json FROM telemetry_records WHERE id=?",
                                (planned["record_id"],),
                            ).fetchone()
                            if current_body is None or parse_marker(current_body[0]) is not None:
                                raise RetentionError(
                                    "snapshot_changed", "Telemetri güncel gövdesi değişti.",
                                )
                            connection.execute(
                                "UPDATE telemetry_records SET body_json=? WHERE id=?",
                                (marker(item_id, "snapshot", snapshot_sha), planned["record_id"]),
                            )
                        for version in material["versions"]:
                            encoded = canonical(version["body"])
                            cursor = connection.execute(
                                "UPDATE telemetry_record_versions SET body_json=? "
                                "WHERE id=? AND record_id=? AND revision=? AND body_sha256=? "
                                "AND body_json=?",
                                (marker(item_id, f"version.{version['revision']}",
                                        version["body_sha256"]), version["id"],
                                 planned["record_id"], version["revision"],
                                 version["body_sha256"], encoded),
                            )
                            if cursor.rowcount != 1:
                                raise RetentionError(
                                    "snapshot_changed", "Telemetri sürüm gövdesi değişti.",
                                )
                        read_telemetry_record_in(connection, planned["record_id"])
                    raw_total += snapshot_size + report_size
                    packed = len(report_body) + (len(snapshot_body) if snapshot_body else 0)
                    packed_total += packed
                    items.append({"id": item_id, "family": family,
                                  "record_id": planned["record_id"],
                                  "snapshot_sha256": snapshot_sha,
                                  "report_sha256": report_sha,
                                  "original_bytes": snapshot_size + report_size,
                                  "compressed_bytes": packed})
                receipt = {"policy": POLICY, "operation": "archive", "run_id": run_id,
                           "policy_id": policy["id"], "plan_token": token,
                           "changed_count": len(items), "items": items,
                           "original_body_bytes": raw_total, "compressed_body_bytes": packed_total,
                           "backup_name": backup.name if backup else None,
                           "logical_record_delete": False, "completed_at": _time(at)}
                raw = canonical(receipt)
                connection.execute(
                    "UPDATE retention_runs SET status='complete',receipt_json=?,receipt_sha256=?,"
                    "finished_at=? WHERE id=? AND status='running'",
                    (raw, digest(receipt), at, run_id),
                )
                self._append_audit(
                    connection, organization_id=policy["organization"]["id"],
                    action="archive_completed", resource_kind="retention_run", resource_id=run_id,
                    actor=run["actor"], reason=run["reason"],
                    details={"changed_count": len(items), "original_body_bytes": raw_total,
                             "compressed_body_bytes": packed_total,
                             "backup_name": receipt["backup_name"]}, at=at,
                )
                self._guard(connection); result = self._run(connection, run_id)
                connection.commit(); return result
            except BaseException:
                connection.rollback(); raise

    def reserve_restore(self, values: dict, at: str) -> tuple[dict, bool]:
        with self.storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE"); self._guard(connection)
                row = connection.execute(
                    "SELECT id,request_sha256,operation FROM retention_runs WHERE request_key=?",
                    (values["idempotency_key"],),
                ).fetchone()
                if row is not None:
                    if row[1] != request_sha256(PREFIX + "restore", values) or row[2] != "restore":
                        raise RetentionError("idempotency_conflict", "Tekrar anahtarı farklı geri alma çalışmasına ait.")
                    result = self._run(connection, row[0]); connection.rollback(); return result, True
                target = self._run(connection, values["identifier"])
                if target["operation"] != "archive" or target["status"] != "complete":
                    raise RetentionError("not_found", "Geri alınabilir tamamlanmış arşiv çalışması bulunamadı.")
                policy = self._policy(connection, target["policy_id"])
                active = connection.execute(
                    "SELECT COUNT(*),COALESCE(SUM(snapshot_raw_size+report_raw_size),0) "
                    "FROM retention_archive_items WHERE archive_run_id=? AND active=1",
                    (target["id"],),
                ).fetchone()
                if active[0] == 0:
                    raise RetentionError(
                        "not_found", "Bu arşiv çalışmasında geri alınabilir etkin gövde bulunamadı."
                    )
                plan = {"policy": POLICY, "operation": "restore", "target_run_id": target["id"],
                        "policy_id": policy["id"], "organization": policy["organization"],
                        "selected_count": active[0], "original_body_bytes": active[1],
                        "generated_at": _time(at)}
                plan["token"] = digest({"database": str(self._path(connection)), "plan": plan})
                self._ensure_room(connection, "runs")
                identifier = str(uuid4()); raw = canonical(plan)
                connection.execute(
                    "INSERT INTO retention_runs (id,operation,policy_id,policy_event_id,target_run_id,"
                    "request_key,request_sha256,status,plan_json,plan_sha256,receipt_json,receipt_sha256,"
                    "actor,reason,error_code,error_message,started_at,finished_at) "
                    "VALUES (?,'restore',?,?,?,?,?,'running',?,?,NULL,NULL,?,?,NULL,NULL,?,NULL)",
                    (identifier, policy["id"], policy["event"]["id"], target["id"],
                     values["idempotency_key"], request_sha256(PREFIX + "restore", values),
                     raw, digest(plan), values["actor"], values["reason"], at),
                )
                self._append_audit(
                    connection, organization_id=policy["organization"]["id"],
                    action="restore_reserved", resource_kind="retention_run", resource_id=identifier,
                    actor=values["actor"], reason=values["reason"],
                    details={"target_run_id": target["id"], "selected_count": active[0]}, at=at,
                )
                result = self._run(connection, identifier); connection.commit(); return result, False
            except BaseException:
                connection.rollback(); raise

    def apply_restore(self, run_id: str, at: str) -> dict:
        with self.storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE"); self._guard(connection)
                run = self._run(connection, run_id)
                if run["operation"] != "restore" or run["status"] != "running":
                    raise RetentionError("run_terminal", "Geri alma çalışması artık uygulanabilir değil.")
                policy = self._policy(connection, run["policy_id"])
                rows = connection.execute(
                    "SELECT id,family,record_id,active_key,snapshot_sha256,report_sha256,snapshot_raw_size,"
                    "report_raw_size,snapshot_body,report_body FROM retention_archive_items "
                    "WHERE archive_run_id=? AND active=1 ORDER BY sequence", (run["target_run_id"],),
                ).fetchall()
                backup = None
                if rows:
                    destination = self.storage.path.parent / "backups" / f"{self.storage.path.stem}.pre-retention-{run_id}.db"
                    backup = self.storage.backup(destination)
                restored = []
                for row in rows:
                    (item_id, family, record_id, active_key, snapshot_sha, report_sha,
                     snapshot_size, report_size, snapshot_body, report_body) = row
                    if family == FAMILY:
                        if active_key != FAMILY + ":" + record_id:
                            raise StorageError("Saklama arşiv kapsamı bozuk.")
                        current = connection.execute(
                            "SELECT snapshot_json,report_json FROM monitoring_runs WHERE id=?",
                            (record_id,),
                        ).fetchone()
                        expected_snapshot = (marker(item_id, "snapshot", snapshot_sha)
                                             if snapshot_size else None)
                        if current != (expected_snapshot, marker(item_id, "report", report_sha)):
                            raise StorageError("Saklama arşiv işaretçisi değişmiş.")
                        snapshot_json = (unpack(snapshot_body, snapshot_size, snapshot_sha)
                                         if snapshot_size else None)
                        report_json = unpack(report_body, report_size, report_sha)
                        connection.execute(
                            "UPDATE monitoring_runs SET snapshot_json=?,report_json=? WHERE id=?",
                            (snapshot_json, report_json, record_id),
                        )
                    elif family == TELEMETRY_FAMILY:
                        if (not isinstance(active_key, str)
                                or not active_key.startswith(TELEMETRY_FAMILY + ":" + record_id + ":")):
                            raise StorageError("Telemetri arşiv kapsamı bozuk.")
                        bundle = _json(unpack(report_body, report_size, report_sha), report_sha)
                        if (not isinstance(bundle, dict)
                                or bundle.get("policy") != TELEMETRY_BUNDLE
                                or bundle.get("record_id") != record_id
                                or not isinstance(bundle.get("versions"), list)):
                            raise StorageError("Telemetri arşiv paketi bozuk.")
                        current = connection.execute(
                            "SELECT body_json,body_sha256 FROM telemetry_records WHERE id=?",
                            (record_id,),
                        ).fetchone()
                        if current is None:
                            raise StorageError("Telemetri arşiv üst kaydı bulunamadı.")
                        if snapshot_size:
                            expected = marker(item_id, "snapshot", snapshot_sha)
                            if current[0] == expected:
                                connection.execute(
                                    "UPDATE telemetry_records SET body_json=? WHERE id=?",
                                    (unpack(snapshot_body, snapshot_size, snapshot_sha), record_id),
                                )
                            else:
                                parsed = parse_marker(current[0])
                                if parsed is not None and parsed[0] == item_id:
                                    raise StorageError("Telemetri güncel arşiv işaretçisi değişmiş.")
                        for version in bundle["versions"]:
                            if (not isinstance(version, dict)
                                    or set(version) != {"id", "run_id", "revision", "action",
                                                           "body", "body_sha256", "recorded_at"}
                                    or not isinstance(version["body"], dict)
                                    or digest(version["body"]) != version["body_sha256"]):
                                raise StorageError("Telemetri sürüm arşivi bozuk.")
                            stored = connection.execute(
                                "SELECT run_id,revision,action,body_json,body_sha256,recorded_at "
                                "FROM telemetry_record_versions WHERE id=? AND record_id=?",
                                (version["id"], record_id),
                            ).fetchone()
                            expected = marker(
                                item_id, f"version.{version['revision']}", version["body_sha256"],
                            )
                            if stored != (
                                version["run_id"], version["revision"], version["action"],
                                expected, version["body_sha256"], version["recorded_at"],
                            ):
                                raise StorageError("Telemetri sürüm arşiv işaretçisi değişmiş.")
                            connection.execute(
                                "UPDATE telemetry_record_versions SET body_json=? WHERE id=?",
                                (canonical(version["body"]), version["id"]),
                            )
                    else:
                        raise StorageError("Saklama arşivinde bilinmeyen veri ailesi var.")
                    connection.execute(
                        "UPDATE retention_archive_items SET active=0,active_key=NULL,snapshot_body=NULL,"
                        "report_body=NULL,restored_at=? WHERE id=? AND active=1", (at, item_id),
                    )
                    if family == FAMILY:
                        SQLiteUnifiedMonitoringRepository._run(connection, record_id)
                    else:
                        read_telemetry_record_in(connection, record_id)
                    restored.append({"archive_item_id": item_id, "family": family,
                                     "record_id": record_id})
                receipt = {"policy": POLICY, "operation": "restore", "run_id": run_id,
                           "target_run_id": run["target_run_id"], "changed_count": len(restored),
                           "items": restored, "backup_name": backup.name if backup else None,
                           "completed_at": _time(at)}
                raw = canonical(receipt)
                connection.execute(
                    "UPDATE retention_runs SET status='complete',receipt_json=?,receipt_sha256=?,"
                    "finished_at=? WHERE id=? AND status='running'",
                    (raw, digest(receipt), at, run_id),
                )
                self._append_audit(
                    connection, organization_id=policy["organization"]["id"],
                    action="restore_completed", resource_kind="retention_run", resource_id=run_id,
                    actor=run["actor"], reason=run["reason"],
                    details={"target_run_id": run["target_run_id"],
                             "changed_count": len(restored), "backup_name": receipt["backup_name"]}, at=at,
                )
                self._guard(connection); result = self._run(connection, run_id)
                connection.commit(); return result
            except BaseException:
                connection.rollback(); raise

    def fail(self, run_id: str, code: str, message: str, at: str) -> None:
        with self.storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE"); self._guard(connection)
                run = self._run(connection, run_id)
                if run["status"] != "running":
                    connection.rollback(); return
                policy = self._policy(connection, run["policy_id"])
                connection.execute(
                    "UPDATE retention_runs SET status='failed',error_code=?,error_message=?,finished_at=? "
                    "WHERE id=? AND status='running'", (str(code)[:80] or "retention_failed",
                    str(message)[:1000] or "Saklama işlemi tamamlanamadı.", at, run_id),
                )
                self._append_audit(
                    connection, organization_id=policy["organization"]["id"],
                    action="run_failed", resource_kind="retention_run", resource_id=run_id,
                    actor=run["actor"], reason=run["reason"],
                    details={"error_code": str(code)[:80]}, at=at,
                )
                connection.commit()
            except BaseException:
                connection.rollback(); raise

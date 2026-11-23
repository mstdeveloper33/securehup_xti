"""Durable P07 policies, frozen local-search evidence and reviewed alerts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_notification_sequence import next_notification_sequence
from xti.adapters.retention_payloads import archived_value
from xti.domain.assets import ValidationError
from xti.domain.content_monitoring import canonical, digest, text
from xti.domain.unified_monitoring import (
    CHANGE_KINDS, MAX_RESPONSE_BYTES, MonitoringError, POLICY, PREFIX, PRIORITIES,
    REVIEW_DECISIONS, PROFILE_FIELDS, analyse, change_page, folded, policy_definition, public_match,
    subject, validate_snapshot,
)
from xti.domain.mentions import mention_uuid


P = "monitoring_"
MAX_POLICIES = 1000
MAX_EVENTS = 10_000
MAX_RUNS = 20_000
MAX_ALERTS = 20_000
MAX_REVIEWS = 50_000
MAX_MUTATIONS = 50_000
MAX_STORED_BYTES = 128 * 1024 * 1024


def _time(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("invalid time")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc).isoformat()


def _sha(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("invalid sha256")
    return value


def _json(value: str, checksum: str, *, maximum: int = 16 * 1024 * 1024):
    if not isinstance(value, str) or len(value.encode("ascii")) > maximum:
        raise ValueError("json size")
    parsed = json.loads(value)
    if canonical(parsed) != value or digest(parsed) != _sha(checksum):
        raise ValueError("json digest")
    return parsed


def _page(values: dict) -> tuple[int, int]:
    return values.get("after", 0), values.get("limit", 20)


class SQLiteUnifiedMonitoringRepository:
    def __init__(self, path: Path) -> None:
        self.storage = SQLiteAssetRepository(path)

    @staticmethod
    def _guard(connection) -> None:
        limits = {
            "policies": MAX_POLICIES, "policy_events": MAX_EVENTS, "runs": MAX_RUNS,
            "alerts": MAX_ALERTS, "alert_reviews": MAX_REVIEWS, "mutations": MAX_MUTATIONS,
        }
        for table, maximum in limits.items():
            count = connection.execute(f"SELECT COUNT(*) FROM {P + table}").fetchone()[0]
            if type(count) is not int or not 0 <= count <= maximum:
                raise StorageError("Birleşik izleme kayıtları güvenli kapasite sınırını aşıyor.")
        size = connection.execute(
            f"SELECT COALESCE(SUM(LENGTH(CAST(snapshot_json AS BLOB))),0)+"
            f"COALESCE(SUM(LENGTH(CAST(report_json AS BLOB))),0) FROM {P}runs"
        ).fetchone()[0]
        if type(size) is not int or not 0 <= size <= MAX_STORED_BYTES:
            raise StorageError("Birleşik izleme kanıt geçmişi 128 MiB güvenli sınırını aşıyor.")

    @staticmethod
    def _ensure_room(connection, **increments: int) -> None:
        limits = {
            "policies": MAX_POLICIES, "policy_events": MAX_EVENTS, "runs": MAX_RUNS,
            "alerts": MAX_ALERTS, "alert_reviews": MAX_REVIEWS, "mutations": MAX_MUTATIONS,
        }
        if set(increments) - set(limits) or any(type(value) is not int or value < 0 for value in increments.values()):
            raise StorageError("Birleşik izleme kapasite isteği geçersiz.")
        for table, increment in increments.items():
            count = connection.execute(f"SELECT COUNT(*) FROM {P + table}").fetchone()[0]
            if type(count) is not int or count + increment > limits[table]:
                raise MonitoringError("capacity", "Birleşik izleme kalıcı kayıt kapasitesi doldu.")

    @staticmethod
    def _organization(connection, identifier: str) -> dict:
        row = connection.execute(
            "SELECT id,display_name,active FROM organizations WHERE id=?", (identifier,),
        ).fetchone()
        if row is None:
            raise MonitoringError("not_found", "Birleşik izleme kuruluşu bulunamadı.")
        return {"id": row[0], "display_name": row[1], "active": bool(row[2])}

    @classmethod
    def _event(cls, connection, identifier: str) -> dict:
        row = connection.execute(
            f"SELECT sequence,id,policy_id,revision,action,definition_json,definition_sha256,"
            f"reason,actor,recorded_at FROM {P}policy_events WHERE id=?", (identifier,),
        ).fetchone()
        if row is None:
            raise StorageError("Birleşik izleme politika olayı bulunamadı.")
        try:
            definition = policy_definition(_json(row[5], row[6], maximum=1_000_000))
            if (type(row[0]) is not int or row[0] < 1 or type(row[3]) is not int or row[3] < 1
                    or row[4] not in ("added", "updated", "reactivated", "disabled")
                    or text(row[7], 2000, 2) != row[7] or text(row[8], 200, 2) != row[8]):
                raise ValueError()
            return {"sequence": row[0], "id": row[1], "policy_id": row[2],
                    "revision": row[3], "action": row[4], "definition": definition,
                    "definition_sha256": row[6], "reason": row[7], "actor": row[8],
                    "recorded_at": _time(row[9])}
        except (TypeError, ValueError, KeyError, ValidationError, json.JSONDecodeError) as error:
            raise StorageError("Birleşik izleme politika olayı bozuk.") from error

    @classmethod
    def _policy(cls, connection, identifier: str) -> dict:
        row = connection.execute(
            f"SELECT sequence,id,organization_id,name_key,revision,enabled,definition_json,"
            f"definition_sha256,created_at,updated_at FROM {P}policies WHERE id=?", (identifier,),
        ).fetchone()
        if row is None:
            raise MonitoringError("not_found", "Birleşik izleme politikası bulunamadı.")
        try:
            definition = policy_definition(_json(row[6], row[7], maximum=1_000_000))
            organization = cls._organization(connection, row[2])
            if (definition["organization_id"] != row[2]
                    or row[3] != folded(definition["name"])
                    or type(row[4]) is not int or row[4] < 1
                    or type(row[5]) is not int or row[5] not in (0, 1)):
                raise ValueError()
            event_row = connection.execute(
                f"SELECT id FROM {P}policy_events WHERE policy_id=? AND revision=?",
                (row[1], row[4]),
            ).fetchone()
            if event_row is None:
                raise ValueError()
            event = cls._event(connection, event_row[0])
            if (event["definition"] != definition or event["recorded_at"] != _time(row[9])
                    or (event["action"] == "disabled") == bool(row[5])):
                raise ValueError()
        except (TypeError, ValueError, KeyError, ValidationError, json.JSONDecodeError) as error:
            raise StorageError("Birleşik izleme politika kaydı bozuk.") from error
        return {"sequence": row[0], "id": row[1], "organization": organization,
                "revision": row[4], "enabled": bool(row[5]), "definition": definition,
                "definition_sha256": row[7], "created_at": _time(row[8]),
                "updated_at": _time(row[9]), "event": event}

    @classmethod
    def _latest_complete(cls, connection, policy_id: str, event_id: str | None = None):
        clause, args = "policy_id=? AND status='complete'", [policy_id]
        if event_id is not None:
            clause += " AND policy_event_id=?"; args.append(event_id)
        row = connection.execute(
            f"SELECT sequence,id,policy_id,policy_event_id,snapshot_sha256,report_sha256,"
            f"started_at,finished_at FROM {P}runs WHERE {clause} ORDER BY sequence DESC LIMIT 1", args,
        ).fetchone()
        if row is None:
            return None
        try:
            if (type(row[0]) is not int or row[0] < 1 or row[2] != policy_id
                    or (event_id is not None and row[3] != event_id)):
                raise ValueError()
            _sha(row[4]); _sha(row[5]); _time(row[6]); finished_at = _time(row[7])
            return {"sequence": row[0], "id": row[1], "policy_id": row[2],
                    "policy_event_id": row[3], "snapshot_sha256": row[4],
                    "report_sha256": row[5], "started_at": _time(row[6]),
                    "finished_at": finished_at}
        except (TypeError, ValueError) as error:
            raise StorageError("Birleşik izleme son çalışma başlığı bozuk.") from error

    @classmethod
    def _due(cls, policy: dict, last: dict | None, at: str) -> dict:
        if last is None:
            due_at = policy["updated_at"]
        else:
            due_at = (datetime.fromisoformat(last["finished_at"]) + timedelta(
                seconds=policy["definition"]["interval_seconds"]
            )).astimezone(timezone.utc).isoformat()
        return {"due": policy["enabled"] and datetime.fromisoformat(at) >= datetime.fromisoformat(due_at),
                "due_at": due_at, "last_complete_run_id": last["id"] if last else None}

    @classmethod
    def _run(cls, connection, identifier: str, *, include_payload: bool = True) -> dict:
        row = connection.execute(
            f"SELECT sequence,id,policy_id,policy_event_id,request_key,request_sha256,"
            f"previous_run_id,status,snapshot_json,snapshot_sha256,report_json,report_sha256,"
            f"error_code,error_message,started_at,finished_at FROM {P}runs WHERE id=?",
            (identifier,),
        ).fetchone()
        if row is None:
            raise MonitoringError("not_found", "Birleşik izleme çalışması bulunamadı.")
        try:
            status = row[7]
            if status not in ("running", "complete", "failed", "interrupted"):
                raise ValueError()
            _sha(row[5])
            if not isinstance(row[4], str) or not 1 <= len(row[4]) <= 128:
                raise ValueError()
            event = cls._event(connection, row[3])
            if event["policy_id"] != row[2]:
                raise ValueError()
            expected_previous = connection.execute(
                f"SELECT id FROM {P}runs WHERE policy_id=? AND policy_event_id=? "
                f"AND status='complete' AND sequence<? ORDER BY sequence DESC LIMIT 1",
                (row[2], row[3], row[0]),
            ).fetchone()
            if (expected_previous[0] if expected_previous else None) != row[6]:
                raise ValueError()
            previous_snapshot = None
            if row[6] is not None:
                previous = connection.execute(
                    f"SELECT sequence,id,policy_id,policy_event_id,status,snapshot_json,snapshot_sha256,"
                    f"previous_run_id "
                    f"FROM {P}runs WHERE id=?", (row[6],),
                ).fetchone()
                if (previous is None or previous[2] != row[2] or previous[3] != row[3]
                        or previous[4] != "complete" or previous[0] >= row[0]):
                    raise ValueError()
                if status == "complete":
                    previous_snapshot = cls._resolved_snapshot(
                        connection, run_id=previous[1], sequence=previous[0],
                        policy_id=previous[2], event_id=previous[3],
                        previous_run_id=previous[7], snapshot_json=previous[5],
                        snapshot_sha256=previous[6],
                    )
                    validate_snapshot(previous_snapshot, event["definition"])
            snapshot = report = None
            if status == "complete":
                if None in (row[9], row[10], row[11], row[15]) or row[12] is not None or row[13] is not None:
                    raise ValueError()
                snapshot = cls._resolved_snapshot(
                    connection, run_id=row[1], sequence=row[0], policy_id=row[2], event_id=row[3],
                    previous_run_id=row[6], snapshot_json=row[8], snapshot_sha256=row[9],
                )
                report_json = archived_value(
                    connection, run_id=row[1], field="report", value=row[10], checksum=row[11],
                )
                report = _json(report_json, row[11], maximum=MAX_RESPONSE_BYTES)
                validate_snapshot(snapshot, event["definition"])
                if (snapshot["policy_id"] != row[2]
                        or snapshot["policy_revision"] != event["revision"]
                        or report != analyse(snapshot, previous_snapshot, event["definition"], row[14])):
                    raise ValueError()
            elif row[8] is not None or row[9] is not None or row[10] is not None or row[11] is not None:
                raise ValueError()
            if status == "running" and (row[12] is not None or row[13] is not None or row[15] is not None):
                raise ValueError()
            if status in ("failed", "interrupted") and (not row[12] or not row[13] or row[15] is None):
                raise ValueError()
            result = {"sequence": row[0], "id": row[1], "policy_id": row[2],
                "policy_event_id": row[3], "previous_run_id": row[6], "status": status,
                "snapshot_sha256": row[9], "report_sha256": row[11],
                "error_code": row[12], "error_message": row[13],
                "started_at": _time(row[14]), "finished_at": _time(row[15]) if row[15] else None}
            if include_payload:
                result.update({"snapshot": snapshot, "report": report})
            return result
        except (TypeError, ValueError, KeyError, ValidationError, json.JSONDecodeError) as error:
            raise StorageError("Birleşik izleme çalışma kaydı bozuk.") from error

    @classmethod
    def _resolved_snapshot(cls, connection, *, run_id: str, sequence: int,
                           policy_id: str, event_id: str,
                           previous_run_id: str | None, snapshot_json: str | None,
                           snapshot_sha256: str) -> dict:
        checksum = _sha(snapshot_sha256)
        if snapshot_json is not None:
            value = archived_value(
                connection, run_id=run_id, field="snapshot", value=snapshot_json,
                checksum=checksum,
            )
            return _json(value, checksum)
        if previous_run_id is None:
            raise ValueError("missing snapshot origin")
        previous = connection.execute(
            f"SELECT sequence,policy_id,policy_event_id,status,snapshot_sha256 "
            f"FROM {P}runs WHERE id=?", (previous_run_id,),
        ).fetchone()
        if (previous is None or previous[0] >= sequence or previous[1] != policy_id
                or previous[2] != event_id or previous[3] != "complete"
                or previous[4] != checksum):
            raise ValueError("invalid snapshot reference")
        origin = connection.execute(
            f"SELECT id,snapshot_json,snapshot_sha256 FROM {P}runs WHERE policy_id=? "
            f"AND policy_event_id=? AND sequence<? AND status='complete' "
            f"AND snapshot_sha256=? AND snapshot_json IS NOT NULL "
            f"ORDER BY sequence DESC LIMIT 1",
            (policy_id, event_id, sequence, checksum),
        ).fetchone()
        if origin is None:
            raise ValueError("snapshot origin not found")
        value = archived_value(
            connection, run_id=origin[0], field="snapshot", value=origin[1],
            checksum=origin[2],
        )
        return _json(value, origin[2])

    @classmethod
    def _review(cls, connection, row) -> dict:
        if row is None:
            return None
        try:
            if (type(row[0]) is not int or row[0] < 1 or type(row[3]) is not int or row[3] < 1
                    or row[4] not in REVIEW_DECISIONS
                    or text(row[5], 2000, 2) != row[5] or text(row[6], 200, 2) != row[6]):
                raise ValueError()
            return {"sequence": row[0], "id": row[1], "alert_id": row[2],
                    "revision": row[3], "decision": row[4], "reason": row[5],
                    "actor": row[6], "recorded_at": _time(row[7])}
        except (TypeError, ValueError, ValidationError) as error:
            raise StorageError("Birleşik izleme alarm incelemesi bozuk.") from error

    @classmethod
    def _alert(cls, connection, identifier: str) -> dict:
        row = connection.execute(
            f"SELECT sequence,id,run_id,policy_id,priority,event_type,origin,change_count,"
            f"created_at,read_at FROM {P}alerts WHERE id=?", (identifier,),
        ).fetchone()
        if row is None:
            raise MonitoringError("not_found", "Birleşik izleme alarmı bulunamadı.")
        run = cls._run(connection, row[2])
        review_row = connection.execute(
            f"SELECT sequence,id,alert_id,revision,decision,reason,actor,recorded_at "
            f"FROM {P}alert_reviews WHERE alert_id=? ORDER BY revision DESC LIMIT 1",
            (row[1],),
        ).fetchone()
        if (row[4] not in PRIORITIES or row[5] != "unified_monitoring_changed" or row[6] != "new"
                or type(row[7]) is not int or row[7] < 1 or run["status"] != "complete"
                or not run["report"]["alert_required"]
                or row[7] != run["report"]["trigger_change_count"]):
            raise StorageError("Birleşik izleme alarm bağı bozuk.")
        return {"sequence": row[0], "id": row[1], "run_id": row[2],
                "policy_id": row[3], "priority": row[4], "event_type": row[5],
                "origin": row[6], "change_count": row[7], "created_at": _time(row[8]),
                "read_at": _time(row[9]) if row[9] else None,
                "review": cls._review(connection, review_row), "review_revision": review_row[3] if review_row else 0,
                "run": run}

    @staticmethod
    def _run_public(run: dict, *, include_report: bool) -> dict:
        result = {key: value for key, value in run.items() if key not in ("snapshot", "report")}
        snapshot = run.get("snapshot")
        if snapshot is not None:
            result["snapshot"] = {
                "policy": snapshot["policy"], "policy_id": snapshot["policy_id"],
                "policy_revision": snapshot["policy_revision"],
                "organization": snapshot["organization"],
                "definition_sha256": snapshot["definition_sha256"],
                "subjects": snapshot["subjects"],
                "match_count": len(snapshot["matches"]),
                "coverage_count": len(snapshot["coverage"]),
            }
        if include_report:
            result["report"] = run.get("report")
        return result

    @classmethod
    def _alert_public(cls, alert: dict, *, include_report: bool) -> dict:
        return {
            **{key: value for key, value in alert.items() if key != "run"},
            "run": cls._run_public(alert["run"], include_report=include_report),
        }

    @classmethod
    def _policy_public(cls, connection, policy: dict, at: str) -> dict:
        last = cls._latest_complete(connection, policy["id"], policy["event"]["id"])
        return {**{key: policy[key] for key in (
            "sequence", "id", "organization", "revision", "enabled", "definition",
            "definition_sha256", "created_at", "updated_at")},
            "binding_state": "active" if policy["organization"]["active"] else "organization_inactive",
            "schedule": cls._due(policy, last, at)}

    @staticmethod
    def _request_hash(operation: str, values: dict) -> str:
        return digest({"operation": operation,
                       "parameters": {key: value for key, value in values.items() if key != "idempotency_key"}})

    @classmethod
    def _mutation_replay(cls, connection, operation: str, values: dict):
        row = connection.execute(
            f"SELECT request_sha256,operation,result_json,result_sha256 FROM {P}mutations WHERE request_key=?",
            (values["idempotency_key"],),
        ).fetchone()
        if row is None:
            return None
        if row[0] != cls._request_hash(operation, values) or row[1] != operation:
            raise MonitoringError("idempotency_conflict", "Tekrar önleme anahtarı farklı bir işleme ait.")
        result = _json(row[2], row[3], maximum=MAX_RESPONSE_BYTES)
        return {**result, "replayed": True}

    @classmethod
    def _save_mutation(cls, connection, operation: str, values: dict, result: dict, at: str):
        raw = canonical(result)
        connection.execute(
            f"INSERT INTO {P}mutations (id,request_key,request_sha256,operation,result_json,"
            "result_sha256,created_at) VALUES (?,?,?,?,?,?,?)",
            (str(uuid4()), values["idempotency_key"], cls._request_hash(operation, values),
             operation, raw, digest(result), at),
        )

    def plan(self, identifier: str, at: str) -> dict:
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            self._guard(connection)
            policy = self._policy(connection, identifier)
            public = self._policy_public(connection, policy, at)
            return {**public, "collection": {"network_access": False,
                "mode": "stored_evidence_only",
                "note": "Uzak kaynakları önce kendi collector/source job akışları günceller."}}

    def read(self, operation: str, values: dict, at: str) -> dict:
        name = operation.removeprefix(PREFIX)
        if name == "capabilities":
            return {"policy": POLICY, "subjects": list(("domain", "brand", "ip", "keyword", "person", "supplier")),
                    "stored_evidence_only": True, "network_access": False,
                    "first_run": "silent_baseline", "minimum_interval_seconds": 300,
                    "automatic_threat_verdict": False, "case_evidence_type": "unified_monitoring"}
        if name == "plan":
            return self.plan(values["identifier"], at)
        with self.storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            self._guard(connection)
            if name == "policy.show":
                return self._policy_public(connection, self._policy(connection, values["identifier"]), at)
            if name == "run.show":
                return self._run_public(self._run(connection, values["identifier"]), include_report=True)
            if name in ("run.matches", "run.coverage", "run.changes"):
                run = self._run(connection, values["identifier"])
                if name == "run.changes":
                    previous = (self._run(connection, run["previous_run_id"])["snapshot"]
                                if run["previous_run_id"] else None)
                    page = change_page(run["snapshot"], previous, values["offset"], values["limit"])
                    return {"run_id": run["id"], "snapshot_sha256": run["snapshot_sha256"], **page}
                source = run["snapshot"]["matches" if name == "run.matches" else "coverage"]
                offset, limit = values["offset"], values["limit"]
                selected = source[offset:offset + limit]
                if name == "run.matches":
                    selected = [public_match(item) for item in selected]
                return {"run_id": run["id"], "snapshot_sha256": run["snapshot_sha256"],
                        "items": selected, "total_count": len(source), "offset": offset,
                        "limit": limit, "has_more": offset + len(selected) < len(source)}
            if name == "alert.show":
                return self._alert_public(
                    self._alert(connection, values["identifier"]), include_report=True,
                )
            if name == "due":
                result = []
                rows = connection.execute(
                    f"SELECT id FROM {P}policies WHERE enabled=1 ORDER BY sequence",
                ).fetchall()
                for row in rows:
                    policy = self._policy(connection, row[0])
                    public = self._policy_public(connection, policy, values["at"])
                    if public["schedule"]["due"]:
                        result.append(public)
                total = len(result)
                result = result[:values["limit"]]
                return {"at": values["at"], "items": result, "count": len(result),
                        "total_due_count": total, "truncated": total > len(result),
                        "network_access": False}
            after, limit = _page(values)
            if name == "policies":
                rows = connection.execute(
                    f"SELECT id FROM {P}policies WHERE sequence>? ORDER BY sequence LIMIT ?",
                    (after, limit + 1),
                ).fetchall()
                items = [self._policy_public(connection, self._policy(connection, row[0]), at)
                         for row in rows[:limit]]
                total = connection.execute(f"SELECT COUNT(*) FROM {P}policies").fetchone()[0]
            elif name == "runs":
                clause, args = "sequence>?", [after]
                if values.get("policy_id"):
                    clause += " AND policy_id=?"; args.append(values["policy_id"])
                rows = connection.execute(
                    f"SELECT id FROM {P}runs WHERE {clause} ORDER BY sequence LIMIT ?",
                    (*args, limit + 1),
                ).fetchall()
                items = [self._run(connection, row[0], include_payload=False) for row in rows[:limit]]
                total = connection.execute(
                    f"SELECT COUNT(*) FROM {P}runs" + (" WHERE policy_id=?" if values.get("policy_id") else ""),
                    ((values["policy_id"],) if values.get("policy_id") else ()),
                ).fetchone()[0]
            elif name == "alerts":
                filters, filter_args = [], []
                if values.get("policy_id"):
                    filters.append(f"{P}alerts.policy_id=?"); filter_args.append(values["policy_id"])
                if values.get("priority"):
                    filters.append(f"{P}alerts.priority=?"); filter_args.append(values["priority"])
                if values.get("read_state") == "read": filters.append(f"{P}alerts.read_at IS NOT NULL")
                if values.get("read_state") == "unread": filters.append(f"{P}alerts.read_at IS NULL")
                if values.get("decision"):
                    filters.append(
                        f"EXISTS (SELECT 1 FROM {P}alert_reviews review "
                        f"WHERE review.alert_id={P}alerts.id AND review.revision=(SELECT MAX(latest.revision) "
                        f"FROM {P}alert_reviews latest WHERE latest.alert_id={P}alerts.id) "
                        "AND review.decision=?)"
                    )
                    filter_args.append(values["decision"])
                clauses, args = [f"{P}alerts.sequence>?", *filters], [after, *filter_args]
                rows = connection.execute(
                    f"SELECT id FROM {P}alerts WHERE {' AND '.join(clauses)} ORDER BY sequence LIMIT ?",
                    (*args, limit + 1),
                ).fetchall()
                items = [self._alert_public(self._alert(connection, row[0]), include_report=False)
                         for row in rows[:limit]]
                where = " WHERE " + " AND ".join(filters) if filters else ""
                total = connection.execute(
                    f"SELECT COUNT(*) FROM {P}alerts{where}", filter_args,
                ).fetchone()[0]
            elif name == "reviews":
                alert = self._alert(connection, values["identifier"])
                rows = connection.execute(
                    f"SELECT sequence,id,alert_id,revision,decision,reason,actor,recorded_at "
                    f"FROM {P}alert_reviews WHERE alert_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                    (alert["id"], after, limit + 1),
                ).fetchall()
                items = [self._review(connection, row) for row in rows[:limit]]
                total = connection.execute(
                    f"SELECT COUNT(*) FROM {P}alert_reviews WHERE alert_id=?", (alert["id"],),
                ).fetchone()[0]
            elif name == "report":
                policy = self._policy_public(connection, self._policy(connection, values["policy_id"]), at)
                if values.get("run_id"):
                    run = self._run(connection, values["run_id"])
                    if run["policy_id"] != policy["id"]:
                        raise MonitoringError("scope_mismatch", "Çalışma seçili politikaya ait değil.")
                else:
                    row = connection.execute(
                        f"SELECT id FROM {P}runs WHERE policy_id=? ORDER BY sequence DESC LIMIT 1",
                        (policy["id"],),
                    ).fetchone()
                    run = self._run(connection, row[0]) if row else None
                alerts = connection.execute(
                    f"SELECT COUNT(*),COALESCE(SUM(read_at IS NULL),0) FROM {P}alerts WHERE policy_id=?",
                    (policy["id"],),
                ).fetchone()
                return {"policy": policy,
                        "latest_run": self._run_public(run, include_report=True) if run else None,
                        "alert_count": alerts[0], "unread_alert_count": alerts[1],
                        "automatic_verdict": False}
            else:
                raise ValidationError("Birleşik izleme okuma işlemi bilinmiyor.")
            more = len(rows) > limit
            return {"items": items, "total_count": total,
                    "next_after": items[-1]["sequence"] if more and items else None,
                    "limit": limit}

    def mutate(self, operation: str, values: dict, at: str) -> dict:
        name = operation.removeprefix(PREFIX)
        with self.storage._connection() as connection:
            previous_factory = connection.row_factory
            try:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN IMMEDIATE")
                self._guard(connection)
                replay = self._mutation_replay(connection, operation, values)
                if replay is not None:
                    connection.rollback(); return replay
                self._ensure_room(connection, mutations=1)
                if name == "policy.add":
                    definition = policy_definition({key: values[key] for key in PROFILE_FIELDS if key in values})
                    organization = self._organization(connection, definition["organization_id"])
                    if not organization["active"]:
                        raise MonitoringError("organization_inactive", "Etkin olmayan kuruluşa izleme politikası eklenemez.")
                    self._validate_scope(connection, definition)
                    self._ensure_room(connection, policies=1, policy_events=1)
                    identifier = str(uuid4()); raw = canonical(definition); checksum = digest(definition)
                    try:
                        cursor = connection.execute(
                            f"INSERT INTO {P}policies (id,organization_id,name_key,revision,enabled,"
                            "definition_json,definition_sha256,created_at,updated_at) VALUES (?,?,?,?,1,?,?,?,?)",
                            (identifier, definition["organization_id"], folded(definition["name"]),
                             1, raw, checksum, at, at),
                        )
                    except sqlite3.IntegrityError as error:
                        raise MonitoringError("already_exists", "Bu kuruluşta aynı adlı izleme politikası var.") from error
                    event_id = str(uuid4())
                    connection.execute(
                        f"INSERT INTO {P}policy_events (id,policy_id,revision,action,definition_json,"
                        "definition_sha256,reason,actor,recorded_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (event_id, identifier, 1, "added", raw, checksum,
                         values["reason"], values["actor"], at),
                    )
                    result = self._policy_public(connection, self._policy(connection, identifier), at)
                elif name in ("policy.update", "policy.disable"):
                    current = self._policy(connection, values["identifier"])
                    if current["revision"] != values["expected_revision"]:
                        raise MonitoringError("revision_conflict", "İzleme politikası değişti; güncel sürümü okuyun.")
                    if name == "policy.disable":
                        if not current["enabled"]:
                            result = self._policy_public(connection, current, at)
                        else:
                            result = self._replace_policy(connection, current, current["definition"], False,
                                                          "disabled", values, at)
                    else:
                        merged = dict(current["definition"])
                        for key in PROFILE_FIELDS:
                            if key in values: merged[key] = values[key]
                        definition = policy_definition(merged)
                        if definition["organization_id"] != current["definition"]["organization_id"]:
                            raise MonitoringError("scope_mismatch", "Politika başka kuruluşa taşınamaz; yeni politika oluşturun.")
                        self._validate_scope(connection, definition)
                        enabled = values.get("enabled", current["enabled"])
                        action = "reactivated" if enabled and not current["enabled"] else "updated" if enabled else "disabled"
                        if definition == current["definition"] and enabled == current["enabled"]:
                            result = self._policy_public(connection, current, at)
                        else:
                            self._ensure_room(connection, policy_events=1)
                            result = self._replace_policy(connection, current, definition, enabled, action, values, at)
                elif name == "alert.review":
                    alert = self._alert(connection, values["identifier"])
                    if alert["review_revision"] != values["expected_revision"]:
                        raise MonitoringError("revision_conflict", "Alarm incelemesi değişti; güncel sürümü okuyun.")
                    self._ensure_room(connection, alert_reviews=1)
                    revision = alert["review_revision"] + 1
                    review_id = str(uuid4())
                    cursor = connection.execute(
                        f"INSERT INTO {P}alert_reviews (id,alert_id,revision,decision,reason,actor,recorded_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (review_id, alert["id"], revision, values["decision"], values["reason"], values["actor"], at),
                    )
                    result = self._review(connection, (cursor.lastrowid, review_id, alert["id"], revision,
                                                       values["decision"], values["reason"], values["actor"], at))
                elif name == "recover":
                    policy = self._policy(connection, values["identifier"])
                    rows = connection.execute(
                        f"SELECT id FROM {P}runs WHERE policy_id=? AND status='running' ORDER BY sequence",
                        (policy["id"],),
                    ).fetchall()
                    for row in rows:
                        connection.execute(
                            f"UPDATE {P}runs SET status='interrupted',error_code='interrupted',"
                            "error_message=?,finished_at=? WHERE id=? AND status='running'",
                            (values["reason"], at, row[0]),
                        )
                    result = {"policy_id": policy["id"], "recovered_count": len(rows),
                              "run_ids": [row[0] for row in rows], "at": at}
                else:
                    raise ValidationError("Birleşik izleme yazma işlemi bilinmiyor.")
                self._save_mutation(connection, operation, values, result, at)
                connection.commit()
                return result
            except BaseException:
                connection.rollback(); raise
            finally:
                connection.row_factory = previous_factory

    @classmethod
    def _validate_scope(cls, connection, definition: dict) -> None:
        linked = {row[0] for row in connection.execute(
            "SELECT target_value FROM organization_links WHERE organization_id=? "
            "AND target_kind='domain' AND active=1", (definition["organization_id"],),
        ).fetchall()}
        missing = [item["value"] for item in definition["subjects"]
                   if item["kind"] == "domain" and item["value"] not in linked]
        if missing:
            raise MonitoringError("scope_mismatch", "Domain hedefi önce etkin kuruluşa bağlanmalı: " + ", ".join(missing))

    @classmethod
    def _replace_policy(cls, connection, current, definition, enabled, action, values, at):
        revision = current["revision"] + 1; raw = canonical(definition); checksum = digest(definition)
        try:
            connection.execute(
                f"UPDATE {P}policies SET name_key=?,revision=?,enabled=?,definition_json=?,"
                "definition_sha256=?,updated_at=? WHERE id=?",
                (folded(definition["name"]), revision, int(enabled), raw, checksum, at, current["id"]),
            )
        except sqlite3.IntegrityError as error:
            raise MonitoringError("already_exists", "Bu kuruluşta aynı adlı izleme politikası var.") from error
        connection.execute(
            f"INSERT INTO {P}policy_events (id,policy_id,revision,action,definition_json,"
            "definition_sha256,reason,actor,recorded_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), current["id"], revision, action, raw, checksum,
             values["reason"], values["actor"], at),
        )
        return cls._policy_public(connection, cls._policy(connection, current["id"]), at)

    def replay_run(self, values: dict) -> dict | None:
        with self.storage._connection(readonly=True) as connection:
            row = connection.execute(
                f"SELECT id,request_sha256 FROM {P}runs WHERE request_key=?",
                (values["idempotency_key"],),
            ).fetchone()
            if row is None: return None
            if row[1] != self._request_hash(PREFIX + "run", values):
                raise MonitoringError("idempotency_conflict", "Tekrar önleme anahtarı farklı çalışmaya ait.")
            return self._run_public(self._run(connection, row[0]), include_report=True)

    def reserve(self, values: dict, at: str) -> tuple[dict, bool]:
        with self.storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE"); self._guard(connection)
                row = connection.execute(
                    f"SELECT id,request_sha256 FROM {P}runs WHERE request_key=?",
                    (values["idempotency_key"],),
                ).fetchone()
                request_sha = self._request_hash(PREFIX + "run", values)
                if row:
                    if row[1] != request_sha:
                        raise MonitoringError("idempotency_conflict", "Tekrar önleme anahtarı farklı çalışmaya ait.")
                    result = self._run_public(
                        self._run(connection, row[0]), include_report=True,
                    ); connection.rollback(); return result, True
                policy = self._policy(connection, values["identifier"])
                if not policy["enabled"] or not policy["organization"]["active"]:
                    raise MonitoringError("inactive", "Etkin olmayan politika veya kuruluş çalıştırılamaz.")
                if policy["revision"] != values["expected_revision"]:
                    raise MonitoringError("revision_conflict", "İzleme politikası değişti; planı yeniden okuyun.")
                previous = self._latest_complete(connection, policy["id"], policy["event"]["id"])
                schedule = self._due(policy, previous, at)
                if not schedule["due"] and not values.get("force", False):
                    raise MonitoringError("not_due", "Politika henüz çalışma zamanına gelmedi; --force yalnız açık operatör kararıdır.")
                self._ensure_room(connection, runs=1)
                identifier = str(uuid4())
                connection.execute(
                    f"INSERT INTO {P}runs (id,policy_id,policy_event_id,request_key,request_sha256,"
                    "previous_run_id,status,snapshot_json,snapshot_sha256,report_json,report_sha256,"
                    "error_code,error_message,started_at,finished_at) "
                    "VALUES (?,?,?,?,?,?,'running',NULL,NULL,NULL,NULL,NULL,NULL,?,NULL)",
                    (identifier, policy["id"], policy["event"]["id"], values["idempotency_key"],
                     request_sha, previous["id"] if previous else None, at),
                )
                result = self._run(connection, identifier); connection.commit(); return result, False
            except BaseException:
                connection.rollback(); raise

    def finish(self, run_id: str, snapshot: dict, at: str) -> dict:
        with self.storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE"); self._guard(connection)
                run = self._run(connection, run_id)
                if run["status"] != "running":
                    raise MonitoringError("run_terminal", "Birleşik izleme çalışması zaten tamamlanmış.")
                event = self._event(connection, run["policy_event_id"])
                snapshot = validate_snapshot(snapshot, event["definition"])
                previous_run = self._run(connection, run["previous_run_id"]) if run["previous_run_id"] else None
                previous = previous_run["snapshot"] if previous_run else None
                report = analyse(snapshot, previous, event["definition"], run["started_at"])
                raw_snapshot, raw_report = canonical(snapshot), canonical(report)
                snapshot_checksum = digest(snapshot)
                stored_snapshot = (
                    None if previous_run is not None
                    and previous_run["snapshot_sha256"] == snapshot_checksum
                    else raw_snapshot
                )
                projected = connection.execute(
                    f"SELECT COALESCE(SUM(LENGTH(CAST(snapshot_json AS BLOB))),0)+"
                    f"COALESCE(SUM(LENGTH(CAST(report_json AS BLOB))),0) FROM {P}runs"
                ).fetchone()[0] + (len(stored_snapshot) if stored_snapshot is not None else 0) + len(raw_report)
                if projected > MAX_STORED_BYTES:
                    raise MonitoringError("capacity", "Birleşik izleme kanıt alanı 128 MiB sınırına ulaştı.")
                connection.execute(
                    f"UPDATE {P}runs SET status='complete',snapshot_json=?,snapshot_sha256=?,"
                    "report_json=?,report_sha256=?,finished_at=? WHERE id=? AND status='running'",
                    (stored_snapshot, snapshot_checksum, raw_report, digest(report), at, run_id),
                )
                alert_id = None
                if report["alert_required"]:
                    self._ensure_room(connection, alerts=1)
                    alert_id = str(uuid4())
                    sequence = next_notification_sequence(connection)
                    connection.execute(
                        f"INSERT INTO {P}alerts (sequence,id,run_id,policy_id,priority,event_type,"
                        "origin,change_count,created_at,read_at) VALUES (?,?,?,?,?,"
                        "'unified_monitoring_changed','new',?,?,NULL)",
                        (sequence, alert_id, run_id, run["policy_id"], report["priority"],
                         report["trigger_change_count"], at),
                    )
                result = self._run_public(self._run(connection, run_id), include_report=True)
                result["alert_id"] = alert_id
                connection.commit(); return result
            except BaseException:
                connection.rollback(); raise

    def fail(self, run_id: str, code: str, message: str, at: str) -> None:
        code = str(code)[:80] or "monitoring_failed"
        message = str(message)[:1000] or "Birleşik izleme çalışması tamamlanamadı."
        with self.storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                changed = connection.execute(
                    f"UPDATE {P}runs SET status='failed',error_code=?,error_message=?,finished_at=? "
                    "WHERE id=? AND status='running'", (code, message, at, run_id),
                ).rowcount
                if changed != 1:
                    raise MonitoringError("run_terminal", "Başarısız çalışma kaydı güncellenemedi.")
                connection.commit()
            except BaseException:
                connection.rollback(); raise


def notification_in(connection, identifier: str) -> dict:
    return SQLiteUnifiedMonitoringRepository._alert_public(
        SQLiteUnifiedMonitoringRepository._alert(connection, identifier), include_report=False,
    )


def case_snapshot(connection, identifier: str):
    from xti.domain.cases import CaseEvidenceSnapshot, canonical_snapshot
    alert = SQLiteUnifiedMonitoringRepository._alert(connection, identifier)
    run, report = alert["run"], alert["run"]["report"]
    snapshot = run["snapshot"]
    changes = report["changes"][:100]
    payload, checksum = canonical_snapshot({
        "version": 1, "type": "unified_monitoring",
        "alert": {
            "id": alert["id"], "policy_id": alert["policy_id"],
            "priority": alert["priority"], "event_type": alert["event_type"],
            "origin": alert["origin"], "change_count": alert["change_count"],
            "created_at": alert["created_at"], "review": alert["review"],
        },
        "run": {
            "id": run["id"], "policy_event_id": run["policy_event_id"],
            "snapshot_sha256": run["snapshot_sha256"],
            "report_sha256": run["report_sha256"],
            "started_at": run["started_at"], "finished_at": run["finished_at"],
        },
        "scope": {
            "organization": snapshot["organization"], "subjects": snapshot["subjects"],
            "definition_sha256": snapshot["definition_sha256"],
            "match_count": len(snapshot["matches"]),
            "coverage_count": len(snapshot["coverage"]),
        },
        "report": {
            "counts": report["counts"], "notify_on": report["notify_on"],
            "minimum_change_count": report["minimum_change_count"],
            "trigger_change_count": report["trigger_change_count"],
            "priority": report["priority"], "automatic_verdict": report["automatic_verdict"],
            "changes": changes, "changes_total": report["changes_total"],
            "changes_truncated": report["changes_truncated"] or len(changes) < len(report["changes"]),
            "limitations": report["limitations"],
        },
    })
    title = f"{alert['priority']} — {alert['change_count']} birleşik izleme değişikliği"
    return CaseEvidenceSnapshot("unified_monitoring", identifier, title[:240],
                                "monitoring alert-show " + identifier, payload, checksum)


def validate_case_snapshot(value):
    try:
        if (set(value) != {"version", "type", "alert", "run", "scope", "report"}
                or value["version"] != 1 or value["type"] != "unified_monitoring"):
            raise ValueError()
        alert, run, scope, report = (value[key] for key in ("alert", "run", "scope", "report"))
        if set(alert) != {"id", "policy_id", "priority", "event_type", "origin",
                          "change_count", "created_at", "review"}:
            raise ValueError()
        if (mention_uuid(alert["id"]) != alert["id"]
                or mention_uuid(alert["policy_id"]) != alert["policy_id"]
                or alert["priority"] not in PRIORITIES
                or alert["event_type"] != "unified_monitoring_changed" or alert["origin"] != "new"
                or type(alert["change_count"]) is not int or alert["change_count"] < 1):
            raise ValueError()
        _time(alert["created_at"])
        review = alert["review"]
        if review is not None:
            if (set(review) != {"sequence", "id", "alert_id", "revision", "decision",
                               "reason", "actor", "recorded_at"}
                    or type(review["sequence"]) is not int or review["sequence"] < 1
                    or mention_uuid(review["id"]) != review["id"]
                    or review["alert_id"] != alert["id"] or review["decision"] not in REVIEW_DECISIONS
                    or type(review["revision"]) is not int or review["revision"] < 1
                    or text(review["reason"], 2000, 2) != review["reason"]
                    or text(review["actor"], 200, 2) != review["actor"]):
                raise ValueError()
            _time(review["recorded_at"])
        if set(run) != {"id", "policy_event_id", "snapshot_sha256", "report_sha256",
                        "started_at", "finished_at"}:
            raise ValueError()
        if (mention_uuid(run["id"]) != run["id"]
                or mention_uuid(run["policy_event_id"]) != run["policy_event_id"]):
            raise ValueError()
        _sha(run["snapshot_sha256"]); _sha(run["report_sha256"])
        _time(run["started_at"]); _time(run["finished_at"])
        if set(scope) != {"organization", "subjects", "definition_sha256",
                          "match_count", "coverage_count"}:
            raise ValueError()
        organization = scope["organization"]
        if (not isinstance(organization, dict) or set(organization) != {"id", "display_name"}
                or mention_uuid(organization["id"]) != organization["id"]
                or text(organization["display_name"], 200, 2) != organization["display_name"]
                or not isinstance(scope["subjects"], list)
                or [subject(item) for item in scope["subjects"]] != scope["subjects"]
                or any(type(scope[key]) is not int or scope[key] < 0
                       for key in ("match_count", "coverage_count"))):
            raise ValueError()
        _sha(scope["definition_sha256"])
        if set(report) != {"counts", "notify_on", "minimum_change_count",
                           "trigger_change_count", "priority", "automatic_verdict", "changes",
                           "changes_total", "changes_truncated", "limitations"}:
            raise ValueError()
        counts = report["counts"]
        if (not isinstance(counts, dict) or set(counts) != {*CHANGE_KINDS, "unchanged"}
                or any(type(counts[key]) is not int or counts[key] < 0 for key in counts)
                or not isinstance(report["notify_on"], list) or not report["notify_on"]
                or report["notify_on"] != [item for item in CHANGE_KINDS if item in report["notify_on"]]
                or type(report["minimum_change_count"]) is not int or report["minimum_change_count"] < 1
                or type(report["trigger_change_count"]) is not int
                or report["trigger_change_count"] != alert["change_count"]
                or report["trigger_change_count"] != sum(counts[item] for item in report["notify_on"])
                or report["priority"] != alert["priority"]
                or report["automatic_verdict"] is not False
                or not isinstance(report["changes"], list) or len(report["changes"]) > 100
                or type(report["changes_total"]) is not int
                or report["changes_total"] != sum(counts[item] for item in CHANGE_KINDS)
                or report["changes_total"] < len(report["changes"])
                or report["changes_truncated"] is not (report["changes_total"] > len(report["changes"]))
                or not isinstance(report["limitations"], list)
                or any(not isinstance(item, str) or not item for item in report["limitations"])):
            raise ValueError()
        for change in report["changes"]:
            if (not isinstance(change, dict) or set(change) != {"key", "action", "subject", "record",
                    "before_state_sha256", "after_state_sha256"}
                    or change["action"] not in CHANGE_KINDS
                    or subject(change["subject"]) != change["subject"]):
                raise ValueError()
            _sha(change["key"])
            before, after = change["before_state_sha256"], change["after_state_sha256"]
            if ((before is not None and _sha(before) != before)
                    or (after is not None and _sha(after) != after)
                    or (change["action"] == "added" and (before is not None or after is None))
                    or (change["action"] == "updated" and (before is None or after is None or before == after))
                    or (change["action"] == "removed" and (before is None or after is not None))):
                raise ValueError()
            record = change["record"]
            record_keys = {"kind", "record_type", "record_id", "display_value", "matched_field",
                           "matched_value", "match_type", "status", "current", "recorded_at",
                           "source", "source_run_id"}
            if (not isinstance(record, dict) or set(record) != record_keys
                    or type(record["current"]) is not bool
                    or any(not isinstance(record[key], str) or not record[key]
                           for key in ("kind", "record_type", "record_id", "display_value",
                                       "matched_field", "matched_value", "match_type", "status", "source"))
                    or (record["source_run_id"] is not None
                        and (not isinstance(record["source_run_id"], str) or not record["source_run_id"]))):
                raise ValueError()
            _time(record["recorded_at"])
        return value
    except (KeyError, TypeError, ValueError, ValidationError):
        raise StorageError("Birleşik izleme vaka kopyası geçersiz.") from None


def company_in(connection, organization_id: str, *, offset: int = 0, limit: int = 20) -> dict:
    rows = connection.execute(
        f"SELECT id FROM {P}policies WHERE organization_id=? ORDER BY sequence DESC LIMIT ? OFFSET ?",
        (organization_id, min(limit, 100), offset),
    ).fetchall()
    total = connection.execute(
        f"SELECT COUNT(*) FROM {P}policies WHERE organization_id=?", (organization_id,),
    ).fetchone()[0]
    at = datetime.now(timezone.utc).isoformat()
    policies = [SQLiteUnifiedMonitoringRepository._policy_public(
        connection, SQLiteUnifiedMonitoringRepository._policy(connection, row[0]), at,
    ) for row in rows]
    alert_total, unread = connection.execute(
        f"SELECT COUNT(*),COALESCE(SUM(read_at IS NULL),0) FROM {P}alerts WHERE policy_id IN "
        f"(SELECT id FROM {P}policies WHERE organization_id=?)", (organization_id,),
    ).fetchone()
    return {"state": "configured" if total else "not_configured", "items": policies,
            "total_count": total, "offset": offset, "limit": min(limit, 100),
            "has_more": total > offset + len(policies), "alert_count": alert_total,
            "unread_alert_count": unread, "stored_evidence_only": True}

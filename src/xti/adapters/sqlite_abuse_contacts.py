"""SQLite lifecycle for reviewed abuse-contact discovery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_cases import SQLiteCaseRepository
from xti.domain.abuse_contacts import (
    AbuseContactError, SourceOutcome, candidate_key, normalize_candidate_id,
    normalize_interval, normalize_limit, normalize_offset, normalize_review_decision,
    normalize_run_id, normalize_sha256, normalize_source_error, normalize_subject, normalize_timestamp,
    normalize_watch_id, validate_outcome,
)
from xti.domain.actionability import canonical, normalize_actor, normalize_key, normalize_reason
from xti.domain.assets import ValidationError, normalize_domain
from xti.domain.cases import normalize_case_id


P = "action_contact_"
_EVIDENCE_COLUMNS = (
    "id, case_id, evidence_type, evidence_id, display_value, source_reference, "
    "snapshot_json, snapshot_sha256, active, added_reason, added_at, updated_at, "
    "removed_reason, removed_at"
)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("uuid")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("uuid")
    return normalized


def _time(value: object) -> str:
    return normalize_timestamp(value)


def _sha(value: object) -> str:
    return normalize_sha256(value)


def _json(value: object, digest: object, message: str) -> object:
    if not isinstance(value, str):
        raise StorageError(message)
    try:
        decoded = json.loads(value)
        encoded, actual = canonical(decoded)
    except (TypeError, ValueError, json.JSONDecodeError, ValidationError) as error:
        raise StorageError(message) from error
    if encoded != value or actual != digest:
        raise StorageError(message)
    return decoded


def _row(connection, sql: str, values=()):
    item = connection.execute(sql, values).fetchone()
    return None if item is None else dict(item)


def _request_sha(operation: str, values: dict) -> str:
    _encoded, digest = canonical({
        "operation": operation,
        "parameters": values,
    })
    return digest


class SQLiteAbuseContactRepository:
    def __init__(self, path: Path) -> None:
        self.storage = SQLiteAssetRepository(path)

    @staticmethod
    def _prepare(connection) -> None:
        connection.row_factory = sqlite3.Row

    @staticmethod
    def _evidence(connection, case_id: str, evidence_link_id: str):
        case = SQLiteCaseRepository._get_case(connection, normalize_case_id(case_id))
        row = connection.execute(
            f"SELECT {_EVIDENCE_COLUMNS} FROM case_evidence WHERE id=?",
            (evidence_link_id,),
        ).fetchone()
        if row is None:
            raise ValidationError("Abuse iletişimi için vaka kanıtı bulunamadı.")
        evidence = SQLiteCaseRepository._evidence(tuple(row))
        if evidence.case_id != case_id:
            raise ValidationError("Abuse iletişim kanıtı bu vakaya ait değil.")
        if not evidence.active:
            raise ValidationError("Abuse iletişim keşfi yalnız etkin vaka kanıtına bağlanabilir.")
        if case.status == "closed":
            raise ValidationError("Kapalı vakada abuse iletişim keşfi başlatılamaz.")
        return case, evidence

    @staticmethod
    def _evidence_subject(evidence, subject_kind: str, subject_value: str) -> None:
        try:
            payload = json.loads(evidence.snapshot_json)
        except (TypeError, json.JSONDecodeError) as error:
            raise StorageError("Vaka kanıtı okunamadı; iletişim keşfi durduruldu.") from error
        candidates: set[tuple[str, str]] = set()
        if evidence.evidence_type == "finding":
            try:
                domain = payload["finding"]["domain"]
                candidates.add(("domain", normalize_domain(domain)))
                for observation in payload.get("observations", []):
                    if isinstance(observation, dict):
                        for key in ("address", "ip", "ip_address"):
                            if key in observation:
                                try:
                                    candidates.add(normalize_subject("ip", observation[key]))
                                except ValidationError:
                                    pass
            except (KeyError, TypeError, ValidationError) as error:
                raise StorageError("Finding vaka kanıtı iletişim hedefini doğrulamıyor.") from error
        elif evidence.evidence_type == "brand_protection":
            try:
                url = payload["candidate"]["url"]
                host = urlsplit(url).hostname
                candidates.add(("domain", normalize_domain(host)))
            except (KeyError, TypeError, ValueError, ValidationError) as error:
                raise StorageError("Marka vaka kanıtı iletişim hedefini doğrulamıyor.") from error
        else:
            raise ValidationError(
                "Abuse iletişim keşfi şimdilik domain/IP taşıyan finding veya marka koruma kanıtını destekler."
            )
        if (subject_kind, subject_value) not in candidates:
            raise ValidationError(
                "İletişim hedefi seçilen vaka kanıtındaki domain veya IP ile uyuşmuyor."
            )

    @staticmethod
    def _watch_payload(row: dict) -> dict:
        return {
            "id": _uuid(row["id"]), "case_id": normalize_case_id(row["case_id"]),
            "evidence_link_id": _uuid(row["evidence_link_id"]),
            "subject_kind": row["subject_kind"], "subject_value": row["subject_value"],
            "evidence_sha256": _sha(row["evidence_sha256"]),
            "interval_seconds": normalize_interval(row["interval_seconds"]),
            "include_whois": bool(row["include_whois"]), "enabled": bool(row["enabled"]),
            "revision": row["revision"], "created_by": normalize_actor(row["created_by"]),
            "reason": normalize_reason(row["reason"]), "created_at": _time(row["created_at"]),
            "updated_at": _time(row["updated_at"]),
            "last_started_at": None if row["last_started_at"] is None else _time(row["last_started_at"]),
            "last_run_id": None if row["last_run_id"] is None else _uuid(row["last_run_id"]),
        }

    @classmethod
    def _watch(cls, connection, watch_id: str, *, audit: bool = True) -> dict:
        row = _row(connection, f"SELECT * FROM {P}watches WHERE id=?", (watch_id,))
        if row is None:
            raise AbuseContactError("not_found", "Abuse iletişim izlemesi bulunamadı.")
        try:
            result = cls._watch_payload(row)
            if (
                type(row["revision"]) is not int or row["revision"] <= 0
                or row["include_whois"] not in (0, 1) or row["enabled"] not in (0, 1)
                or normalize_subject(row["subject_kind"], row["subject_value"])
                    != (row["subject_kind"], row["subject_value"])
            ):
                raise ValueError("watch")
            if audit:
                events = connection.execute(
                    f"SELECT * FROM {P}watch_events WHERE watch_id=? ORDER BY revision",
                    (watch_id,),
                ).fetchall()
                if len(events) != row["revision"]:
                    raise ValueError("events")
                for expected, event_row in enumerate(events, 1):
                    event = dict(event_row)
                    snapshot = _json(event["snapshot_json"], event["snapshot_sha256"],
                                     "Abuse iletişim izleme olay kaydı bozuk.")
                    request_sha = snapshot.get("event", {}).get("request_sha256")
                    if (
                        event["revision"] != expected or snapshot.get("watch", {}).get("revision") != expected
                        or snapshot.get("watch", {}).get("id") != watch_id
                        or snapshot.get("event") != {
                            "action": event["action"], "actor": event["actor"],
                            "reason": event["reason"], "recorded_at": event["recorded_at"],
                            "request_sha256": request_sha,
                        }
                        or normalize_sha256(request_sha) != request_sha
                    ):
                        raise ValueError("event")
                if events:
                    latest = _json(
                        events[-1]["snapshot_json"], events[-1]["snapshot_sha256"],
                        "Abuse iletişim izleme olay kaydı bozuk.",
                    )["watch"]
                    # Run pointers are operational progress, not watch configuration
                    # revisions. They intentionally change without a watch event.
                    stable = tuple(key for key in result if key not in {
                        "last_started_at", "last_run_id",
                    })
                    if any(latest.get(key) != result[key] for key in stable):
                        raise ValueError("latest")
            return result
        except (TypeError, ValueError, KeyError, ValidationError) as error:
            raise StorageError("Abuse iletişim izleme kaydı bozuk; işlem durduruldu.") from error

    @classmethod
    def _insert_watch_event(
        cls, connection, watch: dict, *, action: str, actor: str, reason: str,
        idempotency_key: str, request_sha256: str, recorded_at: str,
    ) -> None:
        snapshot_json, snapshot_sha = canonical({
            "kind": "abuse_contact_watch_event", "version": 1,
            "event": {
                "action": action, "actor": actor, "reason": reason,
                "recorded_at": recorded_at,
                "request_sha256": normalize_sha256(request_sha256),
            },
            "watch": watch,
        })
        connection.execute(
            f"INSERT INTO {P}watch_events "
            "(id,watch_id,revision,action,snapshot_json,snapshot_sha256,idempotency_key,actor,reason,recorded_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), watch["id"], watch["revision"], action, snapshot_json,
             snapshot_sha, idempotency_key, actor, reason, recorded_at),
        )

    @staticmethod
    def _schedule(watch: dict, at: str) -> dict:
        now = datetime.fromisoformat(_time(at))
        if watch["last_started_at"] is None:
            due_at = watch["created_at"]
        else:
            due_at = (
                datetime.fromisoformat(watch["last_started_at"])
                + timedelta(seconds=watch["interval_seconds"])
            ).astimezone(timezone.utc).isoformat()
        return {"due_at": due_at, "due": watch["enabled"] and datetime.fromisoformat(due_at) <= now}

    @classmethod
    def _watch_details(cls, connection, watch_id: str, at: str) -> dict:
        watch = cls._watch(connection, watch_id)
        total_runs = connection.execute(
            f"SELECT COUNT(*) FROM {P}runs WHERE watch_id=?", (watch_id,),
        ).fetchone()[0]
        active_candidates = connection.execute(
            f"SELECT COUNT(*) FROM {P}candidates WHERE watch_id=? AND active=1", (watch_id,),
        ).fetchone()[0]
        return {
            **watch, "schedule": cls._schedule(watch, at),
            "total_run_count": total_runs, "active_candidate_count": active_candidates,
            "notes": [
                "Bulunan adres başvuru yetkisi değildir; analist onayı gerekir.",
                "Başarısız kaynak turu önceki başarılı adayı silmez.",
            ],
        }

    @staticmethod
    def _run_row(row: dict) -> dict:
        try:
            report = None
            if row["report_json"] is not None:
                report = _json(row["report_json"], row["report_sha256"],
                               "Abuse iletişim çalışma raporu bozuk.")
            result = {
                "id": _uuid(row["id"]), "watch_id": _uuid(row["watch_id"]),
                "watch_revision": row["watch_revision"], "status": row["status"],
                "source_count": row["source_count"],
                "succeeded_source_count": row["succeeded_source_count"],
                "failed_source_count": row["failed_source_count"],
                "candidate_count": row["candidate_count"],
                "added_count": row["added_count"], "updated_count": row["updated_count"],
                "reactivated_count": row["reactivated_count"],
                "unchanged_count": row["unchanged_count"], "removed_count": row["removed_count"],
                "report": report, "error_code": row["error_code"], "error": row["error"],
                "started_at": _time(row["started_at"]),
                "finished_at": None if row["finished_at"] is None else _time(row["finished_at"]),
                "previous_chain_sha256": None if row["previous_chain_sha256"] is None else _sha(row["previous_chain_sha256"]),
                "chain_sha256": None if row["chain_sha256"] is None else _sha(row["chain_sha256"]),
                "recovered_by": None if row["recovered_by"] is None else normalize_actor(row["recovered_by"]),
                "recovery_reason": None if row["recovery_reason"] is None else normalize_reason(row["recovery_reason"]),
            }
            if result["status"] == "running":
                if report is not None or result["finished_at"] is not None or result["chain_sha256"] is not None:
                    raise ValueError("running")
            else:
                if report is None or result["finished_at"] is None or result["chain_sha256"] is None:
                    raise ValueError("terminal")
                chain_json, chain = canonical({
                    "kind": "abuse_contact_run_chain", "version": 1,
                    "run_id": result["id"], "watch_id": result["watch_id"],
                    "status": result["status"], "report_sha256": row["report_sha256"],
                    "previous_chain_sha256": result["previous_chain_sha256"],
                    "finished_at": result["finished_at"],
                })
                del chain_json
                if chain != result["chain_sha256"]:
                    raise ValueError("chain")
            return result
        except (TypeError, ValueError, KeyError, ValidationError) as error:
            raise StorageError("Abuse iletişim çalışma kaydı bozuk; işlem durduruldu.") from error

    @classmethod
    def _run(cls, connection, run_id: str, *, details: bool = False) -> dict:
        row = _row(connection, f"SELECT * FROM {P}runs WHERE id=?", (run_id,))
        if row is None:
            raise AbuseContactError("not_found", "Abuse iletişim çalışması bulunamadı.")
        result = cls._run_row(row)
        if details:
            sources = []
            for raw in connection.execute(
                f"SELECT * FROM {P}source_results WHERE run_id=? ORDER BY sequence", (run_id,),
            ):
                item = dict(raw)
                summary = _json(item["result_json"], item["result_sha256"],
                                "Abuse iletişim kaynak makbuzu bozuk.")
                if summary.get("source_key") != item["source_key"] or summary.get("status") != item["status"]:
                    raise StorageError("Abuse iletişim kaynak makbuzu kapsamı bozuk.")
                sources.append(summary)
            result["sources"] = sources
        return result

    @staticmethod
    def _candidate_payload(row: dict) -> dict:
        return {
            "contact_kind": row["contact_kind"], "channel": row["channel"],
            "contact_value": row["contact_value"], "routing_kind": row["routing_kind"],
            "source_key": row["source_key"], "source_reference": row["source_reference"],
            "confidence": row["confidence"], "evidence": row["evidence"],
        }

    @classmethod
    def _current_review(cls, connection, row: dict) -> tuple[dict | None, str]:
        review = _row(
            connection,
            f"SELECT * FROM {P}reviews WHERE candidate_id=? ORDER BY revision DESC LIMIT 1",
            (row["id"],),
        )
        if review is None:
            return None, "unreviewed"
        result = {
            "id": _uuid(review["id"]), "candidate_id": _uuid(review["candidate_id"]),
            "revision": review["revision"], "observation_revision": review["observation_revision"],
            "decision": normalize_review_decision(review["decision"]),
            "actor": normalize_actor(review["actor"]), "reason": normalize_reason(review["reason"]),
            "evidence_sha256": _sha(review["evidence_sha256"]),
            "recorded_at": _time(review["recorded_at"]),
        }
        state = "current" if (
            result["observation_revision"] == row["observation_revision"]
            and result["evidence_sha256"] == row["evidence_sha256"]
        ) else "stale"
        return result, state

    @classmethod
    def _candidate(cls, connection, candidate_id: str, *, details: bool = False) -> dict:
        row = _row(connection, f"SELECT * FROM {P}candidates WHERE id=?", (candidate_id,))
        if row is None:
            raise AbuseContactError("not_found", "Abuse iletişim adayı bulunamadı.")
        try:
            persisted = _json(row["evidence_json"], row["evidence_sha256"],
                              "Abuse iletişim aday kanıtı bozuk.")
            if not isinstance(persisted, dict) or not isinstance(persisted.get("evidence"), dict):
                raise ValueError("evidence")
            row["evidence"] = persisted["evidence"]
            payload = cls._candidate_payload(row)
            encoded, digest = canonical(payload)
            if encoded != row["evidence_json"] or digest != row["evidence_sha256"]:
                raise ValueError("payload")
            review, review_state = cls._current_review(connection, row)
            result = {
                "id": _uuid(row["id"]), "watch_id": _uuid(row["watch_id"]),
                "candidate_key": _sha(row["candidate_key"]),
                **payload, "evidence_sha256": _sha(row["evidence_sha256"]),
                "active": bool(row["active"]),
                "observation_revision": row["observation_revision"],
                "review_revision": row["review_revision"],
                "review": review, "review_state": review_state,
                "first_run_id": _uuid(row["first_run_id"]), "last_run_id": _uuid(row["last_run_id"]),
                "first_seen": _time(row["first_seen"]), "last_seen": _time(row["last_seen"]),
                "usable_for_takedown": bool(
                    row["active"] and review_state == "current" and review
                    and review["decision"] == "approved"
                ),
            }
            if details:
                result["event_count"] = connection.execute(
                    f"SELECT COUNT(*) FROM {P}candidate_events WHERE candidate_id=?", (candidate_id,),
                ).fetchone()[0]
                result["review_count"] = connection.execute(
                    f"SELECT COUNT(*) FROM {P}reviews WHERE candidate_id=?", (candidate_id,),
                ).fetchone()[0]
            return result
        except (TypeError, ValueError, KeyError, ValidationError) as error:
            raise StorageError("Abuse iletişim adayı bozuk; işlem durduruldu.") from error

    @classmethod
    def _candidate_state(cls, row: dict) -> dict:
        return {
            "id": row["id"], "watch_id": row["watch_id"],
            "active": bool(row["active"]), "observation_revision": row["observation_revision"],
            "evidence_sha256": row["evidence_sha256"], "last_run_id": row["last_run_id"],
            "last_seen": row["last_seen"],
        }

    @classmethod
    def _insert_candidate_event(
        cls, connection, row: dict, *, run_id: str, action: str, recorded_at: str,
    ) -> None:
        state_json, state_sha = canonical({
            "kind": "abuse_contact_candidate_state", "version": 1,
            "candidate": cls._candidate_state(row),
        })
        connection.execute(
            f"INSERT INTO {P}candidate_events "
            "(id,candidate_id,run_id,revision,action,state_json,state_sha256,recorded_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid4()), row["id"], run_id, row["observation_revision"], action,
             state_json, state_sha, recorded_at),
        )

    def _plan(self, connection, values: dict, at: str) -> dict:
        _case, evidence = self._evidence(connection, values["case_id"], values["evidence_link_id"])
        self._evidence_subject(evidence, values["subject_kind"], values["subject_value"])
        sources = ["domain_rdap" if values["subject_kind"] == "domain" else "ip_rdap"]
        if values["subject_kind"] == "domain":
            sources.append("security_txt")
        if values["include_whois"]:
            sources.append("whois")
        payload = {
            "case_id": values["case_id"], "evidence_link_id": values["evidence_link_id"],
            "evidence_sha256": evidence.snapshot_sha256,
            "subject_kind": values["subject_kind"], "subject_value": values["subject_value"],
            "interval_seconds": values["interval_seconds"], "include_whois": values["include_whois"],
            "sources": sources,
            "limits": {"http_requests_max": 4, "candidates_per_source": 100, "timeout_seconds_max": 120},
            "created_at": at,
        }
        _encoded, digest = canonical(payload)
        return {
            **payload, "plan_sha256": digest,
            "notes": [
                "RDAP ana kaynaktır; WHOIS yalnız RDAP adres vermezse fallback olarak çalışır.",
                "security.txt site kontrollü yardımcı iletişimdir; registrar veya hosting kanıtı değildir.",
                "Hiçbir adrese otomatik e-posta veya API başvurusu gönderilmez.",
            ],
        }

    def read(self, operation: str, values: dict, recorded_at: str) -> dict:
        with self.storage._connection(readonly=True) as connection:
            self._prepare(connection); connection.execute("BEGIN")
            if operation == "action.contact.plan":
                result = self._plan(connection, values, recorded_at)
            elif operation == "action.contact.watches":
                clauses, parameters = [], []
                if values.get("case_id") is not None:
                    clauses.append("case_id=?"); parameters.append(values["case_id"])
                if values.get("enabled") is not None:
                    clauses.append("enabled=?"); parameters.append(int(values["enabled"]))
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                total = connection.execute(f"SELECT COUNT(*) FROM {P}watches{where}", parameters).fetchone()[0]
                rows = connection.execute(
                    f"SELECT id FROM {P}watches{where} ORDER BY sequence DESC LIMIT ? OFFSET ?",
                    (*parameters, values["limit"], values["offset"]),
                ).fetchall()
                result = {"items": [self._watch_details(connection, row[0], recorded_at) for row in rows],
                          "total_count": total, "offset": values["offset"], "limit": values["limit"],
                          "has_more": total > values["offset"] + values["limit"]}
            elif operation == "action.contact.watch.show":
                result = self._watch_details(connection, values["watch_id"], recorded_at)
            elif operation == "action.contact.watch.events":
                self._watch(connection, values["watch_id"])
                total = connection.execute(f"SELECT COUNT(*) FROM {P}watch_events WHERE watch_id=?", (values["watch_id"],)).fetchone()[0]
                rows = connection.execute(
                    f"SELECT * FROM {P}watch_events WHERE watch_id=? ORDER BY revision LIMIT ? OFFSET ?",
                    (values["watch_id"], values["limit"], values["offset"]),
                ).fetchall()
                items = []
                for raw in rows:
                    row = dict(raw); snapshot = _json(row["snapshot_json"], row["snapshot_sha256"], "Abuse iletişim izleme olayı bozuk.")
                    items.append({"id": row["id"], "watch_id": row["watch_id"], "revision": row["revision"],
                                  "action": row["action"], "actor": row["actor"], "reason": row["reason"],
                                  "recorded_at": row["recorded_at"], "snapshot_sha256": row["snapshot_sha256"],
                                  "watch": snapshot["watch"]})
                result = {"items": items, "total_count": total, "offset": values["offset"], "limit": values["limit"],
                          "has_more": total > values["offset"] + values["limit"]}
            elif operation == "action.contact.due":
                at = values.get("at") or recorded_at
                rows = connection.execute(
                    f"SELECT id FROM {P}watches "
                    "WHERE enabled=1 AND ("
                    "(last_started_at IS NULL AND unixepoch(created_at)<=unixepoch(?)) OR "
                    "(last_started_at IS NOT NULL AND "
                    "unixepoch(last_started_at)+interval_seconds<=unixepoch(?))"
                    ") ORDER BY COALESCE(last_started_at,created_at),sequence LIMIT ?",
                    (at, at, values["limit"] + 1),
                ).fetchall()
                has_more = len(rows) > values["limit"]
                items = [
                    self._watch_details(connection, row[0], at)
                    for row in rows[:values["limit"]]
                ]
                result = {"items": items, "count": len(items), "at": values.get("at") or recorded_at,
                          "limit": values["limit"], "has_more": has_more}
            elif operation == "action.contact.runs":
                clauses, parameters = [], []
                if values.get("watch_id") is not None:
                    clauses.append("watch_id=?"); parameters.append(values["watch_id"])
                if values.get("status") is not None:
                    clauses.append("status=?"); parameters.append(values["status"])
                where = " WHERE " + " AND ".join(clauses) if clauses else ""
                total = connection.execute(f"SELECT COUNT(*) FROM {P}runs{where}", parameters).fetchone()[0]
                rows = connection.execute(
                    f"SELECT * FROM {P}runs{where} ORDER BY sequence DESC LIMIT ? OFFSET ?",
                    (*parameters, values["limit"], values["offset"]),
                ).fetchall()
                result = {"items": [self._run_row(dict(row)) for row in rows], "total_count": total,
                          "offset": values["offset"], "limit": values["limit"],
                          "has_more": total > values["offset"] + values["limit"]}
            elif operation == "action.contact.run.show":
                result = self._run(connection, values["run_id"], details=True)
            elif operation == "action.contact.candidates":
                self._watch(connection, values["watch_id"])
                clauses = ["c.watch_id=?"]
                parameters: list[object] = [values["watch_id"]]
                if values.get("active") is not None:
                    clauses.append("c.active=?")
                    parameters.append(int(values["active"]))
                join = ""
                if values.get("decision") is not None:
                    join = (
                        f" JOIN {P}reviews r ON r.candidate_id=c.id "
                        "AND r.revision=c.review_revision"
                    )
                    clauses.extend((
                        "r.observation_revision=c.observation_revision",
                        "r.evidence_sha256=c.evidence_sha256",
                        "r.decision=?",
                    ))
                    parameters.append(values["decision"])
                where = " WHERE " + " AND ".join(clauses)
                total = connection.execute(
                    f"SELECT COUNT(*) FROM {P}candidates c{join}{where}",
                    parameters,
                ).fetchone()[0]
                rows = connection.execute(
                    f"SELECT c.id FROM {P}candidates c{join}{where} "
                    "ORDER BY c.sequence DESC LIMIT ? OFFSET ?",
                    (*parameters, values["limit"], values["offset"]),
                ).fetchall()
                result = {
                    "items": [self._candidate(connection, row[0]) for row in rows],
                    "total_count": total, "offset": values["offset"],
                    "limit": values["limit"],
                    "has_more": total > values["offset"] + values["limit"],
                }
            elif operation == "action.contact.candidate.show":
                result = self._candidate(connection, values["candidate_id"], details=True)
            elif operation == "action.contact.candidate.events":
                self._candidate(connection, values["candidate_id"])
                total = connection.execute(f"SELECT COUNT(*) FROM {P}candidate_events WHERE candidate_id=?", (values["candidate_id"],)).fetchone()[0]
                rows = connection.execute(
                    f"SELECT * FROM {P}candidate_events WHERE candidate_id=? ORDER BY revision LIMIT ? OFFSET ?",
                    (values["candidate_id"], values["limit"], values["offset"]),
                ).fetchall()
                items = []
                for raw in rows:
                    row = dict(raw); state = _json(row["state_json"], row["state_sha256"], "Abuse iletişim aday olayı bozuk.")
                    items.append({"id": row["id"], "candidate_id": row["candidate_id"], "run_id": row["run_id"],
                                  "revision": row["revision"], "action": row["action"], "state": state["candidate"],
                                  "state_sha256": row["state_sha256"], "recorded_at": row["recorded_at"]})
                result = {"items": items, "total_count": total, "offset": values["offset"], "limit": values["limit"],
                          "has_more": total > values["offset"] + values["limit"]}
            elif operation == "action.contact.reviews":
                self._candidate(connection, values["candidate_id"])
                total = connection.execute(f"SELECT COUNT(*) FROM {P}reviews WHERE candidate_id=?", (values["candidate_id"],)).fetchone()[0]
                rows = connection.execute(
                    f"SELECT * FROM {P}reviews WHERE candidate_id=? ORDER BY revision LIMIT ? OFFSET ?",
                    (values["candidate_id"], values["limit"], values["offset"]),
                ).fetchall()
                items = [{"id": row["id"], "candidate_id": row["candidate_id"], "revision": row["revision"],
                          "observation_revision": row["observation_revision"], "decision": row["decision"],
                          "actor": row["actor"], "reason": row["reason"], "evidence_sha256": row["evidence_sha256"],
                          "recorded_at": row["recorded_at"]} for row in rows]
                result = {"items": items, "total_count": total, "offset": values["offset"], "limit": values["limit"],
                          "has_more": total > values["offset"] + values["limit"]}
            else:
                raise ValidationError("Abuse iletişim okuma işlemi desteklenmiyor.")
            connection.rollback()
            return result

    def mutate(self, operation: str, values: dict, recorded_at: str) -> dict:
        with self.storage._connection() as connection:
            self._prepare(connection)
            try:
                connection.execute("BEGIN IMMEDIATE")
                if operation == "action.contact.watch.add":
                    request_sha = _request_sha(operation, values)
                    replay = _row(
                        connection,
                        f"SELECT * FROM {P}watch_events WHERE idempotency_key=?",
                        (values["idempotency_key"],),
                    )
                    if replay is not None:
                        snapshot = _json(
                            replay["snapshot_json"], replay["snapshot_sha256"],
                            "Abuse iletişim izleme olay kaydı bozuk.",
                        )
                        if snapshot.get("event", {}).get("request_sha256") != request_sha:
                            raise ValidationError("İletişim izleme tekrar anahtarı farklı istek için kullanılmış.")
                        result = self._watch_details(connection, replay["watch_id"], recorded_at)
                        connection.rollback(); return {**result, "replayed": True}
                    plan = self._plan(connection, values, recorded_at)
                    identifier = str(uuid4())
                    connection.execute(
                        f"INSERT INTO {P}watches "
                        "(id,case_id,evidence_link_id,subject_kind,subject_value,evidence_sha256,interval_seconds,include_whois,enabled,revision,idempotency_key,created_by,reason,created_at,updated_at,last_started_at,last_run_id) "
                        "VALUES (?,?,?,?,?,?,?,?,1,1,?,?,?,?,?,NULL,NULL)",
                        (identifier, values["case_id"], values["evidence_link_id"], values["subject_kind"],
                         values["subject_value"], plan["evidence_sha256"], values["interval_seconds"],
                         int(values["include_whois"]), values["idempotency_key"], values["actor"],
                         values["reason"], recorded_at, recorded_at),
                    )
                    watch = self._watch(connection, identifier, audit=False)
                    self._insert_watch_event(connection, watch, action="added", actor=values["actor"],
                                             reason=values["reason"], idempotency_key=values["idempotency_key"],
                                             request_sha256=request_sha,
                                             recorded_at=recorded_at)
                    result = self._watch_details(connection, identifier, recorded_at)
                elif operation in {"action.contact.watch.update", "action.contact.watch.disable"}:
                    request_sha = _request_sha(operation, values)
                    replay = _row(
                        connection,
                        f"SELECT * FROM {P}watch_events WHERE idempotency_key=?",
                        (values["idempotency_key"],),
                    )
                    if replay is not None:
                        snapshot = _json(
                            replay["snapshot_json"], replay["snapshot_sha256"],
                            "Abuse iletişim izleme olay kaydı bozuk.",
                        )
                        if snapshot.get("event", {}).get("request_sha256") != request_sha:
                            raise ValidationError("İletişim izleme tekrar anahtarı farklı istek için kullanılmış.")
                        result = self._watch_details(connection, replay["watch_id"], recorded_at)
                        connection.rollback(); return {**result, "replayed": True}
                    watch = self._watch(connection, values["watch_id"])
                    if watch["revision"] != values["expected_revision"]:
                        raise AbuseContactError("revision_conflict", "İletişim izlemesi değişti; güncel sürümü alın.")
                    interval = values.get("interval_seconds", watch["interval_seconds"])
                    include_whois = values.get("include_whois", watch["include_whois"])
                    enabled = False if operation.endswith("disable") else values.get("enabled", watch["enabled"])
                    revision = watch["revision"] + 1
                    connection.execute(
                        f"UPDATE {P}watches SET interval_seconds=?,include_whois=?,enabled=?,revision=?,updated_at=? WHERE id=?",
                        (interval, int(include_whois), int(enabled), revision, recorded_at, watch["id"]),
                    )
                    updated = self._watch(connection, watch["id"], audit=False)
                    action = "disabled" if not enabled and watch["enabled"] else "enabled" if enabled and not watch["enabled"] else "updated"
                    self._insert_watch_event(connection, updated, action=action, actor=values["actor"],
                                             reason=values["reason"], idempotency_key=values["idempotency_key"],
                                             request_sha256=request_sha,
                                             recorded_at=recorded_at)
                    result = self._watch_details(connection, watch["id"], recorded_at)
                elif operation == "action.contact.review":
                    replay = _row(connection, f"SELECT * FROM {P}reviews WHERE idempotency_key=?", (values["idempotency_key"],))
                    if replay is not None:
                        persisted_request = {
                            "candidate_id": replay["candidate_id"],
                            "expected_observation_revision": replay["observation_revision"],
                            "expected_review_revision": replay["revision"] - 1,
                            "decision": replay["decision"],
                            "actor": replay["actor"],
                            "reason": replay["reason"],
                            "idempotency_key": replay["idempotency_key"],
                        }
                        if _request_sha(operation, persisted_request) != _request_sha(operation, values):
                            raise ValidationError("İletişim kararı tekrar anahtarı farklı istek için kullanılmış.")
                        result = self._candidate(connection, replay["candidate_id"], details=True)
                        connection.rollback(); return {**result, "replayed": True}
                    candidate = self._candidate(connection, values["candidate_id"])
                    if candidate["observation_revision"] != values["expected_observation_revision"] or candidate["review_revision"] != values["expected_review_revision"]:
                        raise AbuseContactError("revision_conflict", "İletişim adayı değişti; güncel kanıtı yeniden inceleyin.")
                    revision = candidate["review_revision"] + 1
                    connection.execute(
                        f"INSERT INTO {P}reviews "
                        "(id,candidate_id,revision,observation_revision,decision,idempotency_key,actor,reason,evidence_sha256,recorded_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (str(uuid4()), candidate["id"], revision, candidate["observation_revision"],
                         values["decision"], values["idempotency_key"], values["actor"], values["reason"],
                         candidate["evidence_sha256"], recorded_at),
                    )
                    connection.execute(f"UPDATE {P}candidates SET review_revision=? WHERE id=?", (revision, candidate["id"]))
                    result = self._candidate(connection, candidate["id"], details=True)
                elif operation == "action.contact.recover":
                    row = _row(connection, f"SELECT * FROM {P}runs WHERE id=?", (values["run_id"],))
                    if row is None:
                        raise AbuseContactError("not_found", "Abuse iletişim çalışması bulunamadı.")
                    if row["recovery_key"] is not None:
                        if row["recovery_key"] != values["idempotency_key"] or row["recovered_by"] != values["actor"] or row["recovery_reason"] != values["reason"]:
                            raise ValidationError("İletişim recovery tekrar anahtarı farklı istek için kullanılmış.")
                        result = self._run(connection, values["run_id"], details=True)
                        connection.rollback(); return {**result, "replayed": True}
                    if row["status"] != "running":
                        raise ValidationError("Yalnız yarım kalmış running iletişim çalışması recover edilebilir.")
                    report = {"kind": "abuse_contact_run_report", "version": 1, "status": "interrupted",
                              "sources": [], "counts": {"candidate_count": row["candidate_count"]},
                              "old_evidence_preserved": True, "recovery": {"actor": values["actor"], "reason": values["reason"]}}
                    report_json, report_sha = canonical(report)
                    chain_json, chain = canonical({"kind": "abuse_contact_run_chain", "version": 1,
                        "run_id": row["id"], "watch_id": row["watch_id"], "status": "interrupted",
                        "report_sha256": report_sha, "previous_chain_sha256": row["previous_chain_sha256"],
                        "finished_at": recorded_at})
                    del chain_json
                    connection.execute(
                        f"UPDATE {P}runs SET status='interrupted',report_json=?,report_sha256=?,error_code='interrupted',error=?,finished_at=?,chain_sha256=?,recovery_key=?,recovered_by=?,recovery_reason=? WHERE id=?",
                        (report_json, report_sha, "Çalışma recovery ile yarım kaldı olarak kapatıldı.", recorded_at, chain,
                         values["idempotency_key"], values["actor"], values["reason"], row["id"]),
                    )
                    result = self._run(connection, row["id"], details=True)
                else:
                    raise ValidationError("Abuse iletişim yazma işlemi desteklenmiyor.")
                connection.commit()
                return {**result, "replayed": False}
            except BaseException:
                connection.rollback(); raise

    def reserve_run(self, values: dict, recorded_at: str) -> tuple[dict, bool]:
        with self.storage._connection() as connection:
            self._prepare(connection)
            try:
                connection.execute("BEGIN IMMEDIATE")
                request_json, request_sha = canonical({
                    "watch_id": values["watch_id"], "expected_revision": values["expected_revision"],
                    "force": values["force"], "timeout_seconds": values["timeout_seconds"],
                })
                del request_json
                replay = _row(connection, f"SELECT * FROM {P}runs WHERE idempotency_key=?", (values["idempotency_key"],))
                if replay is not None:
                    if replay["request_sha256"] != request_sha:
                        raise ValidationError("İletişim yenileme tekrar anahtarı farklı istek için kullanılmış.")
                    result = self._run(connection, replay["id"], details=replay["status"] != "running")
                    connection.rollback(); return result, True
                watch = self._watch(connection, values["watch_id"])
                if not watch["enabled"]:
                    raise ValidationError("Kapalı abuse iletişim izlemesi yenilenemez.")
                if watch["revision"] != values["expected_revision"]:
                    raise AbuseContactError("revision_conflict", "İletişim izlemesi değişti; güncel sürümü alın.")
                _case, evidence = self._evidence(connection, watch["case_id"], watch["evidence_link_id"])
                if evidence.snapshot_sha256 != watch["evidence_sha256"]:
                    raise ValidationError("Vaka kanıtı değişti; yeni abuse iletişim izlemesi oluşturun.")
                self._evidence_subject(evidence, watch["subject_kind"], watch["subject_value"])
                schedule = self._schedule(watch, recorded_at)
                if not values["force"] and not schedule["due"]:
                    raise AbuseContactError("not_due", "İletişim yenileme zamanı gelmedi; planı veya --force seçimini kullanın.")
                if connection.execute(f"SELECT 1 FROM {P}runs WHERE watch_id=? AND status='running'", (watch["id"],)).fetchone():
                    raise AbuseContactError("already_running", "Bu iletişim izlemesinin çalışan bir turu var.")
                previous = _row(connection, f"SELECT chain_sha256 FROM {P}runs WHERE watch_id=? AND status!='running' ORDER BY sequence DESC LIMIT 1", (watch["id"],))
                identifier = str(uuid4())
                connection.execute(
                    f"INSERT INTO {P}runs "
                    "(id,watch_id,watch_revision,idempotency_key,request_sha256,status,source_count,succeeded_source_count,failed_source_count,candidate_count,added_count,updated_count,reactivated_count,unchanged_count,removed_count,report_json,report_sha256,error_code,error,started_at,finished_at,previous_chain_sha256,chain_sha256,recovery_key,recovered_by,recovery_reason) "
                    "VALUES (?,?,?,?,?,'running',0,0,0,0,0,0,0,0,0,NULL,NULL,NULL,NULL,?,NULL,?,NULL,NULL,NULL,NULL)",
                    (identifier, watch["id"], watch["revision"], values["idempotency_key"], request_sha,
                     recorded_at, None if previous is None else previous["chain_sha256"]),
                )
                connection.execute(f"UPDATE {P}watches SET last_started_at=?,last_run_id=? WHERE id=?", (recorded_at, identifier, watch["id"]))
                result = {**self._run(connection, identifier), "watch": watch,
                          "timeout_seconds": values["timeout_seconds"]}
                connection.commit(); return result, False
            except BaseException:
                connection.rollback(); raise

    def finish_run(self, run_id: str, outcomes: tuple[SourceOutcome, ...], recorded_at: str) -> dict:
        run_id = normalize_run_id(run_id)
        outcomes = tuple(validate_outcome(item) for item in outcomes)
        keys = {item.source_key for item in outcomes}
        if len(outcomes) != 3 or keys not in (
            {"domain_rdap", "security_txt", "whois"},
            {"ip_rdap", "security_txt", "whois"},
        ):
            raise ValidationError("İletişim kaynak turu beklenen üç kaynağı taşımıyor.")
        with self.storage._connection() as connection:
            self._prepare(connection)
            try:
                connection.execute("BEGIN IMMEDIATE")
                run_row = _row(connection, f"SELECT * FROM {P}runs WHERE id=?", (run_id,))
                if run_row is None:
                    raise AbuseContactError("not_found", "Abuse iletişim çalışması bulunamadı.")
                if run_row["status"] != "running":
                    result = self._run(connection, run_id, details=True)
                    connection.rollback(); return result
                watch = self._watch(connection, run_row["watch_id"])
                expected_rdap = "domain_rdap" if watch["subject_kind"] == "domain" else "ip_rdap"
                keys = {item.source_key for item in outcomes}
                if keys != {expected_rdap, "security_txt", "whois"}:
                    raise ValidationError("İletişim kaynak turu hedef türüyle uyuşmuyor.")
                for outcome in outcomes:
                    result_json, result_sha = canonical(outcome.summary())
                    connection.execute(
                        f"INSERT INTO {P}source_results "
                        "(id,run_id,source_key,status,source_reference,observed_at,content_sha256,result_json,result_sha256,candidate_count,request_count,received_bytes,elapsed_ms,error_code,error) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (str(uuid4()), run_id, outcome.source_key, outcome.status,
                         outcome.source_reference, outcome.observed_at, outcome.content_sha256,
                         result_json, result_sha, len(outcome.candidates), outcome.request_count,
                         outcome.received_bytes, outcome.elapsed_ms, outcome.error_code, outcome.error),
                    )
                authoritative = {
                    item.source_key for item in outcomes
                    if item.status in {"complete", "empty"}
                    or (item.status == "skipped" and item.error_code in {"disabled", "fallback_not_needed", "not_applicable"})
                }
                observed: dict[str, set[str]] = {key: set() for key in authoritative}
                counts = {"added": 0, "updated": 0, "reactivated": 0, "unchanged": 0, "removed": 0}
                for outcome in outcomes:
                    for candidate in outcome.candidates:
                        key = candidate_key(candidate); observed.setdefault(outcome.source_key, set()).add(key)
                        evidence_json, evidence_sha = canonical({
                            "contact_kind": candidate.contact_kind, "channel": candidate.channel,
                            "contact_value": candidate.contact_value, "routing_kind": candidate.routing_kind,
                            "source_key": candidate.source_key, "source_reference": candidate.source_reference,
                            "confidence": candidate.confidence, "evidence": candidate.evidence,
                        })
                        existing = _row(connection, f"SELECT * FROM {P}candidates WHERE watch_id=? AND candidate_key=?", (watch["id"], key))
                        if existing is None:
                            identifier = str(uuid4())
                            connection.execute(
                                f"INSERT INTO {P}candidates "
                                "(id,watch_id,candidate_key,contact_kind,channel,contact_value,routing_kind,source_key,source_reference,confidence,active,observation_revision,review_revision,evidence_json,evidence_sha256,first_run_id,last_run_id,first_seen,last_seen) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?,1,1,0,?,?,?,?,?,?)",
                                (identifier, watch["id"], key, candidate.contact_kind, candidate.channel,
                                 candidate.contact_value, candidate.routing_kind, candidate.source_key,
                                 candidate.source_reference, candidate.confidence, evidence_json, evidence_sha,
                                 run_id, run_id, candidate.observed_at, candidate.observed_at),
                            )
                            row = _row(connection, f"SELECT * FROM {P}candidates WHERE id=?", (identifier,))
                            self._insert_candidate_event(connection, row, run_id=run_id, action="added", recorded_at=recorded_at)
                            counts["added"] += 1
                        else:
                            action = None
                            if not existing["active"]:
                                action = "reactivated"; counts["reactivated"] += 1
                            elif existing["evidence_sha256"] != evidence_sha:
                                action = "updated"; counts["updated"] += 1
                            else:
                                counts["unchanged"] += 1
                            revision = existing["observation_revision"] + (1 if action else 0)
                            connection.execute(
                                f"UPDATE {P}candidates SET contact_kind=?,channel=?,contact_value=?,routing_kind=?,source_reference=?,confidence=?,active=1,observation_revision=?,evidence_json=?,evidence_sha256=?,last_run_id=?,last_seen=? WHERE id=?",
                                (candidate.contact_kind, candidate.channel, candidate.contact_value,
                                 candidate.routing_kind, candidate.source_reference, candidate.confidence,
                                 revision, evidence_json, evidence_sha, run_id, candidate.observed_at, existing["id"]),
                            )
                            if action:
                                row = _row(connection, f"SELECT * FROM {P}candidates WHERE id=?", (existing["id"],))
                                self._insert_candidate_event(connection, row, run_id=run_id, action=action, recorded_at=recorded_at)
                for source_key in authoritative:
                    rows = connection.execute(
                        f"SELECT * FROM {P}candidates WHERE watch_id=? AND source_key=? AND active=1",
                        (watch["id"], source_key),
                    ).fetchall()
                    for raw in rows:
                        row = dict(raw)
                        if row["candidate_key"] in observed.get(source_key, set()):
                            continue
                        revision = row["observation_revision"] + 1
                        connection.execute(
                            f"UPDATE {P}candidates SET active=0,observation_revision=?,last_run_id=?,last_seen=? WHERE id=?",
                            (revision, run_id, recorded_at, row["id"]),
                        )
                        removed = _row(connection, f"SELECT * FROM {P}candidates WHERE id=?", (row["id"],))
                        self._insert_candidate_event(connection, removed, run_id=run_id, action="removed", recorded_at=recorded_at)
                        counts["removed"] += 1
                active_count = connection.execute(f"SELECT COUNT(*) FROM {P}candidates WHERE watch_id=? AND active=1", (watch["id"],)).fetchone()[0]
                failed = [item for item in outcomes if item.status in {"failed", "requirement_missing"}]
                successful = [item for item in outcomes if item.status in {"complete", "empty"}]
                status = "complete" if not failed else "partial" if successful else "failed"
                report = {
                    "kind": "abuse_contact_run_report", "version": 1, "status": status,
                    "subject": {"kind": watch["subject_kind"], "value": watch["subject_value"]},
                    "sources": [item.summary() for item in outcomes],
                    "counts": {"candidate_count": active_count, **{key + "_count": value for key, value in counts.items()}},
                    "old_evidence_preserved": True,
                    "automatic_submission": False,
                }
                report_json, report_sha = canonical(report)
                chain_json, chain = canonical({"kind": "abuse_contact_run_chain", "version": 1,
                    "run_id": run_id, "watch_id": watch["id"], "status": status,
                    "report_sha256": report_sha, "previous_chain_sha256": run_row["previous_chain_sha256"],
                    "finished_at": recorded_at})
                del chain_json
                error_code = "partial_sources" if status == "partial" else "all_sources_failed" if status == "failed" else None
                error = "Bir veya daha fazla kaynak tamamlanamadı; önceki başarılı adaylar korundu." if status == "partial" else "Hiçbir uygulanabilir kaynak tamamlanamadı; önceki başarılı adaylar korundu." if status == "failed" else None
                connection.execute(
                    f"UPDATE {P}runs SET status=?,source_count=?,succeeded_source_count=?,failed_source_count=?,candidate_count=?,added_count=?,updated_count=?,reactivated_count=?,unchanged_count=?,removed_count=?,report_json=?,report_sha256=?,error_code=?,error=?,finished_at=?,chain_sha256=? WHERE id=?",
                    (status, len(outcomes), len(successful), len(failed), active_count, counts["added"],
                     counts["updated"], counts["reactivated"], counts["unchanged"], counts["removed"],
                     report_json, report_sha, error_code, error, recorded_at, chain, run_id),
                )
                result = self._run(connection, run_id, details=True)
                connection.commit(); return result
            except BaseException:
                connection.rollback(); raise

    def fail_run(self, run_id: str, code: str, message: str, recorded_at: str) -> dict:
        run_id = normalize_run_id(run_id)
        code, message = normalize_source_error(
            code or "collection_failed",
            message or "İletişim kaynak turu tamamlanamadı.",
        )
        with self.storage._connection() as connection:
            self._prepare(connection)
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = _row(connection, f"SELECT * FROM {P}runs WHERE id=?", (run_id,))
                if row is None:
                    raise AbuseContactError("not_found", "Abuse iletişim çalışması bulunamadı.")
                if row["status"] != "running":
                    result = self._run(connection, run_id, details=True)
                    connection.rollback(); return result
                active_count = connection.execute(f"SELECT COUNT(*) FROM {P}candidates WHERE watch_id=? AND active=1", (row["watch_id"],)).fetchone()[0]
                report = {"kind": "abuse_contact_run_report", "version": 1, "status": "failed", "sources": [],
                          "counts": {"candidate_count": active_count}, "old_evidence_preserved": True,
                          "automatic_submission": False}
                report_json, report_sha = canonical(report)
                chain_json, chain = canonical({"kind": "abuse_contact_run_chain", "version": 1,
                    "run_id": run_id, "watch_id": row["watch_id"], "status": "failed",
                    "report_sha256": report_sha, "previous_chain_sha256": row["previous_chain_sha256"],
                    "finished_at": recorded_at})
                del chain_json
                connection.execute(
                    f"UPDATE {P}runs SET status='failed',candidate_count=?,report_json=?,report_sha256=?,error_code=?,error=?,finished_at=?,chain_sha256=? WHERE id=?",
                    (active_count, report_json, report_sha, code, message, recorded_at, chain, run_id),
                )
                result = self._run(connection, run_id, details=True)
                connection.commit(); return result
            except BaseException:
                connection.rollback(); raise

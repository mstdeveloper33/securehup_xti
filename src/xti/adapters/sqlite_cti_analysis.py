"""Immutable P04 evidence, current candidate index and atomic review/notification receipts."""

from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.cti_analysis import (
    PREFIX, PROFILE_FIELDS, CtiAnalysisError, canonical, digest, folded, parameters,
    profile_definition, validate_decision, validate_evidence,
)
from xti.domain.mentions import mention_time


P = "cti_analysis_"
_MAX_RESPONSE = 2 * 1024 * 1024


def one(connection, table: str, identifier: str) -> dict:
    row = connection.execute(f"SELECT * FROM {P + table} WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise CtiAnalysisError("not_found", "CTI analiz kaydı bu çalışma alanında bulunamadı.")
    return dict(row)


def decoded(row, *fields: str) -> dict:
    result = dict(row)
    for field in fields:
        raw, checksum = result.pop(field + "_json"), result.pop(field + "_sha256")
        if raw is None:
            if checksum is not None:
                raise StorageError("CTI analiz kayıt hash alanları uyuşmuyor.")
            value = None
        else:
            try:
                value = json.loads(raw)
            except (ValueError, RecursionError):
                raise StorageError("CTI analiz kayıt gövdesi geçersiz.") from None
            if canonical(value) != raw or digest(value) != checksum:
                raise StorageError("CTI analiz kayıt gövdesi veya hash'i bozuk.")
        result[field] = value
    if "enabled" in result:
        result["enabled"] = bool(result["enabled"])
    return result


def profile_in(connection, identifier: str) -> dict:
    result = decoded(one(connection, "profiles", identifier), "definition")
    definition = profile_definition(result["definition"])
    if (definition != result["definition"] or definition["organization_id"] != result["organization_id"]
            or folded(definition["name"]) != result["name_key"]):
        raise StorageError("CTI analiz profili kanonik değil.")
    organization = connection.execute(
        "SELECT id,display_name,active FROM organizations WHERE id=?", (result["organization_id"],),
    ).fetchone()
    if organization is None:
        raise StorageError("CTI analiz profilinin kuruluş bağı bulunamadı.")
    result["organization"] = {"id": organization[0], "display_name": organization[1], "active": bool(organization[2])}
    result["binding_state"] = "disabled" if not result["enabled"] else "organization_disabled" if not organization[2] else "ready"
    return result


def run_in(connection, identifier: str) -> dict:
    result = decoded(one(connection, "runs", identifier), "snapshot", "report")
    if result["snapshot"]["profile_id"] != result["profile_id"]:
        raise StorageError("CTI analiz çalışma kapsamı bozuk.")
    return result


def run_state_in(connection, identifier: str) -> dict:
    """Read lifecycle state without decoding the potentially 64 MiB input snapshot."""
    row = connection.execute(
        f"SELECT id,profile_id,status,started_at,finished_at FROM {P}runs WHERE id=?",
        (identifier,),
    ).fetchone()
    if row is None:
        raise CtiAnalysisError("not_found", "CTI analiz çalışması bu çalışma alanında bulunamadı.")
    return dict(row)


def run_summary_in(connection, identifier: str) -> dict:
    """Read the integrity-checked report used by bounded company summaries."""
    row = connection.execute(
        f"SELECT id,profile_id,status,started_at,finished_at,report_json,report_sha256 "
        f"FROM {P}runs WHERE id=?",
        (identifier,),
    ).fetchone()
    if row is None:
        raise CtiAnalysisError("not_found", "CTI analiz çalışması bu çalışma alanında bulunamadı.")
    return decoded(row, "report")


def public_run(record: dict) -> dict:
    """Keep frozen input in storage without leaking an unbounded snapshot through JSON."""
    snapshot = record["snapshot"]
    attack = snapshot.get("attack", {})
    result = {key: value for key, value in record.items() if key != "snapshot"}
    result["snapshot"] = {
        "profile_id": snapshot["profile_id"], "profile_revision": snapshot["profile_revision"],
        "captured_at": snapshot["captured_at"], "definition": snapshot["definition"],
        "organization": snapshot["organization"],
        "counts": {"entities": len(snapshot.get("entities", [])),
                   "relationships": len(snapshot.get("relationships", [])),
                   "indicators": len(snapshot.get("indicators", [])),
                   "accepted_identity_links": len(snapshot.get("accepted_identity_links", []))},
        "attack": {"run_id": attack.get("run_id"), "version": attack.get("version"),
                   "content_sha256": attack.get("content_sha256"),
                   "entity_count": len(attack.get("entities", [])),
                   "relationship_count": len(attack.get("relationships", [])),
                   "phase_count": len(attack.get("phases", []))},
        "frozen_input_available": True,
    }
    return result


def evidence_in(connection, identifier: str) -> dict:
    result = decoded(one(connection, "evidence", identifier), "body")
    validate_evidence(result["body"])
    return result


def _priority(score: int) -> str:
    return "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 40 else "low"


def candidate_in(connection, identifier: str) -> dict:
    result = one(connection, "candidates", identifier)
    result["evidence"] = evidence_in(connection, result["evidence_id"])
    body = result["evidence"]["body"]
    if (body["candidate_key"] != result["candidate_key"] or body["kind"] != result["kind"]
            or body["subject"]["kind"] != result["subject_kind"] or body["subject"]["id"] != result["subject_id"]
            or body["object"]["kind"] != result["object_kind"] or body["object"]["id"] != result["object_id"]
            or body["score"]["value"] != result["score"] or _priority(result["score"]) != result["priority"]):
        raise StorageError("CTI analiz adayı özgün kanıtla uyuşmuyor.")
    row = connection.execute(
        f"SELECT * FROM {P}reviews WHERE candidate_id=? ORDER BY revision DESC LIMIT 1", (identifier,),
    ).fetchone()
    result["review"] = dict(row) if row else None
    if (result["review"]["revision"] if result["review"] else 0) != result["review_revision"]:
        raise StorageError("CTI analiz inceleme sürümü bozuk.")
    review = result["review"]
    result["needs_review"] = not review or review["evidence_id"] != result["evidence_id"] or review["observation_revision"] != result["observation_revision"]
    profile = profile_in(connection, result["profile_id"])
    last_observation_run = run_state_in(connection, result["last_run_id"])
    if last_observation_run["profile_id"] != result["profile_id"] or last_observation_run["status"] != "complete":
        raise StorageError("CTI analiz adayının son gözlem turu geçersiz.")
    latest_run = run_state_in(connection, profile["last_run_id"]) if profile["last_run_id"] else None
    if latest_run and latest_run["id"] == result["last_run_id"] and latest_run["status"] == "complete":
        result["observation_state"] = "observed_in_latest_complete_run"
    elif latest_run and latest_run["status"] != "complete":
        result["observation_state"] = "latest_run_" + latest_run["status"] + "_previous_observation_retained"
    else:
        result["observation_state"] = "retained_not_observed_in_latest_complete_run"
    result["scope_current"] = profile["revision"] == result["profile_revision"] and profile["binding_state"] == "ready"
    return result


def change_in(connection, identifier: str) -> dict:
    result = one(connection, "changes", identifier)
    result["before"] = evidence_in(connection, result["before_evidence_id"]) if result["before_evidence_id"] else None
    result["after"] = evidence_in(connection, result["after_evidence_id"])
    return result


def company_in(connection, organization_id: str, *, offset: int = 0, limit: int = 20) -> dict:
    previous = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        effective_limit = min(limit, 100)
        profile_rows = connection.execute(
            f"SELECT id FROM {P}profiles WHERE organization_id=? ORDER BY sequence DESC LIMIT ? OFFSET ?",
            (organization_id, effective_limit, offset),
        ).fetchall()
        profile_total = connection.execute(
            f"SELECT COUNT(*) FROM {P}profiles WHERE organization_id=?", (organization_id,),
        ).fetchone()[0]
        item_rows = connection.execute(
            f"SELECT id FROM {P}candidates WHERE profile_id IN "
            f"(SELECT id FROM {P}profiles WHERE organization_id=?) ORDER BY sequence DESC LIMIT ? OFFSET ?",
            (organization_id, effective_limit + 1, offset),
        ).fetchall()
        total = connection.execute(
            f"SELECT COUNT(*) FROM {P}candidates WHERE profile_id IN "
            f"(SELECT id FROM {P}profiles WHERE organization_id=?)", (organization_id,),
        ).fetchone()[0]
        profiles = []
        for row in profile_rows:
            profile = profile_in(connection, row[0])
            run = run_summary_in(connection, profile["last_run_id"]) if profile["last_run_id"] else None
            profiles.append({"id": profile["id"], "name": profile["definition"]["name"],
                "revision": profile["revision"], "binding_state": profile["binding_state"],
                "last_run_id": run["id"] if run else None,
                "last_status": run["status"] if run else "not_checked",
                "last_checked_at": (run["finished_at"] or run["started_at"]) if run else None,
                "source_coverage": ((run or {}).get("report") or {}).get("source_coverage"),
                "trend": ((run or {}).get("report") or {}).get("trend")})
        items, byte_count = [], 0
        for row in item_rows[:effective_limit]:
            item = candidate_in(connection, row[0])
            size = len(canonical(item).encode())
            if items and byte_count + size > _MAX_RESPONSE:
                break
            items.append(item)
            byte_count += size
        return {"state": "recorded" if total else "no_recorded_candidates" if profile_total else "not_configured",
            "items": items, "total_count": total, "offset": offset, "limit": effective_limit,
            "has_more": total > offset + len(items), "page_byte_budget": _MAX_RESPONSE,
            "profiles": {"items": profiles, "total_count": profile_total, "offset": offset,
                         "limit": effective_limit, "has_more": profile_total > offset + effective_limit}}
    finally:
        connection.row_factory = previous


def case_snapshot(connection, identifier: str):
    from xti.domain.cases import CaseEvidenceSnapshot, canonical_snapshot
    previous = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        record = candidate_in(connection, identifier)
        payload, checksum = canonical_snapshot({"version": 1, "type": "cti_analysis", "candidate": record})
        body = record["evidence"]["body"]
        title = body["subject"]["label"] + " → " + body["object"]["label"]
        return CaseEvidenceSnapshot("cti_analysis", identifier, title[:240],
            "cti analysis-candidate-show " + identifier, payload, checksum)
    finally:
        connection.row_factory = previous


def validate_case_snapshot(value):
    try:
        if set(value) != {"version", "type", "candidate"} or value["version"] != 1 or value["type"] != "cti_analysis":
            raise ValueError()
        record = value["candidate"]
        body = validate_evidence(record["evidence"]["body"])
        if record["evidence_id"] != record["evidence"]["id"] or record["candidate_key"] != body["candidate_key"]:
            raise ValueError()
        if record["kind"] != body["kind"] or record["score"] != body["score"]["value"]:
            raise ValueError()
        return value
    except (KeyError, TypeError, ValueError):
        raise StorageError("CTI analiz vaka kopyası geçersiz.") from None


def notification_in(connection, identifier: str) -> dict:
    previous = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        notice = one(connection, "notifications", identifier)
        change = change_in(connection, notice["change_id"])
        run = run_state_in(connection, change["run_id"])
        candidate = candidate_in(connection, change["candidate_id"])
        if change["profile_id"] != run["profile_id"] or candidate["profile_id"] != run["profile_id"] or run["status"] == "running":
            raise StorageError("CTI analiz bildiriminin çalışma kapsamı uyuşmuyor.")
        return {"id": identifier, "change": change, "candidate": candidate,
                "before": change["before"], "after": change["after"]}
    finally:
        connection.row_factory = previous


class SQLiteCtiAnalysisRepository:
    def __init__(self, path):
        self.storage = SQLiteAssetRepository(path)

    @contextmanager
    def connection(self, *, write: bool = False):
        with self.storage._connection(readonly=not write) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield connection
                if write:
                    connection.commit()
            finally:
                if connection.in_transaction:
                    connection.rollback()

    @staticmethod
    def _request(operation: str, values: dict) -> str:
        return digest({"operation": operation, "parameters": values})

    def _mutation_replay(self, connection, operation: str, values: dict):
        row = connection.execute(
            f"SELECT * FROM {P}mutations WHERE request_key=?", (values["idempotency_key"],),
        ).fetchone()
        if row is None:
            return None
        if row["request_sha256"] != self._request(operation, values):
            raise CtiAnalysisError("idempotency_conflict", "Tekrar anahtarı farklı CTI analiz isteğinde kullanılmış.")
        return decoded(row, "result")["result"]

    @staticmethod
    def _idle(connection, profile_id: str) -> None:
        if connection.execute(
            f"SELECT 1 FROM {P}runs WHERE profile_id=? AND status='running' LIMIT 1", (profile_id,),
        ).fetchone():
            raise CtiAnalysisError("run_in_progress", "CTI analiz çalışması sürüyor; durmuş çalışmayı önce açıkça kurtarın.")

    def plan(self, identifier: str) -> dict:
        with self.connection() as connection:
            profile = profile_in(connection, identifier)
            from xti.domain.cti_analysis_jobs import profile_scope_sha256
            return {"profile": profile, "definition": profile["definition"],
                    "organization": profile["organization"], "network_access": False,
                    "inputs": ["stored_cti", "stored_ioc", "local_mitre_attack"],
                    "queue_scope_sha256": profile_scope_sha256(profile)}

    def replay(self, values: dict) -> dict | None:
        values = parameters(PREFIX + "run", values)
        with self.connection() as connection:
            row = connection.execute(
                f"SELECT * FROM {P}runs WHERE request_key=?", (values["idempotency_key"],),
            ).fetchone()
            if row is None:
                return None
            if row["request_sha256"] != self._request(PREFIX + "run", values):
                raise CtiAnalysisError("idempotency_conflict", "Tekrar anahtarı farklı CTI analiz çalışmasına ait.")
            return public_run(run_in(connection, row["id"]))

    def accepted_identity_links(self, profile_id: str) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute(
                f"SELECT c.id,c.evidence_id,c.observation_revision,r.id,r.created_at "
                f"FROM {P}candidates c JOIN {P}reviews r ON r.candidate_id=c.id "
                f"AND r.revision=c.review_revision WHERE c.profile_id=? AND c.kind='identity' "
                f"AND c.last_run_id=(SELECT id FROM {P}runs WHERE profile_id=c.profile_id "
                f"AND status='complete' ORDER BY sequence DESC LIMIT 1) "
                f"AND r.decision='same_entity' AND r.evidence_id=c.evidence_id "
                f"AND r.observation_revision=c.observation_revision ORDER BY c.sequence LIMIT 10001",
                (profile_id,),
            ).fetchall()
            if len(rows) > 10000:
                raise CtiAnalysisError("scope_too_large", "Kabul edilmiş CTI kimlik bağı sınırı aşıldı.")
            result = []
            for row in rows:
                candidate = candidate_in(connection, row[0])
                subject, object_ = candidate["evidence"]["body"]["subject"], candidate["evidence"]["body"]["object"]
                if subject["kind"] == "cti_entity" and object_["kind"] == "attack_entity":
                    result.append({"candidate_id": row[0], "cti_entity_id": subject["id"],
                        "attack_stix_id": object_["id"], "evidence_id": row[1],
                        "review_id": row[3], "reviewed_at": row[4]})
            return result

    def mutate(self, operation: str, values: dict, at: str) -> dict:
        values = parameters(operation, values)
        mention_time(at)
        name = operation.removeprefix(PREFIX)
        with self.connection(write=True) as connection:
            replay = self._mutation_replay(connection, operation, values)
            if replay is not None:
                return {**replay, "replayed": True}
            identifier = values.get("identifier", str(uuid4()))
            if name.startswith("profile."):
                current = profile_in(connection, identifier) if name.endswith(".update") else None
                if current:
                    if current["revision"] != values["expected_revision"]:
                        raise CtiAnalysisError("revision_conflict", "CTI analiz profili sürümü değişti.")
                    self._idle(connection, identifier)
                definition = profile_definition({**(current["definition"] if current else {}),
                    **{key: value for key, value in values.items() if key in PROFILE_FIELDS}})
                if current and definition["organization_id"] != current["organization_id"]:
                    raise CtiAnalysisError("scope_changed", "Farklı kuruluş için yeni CTI analiz profili oluşturun.")
                organization = connection.execute(
                    "SELECT 1 FROM organizations WHERE id=? AND active=1", (definition["organization_id"],),
                ).fetchone()
                if organization is None:
                    raise CtiAnalysisError("not_found", "CTI analiz kuruluşu bu çalışma alanında etkin değil.")
                if current:
                    connection.execute(
                        f"UPDATE {P}profiles SET name_key=?,definition_json=?,definition_sha256=?,"
                        "revision=revision+1,enabled=?,updated_at=? WHERE id=?",
                        (folded(definition["name"]), canonical(definition), digest(definition),
                         int(values.get("enabled", current["enabled"])), at, identifier),
                    )
                else:
                    try:
                        connection.execute(
                            f"INSERT INTO {P}profiles (id,organization_id,name_key,revision,enabled,"
                            "definition_json,definition_sha256,created_at,updated_at) VALUES (?,?,?,1,1,?,?,?,?)",
                            (identifier, definition["organization_id"], folded(definition["name"]),
                             canonical(definition), digest(definition), at, at),
                        )
                    except sqlite3.IntegrityError as error:
                        raise CtiAnalysisError("already_exists", "Bu kuruluşta aynı adlı CTI analiz profili var.") from error
                result = profile_in(connection, identifier)
            elif name == "review":
                record = candidate_in(connection, identifier)
                if (record["review_revision"] != values["expected_revision"]
                        or record["observation_revision"] != values["expected_observation_revision"]
                        or record["evidence_id"] != values["evidence_id"]):
                    raise CtiAnalysisError("revision_conflict", "CTI analiz adayının kanıtı veya incelemesi değişti.")
                decision = validate_decision(record["kind"], values["decision"])
                revision = record["review_revision"] + 1
                review_id = str(uuid4())
                connection.execute(
                    f"INSERT INTO {P}reviews (id,candidate_id,evidence_id,revision,observation_revision,"
                    "decision,reason,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (review_id, identifier, record["evidence_id"], revision,
                     record["observation_revision"], decision, values["reason"], at),
                )
                connection.execute(
                    f"UPDATE {P}candidates SET review_revision=? WHERE id=?", (revision, identifier),
                )
                result = dict(connection.execute(
                    f"SELECT * FROM {P}reviews WHERE id=?", (review_id,),
                ).fetchone())
            elif name == "recover":
                result = run_in(connection, identifier)
                if result["status"] == "running":
                    report = {"policy": "cti-analysis-v1", "status": "interrupted",
                              "reason": "explicit_operator_recovery", "network_request": False}
                    connection.execute(
                        f"UPDATE {P}runs SET status='interrupted',report_json=?,report_sha256=?,finished_at=? WHERE id=?",
                        (canonical(report), digest(report), at, identifier),
                    )
                    result = run_in(connection, identifier)
            else:
                raise CtiAnalysisError("invalid_parameters", "Bilinmeyen CTI analiz yazma işlemi.")
            connection.execute(
                f"INSERT INTO {P}mutations (id,request_key,request_sha256,result_json,result_sha256,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (str(uuid4()), values["idempotency_key"], self._request(operation, values),
                 canonical(result), digest(result), at),
            )
            return result

    def reserve(self, values: dict, snapshot: dict, at: str) -> tuple[dict, bool]:
        values = parameters(PREFIX + "run", values)
        mention_time(at)
        encoded = canonical(snapshot)
        if len(encoded.encode()) > 64 * 1024 * 1024:
            raise CtiAnalysisError("scope_too_large", "CTI analiz dondurulmuş girdisi 64 MiB sınırını aşıyor.")
        with self.connection(write=True) as connection:
            row = connection.execute(
                f"SELECT id,request_sha256 FROM {P}runs WHERE request_key=?", (values["idempotency_key"],),
            ).fetchone()
            if row:
                if row[1] != self._request(PREFIX + "run", values):
                    raise CtiAnalysisError("idempotency_conflict", "Tekrar anahtarı farklı CTI analiz çalışmasına ait.")
                return public_run(run_in(connection, row[0])), True
            profile = profile_in(connection, values["identifier"])
            if profile["revision"] != values["expected_revision"]:
                raise CtiAnalysisError("revision_conflict", "CTI analiz profili sürümü değişti.")
            if profile["binding_state"] != "ready":
                raise CtiAnalysisError("scope_changed", "CTI analiz profili veya kuruluş kapsamı hazır değil.")
            self._idle(connection, profile["id"])
            if (profile["last_started_at"] and not values.get("force")
                    and datetime.fromisoformat(at) < datetime.fromisoformat(profile["last_started_at"])
                    + timedelta(seconds=profile["definition"]["interval_seconds"])):
                raise CtiAnalysisError("not_due", "CTI analiz çalışma aralığı henüz dolmadı.")
            if (snapshot.get("profile_id"), snapshot.get("profile_revision")) != (profile["id"], profile["revision"]):
                raise StorageError("CTI analiz dondurulmuş profili güncel kapsamla uyuşmuyor.")
            baseline = connection.execute(
                f"SELECT id FROM {P}runs WHERE profile_id=? AND status='complete' ORDER BY sequence DESC LIMIT 1",
                (profile["id"],),
            ).fetchone()
            identifier = str(uuid4())
            connection.execute(
                f"INSERT INTO {P}runs (id,profile_id,request_key,request_sha256,snapshot_json,snapshot_sha256,"
                "input_sha256,status,baseline_run_id,started_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (identifier, profile["id"], values["idempotency_key"], self._request(PREFIX + "run", values),
                 encoded, digest(snapshot), digest({key: value for key, value in snapshot.items() if key != "captured_at"}),
                 "running", baseline[0] if baseline else None, at),
            )
            connection.execute(
                f"UPDATE {P}profiles SET last_started_at=?,last_run_id=? WHERE id=?",
                (at, identifier, profile["id"]),
            )
            return public_run(run_in(connection, identifier)), False

    def finish(self, run_id: str, analysis: dict, at: str) -> dict:
        mention_time(at)
        with self.connection(write=True) as connection:
            run = run_in(connection, run_id)
            if run["status"] != "running":
                raise CtiAnalysisError("run_finished", "CTI analiz çalışması zaten kapatılmış.")
            profile = profile_in(connection, run["profile_id"])
            snapshot = run["snapshot"]
            if profile["revision"] != snapshot["profile_revision"] or profile["binding_state"] != "ready":
                raise CtiAnalysisError("scope_changed", "CTI analiz profili çalışma sırasında değişti; sonuç yayınlanmadı.")
            if (not isinstance(analysis, dict) or analysis.get("policy") != "cti-analysis-v1"
                    or not isinstance(analysis.get("candidates"), list)
                    or len(analysis["candidates"]) > snapshot["definition"]["max_candidates"]):
                raise StorageError("CTI analiz sonucu kapsamı veya biçimi geçersiz.")
            baseline = run["baseline_run_id"] is None
            counts = {"new_candidates": 0, "new_evidence": 0, "changed_candidates": 0,
                      "notifications": 0, "unchanged_candidates": 0}
            seen, prepared = set(), []
            evidence_by_sha = {}
            for item in analysis["candidates"]:
                body = validate_evidence(item["body"])
                if (item.get("candidate_key") != body["candidate_key"] or item.get("kind") != body["kind"]
                        or item.get("score") != body["score"]["value"] or item.get("body_sha256") != digest(body)
                        or item["candidate_key"] in seen):
                    raise StorageError("CTI analiz sonucu yinelenen veya tutarsız aday içeriyor.")
                seen.add(item["candidate_key"])
                prepared.append((item, body))

            stored_evidence = {}
            fingerprints = sorted({item["body_sha256"] for item, _ in prepared})
            for start in range(0, len(fingerprints), 400):
                batch = fingerprints[start:start + 400]
                placeholders = ",".join("?" for _ in batch)
                for row in connection.execute(
                        f"SELECT * FROM {P}evidence WHERE body_sha256 IN ({placeholders})", batch):
                    fingerprint = row["body_sha256"]
                    record = decoded(row, "body")
                    validate_evidence(record["body"])
                    stored_evidence[fingerprint] = record
            old_rows = connection.execute(
                f"SELECT * FROM {P}candidates WHERE profile_id=? ORDER BY sequence LIMIT 10001",
                (run["profile_id"],),
            ).fetchall()
            if len(old_rows) > 10000:
                raise CtiAnalysisError("scope_too_large", "Saklı CTI analiz adayı güvenli sınırı aşıyor.")
            old_by_key = {row["candidate_key"]: row for row in old_rows}
            if len(old_by_key) != len(old_rows):
                raise StorageError("CTI analiz aday anahtarı tekil değil.")
            old_run_ids = sorted({row["last_run_id"] for row in old_rows})
            valid_old_runs = set()
            for start in range(0, len(old_run_ids), 400):
                batch = old_run_ids[start:start + 400]
                placeholders = ",".join("?" for _ in batch)
                valid_old_runs.update(row[0] for row in connection.execute(
                    f"SELECT id FROM {P}runs WHERE id IN ({placeholders}) AND profile_id=? AND status='complete'",
                    (*batch, run["profile_id"]),
                ))
            if set(old_run_ids) != valid_old_runs:
                raise StorageError("CTI analiz adayının son gözlem turu geçersiz.")

            for item, body in prepared:
                fingerprint = item["body_sha256"]
                evidence_record = stored_evidence.get(fingerprint)
                if evidence_record is not None and evidence_record["body"] != body:
                    raise StorageError("CTI analiz kanıt özeti farklı gövdeyle eşleşiyor.")
                evidence_id = evidence_record["id"] if evidence_record else str(uuid4())
                if evidence_record is None:
                    connection.execute(
                        f"INSERT INTO {P}evidence (id,body_json,body_sha256,created_at) VALUES (?,?,?,?)",
                        (evidence_id, canonical(body), fingerprint, at),
                    )
                    stored_evidence[fingerprint] = {"id": evidence_id, "body": body,
                                                    "body_sha256": fingerprint}
                    counts["new_evidence"] += 1
                evidence_by_sha[fingerprint] = evidence_id
                old = old_by_key.get(item["candidate_key"])
                identifier = old["id"] if old else str(uuid4())
                changed = bool(old and old["evidence_id"] != evidence_id)
                if old:
                    old_body = body if not changed else evidence_in(connection, old["evidence_id"])["body"]
                    if (old_body["candidate_key"] != old["candidate_key"]
                            or old_body["kind"] != old["kind"]
                            or old_body["subject"]["kind"] != old["subject_kind"]
                            or old_body["subject"]["id"] != old["subject_id"]
                            or old_body["object"]["kind"] != old["object_kind"]
                            or old_body["object"]["id"] != old["object_id"]
                            or old_body["score"]["value"] != old["score"]
                            or _priority(old["score"]) != old["priority"]):
                        raise StorageError("Saklı CTI analiz adayı özgün kanıtla uyuşmuyor.")
                    connection.execute(
                        f"UPDATE {P}candidates SET evidence_id=?,profile_revision=?,"
                        "last_run_id=?,observation_revision=observation_revision+?,score=?,priority=?,last_seen=? WHERE id=?",
                        (evidence_id, snapshot["profile_revision"], run_id, int(changed),
                         item["score"], _priority(item["score"]), at, identifier),
                    )
                    counts["changed_candidates" if changed else "unchanged_candidates"] += 1
                else:
                    connection.execute(
                        f"INSERT INTO {P}candidates (id,profile_id,candidate_key,kind,subject_kind,subject_id,"
                        "object_kind,object_id,evidence_id,last_run_id,profile_revision,observation_revision,review_revision,"
                        "score,priority,first_seen,last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,1,0,?,?,?,?)",
                        (identifier, run["profile_id"], item["candidate_key"], item["kind"],
                         body["subject"]["kind"], body["subject"]["id"], body["object"]["kind"],
                         body["object"]["id"], evidence_id, run_id, snapshot["profile_revision"], item["score"],
                         _priority(item["score"]), at, at),
                    )
                    counts["new_candidates"] += 1
                if changed or (old is None and not baseline):
                    change_id = str(uuid4())
                    connection.execute(
                        f"INSERT INTO {P}changes (id,profile_id,run_id,candidate_id,kind,before_evidence_id,"
                        "after_evidence_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (change_id, run["profile_id"], run_id, identifier, "changed" if changed else "new",
                         old["evidence_id"] if old else None, evidence_id, at),
                    )
                    if item["score"] >= snapshot["definition"]["alert_score_min"]:
                        from xti.adapters.sqlite_notification_sequence import next_notification_sequence
                        connection.execute(
                            f"INSERT INTO {P}notifications (sequence,id,change_id,created_at) VALUES (?,?,?,?)",
                            (next_notification_sequence(connection), str(uuid4()), change_id, at),
                        )
                        counts["notifications"] += 1

            report = {key: value for key, value in analysis.items() if key != "candidates"}
            graph = dict(report["graph"])
            graph["edges"] = [dict(edge, evidence_id=evidence_by_sha.get(edge["evidence_sha256"])) for edge in graph["edges"]]
            graph["snapshot_sha256"] = digest({key: value for key, value in graph.items() if key != "snapshot_sha256"})
            report["graph"] = graph
            previous = run_in(connection, run["baseline_run_id"])["report"] if run["baseline_run_id"] else None
            coverage_changed = bool(previous and previous.get("source_coverage", {}).get("comparison_sha256")
                                    != report["source_coverage"].get("comparison_sha256"))
            deltas = {kind: report["counts"].get(kind, 0) - (previous or {}).get("counts", {}).get(kind, 0)
                      for kind in report["counts"]}
            change_volume = counts["new_candidates"] + counts["changed_candidates"]
            report["trend"] = {"state": "silent_baseline" if baseline else "coverage_changed" if coverage_changed else "early_warning" if change_volume >= snapshot["definition"]["trend_new_threshold"] else "stable",
                "baseline_run_id": run["baseline_run_id"], "coverage_changed": coverage_changed,
                "candidate_deltas": deltas, "change_volume": change_volume,
                "threshold": snapshot["definition"]["trend_new_threshold"],
                "automatic_incident": False}
            report.update(counts, silent_baseline=baseline, old_evidence_preserved=True,
                          automatic_fact_or_attribution=False)
            report["retained_not_observed_count"] = max(0, connection.execute(
                f"SELECT COUNT(*) FROM {P}candidates WHERE profile_id=?", (run["profile_id"],),
            ).fetchone()[0] - len(seen))
            connection.execute(
                f"UPDATE {P}runs SET status='complete',report_json=?,report_sha256=?,finished_at=? WHERE id=?",
                (canonical(report), digest(report), at, run_id),
            )
            return public_run(run_in(connection, run_id))

    def fail(self, run_id: str, code: str, at: str) -> None:
        with self.connection(write=True) as connection:
            row = connection.execute(
                f"SELECT status FROM {P}runs WHERE id=?", (run_id,),
            ).fetchone()
            if row and row[0] == "running":
                report = {"policy": "cti-analysis-v1", "status": "failed", "error_code": str(code)[:80],
                          "network_request": False, "old_evidence_preserved": True}
                connection.execute(
                    f"UPDATE {P}runs SET status='failed',report_json=?,report_sha256=?,finished_at=? WHERE id=?",
                    (canonical(report), digest(report), at, run_id),
                )

    def _latest_run(self, connection, profile_id: str, run_id: str | None = None) -> dict:
        if run_id:
            run = run_in(connection, run_id)
            if run["profile_id"] != profile_id:
                raise CtiAnalysisError("not_found", "CTI analiz çalışması bu profile ait değil.")
            return run
        row = connection.execute(
            f"SELECT id FROM {P}runs WHERE profile_id=? AND status='complete' ORDER BY sequence DESC LIMIT 1",
            (profile_id,),
        ).fetchone()
        if row is None:
            raise CtiAnalysisError("not_found", "Profil için tamamlanmış CTI analiz çalışması yok.")
        return run_in(connection, row[0])

    def read(self, operation: str, values: dict) -> dict:
        values = parameters(operation, values)
        name = operation.removeprefix(PREFIX)
        with self.connection() as connection:
            if name == "profile.show":
                return profile_in(connection, values["identifier"])
            if name == "plan":
                profile = profile_in(connection, values["identifier"])
                from xti.domain.cti_analysis_jobs import profile_scope_sha256
                return {"profile": profile, "definition": profile["definition"],
                        "organization": profile["organization"], "network_access": False,
                        "cost": "no_external_api", "automatic_verdict": False,
                        "queue_scope_sha256": profile_scope_sha256(profile)}
            if name == "run.show":
                return public_run(run_in(connection, values["identifier"]))
            if name == "candidate.show":
                return candidate_in(connection, values["identifier"])
            if name == "evidence.show":
                return evidence_in(connection, values["identifier"])
            if name in ("graph", "report", "source.quality"):
                profile = profile_in(connection, values["profile_id"])
                if name == "source.quality":
                    return self._source_quality(connection, profile)
                run = self._latest_run(connection, profile["id"], values.get("run_id"))
                if name == "report":
                    candidate_counts = {row[0]: row[1] for row in connection.execute(
                        f"SELECT kind,COUNT(*) FROM {P}candidates WHERE profile_id=? GROUP BY kind",
                        (profile["id"],),
                    )}
                    pending = connection.execute(
                        f"SELECT COUNT(*) FROM {P}candidates WHERE profile_id=? AND (review_revision=0 OR NOT EXISTS "
                        f"(SELECT 1 FROM {P}reviews r WHERE r.candidate_id={P}candidates.id "
                        f"AND r.revision={P}candidates.review_revision AND r.evidence_id={P}candidates.evidence_id "
                        f"AND r.observation_revision={P}candidates.observation_revision))", (profile["id"],),
                    ).fetchone()[0]
                    observation_counts = {row[0]: row[1] for row in connection.execute(
                        f"SELECT CASE WHEN last_run_id=? THEN 'observed_in_latest_complete_run' "
                        f"ELSE 'retained_not_observed_in_latest_complete_run' END,COUNT(*) "
                        f"FROM {P}candidates WHERE profile_id=? GROUP BY 1",
                        (run["id"], profile["id"]),
                    )}
                    return {"profile": profile, "latest_run": public_run(run), "candidate_counts": candidate_counts,
                            "observation_counts": observation_counts,
                            "pending_review_count": pending, "source_quality": self._source_quality(connection, profile),
                            "notes": ["Scores prioritize review; they are not probability or verdict.",
                                      "Missing data does not prove absence or safety."]}
                graph = run["report"]["graph"]
                if values.get("expected_snapshot") and values["expected_snapshot"] != graph["snapshot_sha256"]:
                    raise CtiAnalysisError("snapshot_changed", "CTI graf snapshot'ı değişti; ilk sayfadan yeniden başlayın.")
                nodes = graph["nodes"][values["node_after"]:values["node_after"] + values["node_limit"]]
                edges = graph["edges"][values["edge_after"]:values["edge_after"] + values["edge_limit"]]
                return {"run_id": run["id"], "snapshot_sha256": graph["snapshot_sha256"],
                    "nodes": nodes, "edges": edges,
                    "next_node_after": values["node_after"] + len(nodes) if values["node_after"] + len(nodes) < len(graph["nodes"]) else None,
                    "next_edge_after": values["edge_after"] + len(edges) if values["edge_after"] + len(edges) < len(graph["edges"]) else None,
                    "total_nodes": len(graph["nodes"]), "total_edges": len(graph["edges"]),
                    "truncated": graph["truncated"], "automatic_attribution": False}
            if name in ("timeline", "trends"):
                if not values.get("profile_id"):
                    raise CtiAnalysisError("invalid_parameters", "Zaman görünümü için CTI analiz profili gerekli.")
                if name == "trends":
                    rows = connection.execute(
                        f"SELECT id FROM {P}runs WHERE profile_id=? AND status='complete' AND sequence>? "
                        "ORDER BY sequence LIMIT ?", (values["profile_id"], values["after"], values["limit"] + 1),
                    ).fetchall()
                    more = len(rows) > values["limit"]
                    rows = rows[:values["limit"]]
                    items = [public_run(run_in(connection, row[0])) for row in rows]
                    return {"items": [{"sequence": item["sequence"], "id": item["id"],
                        "finished_at": item["finished_at"], "trend": item["report"]["trend"],
                        "counts": item["report"]["counts"], "source_coverage": item["report"]["source_coverage"]} for item in items],
                        "next_after": items[-1]["sequence"] if more else None}
                run = self._latest_run(connection, values["profile_id"])
                items = run["report"]["timeline"][values["after"]:values["after"] + values["limit"]]
                return {"run_id": run["id"], "items": items,
                        "next_after": values["after"] + len(items) if values["after"] + len(items) < len(run["report"]["timeline"]) else None,
                        "total_count": len(run["report"]["timeline"])}

            table = {"profiles": "profiles", "runs": "runs", "candidates": "candidates",
                     "reviews": "reviews", "changes": "changes"}[name]
            clause, args = "1=1", []
            if "profile_id" in values:
                clause += " AND " + ("id" if table == "profiles" else "profile_id") + "=?"
                args.append(values["profile_id"])
            if name == "reviews":
                clause += " AND candidate_id=?"; args.append(values["identifier"])
            if "kind" in values:
                clause += " AND kind=?"; args.append(values["kind"])
            if "minimum_score" in values and table == "candidates":
                clause += " AND score>=?"; args.append(values["minimum_score"])
            if "decision" in values and table == "candidates":
                clause += f" AND EXISTS (SELECT 1 FROM {P}reviews r WHERE r.candidate_id={P}candidates.id "
                clause += f"AND r.revision={P}candidates.review_revision AND r.decision=?)"; args.append(values["decision"])
            total = connection.execute(f"SELECT COUNT(*) FROM {P + table} WHERE {clause}", args).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM {P + table} WHERE {clause} AND sequence>? ORDER BY sequence LIMIT ?",
                (*args, values["after"], values["limit"] + 1),
            ).fetchall()
            more = len(rows) > values["limit"]
            rows = rows[:values["limit"]]
            loader = {"profiles": profile_in, "runs": run_in, "candidates": candidate_in, "changes": change_in}.get(name)
            items, size = [], 0
            for row in rows:
                item = loader(connection, row["id"]) if loader else dict(row)
                if name == "runs":
                    item = public_run(item)
                encoded = len(canonical(item).encode())
                if items and size + encoded > _MAX_RESPONSE:
                    more = True; break
                items.append(item); size += encoded
            return {"items": items, "total_count": total,
                    "next_after": items[-1]["sequence"] if more and items else None,
                    "page_byte_budget": _MAX_RESPONSE}

    def _source_quality(self, connection, profile: dict) -> dict:
        configured = {folded(item["source_name"]): {**item, "accepted": 0, "rejected": 0,
            "uncertain": 0, "candidate_count": 0} for item in profile["definition"]["source_policies"]}
        rows = connection.execute(
            f"SELECT e.body_json,r.decision FROM {P}candidates c JOIN {P}evidence e ON e.id=c.evidence_id "
            f"LEFT JOIN {P}reviews r ON r.candidate_id=c.id AND r.revision=c.review_revision "
            "WHERE c.profile_id=? ORDER BY c.sequence LIMIT 10001", (profile["id"],),
        ).fetchall()
        if len(rows) > 10000:
            raise CtiAnalysisError("scope_too_large", "Kaynak kalite görünümü 10.000 aday sınırını aşıyor.")
        for raw, decision in rows:
            try:
                body = json.loads(raw)
                validate_evidence(body)
            except (ValueError, RecursionError):
                raise StorageError("Kaynak kalite görünümündeki CTI kanıtı bozuk.") from None
            sources = {anchor["source_name"] for anchor in body["anchors"]}
            for source in sources:
                key = folded(source)
                row = configured.setdefault(key, {"source_name": source, "reliability": 50,
                    "independence_group": key, "accepted": 0, "rejected": 0,
                    "uncertain": 0, "candidate_count": 0})
                row["candidate_count"] += 1
                if decision in ("accepted", "same_entity"):
                    row["accepted"] += 1
                elif decision in ("rejected", "different_entity"):
                    row["rejected"] += 1
                elif decision == "uncertain":
                    row["uncertain"] += 1
        return {"policy": "manual_reliability_plus_review_outcomes_v1",
            "sources": sorted(configured.values(), key=lambda item: folded(item["source_name"])),
            "automatic_reliability_learning": False,
            "meaning": "Analyst outcomes are quality evidence; they do not silently change configured reliability."}

"""P05 immutable claim evidence, review state and pseudonymous credential history."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import re
import sqlite3
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_organization_scope import read_organization_scope
from xti.domain.darkweb_monitoring import (
    ACTIVE_SOURCES,
    DECISIONS,
    KINDS,
    POLICY,
    PREFIX,
    PROFILE_FIELDS,
    SOURCES,
    DarkwebError,
    canonical,
    digest,
    folded,
    parameters,
    profile_definition,
    validate_evidence,
)
from xti.domain.mentions import mention_time


P = "darkweb_"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_FINDINGS = 10_000
MAX_CREDENTIAL_RUNS = 10_000
MAX_CREDENTIAL_ACCOUNTS = 100_000
MAX_CREDENTIAL_CHANGES = 1_000_000
XPOSEDORNOT_DOMAIN_URL = "https://api.xposedornot.com/v1/domain-breaches/"


def _one(connection, table: str, identifier: str) -> dict:
    row = connection.execute(f"SELECT * FROM {P + table} WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise DarkwebError("not_found", "Dark web kaydı bu çalışma alanında bulunamadı.")
    return dict(row)


def _decoded(row, *fields: str) -> dict:
    result = dict(row)
    for field in fields:
        raw, checksum = result.pop(field + "_json"), result.pop(field + "_sha256")
        if raw is None:
            if checksum is not None:
                raise StorageError("Dark web kayıt hash alanları uyuşmuyor.")
            value = None
        else:
            try:
                value = json.loads(raw)
            except (ValueError, RecursionError):
                raise StorageError("Dark web kayıt gövdesi geçersiz.") from None
            if canonical(value) != raw or digest(value) != checksum:
                raise StorageError("Dark web kayıt gövdesi veya hash'i bozuk.")
        result[field] = value
    if "enabled" in result:
        result["enabled"] = bool(result["enabled"])
    if "active" in result:
        result["active"] = bool(result["active"])
    return result


def profile_in(connection, identifier: str) -> dict:
    result = _decoded(_one(connection, "profiles", identifier), "definition")
    definition = profile_definition(result["definition"], allow_legacy=True)
    if (definition != result["definition"] or definition["organization_id"] != result["organization_id"]
            or folded(definition["name"]) != result["name_key"]):
        raise StorageError("Dark web profili kanonik değil.")
    row = connection.execute(
        "SELECT id,display_name,active FROM organizations WHERE id=?", (result["organization_id"],),
    ).fetchone()
    if row is None:
        raise StorageError("Dark web profilinin kuruluş bağı bulunamadı.")
    result["organization"] = {"id": row[0], "display_name": row[1], "active": bool(row[2])}
    result["binding_state"] = (
        "disabled" if not result["enabled"] else
        "organization_disabled" if not row[2] else "ready"
    )
    if result["binding_state"] == "ready" and set(definition["sources"]) - set(ACTIVE_SOURCES):
        result["binding_state"] = "source_retired"
    return result


def run_in(connection, identifier: str) -> dict:
    raw = _one(connection, "runs", identifier)
    snapshot_checksum = raw["snapshot_sha256"]
    result = _decoded(raw, "snapshot", "report")
    snapshot = result["snapshot"]
    if (not isinstance(snapshot, dict) or snapshot.get("profile_id") != result["profile_id"]
            or digest(snapshot) != snapshot_checksum):
        raise StorageError("Dark web çalışma kapsamı bozuk.")
    return result


def run_state_in(connection, identifier: str) -> dict:
    row = connection.execute(
        f"SELECT id,profile_id,status,started_at,finished_at FROM {P}runs WHERE id=?", (identifier,),
    ).fetchone()
    if row is None:
        raise DarkwebError("not_found", "Dark web çalışması bu alanda bulunamadı.")
    return dict(row)


def public_run(record: dict) -> dict:
    snapshot = record["snapshot"]
    result = {key: value for key, value in record.items() if key != "snapshot"}
    result["snapshot"] = {
        "policy": snapshot.get("policy"), "profile_id": snapshot.get("profile_id"),
        "profile_revision": snapshot.get("profile_revision"),
        "captured_at": snapshot.get("captured_at"), "definition": snapshot.get("definition"),
        "organization": snapshot.get("organization"),
        "target_count": len(snapshot.get("targets", [])),
        "sources": [{key: value for key, value in source.items() if key != "records"}
                    | {"record_count": len(source.get("records", []))}
                    for source in snapshot.get("sources", [])],
        "frozen_input_available": True,
    }
    return result


def evidence_in(connection, identifier: str) -> dict:
    result = _decoded(_one(connection, "evidence", identifier), "body")
    validate_evidence(result["body"])
    return result


def finding_in(connection, identifier: str) -> dict:
    result = _one(connection, "findings", identifier)
    evidence = evidence_in(connection, result["evidence_id"])
    body = evidence["body"]
    if (body["candidate_key"] != result["candidate_key"] or body["kind"] != result["kind"]
            or body["target"]["kind"] != result["target_kind"]
            or body["target"]["id"] != result["target_id"]
            or body["source"]["key"] != result["source_key"]
            or body["priority"] != result["priority"]):
        raise StorageError("Dark web bulgusu özgün kanıtıyla uyuşmuyor.")
    result["evidence"] = evidence
    row = connection.execute(
        f"SELECT * FROM {P}reviews WHERE finding_id=? ORDER BY revision DESC LIMIT 1", (identifier,),
    ).fetchone()
    result["review"] = dict(row) if row else None
    if (result["review"]["revision"] if result["review"] else 0) != result["review_revision"]:
        raise StorageError("Dark web inceleme sürümü bozuk.")
    review = result["review"]
    result["needs_review"] = (
        review is None or review["evidence_id"] != result["evidence_id"]
        or review["observation_revision"] != result["observation_revision"]
    )
    profile = profile_in(connection, result["profile_id"])
    observed = run_state_in(connection, result["last_run_id"])
    if observed["profile_id"] != result["profile_id"] or observed["status"] != "complete":
        raise StorageError("Dark web bulgusunun son gözlem turu geçersiz.")
    latest = run_state_in(connection, profile["last_run_id"]) if profile["last_run_id"] else None
    if latest and latest["id"] == result["last_run_id"] and latest["status"] == "complete":
        result["observation_state"] = "observed_in_latest_complete_run"
    elif latest and latest["status"] != "complete":
        result["observation_state"] = "latest_run_" + latest["status"] + "_previous_observation_retained"
    else:
        result["observation_state"] = "retained_not_observed_in_latest_complete_run"
    result["scope_current"] = profile["revision"] == result["profile_revision"] and profile["binding_state"] == "ready"
    return result


def change_in(connection, identifier: str) -> dict:
    result = _one(connection, "changes", identifier)
    result["before"] = evidence_in(connection, result["before_evidence_id"]) if result["before_evidence_id"] else None
    result["after"] = evidence_in(connection, result["after_evidence_id"])
    return result


def credential_account_in(connection, identifier: str, *, internal: bool = False) -> dict:
    result = _decoded(_one(connection, "credential_accounts", identifier), "breaches")
    safe = {"identity_hmac": result["identity_hmac"], "masked_account": result["masked_account"],
            "domain": result["domain"], "breaches": result["breaches"]}
    if digest(safe) != result["state_sha256"]:
        raise StorageError("Credential hesap kanıtı bozuk.")
    if not internal:
        result.pop("identity_hmac", None)
    return result


def _credential_state(raw: str | None, checksum: str | None) -> dict | None:
    if raw is None:
        if checksum is not None:
            raise StorageError("Credential değişiklik hash alanları uyuşmuyor.")
        return None
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        raise StorageError("Credential değişiklik gövdesi geçersiz.") from None
    if canonical(value) != raw or digest(value) != checksum:
        raise StorageError("Credential değişiklik gövdesi veya özeti bozuk.")
    expected = {
        "identity_hmac", "masked_account", "domain", "breaches", "state_sha256", "active",
    }
    safe = {key: value.get(key) for key in (
        "identity_hmac", "masked_account", "domain", "breaches",
    )}
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or not re.fullmatch(r"[0-9a-f]{64}", str(value["identity_hmac"]))
        or not isinstance(value["masked_account"], str)
        or "*" not in value["masked_account"]
        or "@" not in value["masked_account"]
        or not isinstance(value["breaches"], list)
        or value["breaches"] != sorted(set(value["breaches"]), key=folded)
        or value["state_sha256"] != digest(safe)
        or type(value["active"]) is not bool
    ):
        raise StorageError("Credential değişiklik kanıtı güvenli biçimde doğrulanamadı.")
    return value


def credential_run_in(connection, identifier: str) -> dict:
    result = _one(connection, "credential_runs", identifier)
    if result["status"] == "running" and (result["finished_at"] is not None or result["chain_sha256"] is not None):
        raise StorageError("Çalışan credential turu kapanış alanı içeriyor.")
    if result["status"] != "running" and (result["finished_at"] is None or result["chain_sha256"] is None):
        raise StorageError("Kapanmış credential turunun bütünlük alanı eksik.")
    if result["status"] != "running":
        previous = connection.execute(
            f"SELECT chain_sha256 FROM {P}credential_runs WHERE organization_id=? "
            "AND status!='running' AND sequence<? ORDER BY sequence DESC LIMIT 1",
            (result["organization_id"], result["sequence"]),
        ).fetchone()
        changes = []
        for row in connection.execute(
            f"SELECT account_id,action,before_json,before_sha256,after_json,after_sha256 "
            f"FROM {P}credential_changes WHERE run_id=? ORDER BY sequence", (identifier,),
        ):
            changes.append({
                "account_id": row[0], "action": row[1],
                "before": _credential_state(row[2], row[3]),
                "after": _credential_state(row[4], row[5]),
            })
        expected = _credential_chain(previous[0] if previous else None, result, changes)
        if expected != result["chain_sha256"]:
            raise StorageError("Credential çalışma geçmişi bütünlük zinciriyle uyuşmuyor.")
    return result


def _account_state(record: dict, *, active: bool) -> dict:
    return {
        "identity_hmac": record["identity_hmac"], "masked_account": record["masked_account"],
        "domain": record["domain"], "breaches": record["breaches"],
        "state_sha256": record["state_sha256"], "active": bool(active),
    }


def _credential_chain(previous: str | None, run: dict, changes: list[dict]) -> str:
    body = {key: run.get(key) for key in (
        "id", "profile_id", "organization_id", "domain", "provider", "request_sha256",
        "source_url", "status", "content_sha256", "snapshot_sha256", "account_count",
        "added_count", "updated_count", "unchanged_count", "removed_count", "error_code",
        "error", "started_at", "finished_at", "fetched_at",
    )}
    policy = (
        "hibp-domain-history-v1"
        if run.get("provider") == "hibp_domain"
        else "xposedornot-domain-history-v1"
    )
    return digest({"policy": policy, "previous": previous,
                   "run": body, "changes": changes})


def notification_in(connection, identifier: str) -> dict:
    previous = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        notice = _one(connection, "notifications", identifier)
        change = change_in(connection, notice["change_id"])
        finding = finding_in(connection, change["finding_id"])
        if finding["profile_id"] != change["profile_id"]:
            raise StorageError("Dark web bildiriminin kapsamı uyuşmuyor.")
        return {"id": identifier, "change": change, "finding": finding,
                "before": change["before"], "after": change["after"]}
    finally:
        connection.row_factory = previous


class SQLiteDarkwebRepository:
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

    @staticmethod
    def _idle(connection, profile_id: str) -> None:
        if connection.execute(
            f"SELECT 1 FROM {P}runs WHERE profile_id=? AND status='running' LIMIT 1", (profile_id,),
        ).fetchone():
            raise DarkwebError("run_in_progress", "Dark web çalışması sürüyor; durmuş çalışmayı önce kurtarın.")

    @staticmethod
    def _credential_idle(connection, organization_id: str) -> None:
        if connection.execute(
            f"SELECT 1 FROM {P}credential_runs WHERE organization_id=? AND status='running' LIMIT 1",
            (organization_id,),
        ).fetchone():
            raise DarkwebError("run_in_progress", "Kuruluş için credential kaynak çalışması sürüyor.")

    def _mutation_replay(self, connection, operation: str, values: dict):
        row = connection.execute(
            f"SELECT * FROM {P}mutations WHERE request_key=?", (values["idempotency_key"],),
        ).fetchone()
        if row is None:
            return None
        if row["request_sha256"] != self._request(operation, values):
            raise DarkwebError("idempotency_conflict", "Tekrar anahtarı farklı dark web isteğinde kullanılmış.")
        return _decoded(row, "result")["result"]

    def plan(self, identifier: str) -> dict:
        with self.connection() as connection:
            profile = profile_in(connection, identifier)
            if profile["binding_state"] == "source_retired":
                raise DarkwebError(
                    "source_retired",
                    "Profil devre dışı bırakılmış HIBP kaynağı içeriyor; "
                    "kaynakları XposedOrNot veya diğer etkin kaynaklarla güncelleyin.",
                )
            return {"profile": profile, "definition": profile["definition"],
                    "organization": profile["organization"], "network_access": False,
                    "inputs": ["stored_ransomware", "stored_public_breaches", "stored_masked_credentials"]}

    def replay(self, values: dict) -> dict | None:
        values = parameters(PREFIX + "run", values)
        with self.connection() as connection:
            row = connection.execute(
                f"SELECT id,request_sha256 FROM {P}runs WHERE request_key=?", (values["idempotency_key"],),
            ).fetchone()
            if row is None:
                return None
            if row[1] != self._request(PREFIX + "run", values):
                raise DarkwebError("idempotency_conflict", "Tekrar anahtarı farklı dark web çalışmasına ait.")
            return public_run(run_in(connection, row[0]))

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
                current = profile_in(connection, identifier) if name == "profile.update" else None
                if current:
                    if current["revision"] != values["expected_revision"]:
                        raise DarkwebError("revision_conflict", "Dark web profil sürümü değişti.")
                    self._idle(connection, identifier)
                    self._credential_idle(connection, current["organization_id"])
                definition = profile_definition({
                    **(current["definition"] if current else {}),
                    **{key: value for key, value in values.items() if key in PROFILE_FIELDS},
                })
                if current and definition["organization_id"] != current["organization_id"]:
                    raise DarkwebError("scope_changed", "Farklı kuruluş için yeni dark web profili oluşturun.")
                organization = connection.execute(
                    "SELECT 1 FROM organizations WHERE id=? AND active=1", (definition["organization_id"],),
                ).fetchone()
                if organization is None:
                    raise DarkwebError("not_found", "Dark web izleme kuruluşu etkin değil veya bulunamadı.")
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
                            "definition_json,definition_sha256,created_at,updated_at) "
                            "VALUES (?,?,?,1,1,?,?,?,?)",
                            (identifier, definition["organization_id"], folded(definition["name"]),
                             canonical(definition), digest(definition), at, at),
                        )
                    except sqlite3.IntegrityError as error:
                        raise DarkwebError("already_exists", "Bu kuruluşta aynı adlı dark web profili var.") from error
                result = profile_in(connection, identifier)
            elif name == "review":
                record = finding_in(connection, identifier)
                if (record["review_revision"] != values["expected_revision"]
                        or record["observation_revision"] != values["expected_observation_revision"]
                        or record["evidence_id"] != values["evidence_id"]):
                    raise DarkwebError("revision_conflict", "Dark web bulgusunun kanıtı veya incelemesi değişti.")
                if values["decision"] not in DECISIONS:
                    raise DarkwebError("invalid_parameters", "Dark web inceleme kararı bilinmiyor.")
                revision = record["review_revision"] + 1
                review_id = str(uuid4())
                connection.execute(
                    f"INSERT INTO {P}reviews (id,finding_id,evidence_id,revision,observation_revision,"
                    "decision,reason,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (review_id, identifier, record["evidence_id"], revision,
                     record["observation_revision"], values["decision"], values["reason"], at),
                )
                connection.execute(
                    f"UPDATE {P}findings SET review_revision=? WHERE id=?", (revision, identifier),
                )
                result = dict(connection.execute(
                    f"SELECT * FROM {P}reviews WHERE id=?", (review_id,),
                ).fetchone())
            elif name == "recover":
                row = connection.execute(
                    f"SELECT 'analysis' AS kind,id,status FROM {P}runs WHERE id=? UNION ALL "
                    f"SELECT 'credential',id,status FROM {P}credential_runs WHERE id=?",
                    (identifier, identifier),
                ).fetchone()
                if row is None:
                    raise DarkwebError("not_found", "Kurtarılacak dark web çalışması bulunamadı.")
                if row["kind"] == "analysis":
                    result = run_in(connection, identifier)
                    if result["status"] == "running":
                        report = {"policy": POLICY, "status": "interrupted",
                                  "reason": "explicit_operator_recovery", "old_evidence_preserved": True}
                        connection.execute(
                            f"UPDATE {P}runs SET status='interrupted',report_json=?,report_sha256=?,"
                            "finished_at=? WHERE id=?", (canonical(report), digest(report), at, identifier),
                        )
                        result = run_in(connection, identifier)
                else:
                    result = credential_run_in(connection, identifier)
                    if result["status"] == "running":
                        previous = connection.execute(
                            f"SELECT chain_sha256 FROM {P}credential_runs WHERE organization_id=? "
                            "AND status!='running' AND sequence<? ORDER BY sequence DESC LIMIT 1",
                            (result["organization_id"], result["sequence"]),
                        ).fetchone()
                        closed = {**result, "status": "interrupted", "finished_at": at,
                                  "error_code": "explicit_operator_recovery",
                                  "error": "Operatör tamamlanmamış credential turunu kapattı."}
                        chain = _credential_chain(previous[0] if previous else None, closed, [])
                        connection.execute(
                            f"UPDATE {P}credential_runs SET status='interrupted',finished_at=?,"
                            "error_code=?,error=?,chain_sha256=? WHERE id=?",
                            (at, closed["error_code"], closed["error"], chain, identifier),
                        )
                        result = credential_run_in(connection, identifier)
            else:
                raise DarkwebError("invalid_parameters", "Bilinmeyen dark web yazma işlemi.")
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
        if len(encoded.encode("ascii")) > 64 * 1024 * 1024:
            raise DarkwebError("scope_too_large", "Dark web dondurulmuş girdisi 64 MiB sınırını aşıyor.")
        with self.connection(write=True) as connection:
            row = connection.execute(
                f"SELECT id,request_sha256 FROM {P}runs WHERE request_key=?", (values["idempotency_key"],),
            ).fetchone()
            if row:
                if row[1] != self._request(PREFIX + "run", values):
                    raise DarkwebError("idempotency_conflict", "Tekrar anahtarı farklı dark web çalışmasına ait.")
                return public_run(run_in(connection, row[0])), True
            profile = profile_in(connection, values["identifier"])
            if profile["revision"] != values["expected_revision"]:
                raise DarkwebError("revision_conflict", "Dark web profil sürümü değişti.")
            if profile["binding_state"] != "ready":
                raise DarkwebError("scope_changed", "Dark web profili veya kuruluş kapsamı hazır değil.")
            self._idle(connection, profile["id"])
            if (profile["last_started_at"] and not values.get("force")
                    and datetime.fromisoformat(at) < datetime.fromisoformat(profile["last_started_at"])
                    + timedelta(seconds=profile["definition"]["interval_seconds"])):
                raise DarkwebError("not_due", "Dark web profilinin çalışma aralığı henüz dolmadı.")
            if (snapshot.get("profile_id"), snapshot.get("profile_revision")) != (profile["id"], profile["revision"]):
                raise StorageError("Dark web dondurulmuş profili güncel kapsamla uyuşmuyor.")
            baseline = connection.execute(
                f"SELECT id FROM {P}runs WHERE profile_id=? AND status='complete' ORDER BY sequence DESC LIMIT 1",
                (profile["id"],),
            ).fetchone()
            identifier = str(uuid4())
            connection.execute(
                f"INSERT INTO {P}runs (id,profile_id,request_key,request_sha256,snapshot_json,"
                "snapshot_sha256,status,baseline_run_id,started_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (identifier, profile["id"], values["idempotency_key"],
                 self._request(PREFIX + "run", values), encoded, digest(snapshot), "running",
                 baseline[0] if baseline else None, at),
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
                raise DarkwebError("run_finished", "Dark web çalışması zaten kapatılmış.")
            profile = profile_in(connection, run["profile_id"])
            snapshot = run["snapshot"]
            if profile["revision"] != snapshot["profile_revision"] or profile["binding_state"] != "ready":
                raise DarkwebError("scope_changed", "Dark web profili çalışma sırasında değişti; sonuç yayınlanmadı.")
            if (not isinstance(analysis, dict) or analysis.get("policy") != POLICY
                    or not isinstance(analysis.get("candidates"), list)
                    or len(analysis["candidates"]) > profile["definition"]["max_findings"]):
                raise StorageError("Dark web analiz sonucu geçersiz veya güvenli sınırı aşıyor.")
            prepared, keys = [], set()
            for item in analysis["candidates"]:
                if (not isinstance(item, dict)
                        or set(item) != {"candidate_key", "kind", "priority", "body", "body_sha256"}):
                    raise StorageError("Dark web aday sonucu geçersiz.")
                body = validate_evidence(item["body"])
                if (item["candidate_key"] != body["candidate_key"]
                        or item["kind"] != body["kind"] or item["priority"] != body["priority"]
                        or item["body_sha256"] != digest(body) or item["candidate_key"] in keys):
                    raise StorageError("Dark web aday kanıt bağı bozuk veya yineleniyor.")
                keys.add(item["candidate_key"])
                prepared.append((item, body))
            old_rows = connection.execute(
                f"SELECT * FROM {P}findings WHERE profile_id=? ORDER BY sequence LIMIT ?",
                (run["profile_id"], MAX_FINDINGS + 1),
            ).fetchall()
            if len(old_rows) > MAX_FINDINGS:
                raise DarkwebError("scope_too_large", "Saklı dark web bulgusu 10.000 sınırını aşıyor.")
            old_by_key = {row["candidate_key"]: row for row in old_rows}
            if len(old_by_key) != len(old_rows):
                raise StorageError("Dark web aday anahtarı tekil değil.")
            counts = {"new_findings": 0, "changed_findings": 0, "unchanged_findings": 0,
                      "new_evidence": 0, "notifications": 0}
            baseline = run["baseline_run_id"] is None
            for item, body in prepared:
                stored = connection.execute(
                    f"SELECT * FROM {P}evidence WHERE body_sha256=?", (item["body_sha256"],),
                ).fetchone()
                if stored:
                    evidence = _decoded(stored, "body")
                    if evidence["body"] != body:
                        raise StorageError("Dark web kanıt özeti farklı gövdeyle eşleşiyor.")
                    evidence_id = evidence["id"]
                else:
                    evidence_id = str(uuid4())
                    connection.execute(
                        f"INSERT INTO {P}evidence (id,body_json,body_sha256,created_at) VALUES (?,?,?,?)",
                        (evidence_id, canonical(body), item["body_sha256"], at),
                    )
                    counts["new_evidence"] += 1
                old = old_by_key.get(item["candidate_key"])
                finding_id = old["id"] if old else str(uuid4())
                changed = bool(old and old["evidence_id"] != evidence_id)
                if old:
                    old_body = evidence_in(connection, old["evidence_id"])["body"]
                    if (old_body["candidate_key"] != old["candidate_key"]
                            or old_body["kind"] != old["kind"]
                            or old_body["target"]["kind"] != old["target_kind"]
                            or old_body["target"]["id"] != old["target_id"]
                            or old_body["source"]["key"] != old["source_key"]):
                        raise StorageError("Saklı dark web bulgusu özgün kanıtıyla uyuşmuyor.")
                    connection.execute(
                        f"UPDATE {P}findings SET evidence_id=?,last_run_id=?,profile_revision=?,"
                        "observation_revision=observation_revision+?,priority=?,last_seen=? WHERE id=?",
                        (evidence_id, run_id, snapshot["profile_revision"], int(changed),
                         item["priority"], at, finding_id),
                    )
                    counts["changed_findings" if changed else "unchanged_findings"] += 1
                else:
                    connection.execute(
                        f"INSERT INTO {P}findings (id,profile_id,candidate_key,kind,target_kind,target_id,"
                        "source_key,evidence_id,last_run_id,profile_revision,observation_revision,"
                        "review_revision,priority,first_seen,last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,1,0,?,?,?)",
                        (finding_id, run["profile_id"], item["candidate_key"], item["kind"],
                         body["target"]["kind"], body["target"]["id"], body["source"]["key"],
                         evidence_id, run_id, snapshot["profile_revision"], item["priority"], at, at),
                    )
                    counts["new_findings"] += 1
                if changed or (old is None and not baseline):
                    change_id = str(uuid4())
                    connection.execute(
                        f"INSERT INTO {P}changes (id,profile_id,run_id,finding_id,kind,before_evidence_id,"
                        "after_evidence_id,created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (change_id, run["profile_id"], run_id, finding_id,
                         "changed" if changed else "new", old["evidence_id"] if old else None,
                         evidence_id, at),
                    )
                    if item["priority"] in snapshot["definition"]["alert_priorities"]:
                        from xti.adapters.sqlite_notification_sequence import next_notification_sequence
                        connection.execute(
                            f"INSERT INTO {P}notifications (sequence,id,change_id,created_at) VALUES (?,?,?,?)",
                            (next_notification_sequence(connection), str(uuid4()), change_id, at),
                        )
                        counts["notifications"] += 1
            report = {key: value for key, value in analysis.items() if key != "candidates"}
            report.update(counts, silent_baseline=baseline, old_evidence_preserved=True,
                          automatic_incident=False)
            report["retained_not_observed_count"] = max(0, connection.execute(
                f"SELECT COUNT(*) FROM {P}findings WHERE profile_id=?", (run["profile_id"],),
            ).fetchone()[0] - len(keys))
            connection.execute(
                f"UPDATE {P}runs SET status='complete',report_json=?,report_sha256=?,finished_at=? WHERE id=?",
                (canonical(report), digest(report), at, run_id),
            )
            return public_run(run_in(connection, run_id))

    def fail(self, run_id: str, code: str, at: str) -> None:
        mention_time(at)
        with self.connection(write=True) as connection:
            row = connection.execute(f"SELECT status FROM {P}runs WHERE id=?", (run_id,)).fetchone()
            if row and row[0] == "running":
                report = {"policy": POLICY, "status": "failed", "error_code": str(code)[:80],
                          "old_evidence_preserved": True, "network_request": False}
                connection.execute(
                    f"UPDATE {P}runs SET status='failed',report_json=?,report_sha256=?,finished_at=? WHERE id=?",
                    (canonical(report), digest(report), at, run_id),
                )

    def credential_plan(self, identifier: str, domain: str) -> dict:
        with self.connection() as connection:
            profile = profile_in(connection, identifier)
            if profile["binding_state"] != "ready":
                raise DarkwebError("scope_changed", "Credential profili veya kuruluş kapsamı hazır değil.")
            if "xposedornot_domain" not in profile["definition"]["sources"]:
                raise DarkwebError(
                    "source_disabled",
                    "Profilde XposedOrNot verified-domain kaynağı seçili değil.",
                )
            scope = read_organization_scope(connection, profile["organization_id"])
            domains = sorted(target.value for target in scope.effective_targets if target.kind == "domain")
            if domain not in domains:
                raise DarkwebError(
                    "scope_mismatch",
                    "Credential sorgusu yalnız kuruluşun etkin, açıkça bağlı domaininde çalışabilir.",
                )
            return {"profile": profile, "organization": profile["organization"],
                    "domain": domain, "provider": "xposedornot_domain",
                    "source_url": XPOSEDORNOT_DOMAIN_URL,
                    "network_access": True, "requires_verified_domain": True,
                    "raw_alias_persistence": False}

    def reserve_credentials(self, plan: dict, request_key: str, at: str) -> tuple[dict, bool]:
        mention_time(at)
        request = {"operation": PREFIX + "credential.refresh", "profile_id": plan["profile"]["id"],
                   "profile_revision": plan["profile"]["revision"], "domain": plan["domain"],
                   "request_key": request_key}
        request_sha = digest(request)
        with self.connection(write=True) as connection:
            row = connection.execute(
                f"SELECT * FROM {P}credential_runs WHERE request_key=?", (request_key,),
            ).fetchone()
            if row:
                if row["request_sha256"] != request_sha:
                    raise DarkwebError("idempotency_conflict", "Tekrar anahtarı farklı credential isteğinde kullanılmış.")
                return credential_run_in(connection, row["id"]), True
            profile = profile_in(connection, plan["profile"]["id"])
            if (profile["revision"] != plan["profile"]["revision"]
                    or profile["organization_id"] != plan["organization"]["id"]
                    or profile["binding_state"] != "ready"):
                raise DarkwebError("scope_changed", "Credential profili rezervasyon öncesinde değişti.")
            if connection.execute(
                f"SELECT COUNT(*) FROM {P}credential_runs WHERE organization_id=?",
                (profile["organization_id"],),
            ).fetchone()[0] >= MAX_CREDENTIAL_RUNS:
                raise DarkwebError("capacity_exceeded", "Credential çalışma geçmişi 10.000 kayıt sınırına ulaştı.")
            self._credential_idle(connection, profile["organization_id"])
            identifier = str(uuid4())
            connection.execute(
                f"INSERT INTO {P}credential_runs (id,profile_id,organization_id,domain,provider,request_key,"
                "request_sha256,source_url,status,account_count,added_count,updated_count,unchanged_count,"
                "removed_count,started_at) VALUES (?,?,?,?,?,?,?,?, 'running',0,0,0,0,0,?)",
                (identifier, profile["id"], profile["organization_id"], plan["domain"],
                 "xposedornot_domain", request_key, request_sha,
                 XPOSEDORNOT_DOMAIN_URL, at),
            )
            return credential_run_in(connection, identifier), False

    def credential_replay(self, plan: dict, request_key: str) -> dict | None:
        request = {"operation": PREFIX + "credential.refresh", "profile_id": plan["profile"]["id"],
                   "profile_revision": plan["profile"]["revision"], "domain": plan["domain"],
                   "request_key": request_key}
        with self.connection() as connection:
            row = connection.execute(
                f"SELECT id,request_sha256 FROM {P}credential_runs WHERE request_key=?", (request_key,),
            ).fetchone()
            if row is None:
                return None
            if row["request_sha256"] != digest(request):
                raise DarkwebError("idempotency_conflict", "Tekrar anahtarı farklı credential isteğinde kullanılmış.")
            return credential_run_in(connection, row["id"])

    @staticmethod
    def _validate_credential_records(records: list[dict], *, domain: str) -> list[dict]:
        if not isinstance(records, list) or len(records) > 50_000:
            raise StorageError("Credential kaynak sonucu 50.000 hesap sınırını aşıyor.")
        prepared, identities = [], set()
        for record in records:
            if (not isinstance(record, dict)
                    or set(record) != {"identity_hmac", "masked_account", "domain", "breaches", "state_sha256"}
                    or record["domain"] != domain
                    or not re.fullmatch(r"[0-9a-f]{64}", str(record["identity_hmac"]))
                    or not isinstance(record["masked_account"], str)
                    or "*" not in record["masked_account"] or not record["masked_account"].endswith("@" + domain)
                    or not isinstance(record["breaches"], list)
                    or not 1 <= len(record["breaches"]) <= 500
                    or record["breaches"] != sorted(set(record["breaches"]), key=folded)
                    or record["state_sha256"] != digest({key: record[key] for key in
                        ("identity_hmac", "masked_account", "domain", "breaches")})
                    or record["identity_hmac"] in identities):
                raise StorageError("Credential pseudonym kaydı geçersiz veya yineleniyor.")
            identities.add(record["identity_hmac"])
            prepared.append(record)
        return sorted(prepared, key=lambda item: item["identity_hmac"])

    def finish_credentials(self, run_id: str, response: dict, records: list[dict], at: str) -> dict:
        mention_time(at)
        with self.connection(write=True) as connection:
            run = credential_run_in(connection, run_id)
            if run["status"] != "running":
                raise DarkwebError("run_finished", "Credential kaynak çalışması zaten kapatılmış.")
            profile = profile_in(connection, run["profile_id"])
            if profile["binding_state"] != "ready" or profile["organization_id"] != run["organization_id"]:
                raise DarkwebError("scope_changed", "Credential profili çalışma sırasında değişti; sonuç yayınlanmadı.")
            if (not isinstance(response, dict)
                    or set(response) != {"provider", "domain", "source_url", "fetched_at", "content_sha256"}
                    or response["provider"] != "xposedornot_domain"
                    or response["domain"] != run["domain"]
                    or response["source_url"] != XPOSEDORNOT_DOMAIN_URL
                    or not re.fullmatch(r"[0-9a-f]{64}", str(response["content_sha256"]))):
                raise StorageError("Credential kaynak makbuzu beklenen kapsamla uyuşmuyor.")
            mention_time(response["fetched_at"])
            records = self._validate_credential_records(records, domain=run["domain"])
            old_rows = connection.execute(
                f"SELECT id FROM {P}credential_accounts WHERE organization_id=? AND domain=? "
                "ORDER BY sequence LIMIT ?",
                (run["organization_id"], run["domain"], MAX_CREDENTIAL_ACCOUNTS + 1),
            ).fetchall()
            if len(old_rows) > MAX_CREDENTIAL_ACCOUNTS:
                raise DarkwebError("capacity_exceeded", "Credential hesap geçmişi 100.000 kayıt sınırını aşıyor.")
            old_records = [credential_account_in(connection, row[0], internal=True) for row in old_rows]
            old_by_identity = {item["identity_hmac"]: item for item in old_records}
            if len(old_by_identity) != len(old_records):
                raise StorageError("Credential pseudonym kimlikleri tekil değil.")
            new_by_identity = {item["identity_hmac"]: item for item in records}
            newly_allocated = sum(identity not in old_by_identity for identity in new_by_identity)
            if len(old_records) + newly_allocated > MAX_CREDENTIAL_ACCOUNTS:
                raise DarkwebError("capacity_exceeded", "Credential hesap geçmişi 100.000 kayıt sınırına ulaşıyor.")
            planned_changes = sum(
                1 for identity, item in new_by_identity.items()
                if identity not in old_by_identity or not old_by_identity[identity]["active"]
                or old_by_identity[identity]["state_sha256"] != item["state_sha256"]
            ) + sum(item["active"] and identity not in new_by_identity
                    for identity, item in old_by_identity.items())
            change_count = connection.execute(
                f"SELECT COUNT(*) FROM {P}credential_changes",
            ).fetchone()[0]
            if change_count + planned_changes > MAX_CREDENTIAL_CHANGES:
                raise DarkwebError("capacity_exceeded", "Credential değişiklik geçmişi kapasitesine ulaştı.")

            changes, counts = [], {"added": 0, "updated": 0, "unchanged": 0, "removed": 0}
            for identity, record in new_by_identity.items():
                old = old_by_identity.get(identity)
                breaches_json = canonical(record["breaches"])
                if old is None:
                    account_id, action = str(uuid4()), "added"
                    connection.execute(
                        f"INSERT INTO {P}credential_accounts (id,organization_id,domain,identity_hmac,"
                        "masked_account,breaches_json,breaches_sha256,state_sha256,active,first_run_id,"
                        "last_run_id,first_seen,last_seen) VALUES (?,?,?,?,?,?,?,?,1,?,?,?,?)",
                        (account_id, run["organization_id"], run["domain"], identity,
                         record["masked_account"], breaches_json, digest(record["breaches"]),
                         record["state_sha256"], run_id, run_id, at, at),
                    )
                    before = None
                elif not old["active"] or old["state_sha256"] != record["state_sha256"]:
                    account_id, action = old["id"], "updated"
                    before = _account_state(old, active=old["active"])
                    connection.execute(
                        f"UPDATE {P}credential_accounts SET masked_account=?,breaches_json=?,breaches_sha256=?,"
                        "state_sha256=?,active=1,last_run_id=?,last_seen=? WHERE id=?",
                        (record["masked_account"], breaches_json, digest(record["breaches"]),
                         record["state_sha256"], run_id, at, account_id),
                    )
                else:
                    counts["unchanged"] += 1
                    connection.execute(
                        f"UPDATE {P}credential_accounts SET last_run_id=?,last_seen=? WHERE id=?",
                        (run_id, at, old["id"]),
                    )
                    continue
                after = _account_state(record, active=True)
                changes.append({"account_id": account_id, "action": action,
                                "before": before, "after": after})
                counts[action] += 1
            for identity, old in old_by_identity.items():
                if old["active"] and identity not in new_by_identity:
                    before = _account_state(old, active=True)
                    after = _account_state(old, active=False)
                    connection.execute(
                        f"UPDATE {P}credential_accounts SET active=0,last_run_id=? WHERE id=?",
                        (run_id, old["id"]),
                    )
                    changes.append({"account_id": old["id"], "action": "removed",
                                    "before": before, "after": after})
                    counts["removed"] += 1
            for change in changes:
                before, after = change["before"], change["after"]
                connection.execute(
                    f"INSERT INTO {P}credential_changes (id,run_id,account_id,action,before_json,"
                    "before_sha256,after_json,after_sha256,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (str(uuid4()), run_id, change["account_id"], change["action"],
                     canonical(before) if before is not None else None,
                     digest(before) if before is not None else None,
                     canonical(after) if after is not None else None,
                     digest(after) if after is not None else None, at),
                )
            active_snapshot = sorted(
                [_account_state(record, active=True) for record in new_by_identity.values()],
                key=lambda item: item["identity_hmac"],
            )
            closed = {**run, "status": "complete", "content_sha256": response["content_sha256"],
                      "snapshot_sha256": digest(active_snapshot), "account_count": len(records),
                      "added_count": counts["added"], "updated_count": counts["updated"],
                      "unchanged_count": counts["unchanged"], "removed_count": counts["removed"],
                      "error_code": None, "error": None, "finished_at": at,
                      "fetched_at": response["fetched_at"]}
            previous = connection.execute(
                f"SELECT chain_sha256 FROM {P}credential_runs WHERE organization_id=? "
                "AND status!='running' AND sequence<? ORDER BY sequence DESC LIMIT 1",
                (run["organization_id"], run["sequence"]),
            ).fetchone()
            chain_changes = [{key: change[key] for key in ("account_id", "action", "before", "after")}
                             for change in changes]
            chain = _credential_chain(previous[0] if previous else None, closed, chain_changes)
            connection.execute(
                f"UPDATE {P}credential_runs SET status='complete',content_sha256=?,snapshot_sha256=?,"
                "account_count=?,added_count=?,updated_count=?,unchanged_count=?,removed_count=?,"
                "finished_at=?,fetched_at=?,chain_sha256=? WHERE id=?",
                (closed["content_sha256"], closed["snapshot_sha256"], closed["account_count"],
                 counts["added"], counts["updated"], counts["unchanged"], counts["removed"],
                 at, response["fetched_at"], chain, run_id),
            )
            return credential_run_in(connection, run_id)

    def fail_credentials(self, run_id: str, code: str, message: str, at: str) -> dict:
        mention_time(at)
        code = str(code)[:80]
        message = " ".join(str(message).split())[:500]
        with self.connection(write=True) as connection:
            run = credential_run_in(connection, run_id)
            if run["status"] != "running":
                return run
            closed = {**run, "status": "failed", "error_code": code,
                      "error": message, "finished_at": at}
            previous = connection.execute(
                f"SELECT chain_sha256 FROM {P}credential_runs WHERE organization_id=? "
                "AND status!='running' AND sequence<? ORDER BY sequence DESC LIMIT 1",
                (run["organization_id"], run["sequence"]),
            ).fetchone()
            chain = _credential_chain(previous[0] if previous else None, closed, [])
            connection.execute(
                f"UPDATE {P}credential_runs SET status='failed',error_code=?,error=?,finished_at=?,"
                "chain_sha256=? WHERE id=?", (code, message, at, chain, run_id),
            )
            return credential_run_in(connection, run_id)

    def _latest_run(self, connection, profile_id: str, run_id: str | None = None) -> dict:
        if run_id:
            run = run_in(connection, run_id)
            if run["profile_id"] != profile_id:
                raise DarkwebError("not_found", "Dark web çalışması bu profile ait değil.")
            return run
        row = connection.execute(
            f"SELECT id FROM {P}runs WHERE profile_id=? AND status='complete' "
            "ORDER BY sequence DESC LIMIT 1", (profile_id,),
        ).fetchone()
        if row is None:
            raise DarkwebError("not_found", "Profil için tamamlanmış dark web çalışması yok.")
        return run_in(connection, row[0])

    @staticmethod
    def capabilities() -> dict:
        return {
            "contract_version": 1, "policy": POLICY,
            "sources": [
                {"id": "ransomlook", "class": "public_ransomware_claims", "network_in_run": False,
                 "commercial_default": True, "license_review_required": True},
                {"id": "threatcluster", "class": "public_ransomware_claims", "network_in_run": False,
                 "commercial_default": False, "written_provider_permission_required": True},
                {"id": "xposedornot_domain", "class": "verified_domain_credential_exposure",
                 "network_in_run": True, "api_key_and_verified_domain_required": True,
                 "free_personal_low_volume": True,
                 "commercial_terms_review_required": True,
                 "raw_alias_persistence": False},
            ],
            "kinds": list(KINDS), "decisions": list(DECISIONS),
            "reads": list(__import__("xti.domain.darkweb_monitoring", fromlist=["READS"]).READS),
            "writes": list(__import__("xti.domain.darkweb_monitoring", fromlist=["WRITES"]).WRITES),
            "limits": {"findings_per_profile": MAX_FINDINGS,
                       "credential_accounts_per_organization_domain": MAX_CREDENTIAL_ACCOUNTS,
                       "credential_runs_per_organization": MAX_CREDENTIAL_RUNS},
            "password_check": {
                "provider": "xposedornot_passwords",
                "persistence": False,
                "plaintext_transmitted": False,
                "full_hash_transmitted": False,
                "prefix_characters_transmitted": 10,
                "terminal_secret_input": True,
            },
            "automatic_incident": False,
            "notes": [
                "Public source claims are review candidates, not verified breaches.",
                "XposedOrNot verified-domain addresses are pseudonymized in memory before storage.",
                "No password, token, cookie, raw email alias or leak-site content is stored.",
                "Legacy HIBP records remain readable but HIBP is not an active profile source.",
            ],
        }

    def read(self, operation: str, values: dict) -> dict:
        values = parameters(operation, values)
        name = operation.removeprefix(PREFIX)
        if name == "capabilities":
            return self.capabilities()
        with self.connection() as connection:
            if name == "profile.show":
                return profile_in(connection, values["identifier"])
            if name == "plan":
                profile = profile_in(connection, values["identifier"])
                from xti.domain.darkweb_jobs import profile_scope_sha256
                domains = sorted(target.value for target in
                                 read_organization_scope(connection, profile["organization_id"]).effective_targets
                                 if target.kind == "domain")
                return {"profile": profile, "network_access": False,
                        "queue_scope_sha256": profile_scope_sha256(profile),
                        "selected_sources": profile["definition"]["sources"],
                        "organization_domains": domains,
                        "credential_source": {
                            "provider": "xposedornot_domain",
                            "selected": "xposedornot_domain" in profile["definition"]["sources"],
                            "network_access_only_on_explicit_refresh": True,
                            "verified_domain_required": True,
                        }, "automatic_incident": False}
            if name == "run.show":
                return public_run(run_in(connection, values["identifier"]))
            if name == "finding.show":
                return finding_in(connection, values["identifier"])
            if name == "evidence.show":
                return evidence_in(connection, values["identifier"])
            if name == "credential.run.show":
                return credential_run_in(connection, values["identifier"])
            if name == "report":
                profile = profile_in(connection, values["profile_id"])
                run = self._latest_run(connection, profile["id"], values.get("run_id"))
                counts = {row[0]: row[1] for row in connection.execute(
                    f"SELECT kind,COUNT(*) FROM {P}findings WHERE profile_id=? GROUP BY kind",
                    (profile["id"],),
                )}
                pending = connection.execute(
                    f"SELECT COUNT(*) FROM {P}findings f WHERE profile_id=? AND (review_revision=0 OR "
                    f"NOT EXISTS (SELECT 1 FROM {P}reviews r WHERE r.finding_id=f.id "
                    "AND r.revision=f.review_revision AND r.evidence_id=f.evidence_id "
                    "AND r.observation_revision=f.observation_revision))", (profile["id"],),
                ).fetchone()[0]
                observations = {row[0]: row[1] for row in connection.execute(
                    f"SELECT CASE WHEN last_run_id=? THEN 'observed_in_latest_complete_run' "
                    "ELSE 'retained_not_observed_in_latest_complete_run' END,COUNT(*) "
                    f"FROM {P}findings WHERE profile_id=? GROUP BY 1", (run["id"], profile["id"]),
                )}
                latest_credential = connection.execute(
                    f"SELECT id FROM {P}credential_runs WHERE profile_id=? ORDER BY sequence DESC LIMIT 1",
                    (profile["id"],),
                ).fetchone()
                return {"profile": profile, "latest_run": public_run(run), "finding_counts": counts,
                        "observation_counts": observations, "pending_review_count": pending,
                        "latest_credential_run": credential_run_in(connection, latest_credential[0])
                            if latest_credential else None,
                        "automatic_incident": False,
                        "notes": ["Claims and exposure metadata require analyst review.",
                                  "Missing results do not prove absence or safety."]}

            tables = {"profiles": "profiles", "runs": "runs", "findings": "findings",
                      "reviews": "reviews", "changes": "changes",
                      "credential.runs": "credential_runs"}
            table = tables.get(name)
            if table is None:
                raise DarkwebError("invalid_parameters", "Bilinmeyen dark web okuma işlemi.")
            clause, args = "1=1", []
            if "profile_id" in values:
                clause += " AND " + ("id" if table == "profiles" else "profile_id") + "=?"
                args.append(values["profile_id"])
            if name == "reviews":
                clause += " AND finding_id=?"
                args.append(values["identifier"])
            if name == "findings":
                for key in ("kind", "priority", "target_kind"):
                    if key in values:
                        clause += " AND " + key + "=?"
                        args.append(values[key])
                if "decision" in values:
                    clause += (f" AND EXISTS (SELECT 1 FROM {P}reviews r WHERE r.finding_id={P}findings.id "
                               f"AND r.revision={P}findings.review_revision AND r.decision=?)")
                    args.append(values["decision"])
            total = connection.execute(
                f"SELECT COUNT(*) FROM {P + table} WHERE {clause}", args,
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM {P + table} WHERE {clause} AND sequence>? ORDER BY sequence LIMIT ?",
                (*args, values["after"], values["limit"] + 1),
            ).fetchall()
            more = len(rows) > values["limit"]
            rows = rows[:values["limit"]]
            loader = {"profiles": profile_in, "runs": run_in, "findings": finding_in,
                      "changes": change_in, "credential.runs": credential_run_in}.get(name)
            items, size = [], 0
            for row in rows:
                item = loader(connection, row["id"]) if loader else dict(row)
                if name == "runs":
                    item = public_run(item)
                encoded = len(canonical(item).encode("ascii"))
                if items and size + encoded > MAX_RESPONSE_BYTES:
                    more = True
                    break
                items.append(item)
                size += encoded
            return {"items": items, "total_count": total,
                    "next_after": items[-1]["sequence"] if more and items else None,
                    "page_byte_budget": MAX_RESPONSE_BYTES}


def company_in(connection, organization_id: str, *, offset: int = 0, limit: int = 20) -> dict:
    previous = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        effective = min(limit, 100)
        profile_rows = connection.execute(
            f"SELECT id FROM {P}profiles WHERE organization_id=? ORDER BY sequence DESC LIMIT ? OFFSET ?",
            (organization_id, effective, offset),
        ).fetchall()
        profile_total = connection.execute(
            f"SELECT COUNT(*) FROM {P}profiles WHERE organization_id=?", (organization_id,),
        ).fetchone()[0]
        finding_rows = connection.execute(
            f"SELECT id FROM {P}findings WHERE profile_id IN "
            f"(SELECT id FROM {P}profiles WHERE organization_id=?) "
            "ORDER BY sequence DESC LIMIT ? OFFSET ?", (organization_id, effective + 1, offset),
        ).fetchall()
        total = connection.execute(
            f"SELECT COUNT(*) FROM {P}findings WHERE profile_id IN "
            f"(SELECT id FROM {P}profiles WHERE organization_id=?)", (organization_id,),
        ).fetchone()[0]
        profiles = []
        for row in profile_rows:
            profile = profile_in(connection, row[0])
            latest = run_in(connection, profile["last_run_id"]) if profile["last_run_id"] else None
            credential = connection.execute(
                f"SELECT id FROM {P}credential_runs WHERE profile_id=? ORDER BY sequence DESC LIMIT 1",
                (profile["id"],),
            ).fetchone()
            profiles.append({"id": profile["id"], "name": profile["definition"]["name"],
                "revision": profile["revision"], "binding_state": profile["binding_state"],
                "last_run_id": latest["id"] if latest else None,
                "last_status": latest["status"] if latest else "not_checked",
                "last_checked_at": (latest["finished_at"] or latest["started_at"]) if latest else None,
                "source_coverage": (latest.get("report") or {}).get("source_coverage") if latest else None,
                "credential_status": credential_run_in(connection, credential[0]) if credential else None})
        items, byte_count = [], 0
        for row in finding_rows[:effective]:
            item = finding_in(connection, row[0])
            size = len(canonical(item).encode("ascii"))
            if items and byte_count + size > MAX_RESPONSE_BYTES:
                break
            items.append(item)
            byte_count += size
        return {"state": "recorded" if total else "no_recorded_findings" if profile_total else "not_configured",
                "items": items, "total_count": total, "offset": offset, "limit": effective,
                "has_more": total > offset + len(items), "page_byte_budget": MAX_RESPONSE_BYTES,
                "profiles": {"items": profiles, "total_count": profile_total, "offset": offset,
                             "limit": effective, "has_more": profile_total > offset + len(profiles)}}
    finally:
        connection.row_factory = previous


def case_snapshot(connection, identifier: str):
    from xti.domain.cases import CaseEvidenceSnapshot, canonical_snapshot
    previous = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        record = finding_in(connection, identifier)
        payload, checksum = canonical_snapshot({"version": 1, "type": "darkweb_monitoring", "finding": record})
        body = record["evidence"]["body"]
        title = body["target"]["label"] + " — " + body["kind"].replace("_", " ")
        return CaseEvidenceSnapshot("darkweb_monitoring", identifier, title[:240],
            "darkweb finding-show " + identifier, payload, checksum)
    finally:
        connection.row_factory = previous


def validate_case_snapshot(value):
    try:
        if (set(value) != {"version", "type", "finding"} or value["version"] != 1
                or value["type"] != "darkweb_monitoring"):
            raise ValueError()
        record = value["finding"]
        body = validate_evidence(record["evidence"]["body"])
        if (record["evidence_id"] != record["evidence"]["id"]
                or record["candidate_key"] != body["candidate_key"]
                or record["kind"] != body["kind"]):
            raise ValueError()
        return value
    except (KeyError, TypeError, ValueError):
        raise StorageError("Dark web vaka kopyası geçersiz.") from None

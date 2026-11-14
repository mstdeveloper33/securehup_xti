"""Atomic source-result attachment. Call only inside the source write transaction."""

from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime, timezone
import json

from xti.adapters.sqlite import StorageError
from xti.domain.assets import ValidationError
from xti.domain.brand_username import BRAND_USERNAME_SOURCE_NAMES
from xti.domain.brand_username_watches import brand_watch_definition_sha256
from xti.domain.collection_profiles import definition_sha256, parse_definition_json
from xti.domain.collection_history import (
    CollectionOperationToken, CollectionStepReceipt, RESULT_KINDS, RESULT_STATUSES,
    canonical_json, history_sha256, history_uuid, parse_plan_json, plan_sha256,
    sha256_text, unit_sha256, username_contract,
)
from xti.domain.cti_feeds import CTI_FEED_POLICIES
from xti.domain.public_notices import (
    HIBP_ATTRIBUTION, HIBP_CONTRACT_VERSION, HIBP_LICENSE, HIBP_SOURCE_NAME, HIBP_SOURCE_URL,
)
from xti.domain.ransomlook_ransomware import RANSOMLOOK_SOURCE_NAME
from xti.domain.ransomlook_watches import ransomlook_watch_definition_sha256, ransomlook_watch_query_key
from xti.domain.ransomware_claims import RANSOMWARE_SOURCE_NAME
from xti.domain.ransomware_watches import ransomware_watch_definition_sha256, ransomware_watch_query_key

RESULT_TABLES = {
    "scan_attempt": "scan_attempts", "discovery_run": "surface_discovery_runs",
    "feed_run": "cti_feed_runs", "username_run": "brand_username_watch_runs",
    "public_notice_run": "public_notice_runs",
    "threatcluster_source_run": "ransomware_claim_runs", "ransomlook_source_run": "ransomlook_claim_runs",
    "threatcluster_watch_run": "ransomware_watch_runs", "ransomlook_watch_run": "ransomlook_watch_runs",
}
REFERENCE_COLUMNS = tuple(kind + "_id" for kind in RESULT_KINDS)


def canonical_time(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValidationError("Toplama kayıt zamanı geçersiz.")
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone required")
        canonical = parsed.astimezone(timezone.utc).isoformat()
        if canonical != value:
            raise ValueError("UTC canonical time required")
        return canonical
    except (ValueError, TypeError, OverflowError) as error:
        raise ValidationError("Toplama kayıt zamanı kanonik UTC olmalı.") from error


def _row(connection, table: str, key: str, *, column: str = "id") -> dict:
    # table/column are always internal literals or RESULT_TABLES entries.
    cursor = connection.execute(f"SELECT * FROM {table} WHERE {column}=?", (key,))
    values = cursor.fetchone()
    if values is None:
        raise StorageError("Toplama kanıtının bağlı kaydı bulunamadı.")
    return dict(zip((item[0] for item in cursor.description), values))


def _write_transaction(connection) -> None:
    if not connection.in_transaction:
        raise StorageError("Toplama kanıtı kaynak işlemiyle aynı transaction içinde yazılmalı.")


def operation_context(connection, operation: CollectionOperationToken, *, allow_pending: bool = False):
    if not isinstance(operation, CollectionOperationToken):
        raise ValidationError("Geçerli toplama işlem kimliği gerekli.")
    history_uuid(operation.session_id)
    history_uuid(operation.step_id)
    history_sha256(operation.target_sha256)
    if operation.depends_on_step_id is not None:
        history_uuid(operation.depends_on_step_id)
    session = _row(connection, "collection_sessions", operation.session_id)
    step = _row(connection, "collection_session_steps", operation.step_id)
    try:
        definition = parse_definition_json(session["definition_json"])
        plan = parse_plan_json(session["plan_json"], definition)
        unit = next(unit for unit in plan.units if unit.step_key == step["step_key"])
        if (
            session["status"] != "running" or session["finished_at"] is not None
            or step["session_id"] != session["id"]
            or step["status"] not in ({"pending", "running"} if allow_pending else {"running"})
            or step["finished_at"] is not None
            or definition_sha256(definition) != session["definition_sha256"]
            or plan_sha256(plan) != session["plan_sha256"]
            or step["target_sha256"] != unit_sha256(unit)
            or operation.target_sha256 != step["target_sha256"]
            or operation.depends_on_step_id != step["depends_on_step_id"]
            or (step["kind"], step["source"], step["watch_id"]) != (
                unit.kind, unit.source, unit.watch.watch_id if unit.watch else None,
            )
            or connection.execute("SELECT 1 FROM collection_step_receipts WHERE step_id=?", (step["id"],)).fetchone()
        ):
            raise ValueError("operation mismatch")
        return session, step, unit, plan
    except (ValueError, TypeError, KeyError, StopIteration) as error:
        raise StorageError("Toplama işlem kimliği güncel açık adımla uyuşmuyor.") from error


def _public_notice_unit(unit, definition, step) -> None:
    if (
        (unit.step_key, unit.kind, unit.source, unit.contract_version)
        != ("notices-hibp", "public_notice", "hibp", HIBP_CONTRACT_VERSION)
        or unit.asset_value != definition.asset_value or unit.watch is not None
        or "notices-hibp" not in definition.task_ids
        or (step["step_key"], step["kind"], step["source"])
        != (unit.step_key, unit.kind, unit.source)
        or step["watch_id"] is not None or step["depends_on_step_id"] is not None
        or step["scan_job_id"] is not None
    ):
        raise StorageError("Toplama kamu kataloğu hedefi veya kaynak sözleşmesi uyuşmuyor.")


def validate_public_notice_operation(connection, operation: CollectionOperationToken | None) -> None:
    """Read-only preflight, repeated inside the later source transaction."""
    if operation is None:
        return
    session, step, unit, plan = operation_context(connection, operation)
    _public_notice_unit(unit, plan.definition, step)
    # Full session validation also binds profile origins, resume ancestors and
    # earlier receipts. Import lazily: the history reader uses source_result.
    from xti.adapters.sqlite_collection_history import SQLiteCollectionHistoryRepository
    details = SQLiteCollectionHistoryRepository._details(connection, session["id"])
    SQLiteCollectionHistoryRepository._current_origin(connection, plan)
    if (details.session.plan != plan
            or not any(item.id == operation.step_id and item.status == "running" for item in details.steps)
            or not connection.execute("SELECT 1 FROM assets WHERE value=?", (plan.definition.asset_value,)).fetchone()):
        raise StorageError("Toplama kamu kataloğu işlemi etkin oturum kapsamıyla uyuşmuyor.")


def source_result(connection, unit, definition, step, *, result_kind: str, result_id: str, result_status: str):
    """Validate the exact durable source row and derive bounded receipt counters."""
    if result_kind not in RESULT_TABLES or result_status not in RESULT_STATUSES:
        raise StorageError("Toplama kaynak sonuç türü geçersiz.")
    history_uuid(result_id)
    expected_kind = {
        "scan": "scan_attempt", "discovery": "discovery_run", "ioc": "feed_run",
        "username_watch": "username_run", "public_notice": "public_notice_run", "ransomware_refresh": f"{unit.source}_source_run",
        "ransomware_watch": f"{unit.source}_watch_run",
    }.get(unit.kind)
    if result_kind != expected_kind:
        raise StorageError("Toplama kaynak sonucu seçilen birime ait değil.")
    row = _row(connection, RESULT_TABLES[result_kind], result_id)
    if result_kind == "public_notice_run":
        _public_notice_unit(unit, definition, step)
        from xti.adapters.sqlite_public_notices import read_public_notice_history
        history = read_public_notice_history(connection)
        run = next((item for item in history.runs if item.id == result_id), None)
        if (run is None or run.status != result_status or run.status not in {"complete", "failed"}
                or (history.source_name, history.source_url, history.attribution, history.license)
                != (HIBP_SOURCE_NAME, HIBP_SOURCE_URL, HIBP_ATTRIBUTION, HIBP_LICENSE)
                or step["started_at"] is None
                or datetime.fromisoformat(run.started_at) < datetime.fromisoformat(canonical_time(step["started_at"]))):
            raise StorageError("Toplama kamu kataloğu sonucu gerçek kaynak/süreç kanıtıyla uyuşmuyor.")
        counters = {key: value for key, value in asdict(run).items() if key.endswith("_count")}
        counters["is_baseline"] = int(run.status == "complete" and not any(
            previous.status == "complete" and previous.sequence < run.sequence for previous in history.runs
        ))
        recorded_at = run.finished_at
    elif result_kind == "scan_attempt":
        # Lazy import avoids a cycle: source adapters import this helper.
        from xti.adapters.sqlite_jobs import SQLiteJobRepository
        attempt = SQLiteJobRepository._get_attempt(connection, result_id)
        job = SQLiteJobRepository._get_job(connection, attempt.job_id)
        if (
            step["scan_job_id"] != job.id or job.provider != unit.source
            or job.targets != (definition.asset_value,) or job.typos != definition.typos
            or job.rule_version != unit.contract_version or attempt.status != result_status
            or job.status != result_status or attempt.finished_at is None
            or (result_status in {"complete", "partial"} and attempt.result is None)
            or (attempt.result is not None and attempt.result.targets != job.targets)
        ):
            raise StorageError("Toplama arama sonucu iş/hedef/sözleşme bağıyla uyuşmuyor.")
        counters = {"query_count": len(attempt.queries)}
        if attempt.result is not None:
            counters.update(asdict(attempt.result.summary))
            counters["candidate_count"] = len(attempt.result.candidate_domains)
        recorded_at = attempt.finished_at
    else:
        actual_status = row.get("status", "complete")
        if actual_status != result_status:
            raise StorageError("Toplama sonucu gerçek kaynak durumuyla uyuşmuyor.")
        counters = {key: value for key, value in row.items() if key.endswith("_count")}
        if result_kind == "discovery_run":
            if row["asset_value"] != definition.asset_value or row["provider"] != unit.source:
                raise StorageError("Toplama pasif keşif sonucu seçilen domaine ait değil.")
            counters.update({key: row[key] for key in (
                "skipped_names", "ignored_names", "candidates_created", "candidates_existing", "evidence_created", "evidence_existing",
            )})
            recorded_at = row["finished_at"]
        elif result_kind == "feed_run":
            if row["source_name"] != CTI_FEED_POLICIES[unit.source].source_name:
                raise StorageError("Toplama IOC sonucu seçilen kaynağa ait değil.")
            recorded_at = row["finished_at"]
        elif result_kind == "username_run":
            watch = unit.watch
            expected_hash = brand_watch_definition_sha256(username=watch.query, platforms=watch.platforms)
            if (
                row["watch_id"] != watch.watch_id or row["username"] != watch.query
                or json.loads(row["platforms_json"]) != list(watch.platforms)
                or row["source_name"] != BRAND_USERNAME_SOURCE_NAMES[unit.source]
                or username_contract(row["source_version"], row["integration_profile"]) != unit.contract_version
                or row["definition_sha256"] != expected_hash
            ):
                raise StorageError("Toplama sosyal sonucu dondurulmuş izleme/sözleşmeyle uyuşmuyor.")
            recorded_at = row["recorded_at"]
        elif unit.kind == "ransomware_refresh":
            expected_source = RANSOMWARE_SOURCE_NAME if unit.source == "threatcluster" else RANSOMLOOK_SOURCE_NAME
            if row["source_name"] != expected_source:
                raise StorageError("Toplama ransomware yenilemesi seçilen kaynağa ait değil.")
            recorded_at = row["finished_at"]
        else:
            watch = unit.watch
            expected_hash = (
                ransomware_watch_definition_sha256(
                    query=watch.query, query_key=ransomware_watch_query_key(watch.query, kind=watch.kind),
                    kind=watch.kind, match_mode=watch.match_mode,
                ) if unit.source == "threatcluster" else ransomlook_watch_definition_sha256(
                    query=watch.query, query_key=ransomlook_watch_query_key(watch.query), match_mode=watch.match_mode,
                )
            )
            dependency = _row(connection, "collection_session_steps", step["depends_on_step_id"])
            receipt = _row(connection, "collection_step_receipts", dependency["id"], column="step_id")
            if (
                row["watch_id"] != watch.watch_id or row["definition_sha256"] != expected_hash
                or dependency["session_id"] != step["session_id"]
                or dependency["kind"] != "ransomware_refresh" or dependency["source"] != unit.source
                or dependency["status"] != "complete" or receipt["result_status"] != "complete"
                or row["source_run_id"] != receipt[f"{unit.source}_source_run_id"]
            ):
                raise StorageError("Toplama ransomware üyesi aynı yürütmenin başarılı yenilemesine bağlı değil.")
            recorded_at = row["executed_at"]
    canonical_time(recorded_at)
    if len(counters) > 25 or any(type(value) is not int or not 0 <= value <= 2**63-1 for value in counters.values()):
        raise StorageError("Toplama kaynak sonuç sayaçları geçersiz.")
    return recorded_at, tuple(sorted(counters.items()))


def receipt_source_metadata(result_kind: str) -> dict[str, str]:
    if result_kind != "public_notice_run":
        return {}
    return {"source_attribution": HIBP_ATTRIBUTION, "source_license": HIBP_LICENSE,
            "source_scope": "global-catalog"}


def summary_json(counters) -> str:
    return canonical_json({"version": 1, "counters": dict(counters)})


def record_collection_step_receipt(
    connection, operation: CollectionOperationToken | None, *, result_kind: str,
    result_id: str, result_status: str, summary: Mapping[str, int] | None = None,
) -> CollectionStepReceipt | None:
    if operation is None:
        return None
    _write_transaction(connection)
    session, step, unit, plan = operation_context(connection, operation)
    try:
        recorded_at, counters = source_result(
            connection, unit, plan.definition, step,
            result_kind=result_kind, result_id=result_id, result_status=result_status,
        )
        if summary is not None and (not isinstance(summary, Mapping) or dict(summary) != dict(counters)):
            raise ValueError("summary mismatch")
        encoded = summary_json(counters)
        digest = sha256_text(encoded)
        connection.execute(
            "INSERT INTO collection_step_receipts "
            f"(step_id, recorded_at, result_status, summary_json, summary_sha256, {result_kind}_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (step["id"], recorded_at, result_status, encoded, digest, result_id),
        )
        error_code = {"complete": None, "partial": "source_partial", "failed": "source_failed", "interrupted": "interrupted"}[result_status]
        updated = connection.execute(
            "UPDATE collection_session_steps SET status=?, finished_at=?, error_code=? "
            "WHERE id=? AND session_id=? AND status='running'",
            (result_status, recorded_at, error_code, step["id"], session["id"]),
        )
        if updated.rowcount != 1:
            raise ValueError("step already finished")
        source_run_id = (
            _row(connection, RESULT_TABLES[result_kind], result_id)["source_run_id"]
            if unit.kind == "ransomware_watch" else None
        )
        return CollectionStepReceipt(step["id"], recorded_at, result_status, result_kind, result_id, counters, digest, source_run_id,
                                     **receipt_source_metadata(result_kind))
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise StorageError("Toplama kaynak kanıtı doğrulanamadı; kaynak yazımı geri alınmalı.") from error


# Descriptive alias for callers that already use finish terminology.
finish_collection_step = record_collection_step_receipt


def bind_collection_scan_job(connection, operation: CollectionOperationToken | None, job_id: str) -> None:
    if operation is None:
        return
    _write_transaction(connection)
    _, step, unit, plan = operation_context(connection, operation)
    row = _row(connection, "scan_jobs", history_uuid(job_id))
    if (
        unit.kind != "scan" or step["scan_job_id"] is not None
        or row["provider"] != unit.source or row["rule_version"] != unit.contract_version
        or json.loads(row["targets"]) != [plan.definition.asset_value]
        or row["typos"] != int(plan.definition.typos)
        or row["status"] != "queued" or row["attempt_count"] != 0
    ):
        raise StorageError("Toplama arama işi dondurulmuş adıma bağlanamıyor.")
    connection.execute("UPDATE collection_session_steps SET scan_job_id=? WHERE id=? AND scan_job_id IS NULL", (job_id, step["id"]))


def collection_scan_job_owned(connection, job_id: str) -> bool:
    return connection.execute("SELECT 1 FROM collection_session_steps WHERE scan_job_id=?", (job_id,)).fetchone() is not None


def assert_collection_scan_job_owner(connection, job_id: str, operation: CollectionOperationToken | None = None) -> None:
    row = connection.execute("SELECT id FROM collection_session_steps WHERE scan_job_id=?", (job_id,)).fetchone()
    if row is None:
        if operation is not None:
            raise ValidationError("Arama işi belirtilen toplama adımına ait değil.")
        return
    if operation is None or row[0] != operation.step_id:
        raise ValidationError("Bu iş bir toplama oturumuna ait; ayrı kuyruk işçisi çalıştıramaz.")
    _, step, unit, _ = operation_context(connection, operation)
    if unit.kind != "scan" or step["scan_job_id"] != job_id:
        raise ValidationError("Arama işi toplama işlem kimliğiyle uyuşmuyor.")

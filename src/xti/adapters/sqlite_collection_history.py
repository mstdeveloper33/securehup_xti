"""Explicit collection sessions, bounded linear resume chains and recovery."""

from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
import json
from uuid import uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.adapters.sqlite_collection_profiles import SQLiteCollectionProfileRepository
from xti.adapters.sqlite_collection_receipts import (
    REFERENCE_COLUMNS, RESULT_TABLES, _row, canonical_time, operation_context,
    source_result, summary_json,
)
from xti.domain.assets import ValidationError
from xti.domain.collection_profiles import (
    CollectionProfile, canonical_definition_json, definition_sha256, parse_definition_json,
)
from xti.domain.collection_history import (
    ANALYSIS_STATUSES, MAX_COLLECTION_GENERATIONS, SESSION_STATUSES, STEP_STATUSES, STOP_CODES,
    CollectionFrozenPlan, CollectionOperationToken, CollectionProfileOrigin,
    CollectionRetainedResult, CollectionResumePlan, CollectionSession, CollectionSessionDetails,
    CollectionSessionPage, CollectionSessionStep, CollectionStepReceipt,
    canonical_plan_json, history_sha256, history_uuid, normalize_frozen_plan,
    parse_plan_json, plan_sha256, resume_units, sha256_text, unit_sha256,
)

MAX_SESSIONS = 10_000


def _integer(value, *, maximum=2**63-1):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError("invalid positive integer")
    return value


def _optional_time(value):
    return None if value is None else canonical_time(value)


class SQLiteCollectionHistoryRepository:
    def __init__(self, path: Path):
        self._storage = SQLiteAssetRepository(path)

    @contextmanager
    def _write(self):
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _session(row):
        try:
            definition = parse_definition_json(row["definition_json"])
            plan = parse_plan_json(row["plan_json"], definition)
            record = CollectionSession(
                _integer(row["sequence"]), history_uuid(row["id"]), history_uuid(row["root_id"]),
                history_uuid(row["parent_id"]) if row["parent_id"] is not None else None,
                _integer(row["generation"], maximum=MAX_COLLECTION_GENERATIONS),
                history_uuid(row["profile_event_id"]) if row["profile_event_id"] is not None else None,
                plan, history_sha256(row["definition_sha256"]), history_sha256(row["plan_sha256"]),
                row["status"], canonical_time(row["started_at"]), _optional_time(row["finished_at"]),
                row["stop_reason"], row["analysis_status"], _optional_time(row["analysis_recorded_at"]),
            )
            if (
                record.definition_sha256 != definition_sha256(definition)
                or record.plan_sha256 != plan_sha256(plan)
                or row["executor_contract_version"] != plan.executor_contract_version
                or record.profile_event_id != (plan.origin.event_id if plan.origin else None)
                or record.status not in SESSION_STATUSES or record.analysis_status not in ANALYSIS_STATUSES
                or (record.status == "running") != (record.finished_at is None)
                or (record.analysis_status == "pending") != (record.analysis_recorded_at is None)
                or (record.stop_reason is not None and record.stop_reason not in STOP_CODES)
                or (record.status == "running" and (record.stop_reason is not None or record.analysis_status != "pending"))
            ):
                raise ValueError("invalid session state")
            return record
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            raise StorageError("Toplama oturum kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _profile_origin_event(connection, origin, definition):
        if origin is None:
            return
        _row(connection, "collection_profiles", origin.profile_id)
        row = _row(connection, "collection_profile_events", origin.event_id)
        if (
            row["profile_id"] != origin.profile_id or row["revision"] != origin.revision
            or row["display_name"] != origin.display_name or row["action"] == "revoked"
            or row["definition_sha256"] != origin.definition_sha256
            or parse_definition_json(row["definition_json"]) != definition
            or definition_sha256(definition) != origin.definition_sha256
        ):
            raise StorageError("Toplama oturumunun profil revizyonu geçmişle uyuşmuyor.")

    @classmethod
    def _current_origin(cls, connection, plan):
        origin = plan.origin
        if origin is None:
            return
        cls._profile_origin_event(connection, origin, plan.definition)
        profiles, _ = SQLiteCollectionProfileRepository._audit(connection)
        profile = profiles.get(origin.profile_id)
        if (
            profile is None or not profile.active or profile.revision != origin.revision
            or profile.display_name != origin.display_name or profile.definition != plan.definition
            or profile.definition_sha256 != origin.definition_sha256
        ):
            raise ValidationError("Kaynak toplama profili değişmiş veya geri çekilmiş; güncel seçimle yeni çalışma başlatın.")

    def profile_origin(self, profile: CollectionProfile) -> CollectionProfileOrigin:
        if not isinstance(profile, CollectionProfile):
            raise ValidationError("Geçerli toplama profili gerekli.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            profiles, events = SQLiteCollectionProfileRepository._audit(connection)
            if profiles.get(profile.id) != profile or not profile.active:
                raise ValidationError("Toplama profili değişmiş veya geri çekilmiş.")
            event = next(event for event in events if event.profile_id == profile.id and event.revision == profile.revision)
            return CollectionProfileOrigin(event.id, profile.id, profile.display_name, profile.revision, profile.definition_sha256)

    @staticmethod
    def _current_units(connection, units):
        for unit in units:
            if unit.watch is None:
                continue
            watch = unit.watch
            table = {
                "username_watch": "brand_username_watches",
                "threatcluster": "ransomware_watches", "ransomlook": "ransomlook_watches",
            }["username_watch" if unit.kind == "username_watch" else unit.source]
            row = _row(connection, table, watch.watch_id)
            common = row["active"] == 1 and row["display_name"] == watch.display_name
            if unit.kind == "username_watch":
                same = (
                    row["username"] == watch.query and json.loads(row["platforms_json"]) == list(watch.platforms)
                    and row["source_key"] == unit.source
                )
            else:
                same = (
                    row["query"] == watch.query and row["match_mode"] == watch.match_mode
                    and row.get("kind", "organization") == watch.kind
                )
            if not common or not same:
                raise ValidationError("Eksik toplama izlemesinin tanımı veya etkinliği değişmiş; güncel seçimle yeni çalışma başlatın.")

    @staticmethod
    def _step(row, unit, session):
        try:
            record = CollectionSessionStep(
                history_uuid(row["id"]), history_uuid(row["session_id"]), _integer(row["ordinal"], maximum=58),
                row["step_key"], row["kind"], row["source"],
                history_uuid(row["watch_id"]) if row["watch_id"] is not None else None,
                history_sha256(row["target_sha256"]),
                history_uuid(row["depends_on_step_id"]) if row["depends_on_step_id"] is not None else None,
                history_uuid(row["scan_job_id"]) if row["scan_job_id"] is not None else None,
                row["status"], _optional_time(row["started_at"]), _optional_time(row["finished_at"]), row["error_code"],
            )
            if (
                record.session_id != session.id or record.step_key != unit.step_key
                or (record.kind, record.source, record.watch_id) != (unit.kind, unit.source, unit.watch.watch_id if unit.watch else None)
                or record.target_sha256 != unit_sha256(unit) or record.status not in STEP_STATUSES
                or (record.error_code is not None and record.error_code not in STOP_CODES)
                or (record.kind != "scan" and record.scan_job_id is not None)
                or (record.kind == "ransomware_watch") != (record.depends_on_step_id is not None)
                or (record.status in {"pending", "running"}) != (record.finished_at is None)
                or (record.status == "pending" and (record.started_at is not None or record.error_code is not None or record.scan_job_id is not None))
                or (record.status == "running" and (record.started_at is None or record.error_code is not None))
                or (record.status == "complete" and (record.started_at is None or record.error_code is not None))
                or (record.status == "partial" and (record.started_at is None or record.error_code != "source_partial"))
                or (record.status == "skipped" and (record.started_at is not None or record.error_code != "dependency_failed"))
                or (record.status in {"failed", "interrupted"} and record.error_code is None)
                or (session.status != "running" and record.status in {"pending", "running"})
            ):
                raise ValueError("invalid step state")
            return record
        except (ValueError, TypeError, KeyError) as error:
            raise StorageError("Toplama adım kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _receipt(connection, row, step, unit, session):
        try:
            populated = [(column[:-3], row[column]) for column in REFERENCE_COLUMNS if row[column] is not None]
            if len(populated) != 1:
                raise ValueError("ambiguous result reference")
            kind, result_id = populated[0]
            recorded_at, counters = source_result(
                connection, unit, session.plan.definition, asdict(step),
                result_kind=kind, result_id=result_id, result_status=row["result_status"],
            )
            encoded = summary_json(counters)
            if (
                row["step_id"] != step.id or row["recorded_at"] != recorded_at
                or row["summary_json"] != encoded or row["summary_sha256"] != sha256_text(encoded)
                or row["result_status"] != step.status or recorded_at != step.finished_at
                or step.started_at is None or step.error_code != {
                    "complete": None, "partial": "source_partial", "failed": "source_failed", "interrupted": "interrupted",
                }[step.status]
            ):
                raise ValueError("receipt summary mismatch")
            source_run_id = _row(connection, RESULT_TABLES[kind], result_id)["source_run_id"] if unit.kind == "ransomware_watch" else None
            return CollectionStepReceipt(step.id, recorded_at, step.status, kind, result_id, counters, row["summary_sha256"], source_run_id)
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            raise StorageError("Toplama sonuç kanıtı bozuk; işlem durduruldu.") from error

    @classmethod
    def _details(cls, connection, session_id):
        chain = []
        seen = set()
        current = history_uuid(session_id)
        while current is not None:
            if current in seen or len(chain) >= MAX_COLLECTION_GENERATIONS:
                raise StorageError("Toplama devam zinciri bozuk veya güvenli sınırı aşıyor.")
            seen.add(current)
            session = cls._session(_row(connection, "collection_sessions", current))
            chain.append(session)
            current = session.parent_id
        chain.reverse()
        completed = {}
        previous = None
        for session in chain:
            cls._profile_origin_event(connection, session.plan.origin, session.plan.definition)
            if previous is None:
                if session.root_id != session.id or session.generation != 1:
                    raise StorageError("Toplama kök oturumu geçersiz.")
                expected = session.plan.units
            else:
                if (
                    session.parent_id != previous.id or session.root_id != previous.root_id
                    or session.generation != previous.generation + 1 or session.sequence <= previous.sequence
                    or session.plan != previous.plan or session.definition_sha256 != previous.definition_sha256
                    or session.plan_sha256 != previous.plan_sha256 or session.profile_event_id != previous.profile_event_id
                    or previous.status in {"running", "complete"}
                ):
                    raise StorageError("Toplama devam zinciri ebeveyn tanımıyla uyuşmuyor.")
                expected = resume_units(session.plan, set(completed))
            rows = connection.execute(
                "SELECT id FROM collection_session_steps WHERE session_id=? ORDER BY ordinal LIMIT 59", (session.id,),
            ).fetchall()
            if len(rows) != len(expected):
                raise StorageError("Toplama adımları dondurulmuş devam planıyla uyuşmuyor.")
            steps, receipts = [], []
            retained = tuple(completed[unit.step_key] for unit in session.plan.units if unit.step_key in completed)
            by_id = {}
            for ordinal, (item, unit) in enumerate(zip(rows, expected), 1):
                step = cls._step(_row(connection, "collection_session_steps", item[0]), unit, session)
                if unit.watch is not None:
                    watch_table = (
                        "brand_username_watches" if unit.kind == "username_watch"
                        else "ransomware_watches" if unit.source == "threatcluster"
                        else "ransomlook_watches"
                    )
                    # Historical evidence keeps its frozen definition. Only the
                    # polymorphic reference must still exist; later changes or
                    # revocation never reinterpret the original snapshot.
                    _row(connection, watch_table, unit.watch.watch_id)
                if step.ordinal != ordinal:
                    raise StorageError("Toplama adım sırası geçersiz.")
                if step.depends_on_step_id is not None:
                    dependency = by_id.get(step.depends_on_step_id)
                    if (
                        dependency is None or dependency.kind != "ransomware_refresh" or dependency.source != step.source
                        or (step.status in {"running", "complete", "partial"} and dependency.status != "complete")
                        or (step.status == "skipped" and dependency.status not in {"failed", "partial", "interrupted", "skipped"})
                    ):
                        raise StorageError("Toplama yenileme bağımlılığı geçersiz.")
                if step.scan_job_id is not None:
                    job = _row(connection, "scan_jobs", step.scan_job_id)
                    if (
                        unit.kind != "scan" or job["provider"] != unit.source
                        or job["rule_version"] != unit.contract_version
                        or json.loads(job["targets"]) != [session.plan.definition.asset_value]
                        or job["typos"] != int(session.plan.definition.typos)
                    ):
                        raise StorageError("Toplama arama işi hedefi bozuk.")
                receipt_row = connection.execute("SELECT step_id FROM collection_step_receipts WHERE step_id=?", (step.id,)).fetchone()
                if receipt_row:
                    receipt = cls._receipt(connection, _row(connection, "collection_step_receipts", step.id, column="step_id"), step, unit, session)
                    receipts.append(receipt)
                    if step.status == "complete" and unit.kind != "ransomware_refresh":
                        if unit.step_key in completed:
                            raise StorageError("Tamamlanmış toplama birimi yeniden yürütülmüş.")
                        completed[unit.step_key] = CollectionRetainedResult(unit, step, receipt)
                elif step.status in {"complete", "partial"}:
                    raise StorageError("Tamamlanan toplama adımının kaynak kanıtı eksik.")
                steps.append(step)
                by_id[step.id] = step
            if session.status != "running":
                derived = cls._terminal_status(session.plan, completed, session.analysis_status, session.stop_reason, has_partial=any(step.status == "partial" for step in steps))
                if session.status != derived:
                    raise StorageError("Toplama oturum özeti kaynak kanıtlarıyla uyuşmuyor.")
            previous = session
        return CollectionSessionDetails(session, tuple(steps), tuple(receipts), retained)

    @staticmethod
    def _terminal_status(plan, completed, analysis_status, stop_reason, *, has_partial=False):
        if stop_reason in {"interrupted", "recovered"}:
            return "interrupted"
        if stop_reason in {"execution_failed", "analysis_failed"} or analysis_status == "failed":
            return "failed"
        expected = {unit.step_key for unit in plan.units if unit.kind != "ransomware_refresh"}
        if expected <= set(completed) and analysis_status == "complete":
            return "complete"
        return "partial" if completed or has_partial else "failed"

    @classmethod
    def _resume(cls, connection, session_id, *, validate_current=True):
        details = cls._details(connection, session_id)
        session = details.session
        if session.status in {"running", "complete"}:
            raise ValidationError("Bu toplama oturumu devam ettirilemez; çalışan oturumu önce açıkça kurtarın.")
        if session.generation >= MAX_COLLECTION_GENERATIONS:
            raise ValidationError("Toplama devam zinciri 100 yürütme sınırına ulaştı; yeni çalışma başlatın.")
        if connection.execute("SELECT 1 FROM collection_sessions WHERE parent_id=?", (session.id,)).fetchone():
            raise ValidationError("Bu oturumun devamı zaten var; zincirin son oturumunu kullanın.")
        completed = {result.unit.step_key: result for result in details.retained}
        by_id = {step.id: step for step in details.steps}
        unit_map = {unit.step_key: unit for unit in session.plan.units}
        for receipt in details.receipts:
            step = by_id[receipt.step_id]
            if receipt.result_status == "complete" and step.kind != "ransomware_refresh":
                completed[step.step_key] = CollectionRetainedResult(unit_map[step.step_key], step, receipt)
        units = resume_units(session.plan, set(completed))
        if validate_current:
            cls._current_origin(connection, session.plan)
            cls._current_units(connection, units)
        retained = tuple(completed[unit.step_key] for unit in session.plan.units if unit.step_key in completed)
        return CollectionResumePlan(session, units, retained)

    def begin(self, plan: CollectionFrozenPlan, *, started_at: str, parent_id: str | None = None):
        plan = normalize_frozen_plan(plan)
        started_at = canonical_time(started_at)
        if parent_id is not None:
            history_uuid(parent_id)
        with self._write() as connection:
            if connection.execute("SELECT 1 FROM collection_sessions WHERE status='running' LIMIT 1").fetchone():
                raise ValidationError("Açık toplama oturumu var; ortak kilit altında kurtarma gerekli.")
            if connection.execute("SELECT COUNT(*) FROM collection_sessions").fetchone()[0] >= MAX_SESSIONS:
                raise StorageError("Toplama oturum sayısı güvenli kayıt sınırına ulaştı.")
            if not connection.execute("SELECT 1 FROM assets WHERE value=?", (plan.definition.asset_value,)).fetchone():
                raise ValidationError("Toplama domaini önceden kaydedilmeli.")
            self._current_origin(connection, plan)
            identifier = str(uuid4())
            if parent_id is not None:
                resume = self._resume(connection, parent_id)
                if resume.parent.plan != plan:
                    raise ValidationError("Devam planı ilk oturumun seçimini değiştiremez.")
                units, root_id, generation = resume.units, resume.parent.root_id, resume.parent.generation + 1
            else:
                units, root_id, generation = plan.units, identifier, 1
                self._current_units(connection, units)
            connection.execute(
                "INSERT INTO collection_sessions (id,root_id,parent_id,generation,profile_event_id,definition_json,"
                "definition_sha256,plan_json,plan_sha256,executor_contract_version,status,started_at,analysis_status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,'running',?,'pending')",
                (identifier, root_id, parent_id, generation, plan.origin.event_id if plan.origin else None,
                 canonical_definition_json(plan.definition), definition_sha256(plan.definition), canonical_plan_json(plan),
                 plan_sha256(plan), plan.executor_contract_version, started_at),
            )
            ids = {unit.step_key: str(uuid4()) for unit in units}
            for ordinal, unit in enumerate(units, 1):
                dependency = ids[f"ransomware-refresh:{unit.source}"] if unit.kind == "ransomware_watch" else None
                connection.execute(
                    "INSERT INTO collection_session_steps (id,session_id,ordinal,step_key,kind,source,watch_id,"
                    "target_sha256,depends_on_step_id,status) VALUES (?,?,?,?,?,?,?,?,?,'pending')",
                    (ids[unit.step_key], identifier, ordinal, unit.step_key, unit.kind, unit.source,
                     unit.watch.watch_id if unit.watch else None, unit_sha256(unit), dependency),
                )
            return self._details(connection, identifier)

    def start_step(self, session_id: str, step_id: str, *, started_at: str):
        session_id, step_id, started_at = history_uuid(session_id), history_uuid(step_id), canonical_time(started_at)
        with self._write() as connection:
            details = self._details(connection, session_id)
            step = next((step for step in details.steps if step.id == step_id), None)
            if details.session.status != "running" or step is None or step.status != "pending":
                raise ValidationError("Yalnız açık oturumun bekleyen adımı başlatılabilir.")
            if any(other.status == "running" for other in details.steps):
                raise ValidationError("Bu oturumda başka bir toplama adımı çalışıyor.")
            if step.depends_on_step_id is not None:
                dependency = next(other for other in details.steps if other.id == step.depends_on_step_id)
                if dependency.status != "complete":
                    raise ValidationError("Ransomware üyesi aynı yürütmede başarılı kaynak yenilemesi gerektirir.")
            connection.execute("UPDATE collection_session_steps SET status='running',started_at=? WHERE id=? AND status='pending'", (started_at, step.id))
            self._details(connection, session_id)
            return CollectionOperationToken(session_id, step.id, step.target_sha256, step.depends_on_step_id)

    @staticmethod
    def _abandon_scan(connection, step, finished_at, reason):
        if step["scan_job_id"] is None:
            return
        connection.execute(
            "UPDATE scan_attempts SET status='interrupted',finished_at=?,error=? WHERE job_id=? AND status='running'",
            (finished_at, reason, step["scan_job_id"]),
        )
        connection.execute(
            "UPDATE scan_jobs SET status='interrupted',updated_at=? WHERE id=? AND status IN ('queued','running')",
            (finished_at, step["scan_job_id"]),
        )

    def stop_step_without_result(self, token, *, status, error_code, finished_at):
        if status not in {"failed", "interrupted", "skipped"} or error_code not in STOP_CODES:
            raise ValidationError("Sonuçsuz toplama adımı kapanış nedeni geçersiz.")
        finished_at = canonical_time(finished_at)
        with self._write() as connection:
            session, step, _, _ = operation_context(connection, token, allow_pending=True)
            self._details(connection, session["id"])
            if status == "skipped":
                if step["status"] != "pending" or error_code != "dependency_failed" or step["depends_on_step_id"] is None:
                    raise ValidationError("Yalnız kaynak yenilemesi başarısız bekleyen üye atlanabilir.")
                dependency = _row(connection, "collection_session_steps", step["depends_on_step_id"])
                if dependency["status"] not in {"failed", "partial", "interrupted", "skipped"}:
                    raise ValidationError("Atlama için başarısız kaynak yenilemesi gerekli.")
            elif step["status"] != "running" and status != "interrupted":
                raise ValidationError("Başlatılmayan adım başarısız sonuç olarak kapatılamaz.")
            self._abandon_scan(connection, step, finished_at, error_code)
            connection.execute("UPDATE collection_session_steps SET status=?,finished_at=?,error_code=? WHERE id=?", (status, finished_at, error_code, step["id"]))
            self._details(connection, session["id"])

    @classmethod
    def _close_open_steps(cls, connection, details, finished_at, reason):
        for step in details.steps:
            if step.status not in {"pending", "running"}:
                continue
            cls._abandon_scan(connection, asdict(step), finished_at, reason)
            connection.execute(
                "UPDATE collection_session_steps SET status='interrupted',finished_at=?,error_code=? WHERE id=?",
                (finished_at, reason, step.id),
            )

    def finish_session(self, session_id, *, analysis_status, finished_at, stop_reason=None):
        session_id, finished_at = history_uuid(session_id), canonical_time(finished_at)
        if analysis_status not in ANALYSIS_STATUSES or (stop_reason is not None and stop_reason not in STOP_CODES):
            raise ValidationError("Toplama oturum kapanış durumu geçersiz.")
        with self._write() as connection:
            details = self._details(connection, session_id)
            if details.session.status != "running":
                raise ValidationError("Tamamlanan toplama oturumu değiştirilemez.")
            if stop_reason in {"interrupted", "recovered", "execution_failed", "analysis_failed"}:
                self._close_open_steps(connection, details, finished_at, stop_reason)
            elif any(step.status in {"pending", "running"} for step in details.steps):
                raise ValidationError("Açık toplama adımları bitmeden oturum normal kapatılamaz.")
            updated = self._details(connection, session_id)
            completed = {value.unit.step_key for value in updated.retained}
            by_id = {step.id: step for step in updated.steps}
            completed.update(by_id[receipt.step_id].step_key for receipt in updated.receipts if receipt.result_status == "complete" and by_id[receipt.step_id].kind != "ransomware_refresh")
            status = self._terminal_status(details.session.plan, completed, analysis_status, stop_reason, has_partial=any(step.status == "partial" for step in updated.steps))
            connection.execute(
                "UPDATE collection_sessions SET status=?,finished_at=?,stop_reason=?,analysis_status=?,analysis_recorded_at=? WHERE id=? AND status='running'",
                (status, finished_at, stop_reason, analysis_status, finished_at if analysis_status != "pending" else None, session_id),
            )
            return self._details(connection, session_id)

    def recover_interrupted(self, *, recorded_at, reason="recovered"):
        recorded_at = canonical_time(recorded_at)
        if reason not in {"recovered", "interrupted"}:
            raise ValidationError("Toplama kurtarma nedeni geçersiz.")
        with self._write() as connection:
            rows = connection.execute("SELECT id FROM collection_sessions WHERE status='running' ORDER BY sequence LIMIT ?", (MAX_SESSIONS+1,)).fetchall()
            if len(rows) > MAX_SESSIONS:
                raise StorageError("Açık toplama oturum sayısı güvenli sınırı aşıyor.")
            for (session_id,) in rows:
                details = self._details(connection, session_id)
                self._close_open_steps(connection, details, recorded_at, reason)
                connection.execute("UPDATE collection_sessions SET status='interrupted',finished_at=?,stop_reason=? WHERE id=? AND status='running'", (recorded_at, reason, session_id))
                self._details(connection, session_id)
            return tuple(row[0] for row in rows)

    def get(self, session_id):
        history_uuid(session_id)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return self._details(connection, session_id)

    def resume_plan(self, session_id):
        history_uuid(session_id)
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            return self._resume(connection, session_id)

    def list(self, *, limit=50, before=None):
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Toplama geçmişi sınırı 1–500 arasında olmalı.")
        if before is not None and (type(before) is not int or not 1 <= before <= 2**63-1):
            raise ValidationError("Toplama geçmişi sıra imleci geçersiz.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                "SELECT id,sequence FROM collection_sessions WHERE (? IS NULL OR sequence<?) ORDER BY sequence DESC LIMIT ?",
                (before, before, limit+1),
            ).fetchall()
            sessions = tuple(self._details(connection, row[0]).session for row in rows[:limit])
            return CollectionSessionPage(sessions, rows[limit-1][1] if len(rows) > limit else None)

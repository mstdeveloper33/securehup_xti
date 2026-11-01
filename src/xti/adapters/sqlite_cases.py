"""SQLite case lifecycle with current state and one append-only activity stream."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from xti.adapters.sqlite import SQLiteAssetRepository, StorageError
from xti.domain.assets import ValidationError
from xti.domain.cases import (
    CASE_ACTIVITY_TYPES,
    Case,
    CaseActivity,
    CaseDetails,
    CaseEvidence,
    CaseEvidenceMutation,
    CaseEvidenceSnapshot,
    CaseMutation,
    CaseTask,
    CaseTaskMutation,
    canonical_snapshot,
    normalize_case_evidence_id,
    normalize_case_evidence_link_id,
    normalize_case_evidence_type,
    normalize_case_id,
    normalize_case_note,
    normalize_case_note_kind,
    normalize_case_priority,
    normalize_case_reason,
    normalize_case_resolution,
    normalize_case_status,
    normalize_case_summary,
    normalize_case_task_id,
    normalize_case_task_status,
    normalize_case_task_title,
    normalize_case_title,
)


_MAX_ACTIVITY = 100_000


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid UUID")
    normalized = str(UUID(value))
    if normalized != value:
        raise ValueError("non-canonical UUID")
    return normalized


def _time(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc).isoformat()


def _optional_time(value: object) -> str | None:
    return None if value is None else _time(value)


def _latest(first: str, second: str) -> str:
    return max(datetime.fromisoformat(first), datetime.fromisoformat(second)).isoformat()


class SQLiteCaseRepository:
    def __init__(self, path: Path) -> None:
        self._storage = SQLiteAssetRepository(path)

    @staticmethod
    def _case(row) -> Case:
        try:
            record = Case(
                id=_uuid(row[0]), title=normalize_case_title(row[1]),
                summary=normalize_case_summary(row[2]), status=normalize_case_status(row[3]),
                priority=normalize_case_priority(row[4]),
                resolution=(
                    normalize_case_resolution(row[5]) if row[5] is not None else None
                ),
                created_at=_time(row[6]), updated_at=_time(row[7]),
                closed_at=_optional_time(row[8]),
            )
            if datetime.fromisoformat(record.updated_at) < datetime.fromisoformat(record.created_at):
                raise ValueError("time regression")
            if record.status in {"resolved", "closed"} and record.resolution is None:
                raise ValueError("resolution missing")
            if record.status not in {"resolved", "closed"} and record.resolution is not None:
                raise ValueError("unexpected resolution")
            if (record.status == "closed") != (record.closed_at is not None):
                raise ValueError("closed timestamp mismatch")
            return record
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Vaka kaydı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _evidence(row) -> CaseEvidence:
        try:
            snapshot_json = row[6]
            if (
                not isinstance(snapshot_json, str)
                or hashlib.sha256(snapshot_json.encode("ascii")).hexdigest() != row[7]
                or not isinstance(json.loads(snapshot_json), dict)
            ):
                raise ValueError("invalid snapshot")
            record = CaseEvidence(
                id=_uuid(row[0]), case_id=_uuid(row[1]),
                evidence_type=normalize_case_evidence_type(row[2]),
                evidence_id=normalize_case_evidence_id(row[3]),
                display_value=row[4], source_reference=row[5],
                snapshot_json=snapshot_json, snapshot_sha256=row[7], active=bool(row[8]),
                added_reason=normalize_case_reason(row[9]), added_at=_time(row[10]),
                updated_at=_time(row[11]),
                removed_reason=(normalize_case_reason(row[12]) if row[12] else None),
                removed_at=_optional_time(row[13]),
            )
            if (
                type(row[8]) is not int or row[8] not in {0, 1}
                or not isinstance(record.display_value, str)
                or not 1 <= len(record.display_value) <= 1000
                or not isinstance(record.source_reference, str)
                or not 1 <= len(record.source_reference) <= 500
                or record.active == (record.removed_at is not None)
                or record.active == (record.removed_reason is not None)
            ):
                raise ValueError("invalid evidence")
            return record
        except (UnicodeError, TypeError, ValueError, ValidationError, json.JSONDecodeError) as error:
            raise StorageError("Vaka kanıt bağı bozuk; işlem durduruldu.") from error

    @staticmethod
    def _task(row) -> CaseTask:
        try:
            return CaseTask(
                id=_uuid(row[0]), case_id=_uuid(row[1]),
                title=normalize_case_task_title(row[2]),
                status=normalize_case_task_status(row[3]), due_at=_optional_time(row[4]),
                reason=normalize_case_reason(row[5]), created_at=_time(row[6]),
                updated_at=_time(row[7]),
            )
        except (TypeError, ValueError, ValidationError, OverflowError) as error:
            raise StorageError("Vaka görevi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _activity(row) -> CaseActivity:
        try:
            if (
                type(row[0]) is not int
                or row[0] <= 0
                or row[3] not in CASE_ACTIVITY_TYPES
                or not isinstance(row[5], str)
                or not 1 <= len(row[5]) <= 8000
                or any(not character.isprintable() for character in row[5])
                or not isinstance(row[6], str)
                or not 1 <= len(row[6]) <= 2000
                or any(not character.isprintable() for character in row[6])
            ):
                raise ValueError("invalid activity")
            snapshot_json = row[7]
            if (
                not isinstance(snapshot_json, str)
                or hashlib.sha256(snapshot_json.encode("ascii")).hexdigest() != row[8]
                or not isinstance(json.loads(snapshot_json), dict)
            ):
                raise ValueError("invalid activity snapshot")
            return CaseActivity(
                sequence=row[0], id=_uuid(row[1]), case_id=_uuid(row[2]),
                activity_type=row[3], reference_id=(
                    _uuid(row[4]) if row[4] is not None else None
                ), summary=row[5], reason=row[6], snapshot_sha256=row[8],
                recorded_at=_time(row[9]),
            )
        except (UnicodeError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StorageError("Vaka zaman çizelgesi bozuk; işlem durduruldu.") from error

    @staticmethod
    def _case_row(connection, case_id: str):
        return connection.execute(
            "SELECT id, title, summary, status, priority, resolution, created_at, "
            "updated_at, closed_at FROM cases WHERE id = ?", (case_id,),
        ).fetchone()

    @classmethod
    def _get_case(cls, connection, case_id: str) -> Case:
        row = cls._case_row(connection, case_id)
        if row is None:
            raise ValidationError("Vaka bulunamadı.")
        return cls._case(row)

    @staticmethod
    def _case_payload(record: Case) -> dict:
        return {
            "kind": "case", "id": record.id, "title": record.title,
            "summary": record.summary, "status": record.status,
            "priority": record.priority, "resolution": record.resolution,
            "created_at": record.created_at, "updated_at": record.updated_at,
            "closed_at": record.closed_at,
        }

    @staticmethod
    def _insert_activity(
        connection, *, case_id: str, activity_type: str,
        reference_id: str | None, summary: str, reason: str,
        payload: dict, recorded_at: str,
    ) -> CaseActivity:
        snapshot_json, digest = canonical_snapshot(payload)
        activity_id = str(uuid4())
        cursor = connection.execute(
            "INSERT INTO case_activities "
            "(id, case_id, activity_type, reference_id, summary, reason, "
            "snapshot_json, snapshot_sha256, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                activity_id, case_id, activity_type, reference_id,
                summary, reason, snapshot_json, digest, recorded_at,
            ),
        )
        return CaseActivity(
            sequence=cursor.lastrowid, id=activity_id, case_id=case_id,
            activity_type=activity_type, reference_id=reference_id,
            summary=summary, reason=reason, snapshot_sha256=digest,
            recorded_at=recorded_at,
        )

    @staticmethod
    def _recorded(value: str) -> str:
        try:
            return _time(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValidationError("Vaka işlem zamanı geçersiz.") from error

    def create(
        self, *, title: str, summary: str, priority: str, reason: str, recorded_at: str,
    ) -> CaseMutation:
        title, summary = normalize_case_title(title), normalize_case_summary(summary)
        priority, reason = normalize_case_priority(priority), normalize_case_reason(reason)
        recorded_at = self._recorded(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                case_id = str(uuid4())
                connection.execute(
                    "INSERT INTO cases (id, title, summary, status, priority, resolution, "
                    "created_at, updated_at, closed_at) "
                    "VALUES (?, ?, ?, 'open', ?, NULL, ?, ?, NULL)",
                    (case_id, title, summary, priority, recorded_at, recorded_at),
                )
                record = self._get_case(connection, case_id)
                self._insert_activity(
                    connection, case_id=case_id, activity_type="case_created",
                    reference_id=None, summary=title, reason=reason,
                    payload=self._case_payload(record), recorded_at=recorded_at,
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseMutation("created", True, record)

    def update(
        self, case_id: str, *, title: str | None, summary: str | None,
        priority: str | None, reason: str, recorded_at: str,
    ) -> CaseMutation:
        case_id, reason, recorded_at = (
            normalize_case_id(case_id), normalize_case_reason(reason), self._recorded(recorded_at)
        )
        if title is not None:
            title = normalize_case_title(title)
        if summary is not None:
            summary = normalize_case_summary(summary)
        if priority is not None:
            priority = normalize_case_priority(priority)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._get_case(connection, case_id)
                requested = (
                    title if title is not None else current.title,
                    summary if summary is not None else current.summary,
                    priority if priority is not None else current.priority,
                )
                if requested == (current.title, current.summary, current.priority):
                    record, action, changed = current, "unchanged", False
                else:
                    updated_at = _latest(current.updated_at, recorded_at)
                    connection.execute(
                        "UPDATE cases SET title=?, summary=?, priority=?, updated_at=? "
                        "WHERE id=?", (*requested, updated_at, case_id),
                    )
                    record = self._get_case(connection, case_id)
                    self._insert_activity(
                        connection, case_id=case_id, activity_type="case_updated",
                        reference_id=None, summary=record.title, reason=reason,
                        payload=self._case_payload(record), recorded_at=recorded_at,
                    )
                    action, changed = "updated", True
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseMutation(action, changed, record)

    def set_status(
        self, case_id: str, *, status: str, resolution: str | None,
        reason: str, recorded_at: str,
    ) -> CaseMutation:
        case_id, status = normalize_case_id(case_id), normalize_case_status(status)
        reason, recorded_at = normalize_case_reason(reason), self._recorded(recorded_at)
        if status in {"resolved", "closed"}:
            if resolution is None:
                raise ValidationError("Çözülen veya kapanan vaka için sonuç gerekli.")
            resolution = normalize_case_resolution(resolution)
        elif resolution is not None:
            raise ValidationError("Açık vaka durumunda sonuç açıklaması kullanılamaz.")
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                current = self._get_case(connection, case_id)
                if status == "closed":
                    open_tasks = connection.execute(
                        "SELECT COUNT(*) FROM case_tasks WHERE case_id=? AND status='open'",
                        (case_id,),
                    ).fetchone()[0]
                    if open_tasks:
                        raise ValidationError(
                            "Açık görevleri tamamlamadan veya iptal etmeden vaka kapatılamaz."
                        )
                if current.status == status and current.resolution == resolution:
                    record, action, changed = current, "unchanged", False
                else:
                    updated_at = _latest(current.updated_at, recorded_at)
                    closed_at = updated_at if status == "closed" else None
                    connection.execute(
                        "UPDATE cases SET status=?, resolution=?, updated_at=?, closed_at=? "
                        "WHERE id=?", (status, resolution, updated_at, closed_at, case_id),
                    )
                    record = self._get_case(connection, case_id)
                    self._insert_activity(
                        connection, case_id=case_id, activity_type="status_changed",
                        reference_id=None, summary=f"{current.status} → {status}",
                        reason=reason, payload=self._case_payload(record),
                        recorded_at=recorded_at,
                    )
                    action, changed = "status_changed", True
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseMutation(action, changed, record)

    def add_note(
        self, case_id: str, *, kind: str, body: str, recorded_at: str,
    ) -> CaseActivity:
        case_id, kind = normalize_case_id(case_id), normalize_case_note_kind(kind)
        body, recorded_at = normalize_case_note(body), self._recorded(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                self._get_case(connection, case_id)
                activity = self._insert_activity(
                    connection, case_id=case_id, activity_type="note_added",
                    reference_id=None, summary=body, reason=kind,
                    payload={"kind": kind, "body": body}, recorded_at=recorded_at,
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return activity

    @staticmethod
    def _evidence_row(connection, link_id: str):
        return connection.execute(
            "SELECT id, case_id, evidence_type, evidence_id, display_value, "
            "source_reference, snapshot_json, snapshot_sha256, active, added_reason, "
            "added_at, updated_at, removed_reason, removed_at FROM case_evidence WHERE id=?",
            (link_id,),
        ).fetchone()

    def add_evidence(
        self, case_id: str, *, snapshot: CaseEvidenceSnapshot,
        reason: str, recorded_at: str,
    ) -> CaseEvidenceMutation:
        case_id, reason, recorded_at = (
            normalize_case_id(case_id), normalize_case_reason(reason), self._recorded(recorded_at)
        )
        evidence_type = normalize_case_evidence_type(snapshot.evidence_type)
        evidence_id = normalize_case_evidence_id(snapshot.evidence_id)
        try:
            snapshot_payload = json.loads(snapshot.snapshot_json)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValidationError(
                "Kanıt anlık görüntüsü geçerli JSON içermiyor."
            ) from error
        if not isinstance(snapshot_payload, dict):
            raise ValidationError("Kanıt anlık görüntüsü JSON nesnesi olmalı.")
        canonical_json, digest = canonical_snapshot(snapshot_payload)
        if canonical_json != snapshot.snapshot_json or digest != snapshot.snapshot_sha256:
            raise ValidationError("Kanıt anlık görüntüsü bütünlük kontrolünden geçemedi.")
        if (
            not isinstance(snapshot.display_value, str)
            or not 1 <= len(snapshot.display_value) <= 1000
            or any(not char.isprintable() for char in snapshot.display_value)
            or not isinstance(snapshot.source_reference, str)
            or not 1 <= len(snapshot.source_reference) <= 500
            or any(not char.isprintable() for char in snapshot.source_reference)
        ):
            raise ValidationError("Kanıt görünür özeti geçersiz.")
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                case = self._get_case(connection, case_id)
                if case.status == "closed":
                    raise ValidationError("Kapalı vakaya kanıt eklemek için önce vakayı yeniden açın.")
                row = connection.execute(
                    "SELECT id, case_id, evidence_type, evidence_id, display_value, "
                    "source_reference, snapshot_json, snapshot_sha256, active, added_reason, "
                    "added_at, updated_at, removed_reason, removed_at FROM case_evidence "
                    "WHERE case_id=? AND evidence_type=? AND evidence_id=?",
                    (case_id, evidence_type, evidence_id),
                ).fetchone()
                if row is None:
                    link_id, action, activity_type = str(uuid4()), "added", "evidence_added"
                    connection.execute(
                        "INSERT INTO case_evidence "
                        "(id, case_id, evidence_type, evidence_id, display_value, "
                        "source_reference, snapshot_json, snapshot_sha256, active, "
                        "added_reason, added_at, updated_at, removed_reason, removed_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, NULL, NULL)",
                        (
                            link_id, case_id, evidence_type, evidence_id,
                            snapshot.display_value, snapshot.source_reference,
                            snapshot.snapshot_json, snapshot.snapshot_sha256,
                            reason, recorded_at, recorded_at,
                        ),
                    )
                    changed = True
                else:
                    current = self._evidence(row)
                    link_id = current.id
                    if current.active and current.snapshot_sha256 == snapshot.snapshot_sha256:
                        evidence, action, changed = current, "unchanged", False
                        connection.commit()
                        return CaseEvidenceMutation(action, changed, evidence)
                    action = "refreshed" if current.active else "reactivated"
                    activity_type = (
                        "evidence_refreshed" if current.active else "evidence_reactivated"
                    )
                    connection.execute(
                        "UPDATE case_evidence SET display_value=?, source_reference=?, "
                        "snapshot_json=?, snapshot_sha256=?, active=1, added_reason=?, "
                        "updated_at=?, removed_reason=NULL, removed_at=NULL WHERE id=?",
                        (
                            snapshot.display_value, snapshot.source_reference,
                            snapshot.snapshot_json, snapshot.snapshot_sha256, reason,
                            _latest(current.updated_at, recorded_at), link_id,
                        ),
                    )
                    changed = True
                evidence = self._evidence(self._evidence_row(connection, link_id))
                self._insert_activity(
                    connection, case_id=case_id, activity_type=activity_type,
                    reference_id=link_id, summary=evidence.display_value, reason=reason,
                    payload={
                        "kind": "case_evidence", "action": action,
                        "link_id": link_id, "evidence_type": evidence_type,
                        "evidence_id": evidence_id,
                        "source_reference": evidence.source_reference,
                        "snapshot_json": evidence.snapshot_json,
                        "snapshot_sha256": evidence.snapshot_sha256,
                    },
                    recorded_at=recorded_at,
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseEvidenceMutation(action, changed, evidence)

    def remove_evidence(
        self, case_id: str, evidence_link_id: str, *, reason: str, recorded_at: str,
    ) -> CaseEvidenceMutation:
        case_id, evidence_link_id = (
            normalize_case_id(case_id), normalize_case_evidence_link_id(evidence_link_id)
        )
        reason, recorded_at = normalize_case_reason(reason), self._recorded(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                case = self._get_case(connection, case_id)
                if case.status == "closed":
                    raise ValidationError("Kapalı vakadan kanıt çıkarmak için önce vakayı açın.")
                row = self._evidence_row(connection, evidence_link_id)
                if row is None:
                    raise ValidationError("Vaka kanıt bağı bulunamadı.")
                current = self._evidence(row)
                if current.case_id != case_id:
                    raise ValidationError("Kanıt bağı bu vakaya ait değil.")
                if not current.active:
                    evidence, action, changed = current, "unchanged", False
                else:
                    updated_at = _latest(current.updated_at, recorded_at)
                    connection.execute(
                        "UPDATE case_evidence SET active=0, updated_at=?, removed_reason=?, "
                        "removed_at=? WHERE id=?",
                        (updated_at, reason, recorded_at, current.id),
                    )
                    evidence = self._evidence(self._evidence_row(connection, current.id))
                    self._insert_activity(
                        connection, case_id=case_id, activity_type="evidence_removed",
                        reference_id=current.id, summary=current.display_value, reason=reason,
                        payload={
                            "kind": "case_evidence", "action": "removed",
                            "link_id": current.id, "evidence_type": current.evidence_type,
                            "evidence_id": current.evidence_id,
                            "snapshot_json": current.snapshot_json,
                            "snapshot_sha256": current.snapshot_sha256,
                        }, recorded_at=recorded_at,
                    )
                    action, changed = "removed", True
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseEvidenceMutation(action, changed, evidence)

    @staticmethod
    def _task_row(connection, task_id: str):
        return connection.execute(
            "SELECT id, case_id, title, status, due_at, reason, created_at, updated_at "
            "FROM case_tasks WHERE id=?", (task_id,),
        ).fetchone()

    def add_task(
        self, case_id: str, *, title: str, due_at: str | None,
        reason: str, recorded_at: str,
    ) -> CaseTaskMutation:
        case_id, title = normalize_case_id(case_id), normalize_case_task_title(title)
        reason, recorded_at = normalize_case_reason(reason), self._recorded(recorded_at)
        due_at = _optional_time(due_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                case = self._get_case(connection, case_id)
                if case.status == "closed":
                    raise ValidationError("Kapalı vakaya görev eklemek için önce vakayı açın.")
                task_id = str(uuid4())
                connection.execute(
                    "INSERT INTO case_tasks "
                    "(id, case_id, title, status, due_at, reason, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'open', ?, ?, ?, ?)",
                    (task_id, case_id, title, due_at, reason, recorded_at, recorded_at),
                )
                task = self._task(self._task_row(connection, task_id))
                self._insert_activity(
                    connection, case_id=case_id, activity_type="task_added",
                    reference_id=task_id, summary=title, reason=reason,
                    payload={
                        "kind": "case_task", "id": task.id, "title": task.title,
                        "status": task.status, "due_at": task.due_at,
                    }, recorded_at=recorded_at,
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseTaskMutation("added", True, task)

    def update_task(
        self, case_id: str, task_id: str, *, status: str,
        reason: str, recorded_at: str,
    ) -> CaseTaskMutation:
        case_id, task_id = normalize_case_id(case_id), normalize_case_task_id(task_id)
        status, reason = normalize_case_task_status(status), normalize_case_reason(reason)
        recorded_at = self._recorded(recorded_at)
        with self._storage._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                case = self._get_case(connection, case_id)
                if case.status == "closed":
                    raise ValidationError("Kapalı vaka görevini değiştirmek için önce vakayı açın.")
                row = self._task_row(connection, task_id)
                if row is None:
                    raise ValidationError("Vaka görevi bulunamadı.")
                current = self._task(row)
                if current.case_id != case_id:
                    raise ValidationError("Görev bu vakaya ait değil.")
                if current.status == status:
                    task, action, changed = current, "unchanged", False
                else:
                    updated_at = _latest(current.updated_at, recorded_at)
                    connection.execute(
                        "UPDATE case_tasks SET status=?, reason=?, updated_at=? WHERE id=?",
                        (status, reason, updated_at, task_id),
                    )
                    task = self._task(self._task_row(connection, task_id))
                    self._insert_activity(
                        connection, case_id=case_id, activity_type="task_updated",
                        reference_id=task_id, summary=f"{task.title}: {current.status} → {status}",
                        reason=reason, payload={
                            "kind": "case_task", "id": task.id, "title": task.title,
                            "status": task.status, "due_at": task.due_at,
                        }, recorded_at=recorded_at,
                    )
                    action, changed = "updated", True
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return CaseTaskMutation(action, changed, task)

    def list(
        self, *, status: str | None, priority: str | None, limit: int,
    ) -> tuple[Case, ...]:
        if status is not None:
            status = normalize_case_status(status)
        if priority is not None:
            priority = normalize_case_priority(priority)
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValidationError("Vaka liste sınırı 1–500 arasında olmalı.")
        clauses, values = [], []
        if status is not None:
            clauses.append("status=?")
            values.append(status)
        if priority is not None:
            clauses.append("priority=?")
            values.append(priority)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._storage._connection(readonly=True) as connection:
            rows = connection.execute(
                "SELECT id, title, summary, status, priority, resolution, created_at, "
                f"updated_at, closed_at FROM cases{where} "
                "ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
                "WHEN 'medium' THEN 2 ELSE 3 END, updated_at DESC, id LIMIT ?",
                (*values, limit),
            ).fetchall()
        return tuple(self._case(row) for row in rows)

    def show(
        self, case_id: str, *, evidence_limit: int, task_limit: int,
        activity_limit: int,
    ) -> CaseDetails:
        case_id = normalize_case_id(case_id)
        for value, maximum, label in (
            (evidence_limit, 500, "Kanıt"), (task_limit, 500, "Görev"),
            (activity_limit, 1000, "Zaman çizelgesi"),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValidationError(f"{label} sınırı 1–{maximum} arasında olmalı.")
        with self._storage._connection(readonly=True) as connection:
            connection.execute("BEGIN")
            record = self._get_case(connection, case_id)
            evidence_count, active_evidence_count = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(active), 0) FROM case_evidence WHERE case_id=?",
                (case_id,),
            ).fetchone()
            evidence_rows = connection.execute(
                "SELECT id, case_id, evidence_type, evidence_id, display_value, "
                "source_reference, snapshot_json, snapshot_sha256, active, added_reason, "
                "added_at, updated_at, removed_reason, removed_at FROM case_evidence "
                "WHERE case_id=? ORDER BY active DESC, updated_at DESC, id LIMIT ?",
                (case_id, evidence_limit),
            ).fetchall()
            task_count, open_task_count = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(status='open'), 0) FROM case_tasks WHERE case_id=?",
                (case_id,),
            ).fetchone()
            task_rows = connection.execute(
                "SELECT id, case_id, title, status, due_at, reason, created_at, updated_at "
                "FROM case_tasks WHERE case_id=? ORDER BY CASE status WHEN 'open' THEN 0 "
                "WHEN 'done' THEN 1 ELSE 2 END, due_at IS NULL, due_at, created_at, id LIMIT ?",
                (case_id, task_limit),
            ).fetchall()
            activity_count = connection.execute(
                "SELECT COUNT(*) FROM case_activities WHERE case_id=?", (case_id,),
            ).fetchone()[0]
            if activity_count > _MAX_ACTIVITY:
                connection.rollback()
                raise StorageError("Vaka zaman çizelgesi 100.000 olay sınırını aşıyor.")
            activity_rows = connection.execute(
                "SELECT sequence, id, case_id, activity_type, reference_id, summary, "
                "reason, snapshot_json, snapshot_sha256, recorded_at FROM "
                "case_activities WHERE case_id=? ORDER BY sequence DESC LIMIT ?",
                (case_id, activity_limit),
            ).fetchall()
            first = connection.execute(
                "SELECT activity_type FROM case_activities WHERE case_id=? "
                "ORDER BY sequence LIMIT 1", (case_id,),
            ).fetchone()
            lifecycle_row = connection.execute(
                "SELECT sequence, id, case_id, activity_type, reference_id, summary, "
                "reason, snapshot_json, snapshot_sha256, recorded_at FROM "
                "case_activities WHERE case_id=? AND activity_type IN "
                "('case_created', 'case_updated', 'status_changed') "
                "ORDER BY sequence DESC LIMIT 1",
                (case_id,),
            ).fetchone()
            connection.rollback()
        if first != ("case_created",):
            raise StorageError("Vaka başlangıç olayı eksik; işlem durduruldu.")
        if lifecycle_row is None:
            raise StorageError("Vaka yaşam döngüsü kanıtı eksik; işlem durduruldu.")
        lifecycle = self._activity(lifecycle_row)
        expected_snapshot, _ = canonical_snapshot(self._case_payload(record))
        if lifecycle_row[7] != expected_snapshot or lifecycle.case_id != case_id:
            raise StorageError("Vaka güncel durumu zaman çizelgesiyle uyuşmuyor.")
        evidence = tuple(self._evidence(row) for row in evidence_rows)
        tasks = tuple(self._task(row) for row in task_rows)
        activities = tuple(reversed(tuple(self._activity(row) for row in activity_rows)))
        if any(item.case_id != case_id for item in (*evidence, *tasks, *activities)):
            raise StorageError("Vaka kayıt bağlantısı bozuk; işlem durduruldu.")
        return CaseDetails(
            case=record, evidence=evidence, tasks=tasks, activities=activities,
            total_evidence_count=evidence_count,
            active_evidence_count=active_evidence_count,
            total_task_count=task_count, open_task_count=open_task_count,
            total_activity_count=activity_count,
        )

